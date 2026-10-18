"""Explicit, synthetic Docker acceptance. Never accepts an application/business DB URL."""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

SOURCE_DIGEST = """
import hashlib
from pathlib import Path
root = Path.cwd()
files = [p for folder,pattern in [('backend','*.py'),('migrations','*.py'),('config','*.yaml')]
         for p in (root/folder).rglob(pattern)]
files += [root/name for name in ('README.md','pyproject.toml','requirements.lock','alembic.ini')]
digest = hashlib.sha256()
for path in sorted(files):
    digest.update(path.relative_to(root).as_posix().encode() + b'\\0')
    digest.update(path.read_bytes() + b'\\0')
print(digest.hexdigest())
"""

WORKER = """
import time
from sqlalchemy import select, func, text
from app.core.db import SessionLocal
from app.models.job import JobRun
from app.repositories.job_run import update_job
from app.services import job_worker as worker

def synthetic_validation(db, job, metadata):
    db.execute(text('SELECT pg_sleep(0.4)'))
    update_job(db, job, status='SUCCESS', metadata={**metadata, 'synthetic': True})

worker.run_validate_data_job = synthetic_validation
identity = worker.worker_identity()
deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    with SessionLocal() as db:
        key = worker.claim_next_job(db, identity)
        claim = db.info.pop('data_claim', None)
    if key:
        assert claim is not None
        with SessionLocal() as db:
            worker.execute_claimed_job(db, key, expected_worker=claim[1], expected_token=claim[2])
    with SessionLocal() as db:
        done = db.scalar(select(func.count()).select_from(JobRun).where(JobRun.status == 'SUCCESS'))
    if done == 6:
        break
    time.sleep(0.05)
else:
    raise RuntimeError('SYNTHETIC_QUEUE_DEADLINE')
"""

PUBLICATION_FIXTURE = """
from datetime import UTC, datetime
from types import SimpleNamespace
from app.core.config import get_settings
from app.models import market_data as m
from app.services.data_publication import MODELS, KEYS, record_validation
from app.services.job_guard import data_queue_identity
from app.services.analysis_identity import (
 TRADE_STATUS_CALC_VERSION, FACTOR_CALC_VERSION, MARKET_CALC_VERSION,
 SECTOR_CALC_VERSION, THEME_CALC_VERSION, TREND_CALC_VERSION,
 OPPORTUNITY_CALC_VERSION, SIGNAL_CALC_VERSION)
from app.repositories.replace_slice import replace_slice_rows

def synthetic_row(model, job_id, day, value):
    versions = (TRADE_STATUS_CALC_VERSION, FACTOR_CALC_VERSION, MARKET_CALC_VERSION,
      SECTOR_CALC_VERSION, THEME_CALC_VERSION, TREND_CALC_VERSION,
      OPPORTUNITY_CALC_VERSION, SIGNAL_CALC_VERSION)
    identity = data_queue_identity()
    row = dict(trade_date=day,ts_code='TEST.SZ',sector_id=101,theme_code='TEST',
      algo_version=get_settings().algo_version,signal_type='RIGHT_SIDE_NEW',
      state='S4',opportunity_stage='TREND',eligible=True,is_active=True,
      is_suspended=False,tradable=True,strategy_eligible=True,
      calculated_at=datetime.now(UTC),calc_run_id=job_id,
      source_strategy_config_hash=identity['analysis'],
      config_hash=identity['opportunity'] if model.__tablename__ in
        {'theme_factor_daily','stock_opportunity_daily'} else identity['analysis'],
      calc_version=versions[MODELS.index(model)],adj_close=value,market_score=value,
      opportunity_score=value,heat_score=value)
    return {key:value for key,value in row.items() if key in model.__table__.c}

def synthetic_recalculation(db, job, start, end, **kwargs):
    for model in MODELS[:8]:
        replace_slice_rows(db,model,[synthetic_row(model,job.id,start,20)],
          scope_filters=[model.trade_date==start],key_columns=KEYS[model.__tablename__])
        db.commit()
    # This fixture certifies only synthetic publication protocol, not Provider or
    # business quality correctness; real quality has separate integration tests.
    record_validation(db,job.id,start,SimpleNamespace(has_error=False))
    db.commit()
    db.execute(text('SELECT pg_sleep(0.4)'))
    update_job(db,job,status='SUCCESS')
"""


def acceptance(base, workers, *, publication=False):
    from app.services.job_guard import create_queued_ingestion_job

    name = "queue_acceptance_" + uuid.uuid4().hex
    url = base.set(database=name)
    admin = sa.create_engine(base, isolation_level="AUTOCOMMIT")
    engine = None
    processes, names = [], []
    try:
        with admin.connect() as connection:
            assert connection.scalar(sa.text("SHOW server_version_num")).startswith("17")
            connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
        engine = sa.create_engine(url)
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with Session(engine) as db:
            if publication:
                from app.models.job import JobRun
                from app.models.market_data import Sector, Theme, TradeCalendar

                namespace = {}
                exec(PUBLICATION_FIXTURE, namespace)
                db.add(
                    Sector(sector_id=101, source="SW", source_code="TEST", name="test", level="L1")
                )
                db.add(Theme(theme_code="TEST", source="THS", name="test", theme_type="N"))
                old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
                db.add(old)
                db.flush()
                for day in range(1, 7):
                    target = date(2026, 9, day)
                    db.add(TradeCalendar(cal_date=target, is_open=True))
                    for model in namespace["MODELS"][:8]:
                        db.add(model(**namespace["synthetic_row"](model, old.id, target, 10)))
                db.commit()
            for day in range(1, 7):
                target = date(2026, 9, day)
                create_queued_ingestion_job(
                    db,
                    "recalculate" if publication else "validate_data",
                    target,
                    step="synthetic queued",
                    metadata={
                        "start": target.isoformat(),
                        "end": target.isoformat(),
                        "evaluate_signals": False,
                    },
                )
        worker_code = WORKER
        if publication:
            worker_code = PUBLICATION_FIXTURE + WORKER.replace(
                "worker.run_validate_data_job = synthetic_validation",
                "worker.run_recalculation = synthetic_recalculation",
            ).replace("if done == 6:", "if done == 7:")
        for _index in range(workers):
            container = f"ssh-stock-queue-test-{uuid.uuid4().hex}"
            names.append(container)
            args = [
                "docker",
                "run",
                "--rm",
                "--name",
                container,
                "--label",
                "ssh-stock-test=data-queue",
            ]
            args += ["--add-host", "host.docker.internal:host-gateway"]
            args += [
                "-e",
                "DATABASE_URL="
                + url.set(host="host.docker.internal").render_as_string(hide_password=False),
                "-e",
                "TUSHARE_TOKEN=synthetic-test-token",
                "ssh-stock-app:local",
                "python",
                "-c",
                worker_code,
            ]
            processes.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        maximum, samples, deadline = 0, 0, time.monotonic() + 60
        while time.monotonic() < deadline:
            with engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                active = connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM job_run WHERE status='RUNNING' "
                        "AND parent_job_id IS NULL"
                    )
                )
                done = connection.scalar(
                    sa.text("SELECT count(*) FROM job_run WHERE status='SUCCESS'")
                )
                if publication:
                    # All eight public tables must agree for each date, even
                    # while two containers compete and B commits checkpoints.
                    source_union = " UNION ALL ".join(
                        f"SELECT trade_date,calc_run_id FROM {model.__tablename__}"
                        for model in namespace["MODELS"][:8]
                    )
                    assert not connection.execute(
                        sa.text(
                            f"SELECT trade_date FROM ({source_union}) sources GROUP BY trade_date "
                            "HAVING count(*) <> 8 OR count(DISTINCT calc_run_id) <> 1"
                        )
                    ).first(), "SYNTHETIC_MIXED_PUBLICATION"
            maximum = max(maximum, active)
            samples += 1
            assert active <= 1, "SYNTHETIC_DATA_LANE_DOUBLE_WRITER"
            if done == (7 if publication else 6):
                break
            for process in processes:
                if process.poll() not in (None, 0):
                    _, errors = process.communicate()
                    raise AssertionError("SYNTHETIC_WORKER_EXITED: " + errors.decode()[-2000:])
            time.sleep(0.05)
        else:
            raise AssertionError("SYNTHETIC_QUEUE_NOT_FINISHED")
        for process in processes:
            _, errors = process.communicate(timeout=15)
            assert process.returncode == 0, errors.decode()[-1000:]
        assert maximum == 1
        if publication:
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        sa.text("SELECT count(*) FROM data_publication WHERE state='PUBLISHED'")
                    )
                    == 6
                )
        return {
            "workers": workers,
            "completed": done,
            "max_top_level_running": maximum,
            "samples": samples,
            "synthetic": True,
            "atomic_publication": publication,
        }
    finally:
        # Only names generated here, only disposable labelled test containers.
        for container in names:
            label = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "ssh-stock-test"}}',
                    container,
                ],
                capture_output=True,
                text=True,
            )
            if label.returncode == 0:
                assert label.stdout.strip() == "data-queue"
                subprocess.run(
                    ["docker", "stop", "--time", "5", container], capture_output=True, check=True
                )
        for process in processes:
            process.communicate(timeout=15)
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    base = make_url(os.environ["TEST_DATABASE_URL"])
    assert base.host in {"127.0.0.1", "localhost"}, "ISOLATED_LOOPBACK_TEST_DATABASE_REQUIRED"
    assert base.database in {"stock_test", "stock_db"}, "EXPLICIT_TEST_DATABASE_REQUIRED"
    assert os.environ.get("DATABASE_URL") == os.environ["TEST_DATABASE_URL"]
    expected_source = subprocess.check_output(
        [sys.executable, "-c", SOURCE_DIGEST], text=True
    ).strip()
    image_source = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "ssh-stock-app:local",
            "python",
            "-c",
            SOURCE_DIGEST,
        ],
        text=True,
    ).strip()
    assert image_source == expected_source, "ACCEPTANCE_IMAGE_SOURCE_MISMATCH_REBUILD_REQUIRED"
    results = [acceptance(base, workers) for workers in (1, 2)]
    results.append(acceptance(base, 2, publication=True))
    output = Path(".codex_tmp/data-queue-containers.json")
    output.parent.mkdir(exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert not os.environ.get("GITHUB_SHA") or os.environ["GITHUB_SHA"] == head
    output.write_text(
        json.dumps(
            {
                "results": results,
                "head_sha": head,
                "image_source_sha256": image_source,
                "working_tree_dirty": bool(
                    subprocess.check_output(["git", "status", "--short"], text=True)
                ),
                "image_id": subprocess.check_output(
                    ["docker", "image", "inspect", "ssh-stock-app:local", "--format", "{{.Id}}"],
                    text=True,
                ).strip(),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(results))


if __name__ == "__main__":
    main()
