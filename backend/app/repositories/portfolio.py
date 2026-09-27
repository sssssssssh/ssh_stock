import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioPositionDaily,
)


class PortfolioRepository:
    """Persistence operations only; portfolio and execution rules live elsewhere."""

    _RUN_UPDATE_FIELDS = {
        "status",
        "job_id",
        "result_summary",
        "error_message",
        "started_at",
        "finished_at",
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, run: PortfolioBacktestRun) -> PortfolioBacktestRun:
        self.db.add(run)
        self.db.flush()
        return run

    def get_run(self, run_id: uuid.UUID) -> PortfolioBacktestRun | None:
        return self.db.get(PortfolioBacktestRun, run_id)

    def list_runs(self, *, limit: int = 50, offset: int = 0) -> list[PortfolioBacktestRun]:
        return list(
            self.db.execute(
                select(PortfolioBacktestRun)
                .order_by(PortfolioBacktestRun.created_at.desc(), PortfolioBacktestRun.id)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )

    def update_run(self, run_id: uuid.UUID, **values: Any) -> PortfolioBacktestRun:
        unknown = set(values) - self._RUN_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported backtest run fields: {sorted(unknown)}")
        run = self.get_run(run_id)
        if run is None:
            raise LookupError(f"portfolio backtest run not found: {run_id}")
        for name, value in values.items():
            setattr(run, name, value)
        self.db.flush()
        return run

    def insert_orders(self, run_id: uuid.UUID, rows: Sequence[PortfolioOrder]) -> None:
        self._assert_run_id(run_id, rows)
        self.db.add_all(rows)
        self.db.flush()

    def list_orders(self, run_id: uuid.UUID) -> list[PortfolioOrder]:
        return list(
            self.db.execute(
                select(PortfolioOrder)
                .where(PortfolioOrder.run_id == run_id)
                .order_by(
                    PortfolioOrder.scheduled_trade_date,
                    PortfolioOrder.ts_code,
                    PortfolioOrder.id,
                )
            )
            .scalars()
            .all()
        )

    def insert_fills(self, run_id: uuid.UUID, rows: Sequence[PortfolioFill]) -> None:
        self._assert_run_id(run_id, rows)
        self.db.add_all(rows)
        self.db.flush()

    def list_fills(self, run_id: uuid.UUID) -> list[PortfolioFill]:
        return list(
            self.db.execute(
                select(PortfolioFill)
                .where(PortfolioFill.run_id == run_id)
                .order_by(PortfolioFill.trade_date, PortfolioFill.ts_code, PortfolioFill.id)
            )
            .scalars()
            .all()
        )

    def replace_position_snapshot(
        self,
        run_id: uuid.UUID,
        trade_date: date,
        rows: Sequence[PortfolioPositionDaily],
    ) -> None:
        self._assert_run_id(run_id, rows)
        if any(row.trade_date != trade_date for row in rows):
            raise ValueError("position snapshot trade_date mismatch")
        self.db.execute(
            delete(PortfolioPositionDaily).where(
                PortfolioPositionDaily.run_id == run_id,
                PortfolioPositionDaily.trade_date == trade_date,
            )
        )
        self.db.add_all(rows)
        self.db.flush()

    def list_positions(self, run_id: uuid.UUID) -> list[PortfolioPositionDaily]:
        return list(
            self.db.execute(
                select(PortfolioPositionDaily)
                .where(PortfolioPositionDaily.run_id == run_id)
                .order_by(
                    PortfolioPositionDaily.trade_date,
                    PortfolioPositionDaily.ts_code,
                )
            )
            .scalars()
            .all()
        )

    def upsert_nav(self, run_id: uuid.UUID, row: PortfolioNavDaily) -> PortfolioNavDaily:
        self._assert_run_id(run_id, [row])
        current = self.db.get(PortfolioNavDaily, (run_id, row.trade_date))
        if current is None:
            self.db.add(row)
            current = row
        else:
            for column in PortfolioNavDaily.__table__.columns:
                if column.name not in {"run_id", "trade_date", "created_at"}:
                    setattr(current, column.name, getattr(row, column.name))
        self.db.flush()
        return current

    def list_nav(self, run_id: uuid.UUID) -> list[PortfolioNavDaily]:
        return list(
            self.db.execute(
                select(PortfolioNavDaily)
                .where(PortfolioNavDaily.run_id == run_id)
                .order_by(PortfolioNavDaily.trade_date)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _assert_run_id(run_id: uuid.UUID, rows: Sequence[Any]) -> None:
        if any(row.run_id != run_id for row in rows):
            raise ValueError("portfolio persistence row run_id mismatch")
