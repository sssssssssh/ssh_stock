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


@pytest.mark.parametrize("failure_at", [1, 2, 3])
@pytest.mark.parametrize("installed_before_error", [False, True])
def test_r1_partial_install_is_atomic(monkeypatch, failure_at, installed_before_error):
    from sqlalchemy import event

    engine = create_engine("sqlite://")
    observer = SQLObserver(engine, Trace("install-failure"))
    listen = event.listen
    count = 0

    def fail_install(*args, **kwargs):
        nonlocal count
        count += 1
        if count == failure_at and not installed_before_error:
            raise RuntimeError("private-install-error")
        result = listen(*args, **kwargs)
        if count == failure_at:
            raise RuntimeError("private-install-error")
        return result

    monkeypatch.setattr(event, "listen", fail_install)
    try:
        with pytest.raises(RuntimeError):
            observer.install()
        assert observer.listeners == []
        assert not event.contains(engine, "before_cursor_execute", observer.before)
        assert not event.contains(engine, "after_cursor_execute", observer.after)
        assert not event.contains(engine, "handle_error", observer.failed)
    finally:
        observer.close()
        engine.dispose()


def test_r1_engine_observers_do_not_steal_other_trace():
    engine = create_engine("sqlite://")
    first, second = Trace("first"), Trace("second")
    observers = [SQLObserver(engine, value) for value in (first, second)]
    for observer in observers:
        observer.install()
    try:
        for trace in (second, first, second):
            token = active_trace.set(trace)
            try:
                with engine.connect() as db:
                    assert db.execute(text("select 1")).scalar() == 1
            finally:
                active_trace.reset(token)
        assert first.execute_calls == 1
        assert second.execute_calls == 2
    finally:
        for observer in observers:
            observer.close()
        engine.dispose()


@pytest.mark.parametrize("failure_at", [1, 2, 3])
def test_r1_remove_failure_cleans_remaining_handlers(monkeypatch, failure_at):
    from sqlalchemy import event

    engine = create_engine("sqlite://")
    observer = SQLObserver(engine, Trace("remove-failure"))
    observer.install()
    remove, calls = event.remove, 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == failure_at:
            raise RuntimeError("private-remove-error")
        return remove(*args, **kwargs)

    monkeypatch.setattr(event, "remove", fail_once)
    observer.close()
    assert not observer.listeners
    assert not observer.active
    assert calls >= 3
    assert "private-remove-error" not in json.dumps(observer.trace.report())
    engine.dispose()


def test_r1_setup_failure_restores_context_before_business(monkeypatch, tmp_path):
    from app.core import config
    from app.services.performance_diagnostics import observe_worker
    from sqlalchemy import event

    engine = create_engine("sqlite://")
    settings = SimpleNamespace(perf_diagnostics_enabled=True,
        perf_diagnostics_directory=tmp_path, ab_merge_read_enabled=False,
        factor_input_reuse_enabled=False)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    listen = event.listen
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("private")
        return listen(*args, **kwargs)

    monkeypatch.setattr(event, "listen", fail_second)

    @observe_worker
    def work(db, key):
        assert active_trace.get() is None
        assert not engine.dispatch.before_cursor_execute
        return "original-result"

    assert work(SimpleNamespace(get_bind=lambda: engine), "root") == "original-result"
    assert not list(tmp_path.iterdir())
    engine.dispose()


def test_r1_failed_fetch_has_unknown_total_but_known_prefix(trace):
    from app.services.performance_diagnostics import driver_fetch

    driver_fetch(.01, 7)
    driver_fetch(.02, None)
    report = trace.report()["database_summary"]
    assert report["fetched_rows"] is None
    assert report["known_fetched_prefix_rows"] == 7
    assert report["fetch_calls"] == 2


def test_r1_closed_observer_cannot_consume_foreign_event(trace):
    observer = SQLObserver(None, trace)
    observer.close()
    context = SimpleNamespace(performance_diagnostic=(observer, "key", 0))
    observer.finish(context, None, False)
    assert trace.execute_calls == 0


def test_r1_permanent_remove_failure_disables_and_keeps_cleanup_evidence(monkeypatch):
    from sqlalchemy import event

    engine = create_engine("sqlite://")
    observer = SQLObserver(engine, Trace("permanent-remove-failure"))
    observer.install()
    remove = event.remove

    def broken(*args, **kwargs):
        raise OSError("private-remove-failure")

    monkeypatch.setattr(event, "remove", broken)
    observer.close()
    assert len(observer.listeners) == 3
    assert not observer.active
    assert "SQL_LISTENER_CLEANUP_INCOMPLETE" in observer.trace.warnings
    token = active_trace.set(observer.trace)
    try:
        with engine.connect() as db:
            assert db.execute(text("select 1")).scalar() == 1
        assert observer.trace.execute_calls == 0
    finally:
        active_trace.reset(token)
        monkeypatch.setattr(event, "remove", remove)
        observer.close()
        engine.dispose()
    assert not observer.listeners


def test_r1_disabled_worker_does_not_install_or_create_trace(monkeypatch, tmp_path):
    from app.core import config
    from app.services.performance_diagnostics import observe_worker

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        perf_diagnostics_enabled=False))
    monkeypatch.setattr(Trace, "__init__", lambda *a, **k: pytest.fail("trace created"))

    @observe_worker
    def work(db, key):
        return "original-result"

    assert work(None, "root") == "original-result"
    assert not list(tmp_path.iterdir())


def test_r1_link_failure_removes_pending_and_preserves_original(trace, monkeypatch, tmp_path):
    import os

    def broken(*args):
        raise OSError("private-link-failure")

    monkeypatch.setattr(os, "link", broken)
    with pytest.raises(OSError):
        trace.flush(tmp_path)
    assert not list(tmp_path.rglob("*.pending-*"))
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "CANCELLED", None])
def test_r1_worker_terminal_and_unknown_commit_are_not_relabelled(
    monkeypatch, tmp_path, status,
):
    from app.core import config
    from app.services.performance_diagnostics import observe_worker

    settings = SimpleNamespace(perf_diagnostics_enabled=True,
        perf_diagnostics_directory=tmp_path, ab_merge_read_enabled=False,
        factor_input_reuse_enabled=False)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    engine = create_engine("sqlite://")

    @observe_worker
    def work(db, key):
        terminal("SUCCESS", "child")
        if status is not None:
            terminal(status, key)
        return "unchanged-business-result"

    assert work(SimpleNamespace(get_bind=lambda: engine), "root") == "unchanged-business-result"
    report = json.loads(next(tmp_path.rglob("*.json")).read_text())
    assert report["status"] == {"SUCCESS": "success", "FAILED": "error",
                                "CANCELLED": "cancelled", None: "incomplete"}[status]
    assert active_trace.get() is None
    engine.dispose()


def test_r1_concurrent_contexts_keep_observer_ownership():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine("sqlite://")
    traces = [Trace("first-thread"), Trace("second-thread")]
    observers = [SQLObserver(engine, trace) for trace in traces]
    for observer in observers:
        observer.install()
    barrier = Barrier(2)

    def execute(trace):
        token = active_trace.set(trace)
        try:
            barrier.wait(timeout=5)
            with engine.connect() as db:
                db.execute(text("select 1")).all()
        finally:
            active_trace.reset(token)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(execute, traces))
        assert [trace.execute_calls for trace in traces] == [1, 1]
    finally:
        for observer in observers:
            observer.close()
        engine.dispose()


def test_r1_closing_one_observer_does_not_disable_another():
    engine = create_engine("sqlite://")
    first, second = SQLObserver(engine, Trace("one")), SQLObserver(engine, Trace("two"))
    first.install()
    second.install()
    first.close()
    token = active_trace.set(second.trace)
    try:
        with engine.connect() as db:
            db.execute(text("select 1")).all()
        assert second.trace.execute_calls == 1
        assert first.trace.execute_calls == 0
    finally:
        active_trace.reset(token)
        second.close()
        engine.dispose()


def test_r1_sql_aggregation_and_digest_cache_stay_bounded(trace):
    observer = SQLObserver(None, trace)
    for index in range(150):
        context = SimpleNamespace()
        observer.before(None, None, f"select 1 as field_{index}", {}, context, False)
        observer.finish(context, None, False)
    assert len(observer.fingerprints) == 128
    assert len(trace.sql) == 129
    assert trace.execute_calls == 150
    assert trace.sql["overflow"]["calls"] == 22
    assert "field_149" not in json.dumps(trace.report())


def test_r1_span_setup_failure_does_not_replace_business_error(trace, monkeypatch):
    from app.services import performance_diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "stamp", lambda: (_ for _ in ()).throw(OSError("private")))
    with pytest.raises(ValueError, match="business-original"), span("factor.compute"):
        raise ValueError("business-original")


def test_r1_setup_cleanup_exception_still_restores_token(monkeypatch, tmp_path):
    from app.core import config
    from app.services.performance_diagnostics import observe_worker

    settings = SimpleNamespace(perf_diagnostics_enabled=True,
        perf_diagnostics_directory=tmp_path, ab_merge_read_enabled=False,
        factor_input_reuse_enabled=False)
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    def broken(*args):
        raise OSError("private")

    monkeypatch.setattr(SQLObserver, "install", broken)
    monkeypatch.setattr(SQLObserver, "close", broken)
    engine = create_engine("sqlite://")

    @observe_worker
    def work(db, key):
        assert active_trace.get() is None
        return "original"

    assert work(SimpleNamespace(get_bind=lambda: engine), "root") == "original"
    engine.dispose()
