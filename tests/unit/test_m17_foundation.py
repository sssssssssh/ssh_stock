import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from itertools import product

import pytest
from app.core.config import get_settings
from app.core.paper_config import PaperPolicyConfig, PaperRiskConfig, PaperRuntimeConfig
from app.domain.decision.contracts import (
    ACCOUNT_TRANSITIONS,
    ORDER_TRANSITIONS,
    PROPOSAL_TRANSITIONS,
    PaperError,
    canonical_json,
    checked_snapshot,
    content_hash,
    require_transition,
    stable_id,
)
from app.models.paper import (
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
)
from app.services.portfolio.application import PortfolioApplicationService
from pydantic import ValidationError
from sqlalchemy import Float, Numeric

TRANSITIONS = {
    "account": ACCOUNT_TRANSITIONS,
    "proposal": PROPOSAL_TRANSITIONS,
    "order": ORDER_TRANSITIONS,
}


@pytest.mark.parametrize(
    "kind,before,after",
    [
        (kind, before, after)
        for kind, mapping in TRANSITIONS.items()
        for before, after in product(mapping, repeat=2)
    ],
)
def test_every_state_transition(kind, before, after):
    if after in TRANSITIONS[kind][before]:
        require_transition(kind, before, after)
    else:
        with pytest.raises(PaperError, match="PAPER_INVALID_STATE_TRANSITION"):
            require_transition(kind, before, after)


def test_unknown_states_and_domains_fail_closed():
    for value in (
        ("unknown", "CREATED", "ACTIVE"),
        ("account", "LIVE", "ACTIVE"),
        ("order", "ORDER_PENDING", "EXECUTED"),
    ):
        with pytest.raises(PaperError):
            require_transition(*value)


def test_default_config_is_disabled_and_manual_only():
    config = get_settings().paper_config
    assert not config.enabled
    assert not config.auto_advance
    assert not config.auto_approve
    assert not config.decision.daily_observation_enabled
    assert config.policy.mode == "PAPER"
    assert config.policy.approval_mode == "MANUAL_CONFIRM"
    assert config.policy.risk.max_single_position_weight == Decimal("0.10")


@pytest.mark.parametrize(
    "payload",
    [
        {"auto_approve": True},
        {"enabled": "false"},
        {"auto_advance": True},
        {"enabled": False, "decision": {"daily_observation_enabled": True}},
        {"unknown": True},
        {"policy": {"mode": "LIVE"}},
        {"policy": {"approval_mode": "AUTO"}},
        {"policy": {"external_url": "https://invalid"}},
    ],
)
def test_runtime_config_rejects_unsafe_modes(payload):
    with pytest.raises(ValidationError):
        PaperRuntimeConfig.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"max_positions": 0},
        {"max_positions": 1, "max_new_positions_per_day": 2},
        {"max_single_position_weight": "1.01"},
        {"min_cash_ratio": "1"},
        {"min_cash_ratio": "0.95", "max_single_position_weight": "0.1"},
        {"max_sector_weight": "NaN"},
        {"max_theme_weight": "Infinity"},
        {"max_daily_turnover": "-1"},
        {"max_daily_turnover": "2.1"},
    ],
)
def test_risk_config_fails_closed(payload):
    with pytest.raises(ValidationError):
        PaperRiskConfig.model_validate(payload)


def test_policy_is_frozen_and_hash_is_deterministic():
    config = PaperPolicyConfig()
    with pytest.raises(ValidationError):
        config.mode = "LIVE"
    raw = config.model_dump(mode="python")
    assert content_hash(raw) == content_hash(dict(reversed(list(raw.items()))))
    assert content_hash(raw) != content_hash({**raw, "version": "future-policy"})


def test_canonical_money_dates_and_utc_are_context_independent():
    value = Decimal("123456789012345678901234567890.123400")
    with localcontext() as context:
        context.prec = 6
        assert canonical_json(value) == '"123456789012345678901234567890.1234"'
    assert canonical_json(Decimal("-0.000")) == '"0"'
    assert content_hash(Decimal("1.0000")) == content_hash(Decimal("1"))
    assert canonical_json(date(2026, 10, 14)) == '"2026-10-14"'
    instant = datetime(2026, 10, 14, 8, tzinfo=timezone(timedelta(hours=8)))
    assert content_hash(instant) == content_hash(instant.astimezone(UTC))


@pytest.mark.parametrize(
    "value",
    [
        0.1,
        float("nan"),
        Decimal("NaN"),
        Decimal("Infinity"),
        datetime(2026, 10, 14),
        {1: "not-string"},
        object(),
    ],
)
def test_canonical_rejects_ambiguous_financial_inputs(value):
    with pytest.raises(PaperError):
        canonical_json(value)


def test_snapshot_schema_limits_and_stable_owner_scoped_ids():
    snapshot, digest = checked_snapshot({"schema_version": "m17-test-v1", "amount": Decimal("1")})
    assert snapshot["amount"] == "1"
    assert digest == content_hash(snapshot)
    with pytest.raises(PaperError, match="SCHEMA_VERSION_REQUIRED"):
        checked_snapshot({"amount": 1})
    with pytest.raises(PaperError, match="SNAPSHOT_TOO_LARGE"):
        checked_snapshot({"schema_version": "v1", "text": "x" * 100}, limit_bytes=20)
    owner, other = uuid.uuid4(), uuid.uuid4()
    assert stable_id(owner, "account", "request") == stable_id(owner, "account", "request")
    assert stable_id(owner, "account", "request") != stable_id(other, "account", "request")
    assert stable_id(owner, "account", "request") != stable_id(owner, "order", "request")


def test_paper_models_are_independent_and_numeric_only():
    for model in (
        PaperAccount,
        DecisionObservation,
        DecisionProposal,
        PaperFill,
        PaperLedgerEntry,
        PaperNavDaily,
    ):
        assert all(not isinstance(column.type, Float) for column in model.__table__.columns)
        assert all(
            not element.target_fullname.startswith("portfolio_")
            for constraint in model.__table__.foreign_key_constraints
            for element in constraint.elements
        )
    assert isinstance(PaperFill.__table__.c.simulated_price.type, Numeric)
    settings = get_settings().model_copy(
        update={
            "portfolio_config": get_settings().portfolio_config.model_copy(
                update={"account_mode": "PAPER"}
            )
        }
    )
    with pytest.raises(ValueError, match="only supports BACKTEST"):
        PortfolioApplicationService(object(), settings)
