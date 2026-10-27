"""Real PG17 scope adapter and interrupted group lifecycle, not performance claims."""

import os
from types import SimpleNamespace

import pytest

from scripts import ab_read_experiment_v14_a4_2 as experiment
from scripts.a42_artifacts import JobCancelled, ScopedOutput, Writer, isolation
from scripts.a42_ci_contract import VARIANTS, Group
from scripts.a42_gate_io import load_groups
from scripts.a42_receipt_contract import validate_set


def exercise(tmp_path, monkeypatch, groups):
    # Tests may select a subset to exercise the adapter. The production scope CLI
    # has no override for counts, repeats or required keys; complete CI uses all.
    from scripts.business_source_contract import bind_current_diagnostic_contract

    bind_current_diagnostic_contract(monkeypatch)
    for name in ("DATABASE_URL", "TUSHARE_TOKEN", "LLM_ENABLED", "AB_MERGE_READ_ENABLED"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    from loguru import logger

    monkeypatch.setattr(logger, "remove", lambda *args, **kwargs:None)
    writer = Writer(tmp_path/"manifest.json", "pg17-scope-integration", groups, minutes=120)
    writer.manifest.update(isolation())
    output = ScopedOutput(writer, laboratory_sources=experiment.laboratory_sources())
    args = SimpleNamespace(shard=True, active_groups=groups, output=writer.path,
        public_rows=10000, candidate_rows=5253, other_rows=10895, tombstones=1,
        coverage="partial", variants=tuple(sorted({g.variant for g in groups})),
        repeats=3, readers=0, reader_pause=5, cursor_fractions=["0.1", "1.0"],
        monthly=False, window_matrix=False, plans=False, container=os.environ.get("A421_CONTAINER"))
    try:
        experiment.run(args, output)
    except BaseException as error:
        writer.fail(error)
        raise
    return writer


def test_real_scoped_fetch_windows_month_root_and_actual_plan(tmp_path, monkeypatch):
    groups = {Group("10k", "read", v, "0.1", "full", repeat=0) for v in VARIANTS}
    groups |= {Group("10k", "read", "S3", "0.1", "window_matrix", d, 0)
               for d in (None,1,3,5,10,20)}
    groups |= {Group("10k", "read", "Q1_CURRENT", "0.1", f"month_{m}", repeat=0)
               for m in (1,2,3)}
    groups |= {Group("10k", "plan", "Q1_CURRENT", "0.1", "full")}
    writer = exercise(tmp_path, monkeypatch, groups)
    receipts = load_groups(writer.path, writer.manifest)
    validate_set(receipts, groups, head=writer.manifest["head_sha"],
        attempt=writer.manifest["attempt"], job_id=writer.manifest["job_id"],
        model_hash=writer.manifest["model_hash"])
    writer.finish()
    assert writer.manifest["completed_groups"] == 20
    plan = next(r for r in receipts if r["group"]["kind"]=="plan")
    assert plan["result"]["actual_cursor_untimed"][0]["Plan"]["Actual Rows"] > 0
    assert plan["result"]["log_parameter_max_length"] == 0
    from scripts.a42_artifacts import contains_query_parameters

    assert not contains_query_parameters(plan["result"])


def test_cancel_after_real_complete_read_keeps_only_that_evidence(tmp_path, monkeypatch):
    original, calls = experiment.measure, []
    def interrupted(*args, **kwargs):
        calls.append(True)
        if len(calls)==2:
            raise JobCancelled()
        return original(*args, **kwargs)
    monkeypatch.setattr(experiment, "measure", interrupted)
    groups = {Group("10k", "read", "Q1_CURRENT", "0.1", "full", repeat=r) for r in (0,1)}
    with pytest.raises(JobCancelled):
        exercise(tmp_path, monkeypatch, groups)
    import json

    manifest = json.loads((tmp_path/"manifest.json").read_text())
    assert manifest["completed_groups"] == 1 and manifest["status"] == "INCOMPLETE"
    assert len(list(tmp_path.glob("*.json.gz"))) == 1


def test_actual_plan_sql_timeout_keeps_partial_native_profile_and_completed_read(
    tmp_path, monkeypatch
):
    # Fault injection only, never used by the performance CLI. Real 57014 in a
    # named FETCH; do not decrease the actual experiment's 300s SQL budget.
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    def timeout_probe(db, statements):
        db.execute(text("SET LOCAL statement_timeout='1ms'"))
        with db.execute(text("SELECT i,pg_sleep(0.01) FROM generate_series(1,1000) i")
                        .execution_options(yield_per=5000)) as result:
            for _ in result.partitions(5000):
                pass
        pytest.fail("real PostgreSQL timeout required")
    monkeypatch.setattr(experiment, "cursor_plans_without_parameters", timeout_probe)
    groups = {Group("10k", "read", "Q0_SAFETY_EQUIVALENT", "0.1", "full", repeat=0),
              Group("10k", "plan", "Q1_CURRENT", "0.1", "full")}
    with pytest.raises(OperationalError):
        exercise(tmp_path, monkeypatch, groups)
    import gzip
    import json

    manifest = json.loads((tmp_path/"manifest.json").read_text())
    assert manifest["status"] == "INCOMPLETE" and manifest["completed_groups"] == 1
    assert manifest["sqlstate"] == "57014" and manifest["failed_phase"] == "untimed_actual_plans"
    partial = json.loads(gzip.decompress(next(tmp_path.glob("*.incomplete.json.gz")).read_bytes()))
    assert partial["status"] == "INCOMPLETE" and partial["completed_groups"] == 0
    assert partial["sqlstate"] == "57014" and partial["partial_profile"]["cursors"]
    assert not partial["partial_profile"]["cursors"][0].get("until_eof_seconds")
