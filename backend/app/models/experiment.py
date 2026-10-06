import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class PortfolioExperiment(Base):
    __tablename__ = "portfolio_experiment"
    __table_args__ = (
        CheckConstraint(
            "experiment_version = 'experiment_v1'",
            name=conv("ck_portfolio_experiment_version"),
        ),
        CheckConstraint(
            "search_method = 'GRID'",
            name=conv("ck_portfolio_experiment_search_method"),
        ),
        CheckConstraint(
            "end_date >= start_date", name=conv("ck_portfolio_experiment_dates")
        ),
        CheckConstraint(
            "initial_cash > 0", name=conv("ck_portfolio_experiment_initial_cash")
        ),
        CheckConstraint(
            "trial_count > 0", name=conv("ck_portfolio_experiment_trial_count")
        ),
        Index("idx_portfolio_experiment_definition_hash", "definition_hash"),
        Index("idx_portfolio_experiment_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(128))
    experiment_version: Mapped[str] = mapped_column(String(32), nullable=False)
    search_method: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_space_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter_space: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    base_algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_source_strategy_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    base_opportunity_calc_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    base_opportunity_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    base_portfolio_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_portfolio_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_execution_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_execution_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_accounting_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_accounting_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_backtest_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    base_config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PortfolioExperimentTrial(Base):
    __tablename__ = "portfolio_experiment_trial"
    __table_args__ = (
        CheckConstraint(
            "trial_no > 0", name=conv("ck_portfolio_experiment_trial_number")
        ),
        UniqueConstraint(
            "experiment_id",
            "trial_no",
            name=conv("uq_portfolio_experiment_trial_number"),
        ),
        UniqueConstraint(
            "experiment_id",
            "parameter_hash",
            name=conv("uq_portfolio_experiment_trial_parameter"),
        ),
        UniqueConstraint(
            "run_id", name=conv("uq_portfolio_experiment_trial_run_id")
        ),
        UniqueConstraint(
            "id",
            "experiment_id",
            name=conv("uq_portfolio_experiment_trial_owner"),
        ),
        Index("idx_portfolio_experiment_trial_experiment", "experiment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_experiment.id", ondelete="CASCADE"),
        nullable=False,
    )
    trial_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parameter_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parameter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    portfolio_config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    portfolio_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
