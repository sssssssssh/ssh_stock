"""Explicit isolated PG17 synthetic capacity experiment; never accepts a business DB.

Full publication protocol uses real candidate upserts/preimages/commit, but the
performance fixture certifies structural samples, NOT real financial calculations.
Real calculator + quality + Worker coverage lives in test_data_publication.py.
"""

import argparse
import json
import os
import platform
import statistics
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


def peak_rss_bytes():
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    return rss_bytes()


class CapacityProgress:
    """Bounded diagnostic sidecar, deliberately NOT a capacity receipt."""

    def __init__(self, path, identity):
        from scripts.a42_artifacts import atomic, now
        from scripts.a42_receipt_contract import require

        self.path = Path(path)
        require(not self.path.exists(), "CAPACITY_PROGRESS_ALREADY_EXISTS")
        self.started = time.perf_counter()
        self.last_write = self.started
        self.replace_attempts = 5 if os.name == "nt" else 1
        self.stack = []
        self.table = None
        self.expected_probe = False
        self.data = dict(
            schema_version="capacity-progress-v1", artifact_kind="DIAGNOSTIC_ONLY",
            **{key: identity[key] for key in (
                "head_sha", "run_id", "attempt", "job_id", "model_hash", "working_tree_dirty")},
            started_at=now(), updated_at=now(), status="INCOMPLETE",
            current_phase="initialization", current_table=None, completed_table_count=0,
            tables={}, phases={}, completed_levels=[],
            peak_process_rss_bytes=0, rss_scope="PROCESS_LIFETIME_HIGH_WATER_NOT_TABLE_PEAK",
            production_read_authorized=False,
        )
        atomic(self.path, self.data)

    def flush(self, *, force=False):
        from scripts.a42_artifacts import atomic, now

        clock = time.perf_counter()
        if not force and clock - self.last_write < 5:
            return
        self.last_write = clock
        self.data.update(updated_at=now(), last_checkpoint_at=now(),
                         elapsed_seconds=clock-self.started,
                         current_operation_elapsed_seconds=(clock-self.stack[-1][1]
                                                            if self.stack else 0))
        if self.table:
            table = self.data["tables"][self.table]
            table["elapsed_seconds"] = clock-self.table_start
            table["rows_per_second"] = table["rows"] / table["elapsed_seconds"]
        self.data["peak_process_rss_bytes"] = peak_rss_bytes()
        # Windows scanners may briefly hold the destination during os.replace.
        # Retry ONLY this diagnostic file, never a database operation.
        for attempt in range(self.replace_attempts):
            try:
                atomic(self.path, self.data)
                break
            except PermissionError:
                if attempt + 1 == self.replace_attempts:
                    raise
                time.sleep(0.025)

    def begin_level(self, stocks, days, level):
        self.table = None
        self.data.update(level=level, stocks=stocks, days=days, tables={}, phases={},
                         current_table=None, completed_table_count=0)
        self.flush(force=True)

    def finish_table(self):
        if self.table is not None:
            table = self.data["tables"][self.table]
            table.update(status="MEASURED", elapsed_seconds=time.perf_counter()-self.table_start)
            table["rows_per_second"] = table["rows"] / table["elapsed_seconds"]
            table["peak_process_rss_bytes"] = peak_rss_bytes()
            self.data["completed_table_count"] += 1
            self.table = None
            self.data["current_table"] = None
            self.flush(force=True)

    def begin_table(self, name):
        self.finish_table()
        self.table, self.table_start = name, time.perf_counter()
        self.data["current_table"] = name
        self.data["tables"][name] = dict(
            status="INCOMPLETE", rows=0, batch_count=0, commit_count=0,
            payload_count=0, operations={}, sql={},
        )
        self.flush(force=True)

    @contextmanager
    def phase(self, name, *, persist=True):
        from scripts.a42_artifacts import failure

        previous = self.data["current_phase"]
        started = time.perf_counter()
        self.stack.append((name, started))
        self.data["current_phase"] = name
        try:
            if persist:
                totals = (self.data["tables"][self.table]["operations"] if self.table
                          else self.data["phases"])
                self.flush(force=name not in totals)
            yield
        except BaseException as error:
            if not self.expected_probe:
                self.data.setdefault("first_failure", dict(phase=name, table=self.table,
                                                           **failure(error)))
            raise
        finally:
            elapsed = time.perf_counter()-started
            for totals in [self.data["phases"]] + (
                [self.data["tables"][self.table]["operations"]] if self.table else []
            ):
                counter = totals.setdefault(name, dict(count=0, elapsed_seconds=0))
                counter["count"] += 1
                counter["elapsed_seconds"] += elapsed
            try:
                if persist:
                    self.flush()
            finally:
                self.stack.pop()
                self.data["current_phase"] = previous

    @contextmanager
    def lifecycle(self, manager, enter, leave):
        with ExitStack() as stack:
            def close(*error):
                # A diagnostic I/O failure must never prevent real cleanup.
                with self.phase(leave, persist=False):
                    try:
                        self.flush(force=True)
                    finally:
                        result = manager.__exit__(*error)
                    return result
            with self.phase(enter):
                value = manager.__enter__()
                stack.push(close)
            yield value

    def fail(self, error):
        from scripts.a42_artifacts import failure

        self.data.update(status="INCOMPLETE", terminal_failure=failure(error))
        self.flush(force=True)


@contextmanager
def observe_capacity(progress):
    """Observe original driver calls in this lab process; no SQL/budget changes.

    Payload timers are in-memory only. Durable writes happen at operation/table
    boundaries, not for each payload row. SQL timings are nested in upsert, etc.;
    they must not be added to those outer durations.
    """
    from sqlalchemy.orm import Session

    active = [None]
    main_thread = threading.get_ident()

    def wrapped(function, name):
        @wraps(function)
        def call(*args, **kwargs):
            with progress.phase(name):
                return function(*args, **kwargs)
        return call

    original_isolated = isolated_contract_database

    @contextmanager
    def isolated(*args, **kwargs):
        with progress.lifecycle(original_isolated(*args, **kwargs),
                                "isolation_and_migration", "database_cleanup") as (factory, engine):
            def before(c, cursor, statement, parameters, context, executemany):
                if threading.get_ident() == main_thread:
                    context.capacity_started = time.perf_counter()

            def after(c, cursor, statement, parameters, context, executemany):
                started = getattr(context, "capacity_started", None)
                if started is None or progress.table is None:
                    return
                # Only fixed labels are retained, never SQL or bind values.
                verb = statement.lstrip().split(None, 1)[0].upper()
                verb = verb if verb in {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE",
                                        "EXPLAIN", "SET"} else "OTHER"
                counter = progress.data["tables"][progress.table]["sql"].setdefault(
                    verb, dict(count=0, elapsed_seconds=0))
                counter["count"] += 1
                counter["elapsed_seconds"] += time.perf_counter()-started

            event.listen(engine, "before_cursor_execute", before)
            event.listen(engine, "after_cursor_execute", after)
            try:
                yield factory, engine
            finally:
                event.remove(engine, "before_cursor_execute", before)
                event.remove(engine, "after_cursor_execute", after)

    original_candidate = candidate

    @contextmanager
    def observed_candidate(*args, **kwargs):
        with progress.lifecycle(original_candidate(*args, **kwargs),
                                "candidate_create", "candidate_cleanup") as (db, job):
            active[0] = db
            try:
                yield db, job
            finally:
                active[0] = None

    from app.services.data_publication import PublicationWorkspace

    original_scope, original_upsert = PublicationWorkspace.record_scope, PublicationWorkspace.upsert
    original_payload, original_commit = payload, Session.commit
    original_validation = record_validation
    original_execute = Session.execute

    def execute(db, statement, *args, **kwargs):
        if db is not active[0]:
            return original_execute(db, statement, *args, **kwargs)
        name = None
        if getattr(statement, "is_select", False):
            columns = list(statement.selected_columns)
            if len(columns) == 2 and [c.name for c in columns] == ["ts_code", "id"]:
                name = "signal_id_lookup"
        elif isinstance(statement, type(text(""))):
            sql = statement.text.lstrip()
            if sql.startswith("EXPLAIN"):
                name = ("publication_plan" if "_publishable" in sql or "SELECT count(*)" in sql
                        else "candidate_plan" if "data_publication_row" in sql else "public_plan")
            elif "AS json_bytes" in sql or "AS rows" in sql:
                name = "candidate_or_preimage_statistics"
        if name is None:
            return original_execute(db, statement, *args, **kwargs)
        with progress.phase(name):
            return original_execute(db, statement, *args, **kwargs)

    def scope(ws, model, filters):
        progress.begin_table(model.__tablename__)
        with progress.phase("record_scope"):
            return original_scope(ws, model, filters)

    def construct(*args, **kwargs):
        with progress.phase("payload", persist=False):
            row = original_payload(*args, **kwargs)
        if progress.table:
            progress.data["tables"][progress.table]["payload_count"] += 1
        return row

    def upsert(ws, model, rows, *args, **kwargs):
        with progress.phase("workspace_upsert"):
            result = original_upsert(ws, model, rows, *args, **kwargs)
            table = progress.data["tables"][model.__tablename__]
            table["rows"] += len(rows)
            table["batch_count"] += (len(rows)+499)//500
            return result

    def commit(db):
        if db is not active[0]:
            return original_commit(db)
        with progress.phase("day_commit"):
            result = original_commit(db)
            if progress.table:
                progress.data["tables"][progress.table]["commit_count"] += 1
            return result

    def validation(*args, **kwargs):
        progress.finish_table()
        with progress.phase("record_validation"):
            return original_validation(*args, **kwargs)

    original_probe = rollback_probe

    def probe(*args, **kwargs):
        with progress.phase("rollback_probe"):
            progress.expected_probe = True
            try:
                return original_probe(*args, **kwargs)
            finally:
                progress.expected_probe = False

    with pytest.MonkeyPatch.context() as local:
        local.setattr(sys.modules[__name__], "isolated_contract_database", isolated)
        local.setattr(sys.modules[__name__], "candidate", observed_candidate)
        local.setattr(sys.modules[__name__], "payload", construct)
        local.setattr(sys.modules[__name__], "record_validation", validation)
        local.setattr(sys.modules[__name__], "rollback_probe", probe)
        for name in ("seed", "public_digests", "stats", "update_job"):
            local.setattr(sys.modules[__name__], name, wrapped(globals()[name], name))
        local.setattr(PublicationWorkspace, "record_scope", scope)
        local.setattr(PublicationWorkspace, "upsert", upsert)
        local.setattr(Session, "commit", commit)
        local.setattr(Session, "execute", execute)
        yield


def payload(model, source, day, entity, value):
    if model is m.SignalForwardEval:
        return dict(
            trade_date=day,
            ts_code=f"S{entity:06d}.SZ",
            signal_type="RIGHT_SIDE_NEW",
            algo_version=get_settings().algo_version,
            eval_version="eval_v3",
            entry_basis="NEXT_OPEN",
            horizon_basis="MARKET_TRADING_DAY",
            ret5=value / 1000,
        )
    if model is m.DataQualityDaily:
        return dict(
            trade_date=day,
            dataset="capacity_synthetic",
            status="PASS",
            job_id=source,
            expected_rows=entity,
            actual_rows=entity,
        )
    result = sample_row(model, source, value, day)
    for col in model.__table__.columns:
        if col.name not in result and col.default is not None and col.default.is_scalar:
            result[col.name] = col.default.arg
    if "ts_code" in result:
        result["ts_code"] = f"S{entity:06d}.SZ"
    if "sector_id" in result:
        result["sector_id"] = entity
    if "theme_code" in result:
        result["theme_code"] = f"T{entity:04d}"
    return result


def entities(model, stocks):
    return (
        1
        if model in (m.MarketDaily, m.DataQualityDaily)
        else min(50, stocks)
        if model is m.SectorFactorDaily
        else min(100, stocks)
        if model is m.ThemeFactorDaily
        else stocks
    )


def seed(factory, stocks, days):
    with factory() as db:
        old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
        db.add(old)
        db.add_all(m.TradeCalendar(cal_date=day, is_open=True) for day in days)
        db.add_all(
            m.Sector(sector_id=i, source="SW", source_code=str(i), name="synthetic", level="L1")
            for i in range(1, min(stocks, 50) + 1)
        )
        db.add_all(
            m.Theme(theme_code=f"T{i:04d}", source="THS", name="synthetic", theme_type="N")
            for i in range(1, min(stocks, 100) + 1)
        )
        db.flush()
        for model in MODELS:
            if model is m.SignalForwardEval:
                db.execute(
                    text("""INSERT INTO signal_forward_eval
                    (signal_id,trade_date,ts_code,signal_type,algo_version,eval_version,
                     entry_basis,horizon_basis,ret5)
                    SELECT id,trade_date,ts_code,signal_type,algo_version,'eval_v3',
                     'NEXT_OPEN','MARKET_TRADING_DAY',0.01 FROM strategy_signal""")
                )
                continue
            base = payload(model, old.id, days[0], 1, 10)
            columns = list(base)
            expressions = []
            for column in columns:
                if column == "trade_date":
                    expressions.append("d.day")
                elif column == "ts_code":
                    expressions.append("'S' || lpad(e.n::text,6,'0') || '.SZ'")
                elif column == "sector_id":
                    expressions.append("e.n")
                elif column == "theme_code":
                    expressions.append("'T' || lpad(e.n::text,4,'0')")
                else:
                    expressions.append(f'r."{column}"')
            names = ",".join(f'"{c}"' for c in columns)
            db.execute(
                text(f"""INSERT INTO "{model.__tablename__}" ({names})
                SELECT {",".join(expressions)} FROM unnest(CAST(:days AS date[])) d(day)
                CROSS JOIN generate_series(1,:entities) e(n)
                CROSS JOIN LATERAL jsonb_populate_record(
                  NULL::public."{model.__tablename__}", CAST(:base AS jsonb)) r"""),
                dict(
                    days=days,
                    entities=entities(model, stocks),
                    base=json.dumps(base, default=str, allow_nan=False),
                ),
            )
        db.commit()
        return old.id


def stats(db):
    return dict(
        db.execute(
            text("""SELECT
        pg_database_size(current_database()) AS database_bytes,
        (SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)::bigint
         FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='public' AND c.relkind='r') AS table_and_index_bytes,
        (SELECT pg_current_wal_insert_lsn()::text) AS wal_lsn""")
        )
        .mappings()
        .one()
    )


def public_digests(factory):
    """Bounded aggregate (32 bytes/row), not one huge JSON array in server memory."""
    with factory() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = {}
        for model in MODELS:
            keys = ",".join(f'p."{key}"' for key in KEYS[model.__tablename__])
            result[model.__tablename__] = db.scalar(
                text(
                    "SELECT md5(string_agg(md5(to_jsonb(p)::text),'' ORDER BY " + keys + ")) "
                    f'FROM public."{model.__tablename__}" p'
                )
            )
        return result


def rollback_probe(db, job, factory, expected_a, mode):
    """Known, acknowledged rollback probes only; never a Worker recovery/replay path."""
    from app.models.data_publication import DataPublication
    from app.services import data_publication as publication

    started = time.perf_counter()
    if mode == "row_budget":
        original = publication.scheduler_setting
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                publication,
                "scheduler_setting",
                lambda name, default: (
                    1 if name == "data_publish_max_rows" else original(name, default)
                ),
            )
            try:
                with pytest.raises(ValueError, match="^PUBLICATION_ROW_BUDGET_EXCEEDED$"):
                    update_job(db, job, status="SUCCESS")
            finally:
                db.rollback()
        code = "PUBLICATION_ROW_BUDGET_EXCEEDED"
    else:
        # Trade-status merge has already executed in the SAME uncommitted root
        # transaction. Interrupt before the next table using a real PG timeout.
        connection = db.info["publication_workspace"].connection
        fired = []

        def interrupt(c, cursor, statement, parameters, context, executemany):
            if not fired and statement.lstrip().startswith(
                'INSERT INTO public."stock_factor_daily"'
            ):
                fired.append(True)
                c.exec_driver_sql("SET LOCAL statement_timeout = '1ms'")
                c.exec_driver_sql("SELECT pg_sleep(0.05)")

        event.listen(connection, "before_cursor_execute", interrupt)
        try:
            with pytest.raises(DBAPIError) as error:
                update_job(db, job, status="SUCCESS")
            assert fired and error.value.orig.sqlstate == "57014"
        finally:
            db.rollback()
            event.remove(connection, "before_cursor_execute", interrupt)
        code = "PG_SQLSTATE_57014"
    rollback_seconds = time.perf_counter() - started
    observed_a = public_digests(factory)
    assert observed_a == expected_a
    with factory() as reader:
        root = reader.get(JobRun, job.id)
        ledger = reader.get(DataPublication, job.id)
        assert root.status == "RUNNING" and ledger.state == "PREPARING"
        assert reader.scalar(text("SELECT count(*) FROM data_publication_preimage")) == 0
    return dict(
        mode=mode,
        code=code,
        elapsed_seconds=rollback_seconds,
        a_digest_unchanged=True,
        a_before=expected_a,
        a_after=observed_a,
        root_status="RUNNING",
        ledger_state="PREPARING",
        queue_slot_held=True,
        test_only_known_rollback=True,
    )


def run_level(stocks, count, label):
    days = list(pd.bdate_range("2026-01-01", periods=count).date)
    with (
        pytest.MonkeyPatch.context() as patch,
        isolated_contract_database(patch) as (factory, engine),
    ):
        old = seed(factory, stocks, days)
        expected_a = public_digests(factory)
        with factory() as db:
            before = stats(db)
            pg_version = db.scalar(text("SHOW server_version"))
            database_settings = dict(
                db.execute(
                    text("""SELECT name,setting || ' ' ||
                coalesce(unit,'') FROM pg_settings WHERE name IN
                ('shared_buffers','work_mem','maintenance_work_mem','max_connections',
                 'wal_level','max_wal_size','checkpoint_timeout','block_size')""")
                ).all()
            )
        stop = threading.Event()
        latencies, failures, observations, locks = [], [], [], []

        def reader():
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
                        c.execute(text("SET TRANSACTION READ ONLY"))
                        first = c.execute(
                            text("""SELECT max(trade_date),count(*),
                           min(calc_run_id::text),max(calc_run_id::text) FROM stock_factor_daily""")
                        ).one()
                        assert first[2] == first[3]
                        # Same request includes latest, JOIN, count and ordered pagination.
                        rows = c.execute(
                            text("""SELECT f.calc_run_id::text,s.calc_run_id::text,
                            o.calc_run_id::text FROM stock_factor_daily f
                            JOIN stock_state_daily s USING(trade_date,ts_code)
                            JOIN stock_opportunity_daily o USING(trade_date,ts_code)
                            WHERE f.trade_date=:day ORDER BY f.ts_code LIMIT 20 OFFSET 1"""),
                            dict(day=first[0]),
                        ).all()
                        assert all(set(row) == {first[2]} for row in rows)
                        eval_count = c.scalar(text("SELECT count(*) FROM signal_forward_eval"))
                        assert eval_count == stocks * count
                        for model in MODELS[:8]:
                            sources = c.execute(
                                text(
                                    "SELECT min(calc_run_id::text),max(calc_run_id::text) "
                                    f'FROM public."{model.__tablename__}" WHERE trade_date=:day'
                                ),
                                dict(day=first[0]),
                            ).one()
                            assert sources == (first[2], first[2])
                        returns = c.execute(
                            text(
                                "SELECT min(e.ret5),max(e.ret5) FROM strategy_signal s "
                                "JOIN signal_forward_eval e ON e.signal_id=s.id "
                                "WHERE s.trade_date=:day"
                            ),
                            dict(day=first[0]),
                        ).one()
                        expected_return = 0.01 if first[2] == str(old) else 0.02
                        assert returns == (expected_return, expected_return)
                        observations.append(first[2])
                    latencies.append((time.perf_counter() - started) * 1000)
                except Exception as exc:
                    failures.append(type(exc).__name__ + ":" + str(exc))
                    stop.set()
                stop.wait(0.15)

        def lock_sampler():
            while not stop.wait(0.2):
                with engine.connect() as c:
                    locks.append(
                        dict(
                            c.execute(
                                text("""SELECT
                       count(*) FILTER (WHERE wait_event_type='Lock') AS waiting,
                       (SELECT count(*) FROM job_run WHERE status='RUNNING'
                        AND parent_job_id IS NULL) AS running
                       FROM pg_stat_activity WHERE datname=current_database()""")
                            )
                            .mappings()
                            .one()
                        )
                    )

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=lock_sampler))
        for thread in threads:
            thread.start()
        try:
            # Freeze the actual benchmark range at enqueue, before claim.
            with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
                ws = db.info["publication_workspace"]
                staged, stage_seconds = 0, {}
                stage_peak_rss = {}
                started = time.perf_counter()
                for model in MODELS:
                    stage_start = time.perf_counter()
                    ws.record_scope(
                        model, [model.trade_date >= days[0], model.trade_date <= days[-1]]
                    )
                    n = entities(model, stocks)
                    for day in days:
                        for start in range(1, n + 1, 500):
                            rows = [
                                payload(model, job.id, day, i, 20)
                                for i in range(start, min(n + 1, start + 500))
                            ]
                            if model is m.SignalForwardEval:
                                ids = dict(
                                    db.execute(
                                        select(m.StrategySignal.ts_code, m.StrategySignal.id).where(
                                            m.StrategySignal.trade_date == day,
                                            m.StrategySignal.ts_code.in_(
                                                [r["ts_code"] for r in rows]
                                            ),
                                        )
                                    ).all()
                                )
                                for row in rows:
                                    row["signal_id"] = ids[row["ts_code"]]
                            ws.upsert(model, rows, KEYS[model.__tablename__])
                            staged += len(rows)
                        db.commit()
                    stage_seconds[model.__tablename__] = time.perf_counter() - stage_start
                    stage_peak_rss[model.__tablename__] = peak_rss_bytes()
                    print(
                        json.dumps(dict(level=label, stage=model.__tablename__, rows=staged)),
                        flush=True,
                    )
                write_seconds = time.perf_counter() - started
                # Structural perf fixture only. Real CrossTableQuality is exercised
                # by the actual cold-start Worker regression, never mocked there.
                from types import SimpleNamespace

                for day in days:
                    record_validation(db, job.id, day, SimpleNamespace(has_error=False))
                db.commit()
                plan = db.execute(
                    text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT row_data FROM data_publication_row
                    WHERE publication_id=:root AND table_name='stock_factor_daily'
                    AND trade_date=:day AND entity_key='S000001.SZ'"""),
                    dict(root=job.id, day=days[-1]),
                ).scalar()
                candidate_stats = dict(
                    db.execute(
                        text("""SELECT count(*) AS rows,
                    sum(pg_column_size(row_data)+coalesce(pg_column_size(base_row),0))
                      AS json_bytes,
                    avg(pg_column_size(row_data)) AS average_candidate_json_bytes
                    FROM public.data_publication_row WHERE publication_id=:root"""),
                        dict(root=job.id),
                    )
                    .mappings()
                    .one()
                )
                public_plan = db.execute(
                    text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT f.ts_code,f.adj_close,s.state,o.opportunity_score
                    FROM public.stock_factor_daily f JOIN public.stock_state_daily s
                    USING(trade_date,ts_code) JOIN public.stock_opportunity_daily o
                    USING(trade_date,ts_code) WHERE f.trade_date=:day
                    ORDER BY f.ts_code LIMIT 20 OFFSET 1"""),
                    dict(day=days[-1]),
                ).scalar()
                from app.services.data_publication import _publishable_sql

                publication_plan = db.execute(
                    text(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                        "SELECT count(*) FROM public.data_publication_row s WHERE "
                        + _publishable_sql("stock_factor_daily")
                    ),
                    dict(root=job.id),
                ).scalar()
                assert db.scalar(select(func.count()).select_from(DataPublicationRow)) == staged
                rollback_probes = [
                    rollback_probe(db, job, factory, expected_a, mode)
                    for mode in ("row_budget", "sql_timeout_after_first_table")
                ]
                started = time.perf_counter()
                update_job(db, job, status="SUCCESS")
                publish_seconds = time.perf_counter() - started
                root_key = job.id
                root_id = str(root_key)
            # Require a completed B snapshot, not timing luck on a busy runner.
            reader_deadline = time.monotonic() + 10
            while (
                root_id not in observations and not failures and time.monotonic() < reader_deadline
            ):
                stop.wait(0.05)
            with factory() as db:
                from app.models.data_publication import DataPublication

                final_root_status = db.get(JobRun, root_key).status
                final_ledger_state = db.get(DataPublication, root_key).state
                assert final_root_status == "SUCCESS" and final_ledger_state == "PUBLISHED"
                after = stats(db)
                wal_bytes = db.scalar(
                    text("SELECT pg_wal_lsn_diff(:end,:start)"),
                    dict(end=after["wal_lsn"], start=before["wal_lsn"]),
                )
                preimage = dict(
                    db.execute(
                        text("""SELECT count(*) AS rows,
                    coalesce(sum(pg_column_size(row_data)),0) AS json_bytes
                    FROM data_publication_preimage""")
                    )
                    .mappings()
                    .one()
                )
                relations = [
                    dict(row)
                    for row in db.execute(
                        text("""SELECT relname,
                    pg_table_size(oid) AS table_bytes, pg_indexes_size(oid) AS index_bytes
                    FROM pg_class WHERE relname IN
                    ('data_publication_row','data_publication_preimage')
                    AND relnamespace='public'::regnamespace""")
                    ).mappings()
                ]
            assert not failures, failures
            assert str(old) in observations and root_id in observations
            assert all(x["running"] <= 1 for x in locks)
            ordered = sorted(latencies)
            return dict(
                level=label,
                stocks=stocks,
                days=count,
                postgres=pg_version,
                database_settings=database_settings,
                rows=staged,
                write_seconds=write_seconds,
                rows_per_second=staged / write_seconds,
                stage_seconds=stage_seconds,
                stage_peak_process_rss_bytes=stage_peak_rss,
                publish_seconds=publish_seconds,
                rollback_probes=rollback_probes,
                final_root_status=final_root_status,
                final_ledger_state=final_ledger_state,
                peak_rss_bytes=peak_rss_bytes(),
                candidate=candidate_stats,
                preimage=preimage,
                relations=relations,
                database_before=before,
                database_after=after,
                wal_bytes=int(wal_bytes),
                reader_samples=len(ordered),
                reader_p95_ms=ordered[int((len(ordered) - 1) * 0.95)],
                reader_median_ms=statistics.median(ordered),
                reader_errors=failures,
                max_running=max([x["running"] for x in locks], default=0),
                max_lock_waiters=max([x["waiting"] for x in locks], default=0),
                plan=plan,
                public_plan=public_plan,
                publication_plan=publication_plan,
                production_capacity="UNPROVEN",
                synthetic_quality_fixture=True,
                row_budget=10000000,
                merge_timeout_ms=300000,
            )
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=30)
            assert not any(thread.is_alive() for thread in threads)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-synthetic", action="store_true", required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--levels", choices=["smoke", "all"], default="all")
    selection.add_argument("--level", choices=["L1", "L2", "L3-scaled-10pct"])
    parser.add_argument("--output", type=Path, default=Path(".codex_tmp/cold-start-capacity.json"))
    return parser.parse_args(argv)


def selected_levels(args):
    from scripts.a42_ci_contract import CAPACITY_LEVELS

    names = [args.level] if args.level else list(CAPACITY_LEVELS)[:1 if args.levels=="smoke" else 3]
    return [(*CAPACITY_LEVELS[name], name) for name in names]


def run_cli(args, result):
    global m, DataPublicationRow, JobRun, update_job, KEYS, MODELS, record_validation
    global get_settings, isolated_contract_database, candidate, sample_row

    from scripts.a42_artifacts import container_receipt, isolation
    from scripts.v14_test_database import isolated_v14_database, verified_test_url

    result.update(isolation())  # Physical proof BEFORE all DDL and application imports.
    args.progress = CapacityProgress(args.output.with_suffix(".progress.json"), result)
    if os.environ.get("A421_CONTAINER"):
        result.update(container_receipt(os.environ["A421_CONTAINER"]))
    url = verified_test_url()
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False), LLM_ENABLED="false",
                      AB_MERGE_READ_ENABLED="false")
    os.environ["TUSHARE_TOKEN"] = "synthetic-capacity-fixture"
    # Validate and override the explicit URL BEFORE importing application models,
    # Settings or app.core.db; never even construct an engine from business .env.
    from app.core.config import get_settings
    from app.models import market_data as m
    from app.models.data_publication import DataPublicationRow
    from app.models.job import JobRun
    from app.repositories.job_run import update_job
    from app.services.data_publication import KEYS, MODELS, record_validation

    from tests.integration.test_data_publication import candidate, sample_row

    isolated_contract_database = isolated_v14_database
    get_settings.cache_clear()
    from loguru import logger

    logger.remove()
    result.update(
        environment=dict(
            platform=platform.platform(),
            machine=platform.machine(),
            python=platform.python_version(),
            logical_cpus=os.cpu_count(),
        ),
    )
    from scripts.a42_artifacts import atomic, now
    from scripts.a42_receipt_contract import validate_capacity

    for stocks, days, level in selected_levels(args):
        result.update(status="INCOMPLETE", failed_phase="capacity-"+level)
        atomic(args.output, result)
        args.progress.begin_level(stocks, days, level)
        with observe_capacity(args.progress):
            result["results"].append(run_level(stocks, days, level))
        measurement = result["results"][-1]
        validate_capacity(measurement, level)
        print(
            json.dumps(
                {
                    "capacity_level_result": {
                        key: measurement[key]
                        for key in (
                            "level",
                            "stocks",
                            "days",
                            "rows",
                            "write_seconds",
                            "publish_seconds",
                            "peak_rss_bytes",
                            "wal_bytes",
                            "reader_samples",
                            "reader_p95_ms",
                            "max_running",
                            "max_lock_waiters",
                            "reader_errors",
                            "rollback_probes",
                        )
                    }
                }
            ),
            flush=True,
        )
        result["completed_groups"] = len(result["results"])
        atomic(args.output, result)
        args.progress.data["completed_levels"].append(level)
        args.progress.flush(force=True)
    result.update(status="COMPLETE", finished_at=now(), failed_phase=None)
    atomic(args.output, result)
    args.progress.data.update(status="DIAGNOSTIC_FINISHED", current_phase="finished")
    args.progress.flush(force=True)
    print(json.dumps(dict(output=str(args.output), levels=len(result["results"]))))


def main(argv=None):
    from contextlib import nullcontext

    from scripts.a42_artifacts import atomic, deadline, failure, header, install_signals, now

    args = parse_args(argv)
    result = dict(**header("capacity-"+(args.level or args.levels)),
        level=args.level, results=[], status="NOT_STARTED", started_at=now(),
        finished_at=None, expected_groups=len(selected_levels(args)), completed_groups=0)
    atomic(args.output, result)
    install_signals()
    try:
        budget = os.environ.get("A421_CAPACITY_BUDGET_MINUTES")
        with deadline(int(budget)*60) if budget else nullcontext():
            run_cli(args, result)
    except BaseException as error:
        result.update(status="INCOMPLETE", finished_at=now(), **failure(error))
        atomic(args.output, result)
        if hasattr(args, "progress"):
            args.progress.fail(error)
        if result.get("failure_code") == "V14_EXPLICIT_MARKED_PG17_REQUIRED":
            print("EXPLICIT_LOOPBACK_SYNTHETIC_TEST_DATABASE_REQUIRED", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
