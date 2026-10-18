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


def acceptance(base, workers):
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
            for day in range(1, 7):
                target = date(2026, 9, day)
                create_queued_ingestion_job(
                    db,
                    "validate_data",
                    target,
                    step="synthetic queued",
                    metadata={"start": target.isoformat(), "end": target.isoformat()},
                )
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
                WORKER,
            ]
            processes.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        maximum, samples, deadline = 0, 0, time.monotonic() + 60
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                active = connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM job_run WHERE status='RUNNING' "
                        "AND parent_job_id IS NULL"
                    )
                )
                done = connection.scalar(
                    sa.text("SELECT count(*) FROM job_run WHERE status='SUCCESS'")
                )
            maximum = max(maximum, active)
            samples += 1
            assert active <= 1, "SYNTHETIC_DATA_LANE_DOUBLE_WRITER"
            if done == 6:
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
        return {
            "workers": workers,
            "completed": done,
            "max_top_level_running": maximum,
            "samples": samples,
            "synthetic": True,
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
    results = [acceptance(base, workers) for workers in (1, 2)]
    output = Path(".codex_tmp/data-queue-containers.json")
    output.parent.mkdir(exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert not os.environ.get("GITHUB_SHA") or os.environ["GITHUB_SHA"] == head
    output.write_text(
        json.dumps(
            {
                "results": results,
                "head_sha": head,
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
