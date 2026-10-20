import pytest

from scripts.ab_read_profile_summary_v14_a4 import compact_run, quantiles, summarize, verify_monthly
from scripts.ab_read_profile_v14_a4 import alternating_orders, source_receipt, sql_phase


def test_a4_diagnostic_freezes_production_sources():
    assert len(source_receipt()) == 7


def test_a4_orders_are_serial_balanced_not_variant_grouped():
    assert alternating_orders(3) == [
        ("q0", "q1", "q2"), ("q1", "q2", "q0"), ("q2", "q0", "q1")]


@pytest.mark.parametrize("sql,phase", [
    ("LOCK TABLE public.data_publication_row IN SHARE MODE", "T2_lock_acquire"),
    ("SELECT string_agg(encode(sha256(x)))", "T3_fingerprint_sql"),
    ("SELECT EXISTS(SELECT 1 FROM public.data_publication_row s)", "T4_candidate_validation_sql"),
    ("SELECT * FROM trade_calendar", "T1_calendar_sql"),
    ("SELECT * FROM stock_trade_status_daily", "T5_declare"),
    ("SELECT * FROM job_run", "other_sql"),
])
def test_a4_sql_classification_is_observation_only(sql, phase):
    assert sql_phase(sql) == phase


def test_a4_quantiles_preserve_slow_samples():
    result = quantiles([1, 100, 2])
    assert result["raw"] == [1, 100, 2]
    assert result["p50"] == 2
    assert result["p95"] > 90
    assert quantiles([]) is None


def test_a4_partial_receipt_never_passes_summary(tmp_path):
    receipt = tmp_path / "failed.json"
    receipt.write_text('{"failure":{"failure_type":"JobCancelled"}}')
    with pytest.raises(ValueError, match="A4_INCOMPLETE_BASELINE_NOT_ACCEPTED"):
        summarize(receipt)


@pytest.mark.parametrize("closed,rows", [(False, 1), (True, 0)])
def test_a4_unclosed_or_partial_cursor_never_passes(closed, rows):
    run = {"before": {}, "after": {}, "rows": 1, "metrics": [], "events": [],
           "cursors": [{"closed": closed, "fetches": [{"rows": rows, "requested": 5000}]}]}
    with pytest.raises(ValueError, match="A4_INCOMPLETE_OR_UNCLOSED_CURSOR"):
        compact_run(run)


def test_a4_monthly_partial_or_changed_results_cannot_pass():
    runs = [{"variant": variant, "chunk_start": "2025-01-01", "chunk_end": "2025-01-31",
             "rows": 1, "hash": "golden", "dtypes": {"is_st": "bool"}}
            for variant in ("q0", "q1", "q2")]
    assert verify_monthly(runs) == {"chunks": 1, "status": "PASS"}
    with pytest.raises(ValueError, match="A4_INCOMPLETE_MONTHLY_COMPARISON"):
        verify_monthly(runs[:2])
    runs[-1]["hash"] = "different"
    with pytest.raises(ValueError, match="A4_MONTHLY_GOLDEN_MISMATCH"):
        verify_monthly(runs)
