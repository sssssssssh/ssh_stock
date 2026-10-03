import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.performance_risk_config import RISK_VERSION
from app.domain.performance import RiskEngine
from app.models.job import JobRun
from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.repositories.performance_risk import PerformanceRiskRepository
from app.services.calc_metadata import config_hash
from app.services.performance.risk_identity import BENCHMARK_PRICE_QUANTUM_VERSION
from app.services.performance.risk_source import PerformanceRiskSourceProvider

PERFORMANCE_RISK_JOB_TYPE = "portfolio_performance_risk"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}


class PerformanceRiskConflictError(RuntimeError):
    code = "PERFORMANCE_RISK_CALCULATION_CONFLICT"

    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class PerformanceRiskOwnershipError(RuntimeError):
    code = "PERFORMANCE_RISK_OWNERSHIP_LOST"


@dataclass(frozen=True)
class PerformanceRiskArtifact:
    report: PortfolioPerformanceRiskReport
    reused: bool


@dataclass(frozen=True)
class PerformanceRiskExecutionLease:
    job_id: uuid.UUID
    worker_id: str
    run_id: uuid.UUID
    performance_id: uuid.UUID


class PerformanceRiskApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PerformanceRiskRepository | None = None,
        source_provider: PerformanceRiskSourceProvider | None = None,
        engine: RiskEngine | None = None,
        before_terminal_hook: Callable[
            [PerformanceRiskExecutionLease, PerformanceRiskArtifact], None
        ]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.performance_risk_config is None:
            raise RuntimeError("performance risk config is not loaded")
        self.config = self.settings.performance_risk_config
        self.repository = repository or PerformanceRiskRepository(db)
        self.source_provider = source_provider or PerformanceRiskSourceProvider(db)
        self.engine = engine or RiskEngine()
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
                JobRun.job_type == PERFORMANCE_RISK_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains(
                    {"performance_id": str(selected_performance_id)}
                ),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
        )
        if active is not None:
            raise PerformanceRiskConflictError(
                "performance risk calculation already has an active job",
                job_id=active.id,
            )
        job = JobRun(
            job_type=PERFORMANCE_RISK_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for performance risk calculation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "portfolio_run_id": str(run_id),
                "performance_id": str(selected_performance_id),
                "risk_version": RISK_VERSION,
                "stage": "queued",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_job(self, job_id: uuid.UUID) -> PerformanceRiskArtifact:
        job = self.db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if job is None or job.job_type != PERFORMANCE_RISK_JOB_TYPE:
            raise LookupError("performance risk job not found")
        if job.status != "RUNNING" or not job.worker_id:
            raise PerformanceRiskOwnershipError(
                "performance risk job is not owned by a running worker"
            )
        metadata = dict(job.job_metadata or {})
        try:
            run_id = uuid.UUID(str(metadata["portfolio_run_id"]))
            performance_id = uuid.UUID(str(metadata["performance_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PerformanceRiskOwnershipError(
                "performance risk job metadata identities are invalid"
            ) from exc
        if metadata.get("risk_version") != RISK_VERSION:
            raise PerformanceRiskOwnershipError(
                "performance risk job version identity is invalid"
            )
        lease = PerformanceRiskExecutionLease(
            job_id=job.id,
            worker_id=job.worker_id,
            run_id=run_id,
            performance_id=performance_id,
        )
        artifact = self._calculate_uncommitted(run_id, performance_id)
        if self.before_terminal_hook is not None:
            self.before_terminal_hook(lease, artifact)
        terminal_job = self._owned_job_for_terminal_update(lease)
        terminal_job.status = "SUCCESS"
        terminal_job.finished_at = datetime.now(UTC)
        terminal_job.step = "performance risk calculation complete"
        terminal_job.row_count = artifact.report.trade_days
        terminal_job.job_metadata = {
            **dict(terminal_job.job_metadata or {}),
            "stage": "success",
            "risk_id": str(artifact.report.id),
            "benchmark_source_hash": artifact.report.benchmark_source_hash,
            "risk_source_hash": artifact.report.risk_source_hash,
            "reused": artifact.reused,
        }
        self.db.add(terminal_job)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def calculate_now(
        self, run_id: uuid.UUID, performance_id: uuid.UUID
    ) -> PerformanceRiskArtifact:
        artifact = self._calculate_uncommitted(run_id, performance_id)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def _calculate_uncommitted(
        self, run_id: uuid.UUID, performance_id: uuid.UUID
    ) -> PerformanceRiskArtifact:
        self.repository.lock_performance(performance_id)
        risk_config_hash = config_hash(self.config.model_dump(mode="json"))
        source = self.source_provider.load(
            run_id,
            performance_id=performance_id,
            risk_version=RISK_VERSION,
            risk_config_hash=risk_config_hash,
        )
        existing = self.repository.find_by_identity(
            performance_id=performance_id,
            risk_version=RISK_VERSION,
            risk_config_hash=risk_config_hash,
            benchmark_source_hash=source.benchmark_source_hash,
        )
        if existing is not None:
            return PerformanceRiskArtifact(existing, reused=True)

        result = self.engine.calculate(source, self.config)
        report = PortfolioPerformanceRiskReport(
            performance_id=performance_id,
            run_id=run_id,
            risk_version=RISK_VERSION,
            risk_config_hash=risk_config_hash,
            benchmark_code=source.benchmark_code,
            benchmark_source_hash=source.benchmark_source_hash,
            risk_source_hash=source.risk_source_hash,
            status="SUCCESS",
            start_date=result.start_date,
            end_date=result.end_date,
            trade_days=result.trade_days,
            risk_free_rate_annual=result.risk_free_rate_annual,
            benchmark_initial_nav=result.benchmark_initial_nav,
            benchmark_final_nav=result.benchmark_final_nav,
            benchmark_cumulative_return=result.benchmark_cumulative_return,
            benchmark_annualized_return=result.benchmark_annualized_return,
            excess_cumulative_return=result.excess_cumulative_return,
            relative_nav_final=result.relative_nav_final,
            strategy_annualized_volatility=result.strategy_annualized_volatility,
            benchmark_annualized_volatility=result.benchmark_annualized_volatility,
            downside_deviation_annualized=result.downside_deviation_annualized,
            sharpe_ratio=result.sharpe_ratio,
            sortino_ratio=result.sortino_ratio,
            calmar_ratio=result.calmar_ratio,
            tracking_error=result.tracking_error,
            information_ratio=result.information_ratio,
            alpha_daily=result.alpha_daily,
            alpha_annualized=result.alpha_annualized,
            beta=result.beta,
            correlation=result.correlation,
            warnings=list(result.warnings),
            result_summary={
                "annualization_trade_days": source.annualization_trade_days,
                "minimum_observations": self.config.minimum_observations,
                "short_sample_warning_trade_days": (
                    self.config.short_sample_warning_trade_days
                ),
                "zero_denominator_epsilon": str(
                    self.config.zero_denominator_epsilon
                ),
                "benchmark_price_precision_version": (
                    BENCHMARK_PRICE_QUANTUM_VERSION
                ),
                "alpha_annualization": "arithmetic",
                "excess_cumulative_return": "relative_nav_minus_one",
            },
        )
        self.repository.add_report(report)
        self.repository.add_daily(
            [
                PortfolioPerformanceRiskDaily(
                    risk_id=report.id,
                    performance_id=performance_id,
                    run_id=run_id,
                    trade_date=point.trade_date,
                    benchmark_reference_close=point.benchmark_reference_close,
                    benchmark_close=point.benchmark_close,
                    benchmark_daily_return=point.benchmark_daily_return,
                    benchmark_nav=point.benchmark_nav,
                    active_return=point.active_return,
                    relative_nav=point.relative_nav,
                    excess_cumulative_return=point.excess_cumulative_return,
                )
                for point in result.daily
            ]
        )
        return PerformanceRiskArtifact(report, reused=False)

    def get_report(
        self, run_id: uuid.UUID, performance_id: uuid.UUID | None = None
    ) -> PortfolioPerformanceRiskReport:
        base = self.source_provider.select_base(run_id, performance_id)
        report = self.repository.latest_report(base.report.id)
        if report is None:
            raise LookupError("portfolio performance risk report not found")
        return report

    def daily_page(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[
        PortfolioPerformanceRiskReport,
        list[PortfolioPerformanceRiskDaily],
        int,
    ]:
        report = self.get_report(run_id, performance_id)
        return (
            report,
            self.repository.list_daily(report.id, limit=limit, offset=offset),
            self.repository.count_daily(report.id),
        )

    def _owned_job_for_terminal_update(
        self, lease: PerformanceRiskExecutionLease
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
            or job.job_type != PERFORMANCE_RISK_JOB_TYPE
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or metadata.get("portfolio_run_id") != str(lease.run_id)
            or metadata.get("performance_id") != str(lease.performance_id)
            or metadata.get("risk_version") != RISK_VERSION
        ):
            raise PerformanceRiskOwnershipError(
                "performance risk execution lease is no longer current"
            )
        return job
