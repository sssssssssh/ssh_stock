"""Explicit, synthetic PG17 business measurement; never reads .env.

Run in a fresh process. TEST_DATABASE_URL, marker and physical ID are mandatory.
The existing isolation helper owns and removes only its UUID database.
"""

import argparse
import cProfile
import functools
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic, process_time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=int, default=4)
    parser.add_argument("--months", type=int, choices=(1, 3, 12), default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.stocks <= 5000:
        parser.error("stocks must be between 1 and 5000")
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()  # Before importing any business/settings module.
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["TUSHARE_TOKEN"] = "synthetic-business-performance"
    os.environ["LLM_ENABLED"] = "false"
    os.environ["FACTOR_INPUT_REUSE_ENABLED"] = str(args.optimized).lower()
    os.environ["RAW_PREFLIGHT_BATCH_ENABLED"] = str(args.optimized).lower()
    os.environ["FACTOR_CPU_OPTIMIZATION_ENABLED"] = str(args.optimized).lower()
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    import psycopg
    import pytest
    from app.core.config import ROOT_DIR, get_settings
    from app.models import market_data as m
    from app.models.data_publication import DataPublication
    from app.models.job import JobRun
    from app.services.calculation_progress import ProgressStep
    from app.services.data_publication import MODELS
    from app.services.job_worker import claim_next_job, execute_claimed_job
    from app.services.recalculation import create_recalculation_job
    from sqlalchemy import DateTime, event, insert, text

    search_path = list(sys.path)
    from scripts.publication_candidate_benchmark_v13 import rss_bytes

    sys.path[:] = search_path
    from scripts.v14_test_database import isolated_v14_database

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "diff", "--name-only"], text=True).strip())
    report = {"schema": "biz-perf-01.v1", "head_sha": head, "dirty_tree": dirty,
              "optimized": args.optimized, "stocks": args.stocks, "months": args.months,
              "environment": platform.platform(), "status": "PERFORMANCE_OPEN",
              "cloud_status": "REAL_CLOUD_RECALC_NOT_AUTHORIZED", "runs": []}
    source_files = {}
    canonical_sources = {}
    for directory in ("backend", "config", "migrations"):
        for path in sorted((ROOT_DIR / directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".yaml"}:
                content = path.read_bytes()
                key = path.relative_to(ROOT_DIR).as_posix()
                source_files[key] = hashlib.sha256(content).hexdigest()
                canonical_sources[key] = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
    report["implementation_sources"] = source_files
    report["implementation_sha256"] = hashlib.sha256(json.dumps(
        source_files, sort_keys=True).encode()).hexdigest()
    report["git_text_sources_sha256"] = hashlib.sha256(json.dumps(
        canonical_sources, sort_keys=True).encode()).hexdigest()
    report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes().replace(
        b"\r\n", b"\n")).hexdigest()
    report["observation_limits"] = [
        "loopback, not WAN throughput", "driver execution is not exclusive server CPU",
        "progress rows are delivered rows, not wire bytes", "RSS is process-lifetime peak",
        "inclusive stages overlap; do not sum as exclusive overall",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    try:
        with isolated_v14_database(monkeypatch) as (factory, engine):
            # Heartbeat and checkpoint must use the SAME newly-owned test DB.
            monkeypatch.setattr("app.services.job_worker.SessionLocal", factory)
            settings = get_settings()
            if settings.ab_merge_read_enabled:
                raise RuntimeError("BUSINESS_MEASUREMENT_AB_MUST_REMAIN_OFF")
            from app.services.job_guard import data_queue_identity

            report["financial_identity"] = data_queue_identity()
            report["cpu_count"] = os.cpu_count()
            start = date(2025, 1, 1)
            end = date(2025, args.months + 1, 1) - timedelta(days=1) if args.months < 12 \
                else date(2025, 12, 31)
            first = start - timedelta(days=900)
            days = [first + timedelta(days=i) for i in range((end - first).days + 1)]
            opens = [day for day in days if day.weekday() < 5]
            codes = [f"{i:06d}.SZ" for i in range(1, args.stocks + 1)]
            frozen = datetime(2026, 10, 27, tzinfo=UTC)

            def seed_rows(db, model, rows):
                timestamp_columns = [c.name for c in model.__table__.columns
                                     if isinstance(c.type, DateTime)]
                for row in rows:
                    for column in timestamp_columns:
                        row.setdefault(column, frozen)
                if rows:
                    db.execute(insert(model), rows)

            with factory() as db:
                seed_rows(db, m.TradeCalendar, [dict(cal_date=d, is_open=d.weekday() < 5)
                                               for d in days])
                seed_rows(db, m.StockBasic, [dict(ts_code=c, name="synthetic",
                    list_status="L", list_date=first, exchange="SZSE") for c in codes])
                seed_rows(db, m.Sector, [dict(sector_id=101, source="SW", source_code="BIZ",
                                            name="synthetic", level="L1")])
                db.flush()
                seed_rows(db, m.SectorMember, [dict(sector_id=101, ts_code=c,
                                                   valid_from=first) for c in codes])
                for day_index, day in enumerate(opens):
                    rows = [dict(trade_date=day, ts_code=c, open=20, high=20.1,
                                 low=19.9, close=20, pre_close=20, pct_chg=0,
                                 vol=100000, amount=1000000) for c in codes]
                    seed_rows(db, m.StockDaily, rows)
                    seed_rows(db, m.StockAdjFactor, [dict(trade_date=day, ts_code=c,
                                                        adj_factor=1) for c in codes])
                    seed_rows(db, m.StockDailyBasic, [dict(trade_date=day, ts_code=c,
                        close=20, total_mv=1000000, circ_mv=1000000) for c in codes])
                    seed_rows(db, m.StockLimitDaily, [dict(trade_date=day, ts_code=c,
                        pre_close=20, up_limit=22, down_limit=18) for c in codes])
                    seed_rows(db, m.IndexDaily, [{**rows[0], "ts_code": c}
                        for c in settings.strategy["benchmark"]["market_indices"]])
                    seed_rows(db, m.DataQualityDaily, [dict(trade_date=day, dataset=d,
                        status="PASS", expected_rows=0, actual_rows=0)
                        for d in ("stock_st", "suspend_d")])
                    if day_index % 30 == 0:
                        db.commit()
                db.commit()
                report["server_version"] = db.scalar(text("SHOW server_version"))
            report["raw_daily_rows"] = len(opens) * len(codes)
            report["dataset_protocol"] = "constant-price-frozen-audit-v2"
            report["raw_snapshot"] = {}
            with factory() as db:
                db.execute(text("SET LOCAL statement_timeout='300000'"))
                for model in (m.StockBasic, m.TradeCalendar, m.StockDaily, m.StockAdjFactor,
                              m.StockDailyBasic, m.StockLimitDaily, m.IndexDaily,
                              m.StockStDaily, m.StockSuspendDaily, m.DataQualityDaily,
                              m.Sector, m.SectorMember):
                    name = model.__tablename__
                    order = ",".join(f'a."{c.name}"' for c in model.__table__.primary_key)
                    day = 'a."trade_date"' if "trade_date" in model.__table__.c else "NULL::date"
                    value = db.execute(text(f"""SELECT COALESCE(sum(n),0),
                        encode(sha256(convert_to(COALESCE(string_agg(digest,'' ORDER BY day),''),
                        'UTF8')),'hex') FROM (SELECT {day} AS day, count(*) n,
                          encode(sha256(convert_to(string_agg(encode(sha256(convert_to(
                            to_jsonb(a)::text,'UTF8')),'hex'),'' ORDER BY {order}),
                          'UTF8')),'hex') digest FROM public.\"{name}\" a GROUP BY {day}) q"""
                    )).one()
                    report["raw_snapshot"][name] = dict(rows=int(value[0]), sha256=value[1])
            from app.services.recalculation import _factor_warmup_start, _month_chunks

            with factory() as db:
                warmup = _factor_warmup_start(db, start)
            report["windows"] = dict(request_start=start.isoformat(), request_end=end.isoformat(),
                warmup_start=warmup.isoformat(), factor_chunks=[dict(start=lo.isoformat(),
                    end=hi.isoformat(), input_start=(lo - timedelta(days=430)).isoformat())
                    for lo, hi in _month_chunks(warmup, end)])
            report["dataset_sha256"] = hashlib.sha256(json.dumps(
                report["raw_snapshot"], sort_keys=True,
            ).encode()).hexdigest()
            counts = Counter()
            seconds = Counter()
            stages = Counter()
            delivered_rows = Counter()
            sql_by_stage, seconds_by_stage = Counter(), Counter()
            sql_digests, sql_failures = Counter(), []
            fetches = []
            recent_stage = {"name": "job.orchestration"}
            for cursor_class in (psycopg.Cursor, psycopg.ServerCursor):
                for method_name in ("fetchone", "fetchmany", "fetchall"):
                    method = getattr(cursor_class, method_name)

                    def observe_fetch(original, cursor_kind, operation):
                        @functools.wraps(original)
                        def fetch(cursor, *values, **keywords):
                            began = monotonic()
                            result = original(cursor, *values, **keywords)
                            elapsed = monotonic() - began
                            number = (int(result is not None) if operation == "fetchone"
                                      else len(result))
                            first_row = (result if operation == "fetchone" else result[0]) \
                                if number else ()
                            estimate = sum(
                                len(v.encode("utf-8")) if isinstance(v, str)
                                else 1 if v is None or isinstance(v, bool) else 8
                                for v in first_row)
                            fetches.append(dict(stage=recent_stage["name"], cursor=cursor_kind,
                                operation=operation, rows=number, seconds=elapsed,
                                scalar_payload_estimate_bytes=estimate * number))
                            if len(fetches) > 100000:
                                raise RuntimeError("BUSINESS_MEASUREMENT_FETCH_EVIDENCE_BUDGET")
                            return result
                        return fetch

                    monkeypatch.setattr(cursor_class, method_name,
                        observe_fetch(method, cursor_class.__name__, method_name))
            rr_checks = []
            plan_input = {}
            capture_plan = {"lookup": False}
            cache_peak = {"bytes": 0}
            from app.services.factors.service import FactorService

            calculate = FactorService.recalc

            @functools.wraps(calculate)
            def observed_recalc(service, *values, **keywords):
                try:
                    return calculate(service, *values, **keywords)
                finally:
                    window = getattr(service, "input_window", None)
                    cache_peak["bytes"] = max(cache_peak["bytes"],
                        getattr(window, "peak_bytes", 0))

            monkeypatch.setattr(FactorService, "recalc", observed_recalc)
            original_report = ProgressStep.report

            def observe_step(step, phase, **kwargs):
                recent_stage["name"] = step.name
                previous_phase, operation_started = step.phase, step.operation_started
                original_report(step, phase, **kwargs)
                if phase == "complete":
                    stages[step.name] += monotonic() - step.started
                    delivered_rows[step.name] += kwargs.get("completed_rows", 0)
                    if step.kind == "publish":
                        stages["publish_inclusive"] += monotonic() - step.started
                if phase == "store" and step.kind == "publish" \
                        and previous_phase == "lookup_published":
                    stages["preimage_verify_inclusive"] += monotonic() - operation_started
                if phase == "complete" and step.name == "market.factors":
                    with engine.connect().execution_options(
                            isolation_level="REPEATABLE READ") as reader:
                        reader.execute(text("SET TRANSACTION READ ONLY"))
                        rr_checks.append(reader.scalar(text(
                            "SELECT count(*) FROM public.stock_factor_daily")) == 0)

            monkeypatch.setattr(ProgressStep, "report", observe_step)
            from app.services.data_publication import PublicationWorkspace

            for method_name in ("_lookup_batch", "_store_batch"):
                original = getattr(PublicationWorkspace, method_name)

                def instrument(method, label):
                    @functools.wraps(method)
                    def measured(*values, **keywords):
                        began = monotonic()
                        previous = recent_stage["name"]
                        recent_stage["name"] = label
                        capture_plan["lookup"] = label == "candidate_lookup_batch"
                        try:
                            return method(*values, **keywords)
                        finally:
                            stages[label] += monotonic() - began
                            capture_plan["lookup"] = False
                            recent_stage["name"] = previous
                    return measured

                monkeypatch.setattr(PublicationWorkspace, method_name,
                                    instrument(original, "candidate" + method_name))

            def before(conn, cursor, statement, parameters, context, many):
                context.biz_started = monotonic()
                context.biz_stage = context.execution_options.get(
                    "calculation_query_name", recent_stage["name"])
                operation = statement.lstrip().split(None, 1)[0].upper()
                counts[operation] += 1
                sql_by_stage[context.biz_stage] += 1
                sql_digests[hashlib.sha256(statement.encode()).hexdigest()] += 1
                if (capture_plan["lookup"] and not plan_input
                        and statement.lstrip().startswith("WITH")):
                    plan_input.update(statement=statement, parameters=parameters)

            def after(conn, cursor, statement, parameters, context, many):
                # Only fixed SQL operation labels, never SQL or bind values.
                operation = statement.lstrip().split(None, 1)[0].upper()
                seconds[operation] += monotonic() - context.biz_started
                seconds_by_stage[context.biz_stage] += monotonic() - context.biz_started

            def failed(context):
                sql_failures.append(dict(error_class=type(context.original_exception).__name__,
                    sqlstate=getattr(context.original_exception, "sqlstate", None)))

            event.listen(engine, "before_cursor_execute", before)
            event.listen(engine, "after_cursor_execute", after)
            event.listen(engine, "handle_error", failed)
            started, cpu = monotonic(), process_time()
            profile = cProfile.Profile()
            if args.profile:
                profile.enable()
            with factory() as db:
                job = create_recalculation_job(db, start=start, end=end,
                    evaluate_signals=False, mode="manual")
                identity = claim_next_job(db, "biz-perf-isolated")
                db.refresh(job)
                execute_claimed_job(db, identity, expected_worker=job.worker_id,
                                    expected_token=job.execution_token)
                db.expire_all()
                result = db.get(JobRun, job.id)
                ledger = db.get(DataPublication, job.id)
                profile.disable()
                if args.profile:
                    profile.dump_stats(str(args.output.with_suffix(".prof")))
                report["runs"].append(dict(overall=monotonic() - started,
                    cpu=process_time() - cpu, job_status=result.status,
                    publication_state=ledger.state if ledger else None,
                    error=result.error_message, sql_counts=dict(counts),
                    sql_driver_seconds=dict(seconds), stage=result.step,
                    stage_seconds=dict(stages), delivered_rows=dict(delivered_rows)))
                report["runs"][-1].update(sql_by_stage=dict(sql_by_stage),
                    sql_driver_seconds_by_stage=dict(seconds_by_stage),
                    sql_digests=dict(sql_digests), sql_failures=sql_failures.copy())
                report["fetches"] = fetches.copy()
                report["peak_process_rss_bytes"] = rss_bytes()
                report["peak_retained_input_bytes"] = cache_peak["bytes"]
                report["independent_rr_readers_no_candidate_leak"] = (
                    bool(rr_checks) and all(rr_checks))
                report["tables"] = {}
                for model in MODELS:
                    name = model.__tablename__
                    # Normalize only this root UUID; preserve NULL/other sources,
                    # SERIAL IDs, natural keys and every financial field.
                    payload = "to_jsonb(t)-'calculated_at'-'checked_at'-'created_at'"
                    for field in ("calc_run_id", "job_id"):
                        if field in model.__table__.c:
                            payload = (f"jsonb_set({payload}, '{{{field}}}', CASE WHEN "
                                f"t.{field}=:root THEN '\"ROOT\"'::jsonb ELSE "
                                f"COALESCE(to_jsonb(t.{field}), 'null'::jsonb) END)")
                    digest = db.scalar(text(f"""SELECT encode(sha256(convert_to(COALESCE(
                        string_agg(payload, '' ORDER BY payload), ''),'UTF8')),'hex') FROM (
                        SELECT ({payload})::text payload
                        FROM public.\"{name}\" t) q"""), {"root": job.id})
                    report["tables"][name] = digest
                report["root_row_counts"] = ledger.row_counts if ledger else None
                report["candidate_source_mismatches"] = db.scalar(text("""SELECT count(*)
                    FROM public.data_publication_row WHERE publication_id=:root
                    AND source_id IS DISTINCT FROM :root"""), {"root": job.id})
            if plan_input:
                # Untimed: only the original SELECT from our disposable synthetic DB.
                with engine.connect() as connection:
                    raw_plan = connection.exec_driver_sql(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + plan_input["statement"],
                        plan_input["parameters"]).scalar_one()

                def sanitized_plan(value):
                    allowed = {"Plan", "Plans", "Node Type", "Relation Name", "Index Name",
                        "Actual Rows", "Actual Loops", "Execution Time", "Planning Time",
                        "Shared Hit Blocks", "Shared Read Blocks", "Temp Read Blocks",
                        "Temp Written Blocks", "Actual Total Time", "Actual Startup Time"}
                    if isinstance(value, dict):
                        return {k: sanitized_plan(v) for k, v in value.items() if k in allowed}
                    if isinstance(value, list):
                        return [sanitized_plan(v) for v in value]
                    return value

                report["untimed_candidate_lookup_plan"] = sanitized_plan(raw_plan)
    except Exception as exc:
        report["failure_class"] = type(exc).__name__
        raise
    finally:
        monkeypatch.undo()
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runs": report["runs"]}))
    if any(r["job_status"] != "SUCCESS" or r["publication_state"] != "PUBLISHED"
           for r in report["runs"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
