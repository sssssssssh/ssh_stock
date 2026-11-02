import json
from types import SimpleNamespace

import pytest

from scripts.business_candidate_observer import CandidateObserver, safe_plan
from scripts.business_quality_matrix import compare, p95


def test_plan_redacts_sql_parameters_conditions_and_nested_output():
    source = {
        "Query Text": "PRIVATE_SQL",
        "Query Parameters": "PRIVATE_PARAMS",
        "Plan": {
            "Node Type": "Nested Loop",
            "Filter": "PRIVATE_FILTER",
            "Plans": [
                {
                    "Node Type": "Index Scan",
                    "Relation Name": "data_publication_row",
                    "Index Cond": "PRIVATE_KEY",
                    "Actual Rows": 0,
                }
            ],
        },
    }
    result = safe_plan(source)
    assert "PRIVATE" not in json.dumps(result)
    assert result["Plan"]["Plans"][0]["Actual Rows"] == 0


def test_late_extended_protocol_plan_is_kept_until_control_sync():
    observer = CandidateObserver.__new__(CandidateObserver)
    observer.plan_target = None
    observer.plan_error = None
    observer.plans = []
    observer.connections = {}
    observer.plan_tables = set()
    observer.control_sql_calls = 0
    observer.metrics = {}
    observer.stack = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql):
            if sql == "SET auto_explain.log_min_duration=-1":
                observer.notice(
                    SimpleNamespace(
                        message_primary="duration: 0.100 ms plan:"
                        + json.dumps(
                            {
                                "Query Text": "WITH input_keys AS (...) SELECT ...",
                                "Plan": {"Node Type": "Result", "Actual Rows": 1},
                            }
                        )
                    )
                )

    raw = SimpleNamespace(
        cursor=Cursor,
        add_notice_handler=lambda *x: None,
        closed=False,
        info=SimpleNamespace(transaction_status=2),
    )
    db = SimpleNamespace(
        connection=lambda: SimpleNamespace(connection=SimpleNamespace(driver_connection=raw))
    )
    value = observer.first_lookup(
        lambda *x, **y: "ACTUAL_RESULT", (SimpleNamespace(db=db),), {}, "data_quality_daily"
    )
    assert value == "ACTUAL_RESULT"
    assert observer.plan_target is None
    assert len(observer.plans) == 1
    assert observer.plans[0]["capture"] == "ACTUAL_TIMED_LOOKUP"
    assert observer.control_sql_calls == 11


def test_missing_actual_plan_fails_closed_not_replayed():
    observer = CandidateObserver.__new__(CandidateObserver)
    observer.plan_target = "data_quality_daily"
    observer.plan_error = None
    observer.plans = []
    observer.notice(SimpleNamespace(message_primary="duration: x plan: not-json"))
    assert observer.plan_error == "BIZ02_ACTUAL_PLAN_INVALID"
    assert observer.plans == []


@pytest.mark.parametrize("field", ["dataset_sha256", "tables", "financial_identity", "runs"])
def test_matrix_never_accepts_missing_evidence(field):
    old = dict(
        dataset_sha256="a",
        tables={"factor": "b"},
        financial_identity={"analysis": "c"},
        windows={"start": "2025-01-01"},
        root_row_counts={"factor": 1},
        runs=[dict(job_status="SUCCESS", publication_state="PUBLISHED")],
    )
    assert all(compare(old, old).values())
    new = {**old, field: None}
    # Missing runs are invalid, not an empty successful observation.
    if field == "runs":
        new[field] = []
    assert not all(compare(old, new).values())


def test_p95_uses_inclusive_interpolation_not_best_run():
    assert p95([3, 1, 2]) == pytest.approx(2.9)
