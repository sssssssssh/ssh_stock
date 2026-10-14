from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from app.core.accounting_config import AccountingConfig
from app.core.config import get_settings
from app.core.paper_config import DecisionConfig, PaperPolicyConfig, PaperRiskConfig
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import ApproveProposal, RejectProposal
from app.domain.decision.risk import plan_order
from app.domain.portfolio import DailyPortfolioSnapshot, PositionState
from app.services.paper.account_state import FrozenPaperConfig
from pydantic import ValidationError


def config(**risk):
    settings = get_settings()
    return FrozenPaperConfig(
        policy=PaperPolicyConfig(risk=PaperRiskConfig(**risk)),
        execution=settings.execution_config,
        accounting=AccountingConfig.model_validate(settings.accounting_config.model_dump()),
        decision=DecisionConfig(),
    )


def inputs():
    return dict(
        candidate={
            "ts_code": "000001.SZ",
            "close": "10",
            "exchange": "SZSE",
            "market": "主板",
            "risk_codes": [],
            "industry_sector_id": 1,
            "primary_theme_code": None,
        },
        action="PROPOSE_BUY",
        weight=Decimal("0.08"),
        snapshot=DailyPortfolioSnapshot(
            date(2026, 10, 14), Decimal("1000000"), Decimal("1000000"), Decimal("1"), ()
        ),
        contexts={},
        pending=[],
        scheduled=date(2026, 10, 15),
        config=config(),
    )


@pytest.mark.parametrize("confirmed", [False, 1, "true", None])
def test_explicit_human_confirmation_required(confirmed):
    with pytest.raises(ValidationError):
        ApproveProposal(request_id="x", target_weight="0.08", confirmed=confirmed)


def test_weights_are_decimal_and_reject_reason_required():
    with pytest.raises(ValidationError):
        ApproveProposal(request_id="x", target_weight=0.08, confirmed=True)
    with pytest.raises(ValidationError):
        RejectProposal(request_id="x", reason=" ")
    assert ApproveProposal(
        request_id="x", target_weight="0.08", confirmed=True
    ).target_weight == Decimal("0.08")


def test_pure_approval_sizing_and_odd_lot_exit():
    values = inputs()
    plan = plan_order(**values)
    assert plan["quantity"] == 7900 and isinstance(plan["estimated_gross"], Decimal)
    position = PositionState("000001.SZ", 99, 99, Decimal("10"), Decimal("990"))
    values.update(
        action="PROPOSE_EXIT",
        weight=Decimal("0"),
        snapshot=replace(values["snapshot"], positions=(position,)),
    )
    assert plan_order(**values)["quantity"] == 99
    values.update(action="PROPOSE_REDUCE", weight=Decimal("0.0005"))
    with pytest.raises(PaperError):
        plan_order(**values)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("single", "SINGLE_WEIGHT_LIMIT"),
        ("empty_sell", "INSUFFICIENT_POSITION"),
        ("risk", "DECISION_RISK_BLOCKED"),
        ("cash", "CASH_BUFFER_LIMIT"),
        ("unknown_sector", "RISK_CONTEXT_UNAVAILABLE"),
        ("turnover", "DAILY_TURNOVER_LIMIT"),
    ],
)
def test_risk_preconditions_fail_closed(change, reason):
    values = inputs()
    if change == "single":
        values["weight"] = Decimal("0.11")
    elif change == "empty_sell":
        values.update(action="PROPOSE_EXIT", weight=Decimal("0"))
    elif change == "risk":
        values["candidate"]["risk_codes"] = ["WATCH_ONLY"]
    elif change == "cash":
        values["snapshot"] = replace(values["snapshot"], cash=Decimal("10000"))
    elif change == "unknown_sector":
        values["candidate"]["industry_sector_id"] = None
    else:
        values["config"] = config(max_daily_turnover=Decimal("0.01"))
    with pytest.raises(PaperError, match=reason):
        plan_order(**values)


@pytest.mark.parametrize(
    "limit,reason",
    [
        ("positions", "MAX_POSITIONS_LIMIT"),
        ("new", "MAX_NEW_POSITIONS_LIMIT"),
        ("gross", "GROSS_WEIGHT_LIMIT"),
        ("sector", "SECTOR_WEIGHT_LIMIT"),
        ("theme", "THEME_WEIGHT_LIMIT"),
        ("cash", "CASH_BUFFER_LIMIT"),
    ],
)
def test_pending_orders_reserve_shared_cash_and_concentration(limit, reason):
    values = inputs()
    other = {**values["candidate"], "ts_code": "600000.SH", "primary_theme_code": "theme"}
    values["candidate"]["primary_theme_code"] = "theme"
    values["pending"] = [
        {
            "ts_code": other["ts_code"],
            "side": "BUY",
            "target_weight": Decimal("0.08"),
            "data": {
                "candidate": other,
                "estimated_gross": "79000",
                "estimated_cash_required": "79030",
            },
        }
    ]
    limits = {
        "positions": {"max_positions": 1, "max_new_positions_per_day": 1},
        "new": {"max_new_positions_per_day": 1},
        "gross": {"min_cash_ratio": Decimal("0.9")},
        "sector": {"max_sector_weight": Decimal("0.1")},
        "theme": {"max_theme_weight": Decimal("0.1")},
        "cash": {},
    }
    values["config"] = config(**limits[limit])
    if limit == "cash":
        values["pending"][0]["data"]["estimated_cash_required"] = "950000"
    with pytest.raises(PaperError, match=reason):
        plan_order(**values)
