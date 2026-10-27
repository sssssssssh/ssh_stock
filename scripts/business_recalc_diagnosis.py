"""One registered, million-Raw SQL diagnosis on an explicitly marked synthetic PG17.

This is not a Worker matrix or a performance gate. No business .env is loaded.
Only the existing isolation helper creates/drops its own UUID database.
"""

import argparse
import hashlib
import json
import os
import shutil
from datetime import date
from pathlib import Path
from time import monotonic


class ResourceDeferred(RuntimeError):
    pass


def persist(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, default=str, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def check_disk(path, *, minimum=8 * 1024**3):
    free = shutil.disk_usage(path).free
    if free < minimum:
        raise ResourceDeferred("SYNTHETIC_DISK_RESERVE_EXHAUSTED")
    return free


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("existing evidence cannot be overwritten")
    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()  # Before settings/app imports and any DDL.
    os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),
                      TUSHARE_TOKEN="synthetic-business-diagnosis", LLM_ENABLED="false")
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    import pytest
    from app.core.config import get_settings
    from app.models.job import JobRun
    from app.services.calculation_policy import runtime_source
    from app.services.factors.input_window import FactorInputWindow
    from sqlalchemy import event, text

    from scripts.v14_test_database import isolated_v14_database
    from tests.integration.test_data_publication import candidate

    report = dict(schema="biz-perf-01.sql-diagnosis.v1", status="INCOMPLETE",
                  performance_status="PERFORMANCE_OPEN", matrix_status="NOT_RUN",
                  cloud_access=False, source=runtime_source(), statements=[], stages=[],
                  plans=[], limitations=["SQL diagnosis only; not ten-table financial acceptance",
                      "EXPLAIN ANALYZE is a separate replay, never added to stage wall time",
                      "cache uncontrolled; no causal or stable P95 claim from one trial"])
    persist(args.output, report)
    patch = pytest.MonkeyPatch()
    try:
        with isolated_v14_database(patch) as (factory, engine):
            # pg's actual data directory belongs to this verified physical instance.
            with factory() as db:
                directory = db.scalar(text("SHOW data_directory"))
                report["server_version"] = db.scalar(text("SHOW server_version"))
                report["disk_before_bytes"] = check_disk(directory)
                report["settings"] = {name: db.scalar(text("SELECT current_setting(:name)"),
                    {"name": name}) for name in ("shared_buffers", "work_mem", "max_wal_size",
                                                  "temp_file_limit", "max_connections")}
                old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
                db.add(old)
                db.flush()
                old_id = old.id
                db.execute(text("""INSERT INTO stock_basic(ts_code,list_status,list_date,exchange)
                    SELECT lpad(i::text,6,'0')||'.SZ','L','2020-01-01','SZSE'
                    FROM generate_series(1,1000) i"""))
                db.commit()
            seed_start = monotonic()
            for year in range(2022, 2026):
                with factory() as db:
                    db.execute(text("SET LOCAL statement_timeout='300000'"))
                    # Vary prices/volumes deterministically; no source facts are invented
                    # outside this UUID-owned database. SQL has no business connection.
                    db.execute(text("""INSERT INTO stock_daily
                        (trade_date,ts_code,open,high,low,close,pre_close,pct_chg,vol,amount)
                        SELECT d::date,c.ts_code,20+i%10,21+i%10,19+i%10,20+i%10,
                               20+i%10,0,100000+i,1000000+i
                        FROM generate_series(CAST(:lo AS date),CAST(:hi AS date),'1 day') d
                        CROSS JOIN (SELECT ts_code,row_number() OVER(ORDER BY ts_code) i
                                    FROM stock_basic) c WHERE extract(isodow FROM d)<6"""),
                               {"lo": f"{year}-01-01", "hi": f"{year}-12-31"})
                    db.commit()
                check_disk(directory)
                report["seeded_through_year"] = year
                persist(args.output, report)
            with factory() as db:
                db.execute(text("SET LOCAL statement_timeout='300000'"))
                db.execute(text("""INSERT INTO stock_adj_factor
                    SELECT trade_date,ts_code,1 FROM stock_daily"""))
                db.execute(text("""INSERT INTO stock_trade_status_daily
                    (trade_date,ts_code,is_active,is_suspended,is_st,st_status_unknown,
                     tradable,strategy_eligible,calc_version,config_hash,calc_run_id,calculated_at)
                    SELECT trade_date,ts_code,true,false,false,false,true,true,'diagnostic-v1',
                           repeat('a',64),:source,'2026-10-27 00:00:00+00' FROM stock_daily"""),
                           {"source": old_id})
                for code in get_settings().strategy["benchmark"]["market_indices"]:
                    db.execute(text("""INSERT INTO index_daily(trade_date,ts_code,close,pre_close)
                        SELECT DISTINCT trade_date,:code,100,100 FROM stock_daily"""),
                               {"code": code})
                db.commit()
                for name in ("stock_daily", "stock_adj_factor", "stock_basic",
                             "stock_trade_status_daily", "index_daily"):
                    db.execute(text(f'ANALYZE public."{name}"'))
                db.commit()
                report["raw_daily_rows"] = db.scalar(text("SELECT count(*) FROM stock_daily"))
                if report["raw_daily_rows"] < 1_000_000:
                    raise ValueError("BUSINESS_MILLION_ROWS_REQUIRED")
                report["database_bytes"] = db.scalar(text(
                    "SELECT pg_database_size(current_database())"))
            report["seed_seconds"] = monotonic() - seed_start
            report["disk_after_seed_bytes"] = check_disk(directory)
            persist(args.output, report)
            with candidate(factory, engine, start=date(2024, 1, 1),
                           end=date(2025, 12, 31)) as (db, job):
                # Actual production implementation, no SQL rewrite and no publication.
                window = FactorInputWindow(db, job.id, get_settings())
                captured = []

                def before(conn, cursor, sql, params, context, many):
                    if sql.lstrip().startswith("SELECT") and "sha256" in sql:
                        captured.append((sql, params))

                event.listen(engine, "before_cursor_execute", before)
                try:
                    for label, lo, hi in (
                        ("initial", date(2022, 11, 27), date(2024, 1, 31)),
                        ("expansion", date(2023, 1, 27), date(2024, 3, 31)),
                        ("final_span", date(2024, 10, 27), date(2025, 12, 31)),
                    ):
                        captured.clear()
                        began = monotonic()
                        window.prepare(lo, hi)
                        report["stages"].append(dict(name=label, wall_seconds=monotonic()-began,
                            verified_start=window.start, verified_end=window.end,
                            fingerprint_queries=len(captured)))
                        report["statements"].extend(dict(stage=label,
                            sql=sql, sha256=hashlib.sha256(sql.encode()).hexdigest())
                            for sql, _ in captured)
                        # Replay only SELECTs under the same SHARE lock and snapshot.
                        replay = list(captured)
                        for number, (sql, params) in enumerate(replay):
                            plan = db.connection().exec_driver_sql(
                                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params).scalar()
                            report["plans"].append(dict(stage=label, query=number, plan=plan))
                        db.commit()
                        check_disk(directory)
                        persist(args.output, report)
                    captured.clear()
                    began = monotonic()
                    window.close()
                    charges = []
                    window.verify(publish_budget=lambda: charges.append(1))
                    report["stages"].append(dict(name="independent_final_verify",
                        wall_seconds=monotonic()-began, original_budget_charges=len(charges),
                        fingerprint_queries=len(captured)))
                finally:
                    event.remove(engine, "before_cursor_execute", before)
                    window.close()
            report["status"] = "DIAGNOSIS_COMPLETE_NOT_CAPACITY_ACCEPTANCE"
            report["disk_final_bytes"] = check_disk(directory)
    except BaseException as error:
        report["status"] = "RESOURCE_DEFERRED" if isinstance(error, ResourceDeferred) else "FAILED"
        report["failure_class"] = type(error).__name__
        report["failure_sqlstate"] = getattr(getattr(error, "orig", None), "sqlstate", None)
        # Error messages may contain SQL or credentials; never retain them.
        raise
    finally:
        patch.undo()
        persist(args.output, report)


if __name__ == "__main__":
    main()
