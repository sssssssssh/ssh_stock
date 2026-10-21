"""Atomic bounded checkpoints shared by laboratory CLIs (never imported by app)."""

import gzip
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.a42_ci_contract import BASELINE_SHA, SCHEMA_VERSION, digest, fixture_recipe
from scripts.a42_receipt_contract import require


def now():
    return datetime.now(UTC).isoformat()


def without_query_parameters(value):
    """Strip bind-value blocks, never plan nodes/counters or DECLARE evidence."""
    if isinstance(value, dict):
        return {k:without_query_parameters(v) for k,v in value.items() if k != "Query Parameters"}
    if isinstance(value, (list, tuple)):
        return [without_query_parameters(v) for v in value]
    return value


def contains_query_parameters(value):
    if isinstance(value, dict):
        return ("Query Parameters" in value
                or any(contains_query_parameters(v) for v in value.values()))
    return isinstance(value, (list, tuple)) and any(contains_query_parameters(v) for v in value)


def atomic(path, value, *, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(without_query_parameters(value), default=str, allow_nan=False,
                      separators=(",", ":"))+"\n").encode()
    data = gzip.compress(raw, mtime=0) if compressed else raw
    temporary = path.with_suffix(path.suffix+".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(data).hexdigest()


def model_hash():
    return hashlib.sha256(subprocess.check_output([
        "git", "ls-tree", "-r", "HEAD", "backend/app/models", "migrations", "config"
    ])).hexdigest()


def header(job_id):
    return dict(schema_version=SCHEMA_VERSION, baseline_sha=BASELINE_SHA,
        head_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        working_tree_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"])),
        job_id=job_id, attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "local-1"),
        run_id=os.environ.get("GITHUB_RUN_ID", "local"), model_hash=model_hash(),
        production_read_authorized=False, authorize_a4_3=False,
        read_performance_pass="NOT_CLAIMED")


def isolation():
    # No Settings imports before the physical proof; all subsequent DDL helpers
    # independently repeat this validation, including before owned-child DROP.
    from sqlalchemy import create_engine, text

    from scripts.v14_test_database import verified_test_url

    url = verified_test_url()
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as db:
            marker = db.scalar(text("SELECT current_setting('v14.test_instance')"))
            system = db.scalar(text("SELECT system_identifier::text FROM pg_control_system()"))
            version = db.scalar(text("SHOW server_version"))
    finally:
        engine.dispose()
    return dict(database_instance=marker, physical_system_identifier=system,
        postgres_version=version, isolation=dict(verified=True, before_ddl=True,
            expected_marker=os.environ["V14_TEST_INSTANCE"], observed_marker=marker,
            expected_system_identifier=os.environ["V14_TEST_SYSTEM_IDENTIFIER"],
            observed_system_identifier=system))


def container_receipt(name, *, read=False):
    from sqlalchemy.engine import make_url

    info = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
    labels = info.get("Config", {}).get("Labels", {})
    require(labels.get("purpose") == "ssh-stock-a4-physical-test"
            and labels.get("stage") == "A4-2.1", "NOT_AN_OWNED_A421_INSTANCE")
    port = str(make_url(os.environ["TEST_DATABASE_URL"]).port)
    require(any(p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == port
                for p in info["NetworkSettings"]["Ports"].get("5432/tcp", [])),
            "RESOURCE_PROOF_NOT_THE_TEST_TARGET")
    resources = dict(cpu_limit=info["HostConfig"]["NanoCpus"]/10**9,
                     memory_bytes=info["HostConfig"]["Memory"])
    if read:
        require(resources == dict(cpu_limit=2, memory_bytes=3*1024**3), "RESOURCE_CLASS_MISMATCH")
    return dict(resources=resources, image_id=info["Image"],
                configured_image=info["Config"]["Image"],
                resource_class="a42-pg17-2cpu-3g" if read else "capacity-dedicated-host")


class BudgetExhausted(RuntimeError):
    pass


class JobCancelled(BaseException):
    pass


def failure(error):
    import traceback

    from scripts.a42_receipt_contract import ReceiptError

    message = str(error)
    allowed = (isinstance(error, ReceiptError) or message.startswith(
        ("A42_", "A4_", "V14_", "PUBLICATION_", "RESOURCE_DEFERRED")))
    code = message if allowed and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", message) else None
    budget_exhausted = (isinstance(error, BudgetExhausted)
                        or getattr(error, "a421_budget_exhausted", False) is True)
    if budget_exhausted:
        code = "RESOURCE_DEFERRED"
    return dict(failure_type=type(error).__name__, failure_code=code,
        budget_exhausted=budget_exhausted,
        sqlstate=getattr(getattr(error, "orig", error), "sqlstate", None),
        failure_trace=[dict(file=Path(f.filename).name, line=f.lineno, function=f.name)
                       for f in traceback.extract_tb(error.__traceback__)])


def interrupted(signum, frame):
    raise JobCancelled()


@contextmanager
def deadline(seconds):
    """Whole-workload soft deadline, including seed/probes; SQL budgets unchanged.

    CI Linux supports setitimer. Do not promise an interruptible budget on an
    unsupported runner, and do not leave a timer/handler in subsequent tests.
    """
    require(hasattr(signal, "setitimer") and seconds > 0, "SOFT_DEADLINE_UNSUPPORTED")
    previous = signal.getsignal(signal.SIGALRM)
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "NESTED_DEADLINE_NOT_ALLOWED")
    budget_exhausted = False
    def exhausted(signum, frame):
        nonlocal budget_exhausted
        budget_exhausted = True
        raise BudgetExhausted("RESOURCE_DEFERRED")
    signal.signal(signal.SIGALRM, exhausted)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    except BaseException as error:
        # A driver rollback/close exception can replace the original SIGALRM.
        # Preserve the terminal exception and its SQLSTATE, but retain proof
        # from the timer itself; never infer resource exhaustion from elapsed time.
        if budget_exhausted:
            error.a421_budget_exhausted = True
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def install_signals():
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)


class Writer:
    def __init__(self, path, job_id, groups, *, minutes):
        self.path, self.groups = Path(path), {g.id:g for g in groups}
        require(not self.path.exists(), "OUTPUT_ALREADY_EXISTS_NO_IMPLICIT_RESUME")
        self.started, self.deadline = time.monotonic(), time.monotonic()+minutes*60
        self.manifest = dict(**header(job_id), status="NOT_STARTED", started_at=now(),
            finished_at=None, expected_groups=len(groups), completed_groups=0,
            entries={g.id:dict(group=asdict(g), status="NOT_STARTED") for g in groups})
        self.current = None
        self.flush()

    def flush(self):
        self.manifest["elapsed_seconds"] = time.monotonic()-self.started
        atomic(self.path, self.manifest)

    def begin(self, group):
        # Reserve 10 min for cleanup/upload; don't start a group without at
        # least another 10 min. This never changes SQL's individual 300s budget.
        if time.monotonic()+1200 >= self.deadline:
            raise BudgetExhausted("RESOURCE_DEFERRED")
        require(group.id in self.groups and self.current is None, "INVALID_GROUP_START")
        entry = self.manifest["entries"][group.id]
        require(entry["status"] == "NOT_STARTED", "GROUP_ALREADY_ATTEMPTED")
        entry.update(status="INCOMPLETE", started_at=now())
        self.current = group.id
        self.manifest.update(status="INCOMPLETE", failed_phase="group_running")
        self.flush()

    def checkpoint(self, output):
        # No growing runs/plans arrays in checkpoints. Each completed raw group
        # is stored exactly once in a separate gzip; small setup metadata only.
        self.manifest["last_phase"] = output.get("phase", "initialization")
        self.manifest["last_successful_group"] = self.manifest.get("last_successful_group")
        metadata = {k:v for k,v in output.items() if k not in (
            "runs", "plans", "monthly", "windows", "source_contract")}
        fixture = output.get("fixture", {})
        name = (f"setup-{fixture.get('coverage', 'pending')}-"
                f"{fixture.get('tombstone_percent', 'pending')}")
        checksum = atomic(self.path.parent/(name+".json"), metadata)
        self.manifest.setdefault("setup_files", {})[name+".json"] = checksum
        self.flush()

    def complete(self, group, result, output):
        require(self.current == group.id, "GROUP_NOT_STARTED")
        fixture = fixture_recipe(group)
        receipt = {**{k:v for k,v in self.manifest.items() if k not in (
            "entries", "expected_groups", "completed_groups", "last_phase", "failed_phase")},
            "group_id":group.id, "group":asdict(group), "status":"COMPLETE",
            "expected_groups":1, "completed_groups":1,
            "started_at":self.manifest["entries"][group.id]["started_at"], "finished_at":now(),
            "fixture":fixture, "fixture_digest":digest(fixture),
            "census":{**output["fixture"]["census"],
                      "actual_counts":output["fixture"]["actual_counts"]},
            "settings":dict(statement_timeout_ms=300000, read_flag=False),
            "resources":dict(cpu_limit=2, memory_bytes=3*1024**3),
            "result":without_query_parameters(result)}
        from scripts.a42_receipt_contract import validate_group

        try:
            validate_group(receipt, group, head=self.manifest["head_sha"],
                attempt=self.manifest["attempt"], job_id=self.manifest["job_id"],
                model_hash=self.manifest["model_hash"])
        except BaseException as error:
            receipt.update(status="INCOMPLETE", completed_groups=0,
                           failure_type=type(error).__name__)
            atomic(self.path.parent/(group.id+".incomplete.json.gz"), receipt, compressed=True)
            raise
        name = group.id+".json.gz"
        started = time.monotonic()
        checksum = atomic(self.path.parent/name, receipt, compressed=True)
        self.manifest["entries"][group.id].update(
            status="COMPLETE", file=name, sha256=checksum, finished_at=receipt["finished_at"],
            artifact_seconds=time.monotonic()-started)
        self.manifest["completed_groups"] += 1
        self.manifest["last_successful_group"] = group.id
        self.current = None
        self.flush()

    def finish(self):
        require(self.manifest["completed_groups"] == len(self.groups), "INCOMPLETE_JOB")
        self.manifest.update(status="COMPLETE", finished_at=now(), failed_phase=None)
        self.flush()

    def fail(self, error):
        self.manifest.update(status="INCOMPLETE", finished_at=now(),
            **failure(error),
            failed_phase=self.manifest.get("last_phase", "initialization"))
        profile = getattr(error, "a42_profile", None)
        if self.current and profile is not None:
            entry = self.manifest["entries"][self.current]
            name = self.current+".incomplete.json.gz"
            partial = {**{k:v for k,v in self.manifest.items() if k != "entries"}, **failure(error),
                "status":"INCOMPLETE", "group_id":self.current, "group":entry["group"],
                "expected_groups":1, "completed_groups":0, "started_at":entry["started_at"],
                "finished_at":now(), "partial_profile":profile}
            checksum = atomic(self.path.parent/name, partial, compressed=True)
            entry.update(partial_file=name, partial_sha256=checksum)
        self.flush()


class ScopedOutput(dict):
    def __init__(self, writer, **values):
        super().__init__(**values)
        self.writer = writer
