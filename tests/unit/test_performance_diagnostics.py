import json
from types import SimpleNamespace

import pytest
from app.services.performance_diagnostics import Trace, active_span, active_trace, span, terminal
from app.services.performance_sql_diagnostics import SQLObserver, fingerprint
from sqlalchemy import create_engine, text

from scripts.performance_diagnostics_report import interval_union_ms, summary


@pytest.fixture
def trace():
    value = Trace("synthetic-task", source={"commit_sha": "a" * 40})
    token = active_trace.set(value)
    yield value
    active_trace.reset(token)


def test_lifecycle_and_parent(trace, tmp_path):
    with span("factor.compute"):
        with span("data.transform"):
            pass
    terminal("SUCCESS")
    path = trace.flush(tmp_path)
    report = json.loads(path.read_text())
    child, parent = report["stages"]
    assert child["parent_span_id"] == parent["span_id"]
    assert all(s["duration_ms"] >= 0 for s in report["stages"])
    assert report["status"] == "success"
    assert active_span.get() is None
    with pytest.raises(FileExistsError):
        trace.flush(tmp_path)


@pytest.mark.parametrize("exception", [ValueError, KeyboardInterrupt])
def test_original_exception_survives(trace, exception):
    original = exception("SECRET_SHOULD_NOT_APPEAR")
    with pytest.raises(exception) as caught, span("quality.check"):
        raise original
    assert caught.value is original
    assert trace.spans[-1]["status"] == "error"
    assert "SECRET_SHOULD_NOT_APPEAR" not in json.dumps(trace.report())


def test_cancel_and_retries(trace):
    class JobCancelled(Exception):
        pass
    with pytest.raises(JobCancelled), span("candidate.write"):
        raise JobCancelled()
    terminal("CANCELLED")
    assert trace.status == "cancelled"
    assert trace.spans[-1]["status"] == "cancelled"
    retry = Trace(trace.task_id)
    assert retry.trace_id != trace.trace_id
    assert retry.root_id == trace.root_id


def test_sql_actual_events_and_no_secrets(trace):
    engine = create_engine("sqlite://")
    observer = SQLObserver(engine, trace)
    observer.install()
    try:
        with engine.connect() as db:
            assert db.execute(text("select :secret"), {"secret": "PRIVATE"}).scalar() == "PRIVATE"
            assert db.execute(text("select 2")).scalar() == 2
        assert trace.execute_calls == 2
        assert "PRIVATE" not in json.dumps(trace.report())
    finally:
        observer.close()
        engine.dispose()
    assert not observer.listeners


@pytest.mark.parametrize("left,right", [
    ("select 'private'", "select 'other'"),
    ("select 123", "select 456"),
    ("select $$secret$$", "select $$different$$"),
    ("select $tag$secret$tag$", "select $x$other$x$"),
    ("select 1 -- private", "select 1 -- other"),
])
def test_literal_stripping(left, right):
    assert fingerprint(left) == fingerprint(right)
    assert "secret" not in fingerprint(left)


def test_sql_failure_and_unknown_rows(trace):
    observer = SQLObserver(None, trace)
    context = SimpleNamespace()
    observer.before(None, None, "select 1", {"secret": "PRIVATE"}, context, False)
    observer.finish(context, None, True)
    item = next(iter(trace.sql.values()))
    assert item["errors"] == 1
    assert item["affected_rows"] is None


def test_disabled_span_no_report(tmp_path):
    assert active_trace.get() is None
    with span("factor.compute"):
        assert sum([1, 2, 3]) == 6
    assert not list(tmp_path.iterdir())


def test_unknown_resources_and_metrics(trace):
    report = trace.report()
    assert report["worker_resources"]["final"]["threads"] is None
    assert report["database_summary"]["result_bytes"] is None
    assert report["database_summary"]["fetch_total_ms"] is None
    assert report["coverage"]["candidate.filter"] == "NOT_INSTRUMENTED"
    assert report["diagnostic_overhead"]["instrumentation_ms"] is None


def test_bounded_span_memory(trace):
    for _ in range(4100):
        trace.interval("candidate.query", trace.started_at, 0)
    assert len(trace.spans) == 4096
    assert "SPAN_LIMIT_REACHED" in trace.warnings


def test_summary_does_not_invent_p95_or_add_nested_wall(trace):
    with span("factor.compute"), span("data.transform"):
        pass
    report = trace.report()
    result = summary([report])[0]
    assert result["p95_ms"] is None
    assert interval_union_ms(report["stages"]) <= report["total_wall_ms"] + 1
    assert result["runs"] == 1


def test_record_fault_preserves_business_exception(trace, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("private")
    monkeypatch.setattr(trace, "interval", broken)
    with pytest.raises(ValueError, match="original"), span("factor.compute"):
        raise ValueError("original")
    assert active_span.get() is None
    assert "SPAN_RECORD_FAILED" in trace.warnings


def test_child_terminal_cannot_publish_root(trace):
    terminal("SUCCESS", "other-child")
    assert trace.status == "incomplete"
    terminal("SUCCESS", trace.root_id)
    assert trace.status == "success"


def test_context_does_not_leak_into_new_thread(trace):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(active_trace.get).result() is None
    assert active_trace.get() is trace


def test_driver_fetch_counts_no_result_consumption(trace):
    from app.services.performance_diagnostics import driver_fetch

    driver_fetch(.01, 5000)
    driver_fetch(.02, 2)
    report = trace.report()["database_summary"]
    assert report["fetch_calls"] == 2
    assert report["fetched_rows"] == 5002
    assert report["fetch_total_ms"] == 30


def test_worker_flush_error_never_overrides_task(monkeypatch, tmp_path):
    from app.core import config
    from app.services.performance_diagnostics import observe_worker

    settings = SimpleNamespace(perf_diagnostics_enabled=True,
        perf_diagnostics_directory=tmp_path, ab_merge_read_enabled=False,
        factor_input_reuse_enabled=False)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(Trace, "flush", lambda *a: (_ for _ in ()).throw(OSError("private")))
    engine = create_engine("sqlite://")
    db = SimpleNamespace(get_bind=lambda: engine)

    @observe_worker
    def work(db, task_id):
        raise ValueError("original")

    with pytest.raises(ValueError, match="original"):
        work(db, "root")
    assert active_trace.get() is None
    engine.dispose()
