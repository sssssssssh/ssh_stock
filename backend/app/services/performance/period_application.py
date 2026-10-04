import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.performance_period_config import PERIOD_VERSION
from app.domain.performance.period_engine import PeriodEngine
from app.models.job import JobRun
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.repositories.performance_period import PerformancePeriodRepository
from app.services.calc_metadata import config_hash
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsArtifactBundleResolver,
)
from app.services.performance.period_source import PerformancePeriodSourceProvider

PERFORMANCE_PERIOD_JOB_TYPE = "portfolio_performance_period"
_ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}


class PerformancePeriodConflictError(RuntimeError):
    code = "PERIOD_CALCULATION_CONFLICT"

    def __init__(self, message: str, *, job_id: uuid.UUID | None = None) -> None:
        self.job_id = job_id
        super().__init__(message)


class PerformancePeriodOwnershipError(RuntimeError):
    code = "PERIOD_OWNERSHIP_LOST"


@dataclass(frozen=True)
class PerformancePeriodArtifact:
    report: PortfolioPerformancePeriodReport
    reused: bool


@dataclass(frozen=True)
class PerformancePeriodExecutionLease:
    job_id: uuid.UUID
    worker_id: str
    run_id: uuid.UUID
    performance_id: uuid.UUID
    risk_id: uuid.UUID
    trade_id: uuid.UUID


class PerformancePeriodApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PerformancePeriodRepository | None = None,
        resolver: AnalyticsArtifactBundleResolver | None = None,
        source_provider: PerformancePeriodSourceProvider | None = None,
        engine: PeriodEngine | None = None,
        before_terminal_hook: Callable[
            [PerformancePeriodExecutionLease, PerformancePeriodArtifact], None
        ]
        | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.performance_period_config is None:
            raise RuntimeError("performance period config is not loaded")
        self.config = self.settings.performance_period_config
        self.repository = repository or PerformancePeriodRepository(db)
        self.resolver = resolver or AnalyticsArtifactBundleResolver(db)
        self.source_provider = source_provider or PerformancePeriodSourceProvider(db)
        self.engine = engine or PeriodEngine()
        self.before_terminal_hook = before_terminal_hook

    def queue_calculation(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None = None,
        risk_id: uuid.UUID | None = None,
        trade_id: uuid.UUID | None = None,
    ) -> tuple[JobRun, AnalyticsArtifactBundle]:
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
        )
        self.repository.lock_bundle(
            bundle.performance.id, bundle.risk.id, bundle.trade.id
        )
        identity = {
            "performance_id": str(bundle.performance.id),
            "risk_id": str(bundle.risk.id),
            "trade_id": str(bundle.trade.id),
        }
        active = self.db.scalar(
            select(JobRun)
            .where(
                JobRun.job_type == PERFORMANCE_PERIOD_JOB_TYPE,
                JobRun.status.in_(_ACTIVE_JOB_STATUSES),
                JobRun.job_metadata.contains(identity),
            )
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
        )
        if active is not None:
            raise PerformancePeriodConflictError(
                "period calculation already has an active job", job_id=active.id
            )
        job = JobRun(
            job_type=PERFORMANCE_PERIOD_JOB_TYPE,
            target_trade_date=None,
            status="QUEUED",
            step="queued for performance period calculation",
            row_count=0,
            cancel_requested=False,
            job_metadata={
                "portfolio_run_id": str(run_id),
                **identity,
                "period_version": PERIOD_VERSION,
                "stage": "queued",
            },
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job, bundle

    def run_job(self, job_id: uuid.UUID) -> PerformancePeriodArtifact:
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
        )
        if job is None or job.job_type != PERFORMANCE_PERIOD_JOB_TYPE:
            raise LookupError("performance period job not found")
        if job.status != "RUNNING" or not job.worker_id:
            raise PerformancePeriodOwnershipError("period job is not owned by a running worker")
        metadata = dict(job.job_metadata or {})
        try:
            lease = PerformancePeriodExecutionLease(
                job_id=job.id,
                worker_id=job.worker_id,
                run_id=uuid.UUID(str(metadata["portfolio_run_id"])),
                performance_id=uuid.UUID(str(metadata["performance_id"])),
                risk_id=uuid.UUID(str(metadata["risk_id"])),
                trade_id=uuid.UUID(str(metadata["trade_id"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PerformancePeriodOwnershipError("period job identities are invalid") from exc
        if metadata.get("period_version") != PERIOD_VERSION:
            raise PerformancePeriodOwnershipError("period job version is invalid")
        artifact = self._calculate_uncommitted(
            lease.run_id,
            performance_id=lease.performance_id,
            risk_id=lease.risk_id,
            trade_id=lease.trade_id,
        )
        if self.before_terminal_hook:
            self.before_terminal_hook(lease, artifact)
        terminal = self._owned_job_for_terminal_update(lease)
        terminal.status = "SUCCESS"
        terminal.finished_at = datetime.now(UTC)
        terminal.step = "performance period calculation complete"
        terminal.row_count = artifact.report.month_count + artifact.report.year_count
        terminal.job_metadata = {
            **dict(terminal.job_metadata or {}),
            "stage": "success",
            "period_id": str(artifact.report.id),
            "period_source_hash": artifact.report.period_source_hash,
            "reused": artifact.reused,
        }
        self.db.add(terminal)
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def calculate_now(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID,
        risk_id: uuid.UUID,
        trade_id: uuid.UUID,
    ) -> PerformancePeriodArtifact:
        artifact = self._calculate_uncommitted(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
        )
        self.db.commit()
        self.db.refresh(artifact.report)
        return artifact

    def _calculate_uncommitted(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID,
        risk_id: uuid.UUID,
        trade_id: uuid.UUID,
    ) -> PerformancePeriodArtifact:
        self.repository.lock_bundle(performance_id, risk_id, trade_id)
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
        )
        period_config_hash = config_hash(self.config.model_dump(mode="json"))
        source = self.source_provider.load(
            bundle,
            period_version=PERIOD_VERSION,
            period_config_hash=period_config_hash,
        )
        existing = self.repository.find_by_identity(
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_version=PERIOD_VERSION,
            period_config_hash=period_config_hash,
            period_source_hash=source.period_source_hash,
        )
        if existing is not None:
            return PerformancePeriodArtifact(existing, reused=True)
        result = self.engine.calculate(source, self.config)
        report = PortfolioPerformancePeriodReport(
            id=uuid.uuid4(),
            run_id=run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            period_version=PERIOD_VERSION,
            period_config_hash=period_config_hash,
            period_source_hash=source.period_source_hash,
            status="SUCCESS",
            start_date=result.start_date,
            end_date=result.end_date,
            trade_days=result.trade_days,
            month_count=result.month_count,
            year_count=result.year_count,
            warnings=list(result.warnings),
            result_summary={
                "period_types": list(self.config.period_types),
                "excess_return_method": self.config.excess_return_method,
                "closed_episode_attribution": self.config.closed_episode_attribution,
            },
        )
        rows = [
            PortfolioPerformancePeriod(
                period_id=report.id,
                run_id=run_id,
                performance_id=performance_id,
                risk_id=risk_id,
                trade_id=trade_id,
                **point.__dict__,
            )
            for point in result.periods
        ]
        self.repository.add(report, rows)
        return PerformancePeriodArtifact(report, reused=False)

    def page(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID | None,
        risk_id: uuid.UUID | None,
        trade_id: uuid.UUID | None,
        period_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[PortfolioPerformancePeriodReport, list[PortfolioPerformancePeriod], int]:
        bundle = self.resolver.resolve(
            run_id,
            performance_id=performance_id,
            risk_id=risk_id,
            trade_id=trade_id,
            require_period=True,
        )
        assert bundle.period is not None
        return (
            bundle.period,
            self.repository.list_rows(
                bundle.period.id, period_type=period_type, limit=limit, offset=offset
            ),
            self.repository.count_rows(bundle.period.id, period_type),
        )

    def _owned_job_for_terminal_update(
        self, lease: PerformancePeriodExecutionLease
    ) -> JobRun:
        job = self.db.scalar(
            select(JobRun)
            .where(JobRun.id == lease.job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        metadata = dict(job.job_metadata or {}) if job else {}
        expected = {
            "portfolio_run_id": str(lease.run_id),
            "performance_id": str(lease.performance_id),
            "risk_id": str(lease.risk_id),
            "trade_id": str(lease.trade_id),
            "period_version": PERIOD_VERSION,
        }
        if (
            job is None
            or job.job_type != PERFORMANCE_PERIOD_JOB_TYPE
            or job.status != "RUNNING"
            or job.worker_id != lease.worker_id
            or any(metadata.get(key) != value for key, value in expected.items())
        ):
            raise PerformancePeriodOwnershipError("period execution lease is no longer current")
        return job
