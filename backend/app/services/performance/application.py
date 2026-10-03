import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.performance_config import PERFORMANCE_VERSION
from app.domain.performance import PerformanceEngine
from app.models.job import JobRun
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.portfolio import PortfolioBacktestRun
from app.repositories.performance import PerformanceRepository
from app.services.calc_metadata import config_hash
from app.services.performance.source import PerformanceSourceProvider

PERFORMANCE_JOB_TYPE = "portfolio_performance"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}


class PerformanceConflictError(RuntimeError):
    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class PerformanceRunNotSuccessError(RuntimeError):
    code = "PERFORMANCE_RUN_NOT_SUCCESS"


class PerformanceOwnershipError(RuntimeError):
    pass


@dataclass(frozen=True)
class PerformanceArtifact:
    report: PortfolioPerformanceReport
    reused: bool


@dataclass(frozen=True)
class PerformanceExecutionLease:
    job_id: uuid.UUID
    worker_id: str
    run_id: uuid.UUID


class PerformanceApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PerformanceRepository | None = None,
        source_provider: PerformanceSourceProvider | None = None,
        engine: PerformanceEngine | None = None,
        before_terminal_hook: Callable[
            [PerformanceExecutionLease, PerformanceArtifact], None
        ]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.performance_config is None:
            raise RuntimeError("performance config is not loaded")
        self.config = self.settings.performance_config
        self.repository = repository or PerformanceRepository(db)
        self.source_provider = source_provider or PerformanceSourceProvider(db)
        self.engine = engine or PerformanceEngine()
        self.before_terminal_hook = before_terminal_hook

    def queue_calculation(self, run_id: uuid.UUID) -> JobRun:
        self.repository.lock_run(run_id)
        run = self.db.execute(
            select(PortfolioBacktestRun)
            .where(PortfolioBacktestRun.id == run_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if run is None:
            raise LookupError("portfolio backtest run not found")
        if run.account_mode != "BACKTEST" or run.status != "SUCCESS":
            raise PerformanceRunNotSuccessError(
                "performance calculation requires a successful BACKTEST run"
            )
        active = self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == PERFORMANCE_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains({"portfolio_run_id": str(run_id)}),
            )
            .order_by(JobRun.started_at.desc())
            .limit(1)
        )
        if active is not None:
            raise PerformanceConflictError(
                "performance calculation already has an active job", job_id=active.id
            )
        job = JobRun(
            job_type=PERFORMANCE_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for performance calculation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "portfolio_run_id": str(run_id),
                "performance_version": PERFORMANCE_VERSION,
                "stage": "queued",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_job(self, job_id: uuid.UUID) -> PerformanceArtifact:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if job is None or job.job_type != PERFORMANCE_JOB_TYPE:
            raise LookupError("performance job not found")
        if job.status != "RUNNING" or not job.worker_id:
            raise PerformanceOwnershipError(
                "performance job is not owned by a running worker"
            )
        metadata = dict(job.job_metadata or {})
        try:
            run_id = uuid.UUID(str(metadata["portfolio_run_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("performance job has invalid portfolio_run_id") from exc
        lease = PerformanceExecutionLease(
            job_id=job.id,
            worker_id=job.worker_id,
            run_id=run_id,
        )

        artifact = self.calculate_now(run_id)
        if self.before_terminal_hook is not None:
            self.before_terminal_hook(lease, artifact)
        terminal_job = self._owned_job_for_terminal_update(lease)
        now = datetime.now(UTC)
        terminal_job.status = "SUCCESS"
        terminal_job.finished_at = now
        terminal_job.step = "performance calculation complete"
        terminal_job.row_count = artifact.report.trade_days
        terminal_job.job_metadata = {
            **dict(terminal_job.job_metadata or {}),
            "stage": "success",
            "performance_id": str(artifact.report.id),
            "source_hash": artifact.report.source_hash,
            "reused": artifact.reused,
        }
        self.db.add(terminal_job)
        self.db.commit()
        self.db.refresh(terminal_job)
        return artifact

    def calculate_now(self, run_id: uuid.UUID) -> PerformanceArtifact:
        self.repository.lock_run(run_id)
        config_payload = self.config.model_dump(mode="json")
        performance_config_hash = config_hash(config_payload)
        source = self.source_provider.load(
            run_id,
            performance_version=PERFORMANCE_VERSION,
            performance_config_hash=performance_config_hash,
        )
        existing = self.repository.find_by_identity(
            run_id=run_id,
            performance_version=PERFORMANCE_VERSION,
            performance_config_hash=performance_config_hash,
            source_hash=source.source_hash,
        )
        if existing is not None:
            return PerformanceArtifact(existing, reused=True)

        result = self.engine.calculate(source, self.config)
        report = PortfolioPerformanceReport(
            run_id=run_id,
            performance_version=PERFORMANCE_VERSION,
            performance_config_hash=performance_config_hash,
            source_hash=source.source_hash,
            status="SUCCESS",
            start_date=result.start_date,
            end_date=result.end_date,
            trade_days=result.trade_days,
            initial_nav=result.initial_nav,
            final_nav=result.final_nav,
            cumulative_return=result.cumulative_return,
            annualized_return=result.annualized_return,
            max_drawdown=result.max_drawdown,
            max_drawdown_peak_date=result.max_drawdown_peak_date,
            max_drawdown_trough_date=result.max_drawdown_trough_date,
            max_drawdown_recovery_date=result.max_drawdown_recovery_date,
            max_drawdown_duration_days=result.max_drawdown_duration_days,
            positive_days=result.positive_days,
            negative_days=result.negative_days,
            flat_days=result.flat_days,
            warnings=list(result.warnings),
            result_summary={
                "annualization_trade_days": self.config.annualization_trade_days,
                "short_sample_warning_trade_days": (
                    self.config.short_sample_warning_trade_days
                ),
                "zero_return_epsilon": str(self.config.zero_return_epsilon),
            },
        )
        self.repository.add_report(report)
        daily = [
            PortfolioPerformanceDaily(
                performance_id=report.id,
                run_id=run_id,
                trade_date=point.trade_date,
                nav=point.nav,
                daily_return=point.daily_return,
                cumulative_return=point.cumulative_return,
                running_peak_nav=point.running_peak_nav,
                drawdown=point.drawdown,
                drawdown_duration_days=point.drawdown_duration_days,
                cash_ratio=point.cash_ratio,
                gross_exposure=point.gross_exposure,
                net_exposure=point.net_exposure,
                position_count=point.position_count,
                trading_cost=point.trading_cost,
            )
            for point in result.daily
        ]
        self.repository.add_daily(daily)
        return PerformanceArtifact(report, reused=False)

    def _owned_job_for_terminal_update(
        self, lease: PerformanceExecutionLease
    ) -> JobRun:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == lease.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        metadata = dict(job.job_metadata or {}) if job is not None else {}
        if (
            job is None
            or job.job_type != PERFORMANCE_JOB_TYPE
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or metadata.get("portfolio_run_id") != str(lease.run_id)
        ):
            raise PerformanceOwnershipError(
                "performance execution lease is no longer current"
            )
        return job

    def get_report(self, run_id: uuid.UUID) -> PortfolioPerformanceReport:
        report = self.repository.latest_report(run_id)
        if report is None:
            raise LookupError("portfolio performance report not found")
        return report

    def daily_page(
        self, run_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[PortfolioPerformanceReport, list[PortfolioPerformanceDaily], int]:
        report = self.get_report(run_id)
        return (
            report,
            self.repository.list_daily(report.id, limit=limit, offset=offset),
            self.repository.count_daily(report.id),
        )
