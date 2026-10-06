import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.job import JobRun
from app.models.portfolio import PortfolioBacktestRun


@dataclass(frozen=True)
class ExperimentTrialRecord:
    trial: PortfolioExperimentTrial
    run: PortfolioBacktestRun | None
    job: JobRun | None


class ExperimentRepository:
    """Persistence operations only; orchestration rules live in the service."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        experiment: PortfolioExperiment,
        trials: list[PortfolioExperimentTrial],
    ) -> PortfolioExperiment:
        self.db.add(experiment)
        self.db.add_all(trials)
        self.db.flush()
        return experiment

    def get(self, experiment_id: uuid.UUID) -> PortfolioExperiment | None:
        return self.db.execute(
            select(PortfolioExperiment)
            .where(PortfolioExperiment.id == experiment_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def get_for_update(self, experiment_id: uuid.UUID) -> PortfolioExperiment | None:
        return self.db.execute(
            select(PortfolioExperiment)
            .where(PortfolioExperiment.id == experiment_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()

    def list_trials_for_update(
        self, experiment_id: uuid.UUID
    ) -> list[PortfolioExperimentTrial]:
        return list(
            self.db.execute(
                select(PortfolioExperimentTrial)
                .where(PortfolioExperimentTrial.experiment_id == experiment_id)
                .order_by(PortfolioExperimentTrial.trial_no)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            .scalars()
            .all()
        )

    def list_records(self, experiment_id: uuid.UUID) -> list[ExperimentTrialRecord]:
        return self._records(
            select(PortfolioExperimentTrial, PortfolioBacktestRun, JobRun)
            .outerjoin(
                PortfolioBacktestRun,
                PortfolioBacktestRun.id == PortfolioExperimentTrial.run_id,
            )
            .outerjoin(JobRun, JobRun.id == PortfolioBacktestRun.job_id)
            .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            .order_by(PortfolioExperimentTrial.trial_no)
            .execution_options(populate_existing=True)
        )

    def trial_page(
        self,
        experiment_id: uuid.UUID,
        *,
        state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ExperimentTrialRecord], int]:
        where = [PortfolioExperimentTrial.experiment_id == experiment_id]
        if state == "PLANNED":
            where.append(PortfolioExperimentTrial.run_id.is_(None))
        elif state is not None:
            where.append(PortfolioBacktestRun.status == state)
        statement = (
            select(PortfolioExperimentTrial, PortfolioBacktestRun, JobRun)
            .outerjoin(
                PortfolioBacktestRun,
                PortfolioBacktestRun.id == PortfolioExperimentTrial.run_id,
            )
            .outerjoin(JobRun, JobRun.id == PortfolioBacktestRun.job_id)
            .where(*where)
        )
        count_statement = (
            select(func.count())
            .select_from(PortfolioExperimentTrial)
            .outerjoin(
                PortfolioBacktestRun,
                PortfolioBacktestRun.id == PortfolioExperimentTrial.run_id,
            )
            .where(*where)
        )
        total = int(self.db.scalar(count_statement) or 0)
        records = self._records(
            statement.order_by(PortfolioExperimentTrial.trial_no)
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return records, total

    def get_trial_record(
        self, experiment_id: uuid.UUID, trial_id: uuid.UUID
    ) -> ExperimentTrialRecord | None:
        rows = self._records(
            select(PortfolioExperimentTrial, PortfolioBacktestRun, JobRun)
            .outerjoin(
                PortfolioBacktestRun,
                PortfolioBacktestRun.id == PortfolioExperimentTrial.run_id,
            )
            .outerjoin(JobRun, JobRun.id == PortfolioBacktestRun.job_id)
            .where(
                PortfolioExperimentTrial.experiment_id == experiment_id,
                PortfolioExperimentTrial.id == trial_id,
            )
            .execution_options(populate_existing=True)
        )
        return rows[0] if rows else None

    def add_run(self, run: PortfolioBacktestRun) -> PortfolioBacktestRun:
        self.db.add(run)
        self.db.flush()
        return run

    def get_run(self, run_id: uuid.UUID) -> PortfolioBacktestRun | None:
        return self.db.execute(
            select(PortfolioBacktestRun)
            .where(PortfolioBacktestRun.id == run_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def _records(self, statement: object) -> list[ExperimentTrialRecord]:
        return [
            ExperimentTrialRecord(trial=trial, run=run, job=job)
            for trial, run, job in self.db.execute(statement).all()
        ]
