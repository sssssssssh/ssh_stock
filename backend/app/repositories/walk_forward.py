import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardParameterStability,
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)


class WalkForwardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        study: PortfolioWalkForwardStudy,
        windows: list[PortfolioWalkForwardWindow],
    ) -> None:
        self.db.add(study)
        self.db.add_all(windows)
        self.db.flush()

    def get(self, study_id: uuid.UUID) -> PortfolioWalkForwardStudy | None:
        return self.db.scalar(
            select(PortfolioWalkForwardStudy)
            .where(PortfolioWalkForwardStudy.id == study_id)
            .execution_options(populate_existing=True)
        )

    def get_for_update(
        self, study_id: uuid.UUID
    ) -> PortfolioWalkForwardStudy | None:
        return self.db.scalar(
            select(PortfolioWalkForwardStudy)
            .where(PortfolioWalkForwardStudy.id == study_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )

    def list_windows(self, study_id: uuid.UUID) -> list[PortfolioWalkForwardWindow]:
        return list(
            self.db.scalars(
                select(PortfolioWalkForwardWindow)
                .where(PortfolioWalkForwardWindow.study_id == study_id)
                .order_by(PortfolioWalkForwardWindow.window_no)
                .execution_options(populate_existing=True)
            ).all()
        )

    def get_window_for_update(
        self, study_id: uuid.UUID, window_no: int
    ) -> PortfolioWalkForwardWindow | None:
        return self.db.scalar(
            select(PortfolioWalkForwardWindow)
            .where(
                PortfolioWalkForwardWindow.study_id == study_id,
                PortfolioWalkForwardWindow.window_no == window_no,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )

    def add_run(self, run: PortfolioBacktestRun) -> None:
        self.db.add(run)
        self.db.flush()

    def find_validation(
        self,
        *,
        study_id: uuid.UUID,
        walk_forward_version: str,
        walk_forward_config_hash: str,
        source_hash: str,
    ) -> PortfolioWalkForwardValidationReport | None:
        return self.db.scalar(
            select(PortfolioWalkForwardValidationReport)
            .where(
                PortfolioWalkForwardValidationReport.study_id == study_id,
                PortfolioWalkForwardValidationReport.walk_forward_version
                == walk_forward_version,
                PortfolioWalkForwardValidationReport.walk_forward_config_hash
                == walk_forward_config_hash,
                PortfolioWalkForwardValidationReport.source_hash == source_hash,
            )
            .execution_options(populate_existing=True)
        )

    def add_validation(
        self,
        report: PortfolioWalkForwardValidationReport,
        windows: list[PortfolioWalkForwardWindowValidation],
        stability: list[PortfolioWalkForwardParameterStability],
    ) -> None:
        self.db.add(report)
        self.db.flush()
        self.db.add_all(windows)
        self.db.add_all(stability)
        self.db.flush()

    def get_validation(
        self, study_id: uuid.UUID, validation_id: uuid.UUID
    ) -> PortfolioWalkForwardValidationReport | None:
        return self.db.scalar(
            select(PortfolioWalkForwardValidationReport)
            .where(
                PortfolioWalkForwardValidationReport.id == validation_id,
                PortfolioWalkForwardValidationReport.study_id == study_id,
            )
            .execution_options(populate_existing=True)
        )

    def validation_history(
        self, study_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[PortfolioWalkForwardValidationReport], int]:
        where = PortfolioWalkForwardValidationReport.study_id == study_id
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioWalkForwardValidationReport)
                .where(where)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PortfolioWalkForwardValidationReport)
                .where(where)
                .order_by(
                    PortfolioWalkForwardValidationReport.calculated_at.desc(),
                    PortfolioWalkForwardValidationReport.id.desc(),
                )
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            ).all()
        )
        return rows, total

    def window_validation_page(
        self,
        validation_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[PortfolioWalkForwardWindowValidation], int]:
        where = PortfolioWalkForwardWindowValidation.validation_id == validation_id
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(PortfolioWalkForwardWindowValidation)
                .where(where)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PortfolioWalkForwardWindowValidation)
                .where(where)
                .order_by(PortfolioWalkForwardWindowValidation.window_no)
                .limit(limit)
                .offset(offset)
                .execution_options(populate_existing=True)
            ).all()
        )
        return rows, total

    def stability(
        self, validation_id: uuid.UUID
    ) -> list[PortfolioWalkForwardParameterStability]:
        return list(
            self.db.scalars(
                select(PortfolioWalkForwardParameterStability)
                .where(
                    PortfolioWalkForwardParameterStability.validation_id
                    == validation_id
                )
                .order_by(
                    PortfolioWalkForwardParameterStability.parameter_name,
                    PortfolioWalkForwardParameterStability.parameter_value,
                )
                .execution_options(populate_existing=True)
            ).all()
        )
