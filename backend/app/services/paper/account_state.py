from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.accounting_config import AccountingConfig
from app.core.execution_config import ExecutionConfig
from app.core.paper_config import DecisionConfig, PaperPolicyConfig, PaperRuntimeConfig
from app.domain.decision.contracts import PaperError, content_hash
from app.domain.portfolio import DailyPortfolioSnapshot, PositionState
from app.models.paper import PaperDayRun, PaperLedgerEntry, PaperNavDaily, PaperPositionDaily
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.paper.records import verify_record
from app.services.portfolio.ledger_precision import money, ratio


@dataclass(frozen=True)
class FrozenPaperConfig:
    policy: PaperPolicyConfig
    execution: ExecutionConfig
    accounting: AccountingConfig
    decision: DecisionConfig


def frozen_config(account):
    verify_record(account)
    snapshot = account.config_snapshot_json
    if (
        snapshot.get("schema_version") != "m17-account-config-v1"
        or content_hash(snapshot) != account.config_hash
    ):
        raise PaperError("PAPER_CONFIG_INTEGRITY_ERROR")
    try:
        return FrozenPaperConfig(
            policy=PaperPolicyConfig.model_validate(snapshot["paper"]),
            execution=ExecutionConfig.model_validate(snapshot["execution"]),
            accounting=AccountingConfig.model_validate(snapshot["accounting"]),
            decision=DecisionConfig.model_validate(snapshot["decision"]),
        )
    except (KeyError, ValidationError) as exc:
        raise PaperError("PAPER_CONFIG_VERSION_UNSUPPORTED") from exc


def account_settings(account, settings):
    config = frozen_config(account)
    if account.config_snapshot_json.get("source_contract") != source_contract(settings):
        raise PaperError("PAPER_SOURCE_VERSION_DRIFT")
    return settings.model_copy(
        update={
            "paper_config": PaperRuntimeConfig(
                enabled=settings.paper_config.enabled,
                policy=config.policy,
                decision=config.decision,
            )
        }
    )


def source_contract(settings):
    return {
        "algo_version": settings.algo_version,
        "strategy_hash": analysis_strategy_hash(settings.strategy),
        "opportunity_hash": config_hash(settings.opportunity_config),
        "factor_version": FACTOR_CALC_VERSION,
        "state_version": TREND_CALC_VERSION,
        "status_version": TRADE_STATUS_CALC_VERSION,
        "opportunity_version": OPPORTUNITY_CALC_VERSION,
    }


def mark_day_review(db, account_id, day):
    for row in db.scalars(
        select(PaperDayRun)
        .where(
            PaperDayRun.account_id == account_id,
            PaperDayRun.trade_date == day,
            PaperDayRun.status == "SUCCESS",
        )
        .with_for_update()
    ):
        row.status, row.error_code = "REVIEW_REQUIRED", "PAPER_SOURCE_DRIFT"


def initial_entry(db, account):
    row = db.scalar(
        select(PaperLedgerEntry).where(
            PaperLedgerEntry.account_id == account.id,
            PaperLedgerEntry.owner_user_id == account.owner_user_id,
            PaperLedgerEntry.entry_type == "INITIAL_CASH",
        )
    )
    if row is None:
        raise PaperError("PAPER_INITIAL_LEDGER_MISSING")
    verify_record(row)
    if row.cash_delta != account.initial_cash or row.quantity_delta != 0:
        raise PaperError("PAPER_LEDGER_INCONSISTENT")
    return row


def load_close(db, account, day, *, require_completed=True):
    initial = initial_entry(db, account)
    if day < account.first_trade_date:
        return (
            DailyPortfolioSnapshot(
                trade_date=day,
                cash=account.initial_cash,
                total_assets=account.initial_cash,
                nav=Decimal("1"),
                positions=(),
            ),
            {},
            initial.record_hash,
        )
    nav = db.scalar(
        select(PaperNavDaily).where(
            PaperNavDaily.account_id == account.id,
            PaperNavDaily.owner_user_id == account.owner_user_id,
            PaperNavDaily.trade_date == day,
        )
    )
    if nav is None:
        raise PaperError("PAPER_ACCOUNT_SNAPSHOT_NOT_READY")
    if require_completed:
        completed = db.scalar(
            select(PaperDayRun).where(
                PaperDayRun.account_id == account.id,
                PaperDayRun.owner_user_id == account.owner_user_id,
                PaperDayRun.trade_date == day,
                PaperDayRun.phase == "DAY_COMPLETED",
            )
        )
        if completed is None or completed.status != "SUCCESS":
            raise PaperError("PAPER_ACCOUNT_SNAPSHOT_NOT_READY")
        verify_record(completed)
    verify_record(nav)
    rows = list(
        db.scalars(
            select(PaperPositionDaily)
            .where(
                PaperPositionDaily.account_id == account.id,
                PaperPositionDaily.owner_user_id == account.owner_user_id,
                PaperPositionDaily.trade_date == day,
            )
            .order_by(PaperPositionDaily.ts_code)
        )
    )
    positions, contexts = [], {}
    for row in rows:
        data = verify_record(row)
        if row.market_value != money(row.close_price * row.quantity):
            raise PaperError("PAPER_LEDGER_INCONSISTENT")
        if row.unrealized_pnl != money((row.close_price - row.avg_cost) * row.quantity):
            raise PaperError("PAPER_LEDGER_INCONSISTENT")
        positions.append(
            PositionState(
                ts_code=row.ts_code,
                quantity=row.quantity,
                available_quantity=row.available_quantity,
                avg_cost=row.avg_cost,
                market_value=row.market_value,
                close_price=row.close_price,
                unrealized_pnl=row.unrealized_pnl,
                realized_pnl=row.realized_pnl,
                valuation_source=row.valuation_source,
                adj_factor=row.adj_factor,
            )
        )
        contexts[row.ts_code] = data["context"]
    value = sum((p.market_value for p in positions), Decimal("0"))
    ledger_cash = db.scalar(
        select(func.sum(PaperLedgerEntry.cash_delta)).where(
            PaperLedgerEntry.account_id == account.id,
            PaperLedgerEntry.owner_user_id == account.owner_user_id,
            (PaperLedgerEntry.trade_date <= day) | (PaperLedgerEntry.entry_type == "INITIAL_CASH"),
        )
    )
    quantities = dict(
        db.execute(
            select(PaperLedgerEntry.instrument, func.sum(PaperLedgerEntry.quantity_delta))
            .where(
                PaperLedgerEntry.account_id == account.id,
                PaperLedgerEntry.owner_user_id == account.owner_user_id,
                PaperLedgerEntry.trade_date <= day,
                PaperLedgerEntry.entry_type == "FILL",
            )
            .group_by(PaperLedgerEntry.instrument)
        ).all()
    )
    if (
        len(rows) != nav.position_count
        or value != nav.market_value
        or nav.cash != ledger_cash
        or nav.total_assets != nav.cash + value
        or nav.nav != ratio(nav.total_assets / account.initial_cash)
        or {p.ts_code: p.quantity for p in positions}
        != {code: qty for code, qty in quantities.items() if qty}
    ):
        raise PaperError("PAPER_LEDGER_INCONSISTENT")
    return (
        DailyPortfolioSnapshot(
            trade_date=day,
            cash=nav.cash,
            total_assets=nav.total_assets,
            nav=nav.nav,
            positions=tuple(positions),
            market_value=nav.market_value,
            trading_cost=nav.trading_cost,
        ),
        contexts,
        content_hash([nav.record_hash, [row.record_hash for row in rows]]),
    )
