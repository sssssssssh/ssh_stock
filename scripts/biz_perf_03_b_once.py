"""One reviewed synthetic root only. No application imports in the controller.

The live entry is Actions-only. All interfaces with processes/HTTP are injectable
for offline contracts. This does not grant W02, capacity or production access.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_ACTIVE = False
WATCHDOG_DEADLINE = None
PROTOCOL = ROOT / "docs/acceptance/biz_perf_03_b_actions_once_protocol.json"
ENVIRONMENT = "biz-perf-03-b-once"
ORIGINAL_WORKFLOWS = (
    "ci.yml", "ab-read-a4-baseline.yml", "ab-read-a4-2.yml", "publication-v13.yml",
    "a4232-statistics-tail-diagnostic.yml", "a4233-observer-contracts.yml",
)
TABLES = frozenset((
    "stock_trade_status_daily", "stock_factor_daily", "market_daily", "sector_factor_daily",
    "theme_factor_daily", "stock_state_daily", "stock_opportunity_daily", "strategy_signal",
    "signal_forward_eval", "data_quality_daily",
))
HEX = re.compile(r"[0-9a-f]{64}")
LABEL = re.compile(r"[a-zA-Z0-9_.:/-]{1,160}")
PLAN_NUMBERS = frozenset((
    "Actual Rows", "Actual Loops", "Execution Time", "Planning Time", "Shared Hit Blocks",
    "Shared Read Blocks", "Temp Read Blocks", "Temp Written Blocks", "Plan Rows",
    "Actual Total Time", "Actual Startup Time",
))
PLAN_NODES = frozenset((
    "Nested Loop", "Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Bitmap Index Scan",
    "Seq Scan", "Subquery Scan", "Function Scan", "CTE Scan", "Result", "Limit", "Sort",
    "Aggregate", "Group", "Hash", "Hash Join", "Merge Join", "Materialize", "Memoize",
    "Append", "Merge Append", "Gather", "Gather Merge", "Unique", "Values Scan",
))


class Refused(RuntimeError):
    pass


def arm_deadline(deadline, *, reserve=3):
    global WATCHDOG_DEADLINE

    if WATCHDOG_ACTIVE:
        WATCHDOG_DEADLINE = deadline - reserve
        signal.setitimer(signal.ITIMER_REAL, max(.001, deadline - time.monotonic() - reserve))


@contextmanager
def watchdog(t0, *, deadline=None):
    global WATCHDOG_ACTIVE, WATCHDOG_DEADLINE

    def expired(signum, frame):
        if not WATCHDOG_ACTIVE:
            return
        # An alarm already queued by the old phase can arrive after the timer switch.
        if WATCHDOG_DEADLINE is not None and time.monotonic() < WATCHDOG_DEADLINE:
            arm_deadline(WATCHDOG_DEADLINE, reserve=0)
            return
        raise Refused("BIZ03_ABSOLUTE_DEADLINE")

    previous = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    require(previous_timer == (0.0, 0.0), "EXISTING_WATCHDOG_REFUSED")
    signal.signal(signal.SIGALRM, expired)
    WATCHDOG_ACTIVE = True
    arm_deadline(t0 + 180 if deadline is None else min(deadline, t0 + 420),
                 reserve=3 if deadline is None else 0)
    try:
        yield
    finally:
        WATCHDOG_ACTIVE = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        WATCHDOG_DEADLINE = None
        signal.signal(signal.SIGALRM, previous)


def require(value, code):
    if not value:
        raise Refused("BIZ03_" + code)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path, limit=10 * 1024**2):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), "JSON_REQUIRED")
    require(path.stat().st_size <= limit, "ARTIFACT_LIMIT")

    def pairs(items):
        require(len(dict(items)) == len(items), "DUPLICATE_JSON_KEY")
        return dict(items)

    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, "NONFINITE_JSON"))


def write_json(path, value):
    path = Path(path)
    require(not path.is_symlink(), "OUTPUT_SYMLINK")
    path.parent.mkdir(parents=True, exist_ok=True)
    require(all(not p.is_symlink() for p in (path.parent, *path.parent.parents)),
            "OUTPUT_SYMLINK")
    raw = json.dumps(value, allow_nan=False, sort_keys=True).encode()
    require(len(raw) <= 10 * 1024**2, "ARTIFACT_LIMIT")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw + b"\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def protocol():
    value = read_json(PROTOCOL)
    require(value["schema"] == "biz-perf-03-b.actions-once.v1", "PROTOCOL_SCHEMA")
    require(value["stocks"] == 4 and value["months"] == 1
            and value["expected_raw_rows"] == 2660 and value["maximum_raw_rows"] == 5000,
            "DATASET_CONTRACT")
    require([value[k] for k in ("initialization_seconds", "root_seconds", "cleanup_seconds",
                               "total_seconds", "root_absolute_seconds", "archive_seconds")]
            == [180, 180, 60, 420, 330, 30], "BUDGET_CONTRACT")
    require(value["root_attempts"] == 1 and not any(value[k] for k in
            ("production_read_authorized", "capacity_ready", "performance_eligible")),
            "AUTHORITY_CONTRACT")
    return value


def authorize(env, inputs, spec):
    require(set(inputs) == {"target_sha", "protocol_id", "protocol_sha256", "confirm_once",
                            "run_reason"}, "INPUT_SCHEMA")
    require(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "DISPATCH_REQUIRED")
    require(env.get("GITHUB_REPOSITORY") == spec["repository"], "REPOSITORY")
    require(env.get("GITHUB_REF") == "refs/heads/master", "MASTER")
    require(env.get("GITHUB_WORKFLOW") == spec["workflow"], "WORKFLOW")
    require(env.get("GITHUB_RUN_ATTEMPT") == "1", "RERUN_REFUSED")
    require(inputs["confirm_once"] is True or inputs["confirm_once"] == "true", "CONFIRMATION")
    target = inputs["target_sha"]
    require(isinstance(target, str) and re.fullmatch(r"[0-9a-f]{40}", target), "FULL_SHA")
    require(target == env.get("GITHUB_SHA") == env.get("GITHUB_WORKFLOW_SHA")
            == env.get("BIZ03_ALLOWED_SHA"), "SHA_BINDING")
    require(re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) is not None
            and env["GITHUB_RUN_ID"] == env.get("BIZ03_ALLOWED_RUN_ID"), "RUN_ID_BINDING")
    require(inputs["protocol_id"] == spec["schema"], "PROTOCOL_ID")
    actual = digest(PROTOCOL.read_bytes())
    require(inputs["protocol_sha256"] == actual == env.get("BIZ03_PROTOCOL_SHA256"),
            "PROTOCOL_HASH")
    require(isinstance(inputs["run_reason"], str) and 0 < len(inputs["run_reason"].strip()) <= 1000,
            "REASON_REQUIRED")
    require(env.get("RUNNER_ENVIRONMENT") == "github-hosted" and env.get("RUNNER_OS") == "Linux"
            and env.get("RUNNER_ARCH") == "X64", "HOSTED_LINUX_X64")
    require(all(env.get(k) == "false" for k in spec["flags"]), "FLAGS_MUST_BE_FALSE")
    require(not env.get("DOCKER_HOST") and not env.get("DOCKER_CONTEXT"), "LOCAL_DOCKER_ONLY")
    require(re.fullmatch(r"postgres@sha256:[0-9a-f]{64}", spec["postgres_image"]) is not None,
            "PINNED_PG17_IMAGE_REQUIRED")
    return dict(head_sha=target, run_id=env["GITHUB_RUN_ID"], attempt="1",
                protocol_sha256=actual, run_reason_sha256=digest(inputs["run_reason"].encode()))


def check_environment(value, branches, repository):
    require(isinstance(repository, dict), "REPOSITORY_OWNER_REQUIRED")
    owner = repository.get("owner")
    require(repository.get("full_name") == "sssssssssh/ssh_stock"
            and isinstance(owner, dict) and owner.get("type") == "User"
            and owner.get("login") == "sssssssssh"
            and type(owner.get("id")) is int and owner["id"] > 0,
            "REPOSITORY_OWNER_REQUIRED")
    require(isinstance(value, dict) and value.get("name") == ENVIRONMENT
            and value.get("can_admins_bypass") is False,
            "ENVIRONMENT_PROTECTION")
    protections = value.get("protection_rules")
    require(isinstance(protections, list) and all(isinstance(r, dict)
            and r.get("type") in ("required_reviewers", "branch_policy", "wait_timer")
            for r in protections), "ENVIRONMENT_PROTECTION")
    reviews = [r for r in protections if r["type"] == "required_reviewers"]
    require(len(reviews) == 1 and reviews[0].get("prevent_self_review") is False,
            "SINGLE_OWNER_REVIEW_REQUIRED")
    reviewers = reviews[0].get("reviewers")
    require(isinstance(reviewers, list) and len(reviewers) == 1
            and isinstance(reviewers[0], dict) and reviewers[0].get("type") == "User",
            "SINGLE_OWNER_REVIEW_REQUIRED")
    reviewer = reviewers[0].get("reviewer")
    require(isinstance(reviewer, dict) and reviewer.get("type") == "User"
            and type(reviewer.get("id")) is int and reviewer["id"] == owner["id"]
            and reviewer.get("login") == owner["login"], "SINGLE_OWNER_REVIEW_REQUIRED")
    policy = value.get("deployment_branch_policy")
    require(isinstance(policy, dict)
            and set(policy) == {"protected_branches", "custom_branch_policies"}
            and policy["protected_branches"] is False
            and policy["custom_branch_policies"] is True, "ENVIRONMENT_BRANCH_POLICY")
    require(isinstance(branches, dict) and type(branches.get("total_count")) is int
            and branches["total_count"] == 1, "ENVIRONMENT_MASTER_ONLY")
    rules = branches.get("branch_policies")
    require(isinstance(rules, list) and len(rules) == 1 and isinstance(rules[0], dict)
            and rules[0].get("name") == "master" and rules[0].get("type") == "branch",
            "ENVIRONMENT_MASTER_ONLY")


def clean_error(error):
    code = str(error) if isinstance(error, Refused) else "BIZ03_EXECUTION_FAILED"
    return code if re.fullmatch(r"BIZ03_[A-Z_]+", code) else "BIZ03_EXECUTION_FAILED"


def completion_status(receipt, wall, *, archive_limit=390):
    cleanup_finished = receipt.get("cleanup_finished_seconds", 0)
    return "COMPLETE_DIAGNOSTIC_ONLY" if (
        receipt["status"] == "MEASURED_CLEANUP_PENDING" and receipt["root_attempts"] == 1
        and receipt["cleanup"] == "COMPLETE" and not receipt["first_failure"]
        and type(cleanup_finished) in (int, float) and math.isfinite(cleanup_finished)
        and 0 <= cleanup_finished <= 390
        and type(archive_limit) in (int, float) and math.isfinite(archive_limit)
        and 0 < archive_limit <= 420
        and type(wall) in (int, float) and math.isfinite(wall)
        and cleanup_finished <= wall <= archive_limit and wall < 420
        and ("cleanup_finished_seconds" not in receipt or wall < cleanup_finished + 30)
    ) else "INCOMPLETE"


def number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "METRIC_INVALID")
    return value


def metric_map(value):
    require(isinstance(value, dict) and len(value) <= 4096, "METRIC_INVALID")
    result = {}
    for key, item in value.items():
        require(isinstance(key, str) and LABEL.fullmatch(key), "METRIC_LABEL")
        result[key] = number(item)
    return result


def safe_plan(value, depth=0):
    require(depth <= 40, "PLAN_DEPTH")
    if isinstance(value, list):
        require(len(value) <= 128, "PLAN_SIZE")
        return [safe_plan(v, depth + 1) for v in value]
    require(isinstance(value, dict), "PLAN_SCHEMA")
    result = {}
    for key, item in value.items():
        if key in ("Plan", "Plans"):
            result[key] = safe_plan(item, depth + 1)
        elif key in PLAN_NUMBERS:
            result[key] = number(item)
        elif key == "Node Type":
            require(item in PLAN_NODES, "PLAN_NODE")
            result[key] = item
        elif key in ("Relation Name", "Index Name"):
            require(isinstance(item, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,100}", item),
                    "PLAN_IDENTIFIER")
            result[key] = item
    return result


def export_measurement(raw):
    """Never forward arbitrary job messages, exception text, SQL or bind parameters."""
    require(raw.get("stocks") == 4 and raw.get("months") == 1
            and raw.get("optimized") is False and raw.get("dirty_tree") is False, "RESULT_IDENTITY")
    require(raw.get("raw_daily_rows") == 2660, "RAW_ROWS")
    runs = raw.get("runs", [])
    require(len(runs) == 1, "EXACTLY_ONE_RESULT")
    result = {k: raw[k] for k in ("stocks", "months", "optimized", "raw_daily_rows", "head_sha")}
    for key in ("dataset_sha256", "implementation_sha256", "harness_sha256"):
        require(isinstance(raw.get(key), str) and HEX.fullmatch(raw[key]), "RESULT_HASH")
        result[key] = raw[key]
    tables = raw.get("tables", {})
    require(set(tables) == TABLES and all(HEX.fullmatch(v) for v in tables.values()),
            "TABLE_HASHES")
    result["tables"] = tables
    r = runs[0]
    result["root"] = {key: number(r[key]) for key in
                      ("overall", "cpu", "execute_claimed_job_seconds")}
    for key in ("sql_counts", "sql_driver_seconds", "stage_seconds", "sql_by_stage",
                "sql_driver_seconds_by_stage"):
        result["root"][key] = metric_map(r.get(key, {}))
    failures = r.get("sql_failures", [])
    require(isinstance(failures, list) and len(failures) <= 10000, "SQL_FAILURE_LIMIT")
    result["root"]["sql_failures"] = []
    for failure in failures:
        name, state, stage = (failure.get(k) for k in ("error_class", "sqlstate", "stage"))
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", name)
                and (state is None or re.fullmatch(r"[A-Z0-9]{5}", state))
                and (stage is None or LABEL.fullmatch(stage)), "SQL_FAILURE_SCHEMA")
        result["root"]["sql_failures"].append(dict(error_class=name, sqlstate=state, stage=stage))
    require(r.get("job_status") in {"SUCCESS", "FAILED", "CANCELLED", "RUNNING"}
            and r.get("publication_state") in {"PUBLISHED", "ABORTED", "PREPARING", None},
            "ROOT_STATE")
    require(raw.get("candidate_source_mismatches") == 0, "CANDIDATE_SOURCE")
    require(raw.get("independent_rr_readers_no_candidate_leak") is True, "READER_ISOLATION")
    result["root"].update(job_status=r["job_status"], publication_state=r["publication_state"])
    require(str(uuid.UUID(raw.get("root_job_id", ""))) == raw["root_job_id"], "ROOT_ID")
    result["root_job_id"] = raw["root_job_id"]
    result["financial_identity_sha256"] = digest(json.dumps(
        raw["financial_identity"], sort_keys=True, allow_nan=False).encode())
    result["root_row_counts"] = metric_map(raw["root_row_counts"] or {})
    require(raw.get("alembic_revision") == "0058_data_publication", "MIGRATION_IDENTITY")
    result["alembic_revision"] = raw["alembic_revision"]
    result["peak_process_rss_bytes"] = number(raw["peak_process_rss_bytes"])
    observer = raw.get("candidate_diagnostics", {})
    plans = observer.get("plans", [])
    require(isinstance(plans, list) and len(plans) <= len(TABLES), "ACTUAL_PLANS_REQUIRED")
    if r["job_status"] == "SUCCESS":
        require(bool(plans), "ACTUAL_PLANS_REQUIRED")
    result["candidate_stages"] = {key: metric_map(v)
        for key, v in observer.get("stages", {}).items()
        if isinstance(key, str) and LABEL.fullmatch(key)}
    result["plans"] = []
    for plan in plans:
        require(plan.get("table") in TABLES and plan.get("capture") == "ACTUAL_TIMED_LOOKUP"
                and plan.get("parameters_exported") is False
                and HEX.fullmatch(plan.get("query_sha256", "")), "ACTUAL_PLAN_IDENTITY")
        result["plans"].append(dict(table=plan["table"], query_sha256=plan["query_sha256"],
            server_duration_ms=number(plan["server_duration_ms"]), plan=safe_plan(plan["plan"])))
    result["observer_control_sql_calls"] = number(observer["direct_plan_control_sql_count"])
    # Aggregate delivered Python calls; these are not network packets or exclusive server time.
    fetches = raw.get("fetches", [])
    require(isinstance(fetches, list) and len(fetches) <= 100000, "FETCH_LIMIT")
    result["fetch"] = {"calls": len(fetches), "rows": 0, "seconds": 0.0}
    for f in fetches:
        result["fetch"]["rows"] += number(f["rows"])
        result["fetch"]["seconds"] += number(f["seconds"])
    return result


class Channel:
    """Child-to-parent bounded failure prefix; no authority is inferred from this file."""

    def __init__(self, path):
        self.path = Path(path)
        self.root_started = None
        self.attempts = 0
        self.failure = None
        self.observations = {}

    def begin_root(self):
        require(self.root_started is None, "SECOND_ROOT_REFUSED")
        self.root_started = time.monotonic()
        self.attempts = 1
        self.emit("root")

    def emit(self, phase, **values):
        require(phase in {"initializing", "root", "result", "failure"}, "PHASE")
        self.observations.update({key: metric_map(values[key])
            for key in ("stage_seconds", "sql_counts") if key in values})
        safe = dict(self.observations)
        require(phase != "root" or self.root_started is not None, "ROOT_NOT_STARTED")
        safe.update(phase=phase, pid=os.getpid(), root_started=self.root_started,
                    root_attempts=self.attempts, failure_code=self.failure,
                    network_inode=network_inode())
        write_json(self.path, safe)

    def fail(self, code):
        self.failure = self.failure or code
        self.emit("failure")


def validate_single_mode(args, env):
    require(args.stocks == 4 and args.months == 1 and not args.optimized and not args.profile
            and args.candidate_diagnostics and bool(args.phase_file), "SINGLE_MODE_ARGUMENTS")
    require(env.get("BIZ03_ONCE_CHILD") == "1" and env.get("GITHUB_RUN_ATTEMPT") == "1",
            "CONTROLLER_REQUIRED")
    require(all(env.get(k) == "false" for k in protocol()["flags"]), "FLAGS_MUST_BE_FALSE")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL,
                                   timeout=15).decode().strip()


def source_check(spec, target):
    require(git("rev-parse", "HEAD") == target, "CHECKOUT_SHA")
    require(not git("status", "--porcelain", "--untracked-files=all"), "DIRTY_CHECKOUT")
    frozen = ["backend", "frontend", "config", "migrations", "requirements.lock",
              ".github/actions", *[".github/workflows/" + f for f in ORIGINAL_WORKFLOWS]]
    require(not git("diff", spec["business_baseline"], "HEAD", "--", *frozen),
            "BUSINESS_OR_OLD_INFRA_CHANGED")


def dependency_versions(spec):
    require(platform.python_version() == spec["python"], "PYTHON_VERSION")
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==")
        require(metadata.version(name.split("[")[0]) == expected, "LOCKED_DEPENDENCY_VERSION")
    return {d.metadata["Name"]: d.version for d in metadata.distributions() if d.metadata["Name"]}


def api(path):
    # Fixed public GitHub metadata only; never repository/business secrets APIs.
    require(path.startswith("repos/sssssssssh/ssh_stock"), "API_PATH")
    request = urllib.request.Request("https://api.github.com/" + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "biz-perf-03-b-guard"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class Lab:
    def __init__(self, env, spec, directory, *, clock=time.monotonic, runner=None):
        self.env, self.spec, self.directory = env, spec, Path(directory)
        self.clock, self.runner = clock, runner or bounded_run
        self.t0 = int(env["BIZ03_T0_NS"]) / 1e9
        require(0 <= self.clock() - self.t0 < 180, "INITIALIZATION_TIMEOUT")
        self.container = "a4-ci-" + env["GITHUB_RUN_ID"] + "-1-" + uuid.uuid4().hex[:12]
        self.volume = self.container + "-pgdata"
        self.marker = str(uuid.uuid4())
        self.cleanup_deadline = None
        self.archive_deadline = None
        self.volume_intended = self.container_intended = False
        self.identity = None
        self.receipt = dict(status="INCOMPLETE", root_attempts=0, first_failure=None,
            cleanup="NOT_CREATED", head_sha=env["GITHUB_SHA"], run_id=env["GITHUB_RUN_ID"],
            attempt="1", protocol_sha256=digest(PROTOCOL.read_bytes()),
            production_read_authorized=False, capacity_ready=False, performance_eligible=False)
        self.save()

    def save(self):
        write_json(self.directory / "public/receipt.json", self.receipt)
        write_json(self.directory / "owned.json", dict(container=self.container, volume=self.volume,
            marker=self.marker, container_intended=self.container_intended,
            volume_intended=self.volume_intended, identity=self.identity))

    def fail(self, code):
        self.receipt["first_failure"] = self.receipt["first_failure"] or code
        self.receipt["status"] = "INCOMPLETE"
        self.save()

    def command(self, args, *, deadline=None):
        deadline = deadline or self.t0 + 180
        remaining = deadline - self.clock()
        require(remaining > 0, "DEADLINE")
        result = self.runner(args, cwd=ROOT, capture_output=True, text=True,
                             timeout=remaining, check=False)
        require(result.returncode == 0, "SUBPROCESS_FAILED")
        require(self.clock() <= deadline, "DEADLINE")
        return result.stdout.strip()

    def docker(self, *args, deadline=None):
        return self.command(["docker", "--host", "unix:///var/run/docker.sock", *args],
                            deadline=deadline)

    def labels(self):
        return {"purpose": "ssh-stock-a4-physical-test", "ssh-stock.run-id":
                self.env["GITHUB_RUN_ID"], "ssh-stock.attempt": "1",
                "ssh-stock.job": self.env["GITHUB_JOB"]}

    def owned(self, kind, name, deadline):
        value = json.loads(self.docker(kind, "inspect", name, deadline=deadline))[0]
        actual = value.get("Labels") if kind == "volume" else value.get("Config", {}).get("Labels")
        require(isinstance(actual, dict) and all(actual.get(k) == v
                for k, v in self.labels().items()), "RESOURCE_OWNERSHIP")
        return value

    def provision(self):
        s = self.spec
        image = s["postgres_image"]
        self.docker("pull", image)
        label_args = [arg for k, v in self.labels().items() for arg in ("--label", k + "=" + v)]
        self.volume_intended = True
        self.save()  # Registration precedes effects, including ambiguous command completion.
        self.docker("volume", "create", *label_args, self.volume)
        self.owned("volume", self.volume, self.t0 + 180)
        self.container_intended = True
        self.save()
        self.docker("run", "-d", "--name", self.container, *label_args,
            "--network", "none", "--cpus=2", "--memory=3g",
            "--mount", "type=volume,source=" + self.volume + ",target=/var/lib/postgresql/data",
            "-e", "POSTGRES_DB=biz03_test", "-e", "POSTGRES_USER=synthetic",
            "-e", "POSTGRES_PASSWORD=synthetic", image,
            "-c", "v14.test_instance=" + self.marker,
            "-c", "shared_preload_libraries=pg_stat_statements",
            "-c", "pg_stat_statements.track=all", "-c", "track_io_timing=on",
            "-c", "track_wal_io_timing=on", "-c", "max_wal_size=1GB")
        value = self.owned("container", self.container, self.t0 + 180)
        require(value["HostConfig"]["NetworkMode"] == "none"
                and not value["HostConfig"].get("PortBindings"), "NETWORK_ISOLATION")
        require(value["Mounts"] and all(m.get("Type") == "volume" and
                m.get("Name") == self.volume for m in value["Mounts"]), "PGDATA_ISOLATION")
        self.pg_pid = value["State"]["Pid"]
        require(type(self.pg_pid) is int and self.pg_pid > 0, "PG_PID")
        self.net_inode = int(self.command(["sudo", "-n", "/usr/bin/stat", "-Lc", "%i",
                                          f"/proc/{self.pg_pid}/ns/net"]))
        require(self.net_inode != network_inode(), "NETWORK_ISOLATION")
        # Startup polling is readiness only, never a second root or measurement.
        ready = False
        for _ in range(40):
            try:
                self.docker("exec", self.container, "pg_isready", "-h", "127.0.0.1",
                            "-U", "synthetic", "-d", "biz03_test")
                ready = True
                break
            except Refused:
                require(self.clock() < self.t0 + 179, "INITIALIZATION_TIMEOUT")
                time.sleep(.25)
        require(ready, "PG_NOT_READY")
        control = self.docker("exec", self.container, "sh", "-c",
                             'LC_ALL=C pg_controldata "$PGDATA"')
        match = re.search(r"^Database system identifier:\s*([0-9]+)$", control, re.M)
        require(match, "PHYSICAL_ID")
        self.identity = match[1]
        sql = """SELECT json_build_object('version',current_setting('server_version_num'),
            'marker',current_setting('v14.test_instance'),'system',system_identifier::text,
            'shared_buffers',current_setting('shared_buffers'),
            'work_mem',current_setting('work_mem'),'max_connections',current_setting('max_connections'),
            'autovacuum',current_setting('autovacuum'),
            'timezone',current_setting('TimeZone'),
            'statement_timeout',current_setting('statement_timeout'),
            'lock_timeout',current_setting('lock_timeout'),
            'max_wal_size',current_setting('max_wal_size'),
            'analyze_scale_factor',current_setting('autovacuum_analyze_scale_factor'),
            'analyze_threshold',current_setting('autovacuum_analyze_threshold'))
            FROM pg_control_system()"""
        physical = json.loads(self.docker("exec", self.container, "psql", "-X", "-U", "synthetic",
            "-d", "biz03_test", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql))
        require(int(physical["version"]) // 10000 == 17
                and physical.pop("marker") == self.marker
                and physical.pop("system") == self.identity, "PHYSICAL_ID_MISMATCH")
        require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_./+-]{1,80}", v)
                    for v in physical.values()), "PHYSICAL_METADATA")
        write_json(self.directory / "public/physical.json", {
            "system_identifier_sha256": digest(self.identity.encode()),
            "marker_sha256": digest(self.marker.encode()), "image": image,
            "settings": physical, "network": "LOOPBACK_ONLY_NONE_NAMESPACE"})
        self.save()

    def child_environment(self):
        value = {k: "false" for k in self.spec["flags"]}
        value.update(TEST_DATABASE_URL="postgresql+psycopg://synthetic:synthetic@127.0.0.1:5432/biz03_test",
            V14_TEST_INSTANCE=self.marker, V14_TEST_SYSTEM_IDENTIFIER=self.identity,
            LLM_ENABLED="false", TUSHARE_TOKEN="synthetic-biz03", PYTHONUNBUFFERED="1",
            PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "backend"),
            PATH=os.environ.get("PATH", "/usr/bin:/bin"), BIZ03_ONCE_CHILD="1",
            GITHUB_RUN_ATTEMPT="1", BIZ03_EXPECTED_NET_INODE=str(self.net_inode),
            BIZ03_TARGET_SHA=self.env["GITHUB_SHA"])
        return value

    def child_command(self):
        uid, gid = os.getuid(), os.getgid()
        require(uid != 0 and gid != 0, "NONROOT_WORKLOAD_REQUIRED")
        environment = [k + "=" + v for k, v in self.child_environment().items()]
        return ["sudo", "-n", "/usr/bin/nsenter", "--target", str(self.pg_pid), "--net", "--",
            "/usr/bin/setpriv", "--reuid", str(uid), "--regid", str(gid), "--clear-groups",
            "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs",
            "/usr/bin/env", "-i", *environment, sys.executable,
            "-m", "scripts.business_recalc_measure", "--biz03-once", "--stocks", "4",
            "--months", "1", "--candidate-diagnostics", "--implementation-sha",
            self.env["GITHUB_SHA"], "--output", str(self.directory / "internal.json"),
            "--phase-file", str(self.directory / "phase.json")]

    def run_root(self, *, popen=subprocess.Popen):
        phase_path = self.directory / "phase.json"
        # Raw process output is never exported; only fixed safe codes reach Actions logs.
        with (self.directory / "private-process-output").open("xb") as output:
            process = popen(self.child_command(), cwd=ROOT, stdout=output, stderr=output,
                            stdin=subprocess.DEVNULL, close_fds=True, start_new_session=True)
            try:
                while process.poll() is None:
                    phase = validate_phase(read_json(phase_path)) if phase_path.exists() else {}
                    deadline = phase_deadline(self.t0, phase)
                    arm_deadline(deadline)
                    if phase:
                        require(phase["network_inode"] == self.net_inode, "NETWORK_ISOLATION")
                        require(phase["root_attempts"] in (0, 1), "SECOND_ROOT_REFUSED")
                        self.receipt["root_attempts"] = phase["root_attempts"]
                        self.receipt["last_phase"] = phase
                        self.save()
                        if phase.get("failure_code"):
                            raise Refused(phase["failure_code"])
                        pid = phase["pid"]
                        require(os.getpgid(pid) == process.pid, "CHILD_PROCESS_OWNERSHIP")
                        rss = process_rss(pid)
                        require(rss <= self.spec["worker_rss_limit_bytes"], "WORKER_RSS_LIMIT")
                    require(self.clock() < deadline - 3, "PHASE_TIMEOUT")
                    time.sleep(.05)
                phase = validate_phase(read_json(phase_path))
                require(phase["root_attempts"] == 1, "EXACTLY_ONE_ROOT")
                self.receipt["root_attempts"] = 1
                require(phase["network_inode"] == self.net_inode, "NETWORK_ISOLATION")
                self.receipt["last_phase"] = phase
                require(self.clock() <= phase_deadline(self.t0, phase), "PHASE_TIMEOUT")
            finally:
                if process.poll() is None:
                    # Only the fresh process group returned by our own Popen; no input PID.
                    self.command(["sudo", "-n", "/bin/kill", "-KILL", "--", "-" + str(process.pid)],
                                 deadline=min(phase_deadline(self.t0, phase), self.clock() + 2))
                    process.wait(timeout=1)
        raw = read_json(self.directory / "internal.json")
        require(raw.get("head_sha") == self.env["GITHUB_SHA"], "RESULT_SHA")
        result = export_measurement(raw)
        write_json(self.directory / "public/measurement.json", result)
        require(process.returncode == 0 and result["root"]["job_status"] == "SUCCESS"
                and result["root"]["publication_state"] == "PUBLISHED"
                and not phase.get("failure_code"), "ROOT_NOT_PUBLISHED")
        self.receipt.update(status="MEASURED_CLEANUP_PENDING", root_attempts=1)

    def cleanup(self):
        deadline = min(self.clock() + 60, self.t0 + 390)
        arm_deadline(deadline, reserve=0)
        self.cleanup_deadline = deadline
        self.receipt["cleanup"] = "INCOMPLETE"
        try:
            self.save()
        except OSError:
            # Disk failure must not prevent owned-resource cleanup.
            self.receipt["first_failure"] = self.receipt["first_failure"] or "BIZ03_EVIDENCE_IO"
        for kind, name, intended in (("container", self.container, self.container_intended),
                                     ("volume", self.volume, self.volume_intended)):
            if not intended:
                continue
            names = self.docker("ps" if kind == "container" else "volume", *( ["-a"]
                if kind == "container" else ["ls"]), "--filter",
                "name=^" + ("/" if kind == "container" else "") + name + "$",
                "--format", "{{.Names}}" if kind == "container" else "{{.Name}}", deadline=deadline)
            if not names:
                continue
            require(names == name, "RESOURCE_OWNERSHIP")
            self.owned(kind, name, deadline)
            if kind == "container":
                self.docker("rm", "-f", name, deadline=deadline)
            else:
                self.docker("volume", "rm", name, deadline=deadline)
        finished = self.clock()
        require(finished <= deadline and finished <= self.t0 + 390, "CLEANUP_TIMEOUT")
        self.receipt["cleanup"] = "COMPLETE"
        self.receipt["cleanup_finished_seconds"] = finished - self.t0
        self.begin_archive()  # Replace the cleanup timer before any final evidence I/O.
        self.save()

    def begin_archive(self):
        now = self.clock()
        if self.archive_deadline is None:
            finished = self.receipt.get("cleanup_finished_seconds", now - self.t0)
            limit = min(finished + 30, 420)
            self.archive_deadline = self.t0 + limit
            self.receipt["archive_deadline_seconds"] = limit
        require(now < self.archive_deadline and now < self.t0 + 420, "ARCHIVE_TIMEOUT")
        arm_deadline(self.archive_deadline, reserve=0)

    def finish_archive(self, identity):
        try:
            self.begin_archive()
            self.receipt["controlled_wall_seconds"] = self.clock() - self.t0
            self.receipt["status"] = completion_status(self.receipt,
                self.receipt["controlled_wall_seconds"],
                archive_limit=self.receipt["archive_deadline_seconds"])
            self.save()
            self.begin_archive()
            public = self.directory / "public"
            files = {p.name: {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                     for p in public.glob("*.json") if p.name != "manifest.json"}
            require(sum(v["bytes"] for v in files.values()) <= self.spec["maximum_artifact_bytes"],
                    "ARTIFACT_LIMIT")
            write_json(public / "manifest.json", {
                **identity, "files": files,
                "status": self.receipt["status"], "evidence_kind": "DIAGNOSTIC_ONLY"})
            self.begin_archive()
        except BaseException:
            self.receipt["first_failure"] = (
                self.receipt["first_failure"] or "BIZ03_ARCHIVE_INCOMPLETE")
            self.receipt["status"] = "INCOMPLETE"
            # Never start more evidence I/O after the archive/absolute cutoff.
            if self.archive_deadline is not None and self.clock() < self.archive_deadline:
                self.save()
            return False
        return self.receipt["status"] == "COMPLETE_DIAGNOSTIC_ONLY"


def phase_deadline(t0, phase):
    started = phase.get("root_started")
    if started is None:
        return t0 + 180
    require(type(started) in (float, int) and math.isfinite(started)
            and t0 <= started <= t0 + 180, "PHASE_CLOCK")
    return min(started + 180, t0 + 330)


def network_inode():
    return Path("/proc/self/ns/net").stat().st_ino


def validate_phase(value):
    require(isinstance(value, dict) and set(value) <= {
        "phase", "pid", "root_started", "root_attempts", "failure_code", "network_inode",
        "stage_seconds", "sql_counts"}, "PHASE_SCHEMA")
    require(value.get("phase") in {"initializing", "root", "result", "failure"}
            and type(value.get("pid")) is int and value["pid"] > 0
            and type(value.get("network_inode")) is int and value["network_inode"] > 0
            and type(value.get("root_attempts")) is int
            and value["root_attempts"] in (0, 1), "PHASE_SCHEMA")
    require(value.get("failure_code") is None or re.fullmatch(
        r"BIZ03_[A-Z_]+", value["failure_code"]), "PHASE_SCHEMA")
    for key in ("stage_seconds", "sql_counts"):
        if key in value:
            metric_map(value[key])
    return value


def process_rss(pid):
    raw = Path(f"/proc/{pid}/status").read_text()
    found = re.search(r"^VmRSS:\s+([0-9]+) kB$", raw, re.M)
    require(found, "RSS_UNAVAILABLE")
    return int(found[1]) * 1024


def bounded_run(args, *, cwd, capture_output, text, timeout, check):
    """Bound the complete fresh process group, including pip/build descendants."""
    require(timeout > .1, "DEADLINE")
    process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=text, stdin=subprocess.DEVNULL, start_new_session=True,
                               close_fds=True)
    try:
        out, err = process.communicate(timeout=timeout - .1)
    except BaseException as error:
        unconfirmed = False
        try:
            # The entry can exit while descendants retain the pipes and group.
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=.1)
        except subprocess.TimeoutExpired:
            unconfirmed = True
        if isinstance(error, subprocess.TimeoutExpired):
            failure = Refused("BIZ03_SUBPROCESS_TIMEOUT")
            failure.cleanup_unconfirmed = unconfirmed
            raise failure from None
        error.cleanup_unconfirmed = unconfirmed
        raise
    return subprocess.CompletedProcess(args, process.returncode, out, err)


def resource_check(spec):
    import shutil

    require(platform.system() == "Linux" and platform.machine() == "x86_64", "LINUX_X64")
    raw = Path("/proc/meminfo").read_text()
    available = int(re.search(r"^MemAvailable:\s+([0-9]+) kB$", raw, re.M)[1]) * 1024
    free = shutil.disk_usage(os.environ["RUNNER_TEMP"]).free
    return check_resources(available, free, os.cpu_count() or 0, spec)


def check_resources(available, free, cpus, spec):
    require(available >= spec["minimum_available_memory_bytes"]
            and free >= spec["minimum_free_disk_bytes"] and cpus >= 4, "RESOURCE_DEFERRED")
    return dict(cpu_count=cpus, available_memory_bytes=available, free_disk_bytes=free)


def execute(env):
    spec = protocol()
    inputs = read_json(env["GITHUB_EVENT_PATH"])["inputs"]
    identity = authorize(env, inputs, spec)
    source_check(spec, identity["head_sha"])
    repo = "repos/" + spec["repository"]
    repository = api(repo)
    require(isinstance(repository, dict) and repository.get("private") is False,
            "PUBLIC_STANDARD_RUNNER_REQUIRED")
    require(api(repo + "/branches/master")["commit"]["sha"] == identity["head_sha"], "MASTER_MOVED")
    check_environment(api(repo + "/environments/" + ENVIRONMENT),
                      api(repo + "/environments/" + ENVIRONMENT + "/deployment-branch-policies"),
                      repository)
    directory = Path(env["RUNNER_TEMP"]) / "biz-perf-03-b" / env["GITHUB_RUN_ID"] / "1"
    lab = Lab(env, spec, directory)
    try:
        resources = resource_check(spec)
        write_json(directory / "public/resources.json", resources)
        lab.command([sys.executable, "-m", "pip", "install", "-r", "requirements.lock"])
        versions = dependency_versions(spec)
        write_json(directory / "public/dependencies.json", {
            "python": platform.python_version(), "versions": versions,
            "requirements_sha256": digest((ROOT / "requirements.lock").read_bytes()),
            "transitive_lock_complete": False})
        # Existing whole-worktree/history checks, not a new execution grant.
        from scripts.source_contract_governance import development_receipt

        source = development_receipt(ROOT, expected_sha=identity["head_sha"])
        write_json(directory / "public/source.json", {**identity, "tree_sha": source["tree_sha"]})
        lab.command(["sudo", "-n", "true"])
        lab.provision()
        lab.run_root()
        source_check(spec, identity["head_sha"])
    except BaseException as error:
        if getattr(error, "cleanup_unconfirmed", False):
            lab.receipt["process_cleanup"] = "UNCONFIRMED"
        lab.fail(clean_error(error))
    finally:
        try:
            lab.cleanup()
        except BaseException:
            lab.receipt["cleanup"] = "INCOMPLETE"
            lab.receipt["status"] = "INCOMPLETE"
            lab.receipt["first_failure"] = (
                lab.receipt["first_failure"] or "BIZ03_CLEANUP_INCOMPLETE")
    return lab.finish_archive(identity)


def prepare_export(env, spec, *, deadline=None, clock=None):
    """Publish only a verified bounded snapshot, never a wildcard of raw outputs."""
    clock = clock or time.monotonic

    def check_time():
        if deadline is not None:
            require(clock() < deadline, "ARCHIVE_TIMEOUT")

    check_time()
    require(re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", ""))
            and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")), "EXPORT_ID")
    directory = Path(env["RUNNER_TEMP"]) / "biz-perf-03-b" / env["GITHUB_RUN_ID"] / env[
        "GITHUB_RUN_ATTEMPT"]
    exported = directory / "export"
    require(not exported.exists(), "EXPORT_ALREADY_EXISTS")
    exported.mkdir(parents=True)
    allowed = {"receipt.json", "source.json", "resources.json", "dependencies.json",
               "physical.json", "measurement.json", "manifest.json"}
    ok = False
    try:
        public = directory / "public"
        entries = list(public.iterdir())
        require(all(p.name in allowed and p.is_file() and not p.is_symlink() for p in entries),
                "EXPORT_ALLOWLIST")
        require(sum(p.stat().st_size for p in entries) <= spec["maximum_artifact_bytes"],
                "ARTIFACT_LIMIT")
        data = {p.name: p.read_bytes() for p in entries}
        require("receipt.json" in data, "RECEIPT_REQUIRED")
        for path in entries:
            check_time()
            validate_document(path.name, read_json(path))
        receipt = read_json(public / "receipt.json")
        require(receipt.get("head_sha") == env["GITHUB_SHA"]
                and receipt.get("run_id") == env["GITHUB_RUN_ID"]
                and receipt.get("attempt") == env["GITHUB_RUN_ATTEMPT"]
                and all(receipt.get(k) is False for k in
                        ("performance_eligible", "production_read_authorized", "capacity_ready")),
                "EXPORT_IDENTITY")
        if "manifest.json" in data:
            manifest = read_json(public / "manifest.json")
            require(set(manifest["files"]) == set(data) - {"manifest.json"}, "MANIFEST_FILES")
            for name, record in manifest["files"].items():
                require(record == {"sha256": digest(data[name]), "bytes": len(data[name])},
                        "MANIFEST_HASH")
        else:
            require(set(data) == {"receipt.json"} and receipt.get("status") == "INCOMPLETE",
                    "MANIFEST_REQUIRED")
        if receipt.get("status") == "COMPLETE_DIAGNOSTIC_ONLY":
            require(set(data) == allowed, "COMPLETE_ARTIFACTS_REQUIRED")
        for name, raw in data.items():
            check_time()
            with (exported / name).open("xb") as stream:
                stream.write(raw)
        check_time()
        ok = True
    except BaseException:
        check_time()  # On timeout preserve the earlier INCOMPLETE prefix, not a new export.
        # Preserve originals privately, export only the fixed failure receipt.
        for path in exported.iterdir():
            path.unlink()
        write_json(exported / "receipt.json", dict(status="INCOMPLETE",
            first_failure="BIZ03_EXPORT_CONTRACT_FAILED", head_sha=env["GITHUB_SHA"],
            run_id=env["GITHUB_RUN_ID"], attempt=env["GITHUB_RUN_ATTEMPT"],
            performance_eligible=False, production_read_authorized=False, capacity_ready=False))
    check_time()
    if env.get("GITHUB_OUTPUT"):
        with Path(env["GITHUB_OUTPUT"]).open("a") as stream:
            stream.write("artifact_dir=" + str(exported) + "\n")
    check_time()
    return ok


def validate_document(name, value):
    keys = {
        "receipt.json": {"status", "root_attempts", "first_failure", "cleanup", "head_sha",
            "run_id", "attempt", "protocol_sha256", "production_read_authorized", "capacity_ready",
            "performance_eligible", "last_phase", "process_cleanup", "controlled_wall_seconds",
            "cleanup_finished_seconds", "archive_deadline_seconds"},
        "source.json": {"head_sha", "run_id", "attempt", "protocol_sha256",
                        "run_reason_sha256", "tree_sha"},
        "resources.json": {"cpu_count", "available_memory_bytes", "free_disk_bytes"},
        "dependencies.json": {"python", "versions", "requirements_sha256",
                              "transitive_lock_complete"},
        "physical.json": {"system_identifier_sha256", "marker_sha256", "image",
                          "settings", "network"},
        "measurement.json": {"stocks", "months", "optimized", "raw_daily_rows", "head_sha",
            "dataset_sha256", "implementation_sha256", "harness_sha256", "tables", "root",
            "root_job_id", "financial_identity_sha256", "root_row_counts", "alembic_revision",
            "peak_process_rss_bytes", "candidate_stages", "plans", "observer_control_sql_calls",
            "fetch"},
        "manifest.json": {"head_sha", "run_id", "attempt", "protocol_sha256",
                          "run_reason_sha256", "files", "status", "evidence_kind"},
    }
    require(isinstance(value, dict) and name in keys and set(value) <= keys[name], "EXPORT_SCHEMA")
    if name == "receipt.json":
        require(value.get("status") in {"INCOMPLETE", "MEASURED_CLEANUP_PENDING",
                                         "COMPLETE_DIAGNOSTIC_ONLY"}, "EXPORT_STATE")
        code = value.get("first_failure")
        require(code is None or re.fullmatch(r"BIZ03_[A-Z_]+", code), "EXPORT_FAILURE_CODE")
        if "last_phase" in value:
            validate_phase(value["last_phase"])
    elif name == "resources.json":
        metric_map(value)
    elif name == "dependencies.json":
        require(value["transitive_lock_complete"] is False, "DEPENDENCY_LOCK_CLAIM")
        require(all(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", k)
                    and re.fullmatch(r"[0-9][A-Za-z0-9_.!+_-]{0,79}", v)
                    for k, v in value["versions"].items()), "DEPENDENCY_METADATA")
    elif name == "measurement.json":
        require(set(value["root"]) <= {
            "overall", "cpu", "execute_claimed_job_seconds", "sql_counts",
            "sql_driver_seconds", "stage_seconds", "sql_by_stage", "sql_driver_seconds_by_stage",
            "sql_failures", "job_status", "publication_state"}, "EXPORT_ROOT_SCHEMA")
        for plan in value["plans"]:
            require(set(plan) == {"table", "query_sha256", "server_duration_ms", "plan"}
                    and plan["plan"] == safe_plan(plan["plan"]), "EXPORT_PLAN_SCHEMA")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-export", action="store_true")
    args = parser.parse_args()  # No budget, resource, repeat or optimization overrides.
    try:
        if args.check_export:
            t0 = int(os.environ.get("BIZ03_T0_NS", "0")) / 1e9
            require(0 <= time.monotonic() - t0 < 420, "ARCHIVE_TIMEOUT")
            with watchdog(t0, deadline=t0 + 420):
                directory = Path(os.environ["RUNNER_TEMP"]) / "biz-perf-03-b" / os.environ[
                    "GITHUB_RUN_ID"] / os.environ["GITHUB_RUN_ATTEMPT"] / "public"
                receipt = read_json(directory / "receipt.json")
                limit = receipt.get("archive_deadline_seconds", 420)
                require(type(limit) in (int, float) and math.isfinite(limit)
                        and 0 < limit <= 420, "ARCHIVE_TIMEOUT")
                if receipt.get("status") == "COMPLETE_DIAGNOSTIC_ONLY":
                    finished = receipt.get("cleanup_finished_seconds")
                    require(type(finished) in (int, float) and math.isfinite(finished)
                            and 0 <= finished <= 390 and limit == min(finished + 30, 420),
                            "ARCHIVE_TIMEOUT")
                deadline = t0 + limit
                require(time.monotonic() < deadline, "ARCHIVE_TIMEOUT")
                arm_deadline(deadline, reserve=0)
                ok = prepare_export(os.environ, protocol(), deadline=deadline)
        else:
            t0 = int(os.environ.get("BIZ03_T0_NS", "0")) / 1e9
            require(0 <= time.monotonic() - t0 < 180, "INITIALIZATION_TIMEOUT")
            with watchdog(t0):
                ok = execute(os.environ)
    except BaseException as error:
        print(clean_error(error))
        raise SystemExit(1) from None
    if args.check_export:
        print("BIZ03_EXPORT_VERIFIED" if ok else "BIZ03_EXPORT_REFUSED")
    else:
        print("BIZ03_COMPLETE_DIAGNOSTIC_ONLY" if ok else "BIZ03_INCOMPLETE")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
