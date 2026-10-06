import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentParameterSensitivity,
    PortfolioExperimentTrialEvaluation,
)


class ExperimentEvaluationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_identity(
        self,
        *,
        experiment_id: uuid.UUID,
        evaluation_version: str,
        evaluation_config_hash: str,
        policy_hash: str,
        source_hash: str,
    ) -> PortfolioExperimentEvaluationReport | None:
        return self.db.scalar(
            select(PortfolioExperimentEvaluationReport)
            .where(
                PortfolioExperimentEvaluationReport.experiment_id == experiment_id,
                PortfolioExperimentEvaluationReport.evaluation_version
                == evaluation_version,
                PortfolioExperimentEvaluationReport.evaluation_config_hash
                == evaluation_config_hash,
                PortfolioExperimentEvaluationReport.policy_hash == policy_hash,
                PortfolioExperimentEvaluationReport.source_hash == source_hash,
            )
            .execution_options(populate_existing=True)
        )

    def add(
        self,
        report: PortfolioExperimentEvaluationReport,
        trials: list[PortfolioExperimentTrialEvaluation],
        sensitivity: list[PortfolioExperimentParameterSensitivity],
    ) -> None:
        self.db.add(report)
        self.db.flush()
        self.db.add_all(trials)
        self.db.add_all(sensitivity)
        self.db.flush()

    def get(
        self, experiment_id: uuid.UUID, evaluation_id: uuid.UUID
    ) -> PortfolioExperimentEvaluationReport | None:
        return self.db.scalar(
            select(PortfolioExperimentEvaluationReport)
            .where(
                PortfolioExperimentEvaluationReport.id == evaluation_id,
                PortfolioExperimentEvaluationReport.experiment_id == experiment_id,
            )
            .execution_options(populate_existing=True)
        )

    def trial_page(
        self,
        evaluation_id: uuid.UUID,
        *,
        status: str | None,
        feasible: bool | None,
        shortlisted: bool | None,
        pareto_front: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PortfolioExperimentTrialEvaluation], int]:
        where = [PortfolioExperimentTrialEvaluation.evaluation_id == evaluation_id]
        if status is not None:
            where.append(PortfolioExperimentTrialEvaluation.status == status)
        if feasible is not None:
            where.append(PortfolioExperimentTrialEvaluation.feasible == feasible)
        if shortlisted is not None:
            where.append(PortfolioExperimentTrialEvaluation.shortlisted == shortlisted)
        if pareto_front is not None:
            where.append(PortfolioExperimentTrialEvaluation.pareto_front == pareto_front)
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioExperimentTrialEvaluation)
                .where(*where)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PortfolioExperimentTrialEvaluation)
                .where(*where)
                .order_by(
                    case(
                        (PortfolioExperimentTrialEvaluation.status == "EXCLUDED", 1),
                        else_=0,
                    ),
                    PortfolioExperimentTrialEvaluation.selection_rank.asc().nulls_last(),
                    PortfolioExperimentTrialEvaluation.trial_no,
                )
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            ).all()
        )
        return rows, total

    def shortlist(
        self, evaluation_id: uuid.UUID
    ) -> list[PortfolioExperimentTrialEvaluation]:
        return list(
            self.db.scalars(
                select(PortfolioExperimentTrialEvaluation)
                .where(
                    PortfolioExperimentTrialEvaluation.evaluation_id == evaluation_id,
                    PortfolioExperimentTrialEvaluation.shortlisted.is_(True),
                )
                .order_by(PortfolioExperimentTrialEvaluation.selection_rank)
                .execution_options(populate_existing=True)
            ).all()
        )

    def sensitivity(
        self, evaluation_id: uuid.UUID, parameter_name: str | None
    ) -> list[PortfolioExperimentParameterSensitivity]:
        statement = select(PortfolioExperimentParameterSensitivity).where(
            PortfolioExperimentParameterSensitivity.evaluation_id == evaluation_id
        )
        if parameter_name is not None:
            statement = statement.where(
                PortfolioExperimentParameterSensitivity.parameter_name == parameter_name
            )
        return list(
            self.db.scalars(
                statement.execution_options(populate_existing=True)
            ).all()
        )

    def history(
        self, experiment_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PortfolioExperimentEvaluationReport], int]:
        where = PortfolioExperimentEvaluationReport.experiment_id == experiment_id
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioExperimentEvaluationReport)
                .where(where)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PortfolioExperimentEvaluationReport)
                .where(where)
                .order_by(
                    PortfolioExperimentEvaluationReport.calculated_at.desc(),
                    PortfolioExperimentEvaluationReport.id.desc(),
                )
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            ).all()
        )
        return rows, total
