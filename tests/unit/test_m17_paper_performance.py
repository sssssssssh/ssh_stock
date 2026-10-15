from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.domain.decision.contracts import PaperError, canonical_json
from app.domain.decision.performance import decision_metrics, execution_metrics, frozen_performance
from app.services.paper.performance import PaperPerformance


def row(day, nav, benchmark="1"):
    return {
        "trade_date": day,
        "nav": nav,
        "cash": "1000",
        "market_value": "0",
        "benchmark_nav": benchmark,
        "trading_cost": "5",
        "data": {"turnover": "0.1"},
    }


def test_continuous_decimal_nav_and_drawdown():
    rows = [row("2026-10-14", "1.1"), row("2026-10-15", "0.99")]
    result = frozen_performance(
        rows, expected_dates=[r["trade_date"] for r in rows], initial_cash=Decimal("1000")
    )
    assert result["continuous"]
    assert result["cumulative_return"] == Decimal("-0.01")
    assert result["maximum_drawdown"] == Decimal("-0.10")
    assert result["series"][1]["daily_return"] == Decimal("-0.10")
    assert result["cumulative_cost"] == "10" and result["cumulative_turnover"] == "0.2"


def test_gap_inserts_null_not_interpolated_value():
    rows = [row("2026-10-14", "1"), row("2026-10-16", "1.1")]
    result = frozen_performance(
        rows,
        expected_dates=["2026-10-14", "2026-10-15", "2026-10-16"],
        initial_cash=Decimal("1000"),
    )
    assert not result["continuous"] and result["maximum_drawdown"] is None
    assert result["cumulative_return"] is None
    assert result["series"][1]["nav"] is None and not result["series"][1]["valid"]
    assert all(r["daily_return"] is None for r in result["series"])


def test_review_required_and_missing_benchmark_do_not_fake_comparisons():
    rows = [row("2026-10-14", "1.1", None)]
    result = frozen_performance(
        rows,
        expected_dates=["2026-10-14"],
        initial_cash=Decimal("1000"),
        invalid_dates={"2026-10-14"},
    )
    assert not result["continuous"] and not result["series"][0]["valid"]
    assert result["benchmark_status"] == "BENCHMARK_UNAVAILABLE"
    assert result["series"][0]["benchmark_nav"] is None


def test_financial_hash_and_denominator_are_frozen_and_reproducible():
    rows = [row("2026-10-14", "1.1")]
    arguments = {"expected_dates": ["2026-10-14"], "initial_cash": Decimal("1000")}
    result = frozen_performance(rows, **arguments)
    assert result["source_hash"] == frozen_performance(rows, **arguments)["source_hash"]
    assert result["date_range"] == ["2026-10-14", "2026-10-14"]
    assert result["denominator"] == {
        "initial_cash": "1000",
        "settled_days": 1,
        "expected_days": 1,
    }
    changed = frozen_performance([row("2026-10-14", "0.9")], **arguments)
    assert changed["source_hash"] != result["source_hash"]


def test_decision_approval_denominator_includes_watch_without_claiming_fills():
    proposals = [
        {"signal_date": "2026-10-14", "state": "APPROVED", "action": "PROPOSE_BUY"},
        {"signal_date": "2026-10-15", "state": "PENDING_REVIEW", "action": "WATCH"},
        {"signal_date": "2026-10-15", "state": "REJECTED", "action": "PROPOSE_EXIT"},
        {"signal_date": "2026-10-16", "state": "EXPIRED", "action": "PROPOSE_BUY"},
    ]
    result = decision_metrics(proposals)
    assert result["approval_rate"] == Decimal("0.25")
    assert result["denominator"] == {"legal_proposals": 4}
    assert result["counts"]["EXPIRED"] == result["actions"]["WATCH"] == 1
    assert result["date_range"] == ["2026-10-14", "2026-10-16"]
    assert decision_metrics([])["approval_rate"] is None
    proposals[1]["state"] = "REJECTED"
    assert decision_metrics(proposals)["source_hash"] != result["source_hash"]


def order(status, reason=None, amount="1234.5678"):
    return {
        "status": status,
        "reason_code": reason,
        "estimated_gross": amount,
        "scheduled_date": "2026-10-15",
        "stage": "TREND",
        "record_hash": "a" * 64,
    }


def test_execution_counts_and_blocked_sizing_amounts_never_imply_real_pnl():
    orders = [
        order("FILLED"),
        order("SKIPPED", "PRICE_MISSING"),
        order("EXPIRED", "PRICE_MISSING", None),
        order("ORDER_PENDING"),
        order("CANCELLED", "ACCOUNT_PAUSED"),
    ]
    result = execution_metrics(orders)
    assert result["reached_orders"] == result["denominator"]["reached_legal_orders"] == 3
    assert result["hypothetical_fill_rate"] == Decimal("0.33333333")
    assert result["blocked_reasons"] == {"PRICE_MISSING": 2}
    assert result["blocked_amounts"]["PRICE_MISSING"] == {
        "orders": 2,
        "known_amount_orders": 1,
        "estimated_gross_amount": Decimal("1234.5678"),
    }
    assert '"estimated_gross_amount":"1234.5678"' in canonical_json(result)
    assert (
        execution_metrics([order("SKIPPED", "PRICE_MISSING", None)])["blocked_amounts"][
            "PRICE_MISSING"
        ]["estimated_gross_amount"]
        is None
    )
    assert execution_metrics([])["hypothetical_fill_rate"] is None


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1"])
def test_invalid_blocked_amount_fails_closed(amount):
    with pytest.raises(PaperError, match="PAPER_RECORD_INTEGRITY_ERROR"):
        execution_metrics([order("SKIPPED", "PRICE_MISSING", amount)])


def test_proposal_state_changes_hash_without_changing_frozen_record_hash():
    proposal = {
        "record_hash": "a" * 64,
        "state": "PENDING_REVIEW",
        "version": 1,
        "action": "PROPOSE_BUY",
        "signal_date": "2026-10-14",
    }
    before = decision_metrics([proposal])
    approved = {**proposal, "state": "APPROVED", "version": 2}
    after = decision_metrics([approved])
    assert approved["record_hash"] == proposal["record_hash"]
    assert after["source_hash"] != before["source_hash"]
    assert before["approval_rate"] == 0 and after["approval_rate"] == 1


@pytest.mark.parametrize(
    "before_status,after_status", [("SKIPPED", "FILLED"), ("ORDER_PENDING", "CANCELLED")]
)
def test_order_state_changes_hash_even_outside_execution_denominator(before_status, after_status):
    before_order, after_order = order(before_status), order(after_status)
    before, after = execution_metrics([before_order]), execution_metrics([after_order])
    assert before_order["record_hash"] == after_order["record_hash"]
    assert before["source_hash"] != after["source_hash"]
    if before_status == "ORDER_PENDING":
        assert before["reached_orders"] == after["reached_orders"] == 0
        assert before["hypothetical_fill_rate"] is after["hypothetical_fill_rate"] is None


def test_completion_head_state_changes_evaluation_hash_but_preserves_frozen_nav():
    rows = [row("2026-10-14", "1.1")]
    arguments = {"expected_dates": ["2026-10-14"], "initial_cash": Decimal("1000")}
    head = {"record_hash": "a" * 64, "status": "SUCCESS"}
    before = frozen_performance(rows, completion_heads=[head], **arguments)
    after = frozen_performance(
        rows,
        completion_heads=[{**head, "status": "REVIEW_REQUIRED"}],
        invalid_dates={"2026-10-14"},
        **arguments,
    )
    status_only = frozen_performance(
        rows,
        completion_heads=[{**head, "status": "REVIEW_REQUIRED"}],
        **arguments,
    )
    assert status_only["source_hash"] != before["source_hash"]
    assert after["source_hash"] != before["source_hash"]
    assert after["latest"] == before["latest"]
    assert after["cumulative_return"] is after["maximum_drawdown"] is None


@pytest.mark.parametrize("table", range(7))
@pytest.mark.parametrize("limit", ["rows", "bytes"])
def test_capacity_refuses_before_loading_any_history_or_calendar(table, limit):
    byte_budget = 1234

    class Database:
        calls = 0

        def execute(self, statement):
            self.calls += 1
            counts = [0] * 7
            if limit == "rows":
                assert self.calls == 1, "row limit must fail before examining JSON sizes"
                counts[table] = 101
            elif self.calls == 2:
                counts[table] = byte_budget + 1
            return SimpleNamespace(one=lambda: counts)

        def scalar(self, statement):
            pytest.fail("capacity must reject before reading the calendar")

        def scalars(self, statement):
            pytest.fail("capacity must reject before loading historical JSON")

    settings = SimpleNamespace(
        paper_config=SimpleNamespace(
            decision=SimpleNamespace(max_source_rows=100),
            max_history_bytes=byte_budget,
        )
    )
    with pytest.raises(PaperError, match="PAPER_HISTORY_CAPACITY_EXCEEDED"):
        PaperPerformance(Database(), settings)._preflight(
            "owner", SimpleNamespace(id="account", first_trade_date="2026-10-14")
        )
