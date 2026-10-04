import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.performance_trade_config import TRADE_VERSION
from app.domain.performance import TradeEngine
from app.models.job import JobRun
from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
    PortfolioPerformanceTradeReport,
)
from app.repositories.performance_trade import PerformanceTradeRepository
from app.services.calc_metadata import config_hash
from app.services.performance.trade_source import PerformanceTradeSourceProvider

PERFORMANCE_TRADE_JOB_TYPE = "portfolio_performance_trade"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}


class PerformanceTradeConflictError(RuntimeError):
    code = "PERFORMANCE_TRADE_CALCULATION_CONFLICT"

    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class PerformanceTradeOwnershipError(RuntimeError):
    code = "PERFORMANCE_TRADE_OWNERSHIP_LOST"


@dataclass(frozen=True)
class PerformanceTradeArtifact:
    report: PortfolioPerformanceTradeReport
    reused: bool


@dataclass(frozen=True)
class PerformanceTradeExecutionLease:
    job_id: uuid.UUID
    worker_id: str
    run_id: uuid.UUID
    performance_id: uuid.UUID


class PerformanceTradeApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PerformanceTradeRepository | None = None,
        source_provider: PerformanceTradeSourceProvider | None = None,
        engine: TradeEngine | None = None,
        before_terminal_hook: Callable[
            [PerformanceTradeExecutionLease, PerformanceTradeArtifact], None
        ]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.performance_trade_config is None:
            raise RuntimeError("performance trade config is not loaded")
        self.config = self.settings.performance_trade_config
        self.repository = repository or PerformanceTradeRepository(db)
        self.source_provider = source_provider or PerformanceTradeSourceProvider(db)
        self.engine = engine or TradeEngine()
        self.before_terminal_hook = before_terminal_hook

    def queue_calculation(
        self, run_id: uuid.UUID, performance_id: uuid.UUID | None = None
    ) -> JobRun:
        base = self.source_provider.select_base(run_id, performance_id)
        selected_performance_id = base.report.id
        self.repository.lock_performance(selected_performance_id)
        active = self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == PERFORMANCE_TRADE_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains({"performance_id": str(selected_performance_id)}),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
        )
        if active is not None:
            raise PerformanceTradeConflictError(
                "performance trade calculation already has an active job",
                job_id=active.id,
            )
        job = JobRun(
            job_type=PERFORMANCE_TRADE_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for performance trade calculation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "portfolio_run_id": str(run_id),
                "performance_id": str(selected_performance_id),
                "trade_version": TRADE_VERSION,
                "stage": "queued",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_job(self, job_id: uuid.UUID) -> PerformanceTradeArtifact:
        job = self.db.execute(
            select(JobRun).where(JobRun.id == job_id).execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if job is None or job.job_type != PERFORMANCE_TRADE_JOB_TYPE:
            raise LookupError("performance trade job not found")
        if job.status != "RUNNING" or not job.worker_id:
            raise PerformanceTradeOwnershipError(
                "performance trade job is not owned by a running worker"
            )
        metadata = dict(job.job_metadata or {})
        try:
            run_id = uuid.UUID(str(metadata["portfolio_run_id"]))
            performance_id = uuid.UUID(str(metadata["performance_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PerformanceTradeOwnershipError(
                "performance trade job metadata identities are invalid"
            ) from exc
        if metadata.get("trade_version") != TRADE_VERSION:
            raise PerformanceTradeOwnershipError(
                "performance trade job version identity is invalid"
            )
        lease = PerformanceTradeExecutionLease(job.id, job.worker_id, run_id, performance_id)
        artifact = self._calculate_uncommitted(run_id, performance_id)
        if self.before_terminal_hook is not None:
            self.before_terminal_hook(lease, artifact)
        terminal_job = self._owned_job_for_terminal_update(lease)
        terminal_job.status = "SUCCESS"
        terminal_job.finished_at = datetime.now(UTC)
        terminal_job.step = "performance trade calculation complete"
        terminal_job.row_count = artifact.report.trade_days
        terminal_job.job_metadata = {
            **dict(terminal_job.job_metadata or {}),
            "stage": "success",
            "trade_id": str(artifact.report.id),
            "trade_source_hash": artifact.report.trade_source_hash,
            "reused": artifact.reused,
        }
        self.db.add(terminal_job)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def calculate_now(
        self, run_id: uuid.UUID, performance_id: uuid.UUID
    ) -> PerformanceTradeArtifact:
        artifact = self._calculate_uncommitted(run_id, performance_id)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def _calculate_uncommitted(
        self, run_id: uuid.UUID, performance_id: uuid.UUID
    ) -> PerformanceTradeArtifact:
        self.repository.lock_performance(performance_id)
        trade_config_hash = config_hash(self.config.model_dump(mode="json"))
        source = self.source_provider.load(
            run_id,
            performance_id=performance_id,
            trade_version=TRADE_VERSION,
            trade_config_hash=trade_config_hash,
        )
        existing = self.repository.find_by_identity(
            performance_id=performance_id,
            trade_version=TRADE_VERSION,
            trade_config_hash=trade_config_hash,
            trade_source_hash=source.trade_source_hash,
        )
        if existing is not None:
            return PerformanceTradeArtifact(existing, reused=True)

        result = self.engine.calculate(source, self.config)
        report = PortfolioPerformanceTradeReport(
            performance_id=performance_id,
            run_id=run_id,
            trade_version=TRADE_VERSION,
            trade_config_hash=trade_config_hash,
            trade_source_hash=source.trade_source_hash,
            status="SUCCESS",
            start_date=result.start_date,
            end_date=result.end_date,
            trade_days=result.trade_days,
            order_count=result.order_count,
            attempt_count=result.attempt_count,
            fill_count=result.fill_count,
            buy_fill_count=result.buy_fill_count,
            sell_fill_count=result.sell_fill_count,
            buy_gross_amount=result.buy_gross_amount,
            sell_gross_amount=result.sell_gross_amount,
            traded_gross_amount=result.traded_gross_amount,
            commission_total=result.commission_total,
            stamp_tax_total=result.stamp_tax_total,
            transfer_fee_total=result.transfer_fee_total,
            cash_fee_total=result.cash_fee_total,
            slippage_cost_total=result.slippage_cost_total,
            total_execution_cost=result.total_execution_cost,
            cash_fee_to_initial_capital=result.cash_fee_to_initial_capital,
            total_cost_to_initial_capital=result.total_cost_to_initial_capital,
            total_cost_to_traded_amount=result.total_cost_to_traded_amount,
            total_turnover=result.total_turnover,
            average_daily_turnover=result.average_daily_turnover,
            annualized_turnover=result.annualized_turnover,
            closed_episode_count=result.closed_episode_count,
            open_episode_count=result.open_episode_count,
            win_count=result.win_count,
            loss_count=result.loss_count,
            breakeven_count=result.breakeven_count,
            win_rate=result.win_rate,
            gross_profit=result.gross_profit,
            gross_loss_abs=result.gross_loss_abs,
            profit_factor=result.profit_factor,
            average_win=result.average_win,
            average_loss_abs=result.average_loss_abs,
            payoff_ratio=result.payoff_ratio,
            best_episode_pnl=result.best_episode_pnl,
            worst_episode_pnl=result.worst_episode_pnl,
            average_holding_trade_days=result.average_holding_trade_days,
            median_holding_trade_days=result.median_holding_trade_days,
            closed_realized_pnl=result.closed_realized_pnl,
            open_realized_pnl_end=result.open_realized_pnl_end,
            open_unrealized_pnl_end=result.open_unrealized_pnl_end,
            open_mark_to_market_pnl_end=result.open_mark_to_market_pnl_end,
            warnings=list(result.warnings),
            result_summary={
                "annualization_trade_days": source.annualization_trade_days,
                "pnl_zero_epsilon_cny": str(self.config.pnl_zero_epsilon_cny),
                "short_sample_warning_trade_days": (self.config.short_sample_warning_trade_days),
                "fill_replay_order": (
                    "trade_date,side_sell_first,scheduled_trade_date,order_id,fill_id"
                ),
                "turnover_method": "double_sided_no_half",
                "pnl_cost_method": "cash_fees_only_slippage_not_double_deducted",
            },
        )
        self.repository.add_report(report)
        self.repository.add_daily(
            [
                PortfolioPerformanceTradeDaily(
                    trade_id=report.id,
                    performance_id=performance_id,
                    run_id=run_id,
                    **point.__dict__,
                )
                for point in result.daily
            ]
        )
        self.repository.add_episodes(
            [
                PortfolioPerformanceTradeEpisode(
                    trade_id=report.id,
                    performance_id=performance_id,
                    run_id=run_id,
                    **episode.__dict__,
                )
                for episode in result.episodes
            ]
        )
        return PerformanceTradeArtifact(report, reused=False)

    def get_report(
        self, run_id: uuid.UUID, performance_id: uuid.UUID | None = None
    ) -> PortfolioPerformanceTradeReport:
        base = self.source_provider.select_base(run_id, performance_id)
        report = self.repository.latest_report(base.report.id)
        if report is None:
            raise LookupError("portfolio performance trade report not found")
        return report

    def daily_page(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[PortfolioPerformanceTradeReport, list[PortfolioPerformanceTradeDaily], int]:
        report = self.get_report(run_id, performance_id)
        return (
            report,
            self.repository.list_daily(report.id, limit=limit, offset=offset),
            self.repository.count_daily(report.id),
        )

    def episode_page(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None,
        status: str | None,
        ts_code: str | None,
        limit: int,
        offset: int,
    ) -> tuple[
        PortfolioPerformanceTradeReport,
        list[PortfolioPerformanceTradeEpisode],
        int,
    ]:
        report = self.get_report(run_id, performance_id)
        return (
            report,
            self.repository.list_episodes(
                report.id,
                status=status,
                ts_code=ts_code,
                limit=limit,
                offset=offset,
            ),
            self.repository.count_episodes(report.id, status=status, ts_code=ts_code),
        )

    def _owned_job_for_terminal_update(self, lease: PerformanceTradeExecutionLease) -> JobRun:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == lease.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        metadata = dict(job.job_metadata or {}) if job is not None else {}
        if (
            job is None
            or job.job_type != PERFORMANCE_TRADE_JOB_TYPE
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or metadata.get("portfolio_run_id") != str(lease.run_id)
            or metadata.get("performance_id") != str(lease.performance_id)
            or metadata.get("trade_version") != TRADE_VERSION
        ):
            raise PerformanceTradeOwnershipError(
                "performance trade execution lease is no longer current"
            )
        return job
