from types import SimpleNamespace

import pytest
from app.services.agent.report.render import render_comparison


def comparison_view():
    return SimpleNamespace(
        state="COMPARABLE",
        policy_version="m16.6-report-comparison-v4",
        left_report_id="left",
        right_report_id="right",
        left_snapshot_hash="a" * 64,
        right_snapshot_hash="b" * 64,
        reason_codes=[],
        display_safety={"legacy_policy": False, "delta_allowed": True},
        result={"facts": [{"delta": "AUDIT_SECRET"}]},
        display_result={
            "comparison_mode": "WINDOW_DEGRADATION",
            "comparison_permissions": {"allowed": True},
            "facts": [
                {
                    "metric_key": "annualized_return",
                    "left": "20",
                    "right": "8",
                    "delta": "12.345678",
                    "pair_status": "COMPARABLE",
                    "formula": "TRAIN_MINUS_OOS",
                    "comparison_permission": {"allowed": True},
                    "left_fact": {"metric_identity": {"unit": "percent", "sample_role": "TRAIN"}},
                    "right_fact": {"metric_identity": {"unit": "percent", "sample_role": "OOS"}},
                }
            ],
        },
    )


@pytest.mark.parametrize("fault", ["global", "pair", "formula", "legacy", "state", "audit-only"])
def test_comparison_export_never_uses_unlicensed_delta_or_audit_fallback(fault):
    view = comparison_view()
    if fault == "global":
        view.display_result["comparison_permissions"]["allowed"] = False
    elif fault == "pair":
        view.display_result["facts"][0]["comparison_permission"]["allowed"] = False
    elif fault == "formula":
        view.display_result["facts"][0]["formula"] = "UNRECOGNIZED"
    elif fault == "legacy":
        view.policy_version = "m16.4-report-comparison-v1"
    elif fault == "state":
        view.state = "CONTEXT_REQUIRED"
    else:
        view.display_result = None
    for export_format in ("markdown", "html"):
        content = render_comparison(view, export_format)
        assert "12.345678" not in content
        assert "AUDIT_SECRET" not in content


def test_comparison_export_names_percentage_points_and_html_escapes_source_content():
    view = comparison_view()
    view.display_result["sample_context"] = {"note": "<script>window.__xss=true</script>"}
    markdown = render_comparison(view, "markdown")
    assert "百分点" in markdown and "TRAIN_MINUS_OOS" in markdown
    html = render_comparison(view, "html")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
