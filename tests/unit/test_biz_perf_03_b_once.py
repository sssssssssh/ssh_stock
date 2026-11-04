"""Offline only: no Docker, namespace, PG, application settings or HTTP execution."""

import argparse
import copy
import json
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from scripts import biz_perf_03_b_once as b


@pytest.fixture
def spec():
    return b.protocol()


@pytest.fixture
def authorization(spec, tmp_path):
    env = dict(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REPOSITORY=spec["repository"],
        GITHUB_REF="refs/heads/master", GITHUB_WORKFLOW=spec["workflow"],
        GITHUB_SHA="a" * 40, GITHUB_WORKFLOW_SHA="a" * 40, BIZ03_ALLOWED_SHA="a" * 40,
        GITHUB_RUN_ID="123", BIZ03_ALLOWED_RUN_ID="123", GITHUB_RUN_ATTEMPT="1",
        BIZ03_PROTOCOL_SHA256=b.digest(b.PROTOCOL.read_bytes()), RUNNER_ENVIRONMENT="github-hosted",
        RUNNER_OS="Linux", RUNNER_ARCH="X64", GITHUB_JOB="evidence", RUNNER_TEMP=str(tmp_path),
        BIZ03_T0_NS="100000000000")
    env.update({k: "false" for k in spec["flags"]})
    inputs = dict(target_sha="a" * 40, protocol_id=spec["schema"],
        protocol_sha256=b.digest(b.PROTOCOL.read_bytes()), confirm_once=True,
        run_reason="one reviewed synthetic root")
    return env, inputs


def environment():
    return dict(name=b.ENVIRONMENT, can_admins_bypass=False,
        protection_rules=[dict(type="required_reviewers", prevent_self_review=True,
                               reviewers=[{"reviewer": {"id": 1}}])],
        deployment_branch_policy=dict(protected_branches=False, custom_branch_policies=True))


def branches():
    return dict(total_count=1, branch_policies=[dict(name="master", type="branch")])


def measurement():
    return dict(stocks=4, months=1, optimized=False, dirty_tree=False, raw_daily_rows=2660,
        head_sha="a" * 40, dataset_sha256="b" * 64, implementation_sha256="c" * 64,
        harness_sha256="d" * 64, tables={t: "e" * 64 for t in b.TABLES},
        root_job_id="00000000-0000-0000-0000-000000000001",
        financial_identity={"factor": "v1"}, root_row_counts={"stock_factor_daily": 4},
        alembic_revision="0058_data_publication", candidate_source_mismatches=0,
        independent_rr_readers_no_candidate_leak=True, peak_process_rss_bytes=1024,
        runs=[dict(overall=10, cpu=3, execute_claimed_job_seconds=9,
            job_status="SUCCESS", publication_state="PUBLISHED", sql_counts={"SELECT": 10},
            stage_seconds={"factors.compute": 2}, error="password=do-not-export")],
        candidate_diagnostics=dict(stages={"upsert:stock_factor_daily": {"calls": 1}},
            direct_plan_control_sql_count=11, plans=[dict(table="stock_factor_daily",
            capture="ACTUAL_TIMED_LOOKUP", parameters_exported=False, query_sha256="a" * 64,
            server_duration_ms=2, plan={"Plan": {"Node Type": "Index Scan",
                "Index Name": "pk_data_publication_row", "Actual Rows": 4,
                "Filter": "password=hidden", "Query Text": "private-sql"}})]),
        fetches=[dict(rows=4, seconds=.01)])


def phase(**extra):
    return dict(phase="result", pid=77, root_started=110.0, root_attempts=1,
                failure_code=None, network_inode=99, **extra)


def test_frozen_protocol_and_dataset_are_exact(spec):
    from datetime import date, timedelta

    start, end = date(2025, 1, 1), date(2025, 1, 31)
    first = start - timedelta(days=spec["history_calendar_days"])
    count = sum((first + timedelta(days=i)).weekday() < 5
                for i in range((end - first).days + 1)) * 4
    assert count == spec["expected_raw_rows"] == 2660 < spec["maximum_raw_rows"] == 5000
    assert spec["postgres_image"].startswith("postgres@sha256:")
    assert spec["root_absolute_seconds"] + spec["cleanup_seconds"] + spec["archive_seconds"] == 420
    assert len(spec["flags"]) == 5
    assert not spec["performance_eligible"] and not spec["production_read_authorized"]


def test_valid_identity_does_not_grant_another_run(authorization, spec):
    env, inputs = authorization
    receipt = b.authorize(env, inputs, spec)
    assert receipt["run_id"] == "123"
    env["GITHUB_RUN_ID"] = "124"
    with pytest.raises(b.Refused, match="RUN_ID_BINDING"):
        b.authorize(env, inputs, spec)


@pytest.mark.parametrize("key,value", [
    ("GITHUB_EVENT_NAME", "push"), ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_REF", "refs/heads/topic"),
    ("GITHUB_WORKFLOW", "CI"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_WORKFLOW_SHA", "b" * 40), ("BIZ03_ALLOWED_SHA", "b" * 40),
    ("BIZ03_ALLOWED_RUN_ID", ""), ("BIZ03_PROTOCOL_SHA256", "0" * 64),
    ("RUNNER_ENVIRONMENT", "self-hosted"), ("RUNNER_OS", "macOS"),
    ("RUNNER_ARCH", "ARM64"), ("DOCKER_HOST", "ssh://private-host"),
    ("DOCKER_CONTEXT", "remote"),
])
def test_invalid_identity_fails_before_effects(authorization, spec, key, value):
    env, inputs = authorization
    env[key] = value
    with pytest.raises(b.Refused):
        b.authorize(env, inputs, spec)


@pytest.mark.parametrize("key", b.protocol()["flags"])
def test_each_opt_in_flag_is_refused(authorization, spec, key):
    env, inputs = authorization
    env[key] = "true"
    with pytest.raises(b.Refused, match="FLAGS_MUST_BE_FALSE"):
        b.authorize(env, inputs, spec)


@pytest.mark.parametrize("key,value", [
    ("confirm_once", False), ("target_sha", "short"), ("protocol_id", "[a4231-attribution-once]"),
    ("protocol_sha256", "0" * 64), ("run_reason", ""), ("repeats", 2),
])
def test_bad_inputs_or_unregistered_overrides_refused(authorization, spec, key, value):
    env, inputs = authorization
    inputs[key] = value
    with pytest.raises(b.Refused):
        b.authorize(env, inputs, spec)


@pytest.mark.parametrize("mutation", ["self", "reviewer", "bypass", "branch", "environment"])
def test_environment_live_configuration_must_be_protected(mutation):
    e, rules = environment(), branches()
    b.check_environment(e, rules)
    if mutation == "self":
        e["protection_rules"][0]["prevent_self_review"] = False
    elif mutation == "reviewer":
        e["protection_rules"][0]["reviewers"] = []
    elif mutation == "bypass":
        e["can_admins_bypass"] = True
    elif mutation == "branch":
        rules["branch_policies"].append(dict(name="*", type="branch"))
    else:
        e["name"] = "a4-expensive-measurements"
    with pytest.raises(b.Refused):
        b.check_environment(e, rules)


def test_child_environment_has_no_parent_secrets_and_no_network_escape(
        authorization, spec, tmp_path):
    env, _ = authorization
    env["DATABASE_URL"] = "private-business-dsn"
    lab = b.Lab(env, spec, tmp_path, clock=lambda: 120)
    lab.identity, lab.net_inode, lab.pg_pid = "123456", 99, 300
    child = lab.child_environment()
    assert "DATABASE_URL" not in child and "GITHUB_TOKEN" not in child
    assert child["TEST_DATABASE_URL"].endswith("@127.0.0.1:5432/biz03_test")
    assert all(child[k] == "false" for k in spec["flags"])
    command = lab.child_command()
    assert "/usr/bin/nsenter" in command and "--net" in command
    assert "--clear-groups" in command and "--no-new-privs" in command
    assert "--bounding-set=-all" in command and "-i" in command
    assert "private-business-dsn" not in json.dumps(command)


def test_second_root_and_failed_prefix_cannot_turn_success(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "network_inode", lambda: 99)
    channel = b.Channel(tmp_path / "phase.json")
    channel.emit("initializing")
    channel.begin_root()
    with pytest.raises(b.Refused, match="SECOND_ROOT"):
        channel.begin_root()
    channel.fail("BIZ03_FIRST_FAILURE")
    channel.fail("BIZ03_SECOND_FAILURE")
    channel.emit("result")
    value = b.read_json(channel.path)
    assert value["root_attempts"] == 1 and value["failure_code"] == "BIZ03_FIRST_FAILURE"


def test_absolute_and_relative_deadlines_preserve_archive_reserve():
    assert b.phase_deadline(100, {}) == 280
    assert b.phase_deadline(100, dict(root_started=120)) == 300
    assert b.phase_deadline(100, dict(root_started=280)) == 430
    with pytest.raises(b.Refused, match="PHASE_CLOCK"):
        b.phase_deadline(100, dict(root_started=281))


@pytest.mark.parametrize("value", [float("nan"), -1, "secret", True])
def test_non_numeric_metric_does_not_leak(value):
    with pytest.raises(b.Refused):
        b.metric_map({"factors.compute": value})


def test_export_has_only_safe_fields_and_actual_plan():
    raw = measurement()
    raw["database_url"] = "business-secret"
    raw["traceback"] = "private-sql"
    raw["untimed_candidate_lookup_plan"] = {"Query Text": "private-sql"}
    safe = b.export_measurement(raw)
    encoded = json.dumps(safe)
    assert not any(s in encoded for s in (
        "password", "business-secret", "private-sql", "traceback"))
    assert safe["root"]["job_status"] == "SUCCESS" and safe["fetch"]["calls"] == 1
    assert safe["root_job_id"] == raw["root_job_id"]


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(raw_daily_rows=5001), lambda r: r.update(stocks=5),
    lambda r: r.update(optimized=True), lambda r: r.update(runs=[]),
    lambda r: r["runs"].append(copy.deepcopy(r["runs"][0])),
    lambda r: r.update(candidate_source_mismatches=1),
    lambda r: r.update(independent_rr_readers_no_candidate_leak=False),
    lambda r: r.update(alembic_revision="wrong"),
    lambda r: r["candidate_diagnostics"]["plans"].clear(),
    lambda r: r["candidate_diagnostics"]["plans"][0].update(capture="REPLAY"),
    lambda r: r["candidate_diagnostics"]["plans"][0].update(parameters_exported=True),
])
def test_incomplete_or_unsafe_results_rejected(mutate):
    raw = measurement()
    mutate(raw)
    with pytest.raises((b.Refused, ValueError)):
        b.export_measurement(raw)


def test_failed_root_terminal_state_can_be_preserved_without_grant():
    raw = measurement()
    raw["runs"][0].update(job_status="FAILED", publication_state="ABORTED")
    safe = b.export_measurement(raw)
    assert safe["root"]["job_status"] == "FAILED"
    assert "performance_eligible" not in safe


@pytest.mark.parametrize("extra", [dict(error_message="secret"), dict(root_attempts=2),
                                     dict(network_inode=-1)])
def test_child_phase_is_not_arbitrary_public_json(extra):
    value = phase()
    value.update(extra)
    with pytest.raises(b.Refused):
        b.validate_phase(value)


def test_unknown_json_keys_and_nonfinite_numbers_refused(tmp_path):
    p = tmp_path / "input.json"
    p.write_text('{"a":1,"a":2}')
    with pytest.raises(b.Refused, match="DUPLICATE"):
        b.read_json(p)
    p.write_text('{"a":NaN}')
    with pytest.raises(b.Refused, match="NONFINITE"):
        b.read_json(p)


def test_single_mode_has_no_budget_or_optimization_escape(spec):
    args = argparse.Namespace(stocks=4, months=1, optimized=False, profile=False,
                              candidate_diagnostics=True, phase_file="private.json")
    env = {**{k: "false" for k in spec["flags"]}, "BIZ03_ONCE_CHILD": "1",
           "GITHUB_RUN_ATTEMPT": "1"}
    b.validate_single_mode(args, env)
    args.profile = True
    with pytest.raises(b.Refused):
        b.validate_single_mode(args, env)


def test_synthetic_process_is_invoked_once_and_checked(authorization, spec, tmp_path, monkeypatch):
    env, _ = authorization
    lab = b.Lab(env, spec, tmp_path, clock=lambda: 120)
    lab.identity, lab.net_inode, lab.pg_pid = "123", 99, 300
    b.write_json(tmp_path / "internal.json", measurement())
    b.write_json(tmp_path / "phase.json", phase())
    calls = []

    def popen(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(pid=77, returncode=0, poll=lambda: 0)

    lab.run_root(popen=popen)
    assert len(calls) == 1 and calls[0][1]["start_new_session"] is True
    assert lab.receipt["status"] == "MEASURED_CLEANUP_PENDING"
    assert b.read_json(tmp_path / "public/measurement.json")["root"]["job_status"] == "SUCCESS"


def test_parent_init_timeout_does_not_start_a_lab(authorization, spec, tmp_path):
    env, _ = authorization
    with pytest.raises(b.Refused, match="INITIALIZATION_TIMEOUT"):
        b.Lab(env, spec, tmp_path, clock=lambda: 281)
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("wrong", [True, False])
def test_cleanup_only_removes_registered_owned_container_and_volume(
        authorization, spec, tmp_path, wrong):
    env, _ = authorization
    calls = []
    lab = b.Lab(env, spec, tmp_path, clock=lambda: 120)
    lab.container_intended = lab.volume_intended = True

    def docker(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("container", "inspect"):
            labels = lab.labels()
            if wrong:
                labels["ssh-stock.run-id"] = "another-run"
            return json.dumps([{"Config": {"Labels": labels}}])
        if args[:2] == ("volume", "inspect"):
            return json.dumps([{"Labels": lab.labels()}])
        if args[0] == "ps":
            return lab.container
        if args[:2] == ("volume", "ls"):
            return lab.volume
        return ""

    lab.docker = docker
    if wrong:
        with pytest.raises(b.Refused, match="RESOURCE_OWNERSHIP"):
            lab.cleanup()
        assert not any(a[0] == "rm" for a in calls)
    else:
        lab.cleanup()
        assert ("rm", "-f", lab.container) in calls
        assert ("volume", "rm", lab.volume) in calls
        assert lab.receipt["cleanup"] == "COMPLETE"
    assert all("prune" not in args for args in calls)


def test_command_timeout_is_bounded_and_sanitized(authorization, spec, tmp_path):
    env, _ = authorization

    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("private-arguments", kwargs["timeout"])

    lab = b.Lab(env, spec, tmp_path, clock=lambda: 120, runner=run)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        lab.command(["fake-docker"])
    assert b.clean_error(caught.value) == "BIZ03_EXECUTION_FAILED"


def test_source_check_refuses_business_changes_and_dirty_tree(monkeypatch, spec):
    def git(*args):
        if args[:2] == ("rev-parse", "HEAD"):
            return "a" * 40
        if args[0] == "status":
            return ""
        return "backend/app/changed.py"

    monkeypatch.setattr(b, "git", git)
    with pytest.raises(b.Refused, match="BUSINESS_OR_OLD_INFRA_CHANGED"):
        b.source_check(spec, "a" * 40)


def test_workflow_is_dispatch_only_single_job_and_does_not_inherit_production_secrets():
    value = yaml.safe_load((b.ROOT / ".github/workflows/biz-perf-03-b-once.yml").read_text())
    assert set(value["on"]) == {"workflow_dispatch"}
    assert set(value["jobs"]) == {"evidence"}
    job = value["jobs"]["evidence"]
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] == 7
    assert "strategy" not in job and "services" not in job
    assert all(job["env"][k] == "false" for k in b.protocol()["flags"])
    assert "secrets." not in json.dumps(value)
    assert value["permissions"] == {"contents": "read"}
    assert len(job["steps"]) == 7
    assert job["steps"][1]["with"]["persist-credentials"] is False
    guarded = job["steps"][4]
    assert guarded["env"]["BIZ03_ALLOWED_RUN_ID"] == "${{ vars.BIZ03_ALLOWED_RUN_ID }}"
    assert "BIZ03_ALLOWED_RUN_ID" not in job["env"]
    assert job["steps"][5]["run"].endswith("--check-export")
    assert job["steps"][6]["with"]["path"] == "${{ steps.export.outputs.artifact_dir }}/*.json"
    assert "steps.export.outputs.artifact_dir != ''" in job["steps"][6]["if"]


def test_inventory_still_refuses_an_eighth_workflow(tmp_path, monkeypatch):
    from tests.unit import test_a4_ci_governance as legacy

    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in (*b.ORIGINAL_WORKFLOWS, "biz-perf-03-b-once.yml", "unknown.yml"):
        (workflows / name).write_text("")
    monkeypatch.setattr(legacy, "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        legacy.test_inventory_covers_every_workflow_and_no_hidden_trigger_chain()


@pytest.mark.parametrize("available,free,cpus", [
    (8 * 1024**3 - 1, 9 * 1024**3, 4), (9 * 1024**3, 8 * 1024**3 - 1, 4),
    (9 * 1024**3, 9 * 1024**3, 2),
])
def test_resource_shortage_is_deferred_without_smaller_fixture(spec, available, free, cpus):
    with pytest.raises(b.Refused, match="RESOURCE_DEFERRED"):
        b.check_resources(available, free, cpus, spec)
    assert spec["expected_raw_rows"] == 2660 and spec["stocks"] == 4


@pytest.mark.parametrize("reason", ["timeout", "rss", "ownership", "namespace"])
def test_live_supervisor_failures_stop_only_its_single_child_group(
        authorization, spec, tmp_path, monkeypatch, reason):
    env, _ = authorization
    now = [120.0]
    lab = b.Lab(env, spec, tmp_path, clock=lambda: now[0])
    lab.identity, lab.net_inode, lab.pg_pid = "123", 99, 300
    b.write_json(tmp_path / "phase.json", phase())
    if reason == "timeout":
        now[0] = 287
    elif reason == "namespace":
        v = phase()
        v["network_inode"] = 999
        b.write_json(tmp_path / "phase.json", v)
    monkeypatch.setattr(b.os, "getpgid", lambda pid: 88 if reason == "ownership" else 77)
    monkeypatch.setattr(b, "process_rss", lambda pid: 4 * 1024**3 if reason == "rss" else 1024)
    state = {"stopped": False, "calls": 0, "wait": 0}

    def wait(**kwargs):
        state["wait"] += 1

    def start(*args, **kwargs):
        state["calls"] += 1
        return SimpleNamespace(pid=77, returncode=None,
            poll=lambda: -9 if state["stopped"] else None, wait=wait)

    def stop(args, **kwargs):
        assert args == ["sudo", "-n", "/bin/kill", "-KILL", "--", "-77"]
        assert kwargs["deadline"] <= b.phase_deadline(100, phase())
        state["stopped"] = True

    lab.command = stop
    with pytest.raises(b.Refused):
        lab.run_root(popen=start)
    assert state == {"stopped": True, "calls": 1, "wait": 1}
    assert not (tmp_path / "public/measurement.json").exists()


@pytest.mark.parametrize("failure", [None, "network", "marker", "system", "major"])
def test_provisioning_has_pinned_owned_pgdata_and_cross_checked_physical_identity(
        authorization, spec, tmp_path, monkeypatch, failure):
    env, _ = authorization
    lab = b.Lab(env, spec, tmp_path, clock=lambda: 120)
    calls = []
    monkeypatch.setattr(b, "network_inode", lambda: 88)
    lab.command = lambda *a, **k: "99"

    def docker(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("volume", "inspect"):
            return json.dumps([dict(Labels=lab.labels())])
        if args[:2] == ("container", "inspect"):
            return json.dumps([dict(Config={"Labels": lab.labels()},
                HostConfig={"NetworkMode": "bridge" if failure == "network" else "none"},
                Mounts=[dict(Type="volume", Name=lab.volume)], State=dict(Pid=300))])
        if args[:2] == ("exec", lab.container) and "sh" in args:
            return "Database system identifier: 123456"
        if "psql" in args:
            return json.dumps(dict(version="180000" if failure == "major" else "170006",
                marker="wrong" if failure == "marker" else lab.marker,
                system="wrong" if failure == "system" else "123456", work_mem="4MB"))
        return ""

    lab.docker = docker
    if failure:
        with pytest.raises(b.Refused):
            lab.provision()
        assert not (tmp_path / "public/physical.json").exists()
    else:
        lab.provision()
        assert lab.identity == "123456"
        proof = b.read_json(tmp_path / "public/physical.json")
        assert proof["system_identifier_sha256"] == b.digest(b"123456")
        run = next(a for a in calls if a[0] == "run")
        assert run[run.index("--network") + 1] == "none"
        assert spec["postgres_image"] in run and "-p" not in run
        assert all("/Users/" not in v for v in run)
        assert lab.volume in json.dumps(run)
    assert lab.receipt["root_attempts"] == 0


def test_measurement_seed_and_default_replay_remain_but_once_mode_skips_replay():
    import ast

    source = (b.ROOT / "scripts/business_recalc_measure.py").read_text()
    tree = ast.parse(source)
    replay = [n for n in ast.walk(tree) if isinstance(n, ast.If)
              and ast.unparse(n.test) == "plan_input and (not channel)"]
    assert len(replay) == 1
    assert "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" in ast.unparse(replay[0])
    assert 'end = date(2025, args.months + 1, 1)' in source
    assert 'first = start - timedelta(days=900)' in source
    assert 'channel.begin_root()' in source


def test_bounded_command_kills_its_process_group_on_timeout(monkeypatch):
    state = []

    def communicate(timeout):
        state.append(timeout)
        if len(state) == 1:
            raise subprocess.TimeoutExpired("fake", timeout)
        return "", ""

    monkeypatch.setattr(b.subprocess, "Popen", lambda *a, **k:
        SimpleNamespace(pid=77, communicate=communicate, returncode=-9, poll=lambda: None))
    monkeypatch.setattr(b.os, "killpg", lambda pid, sig: state.append((pid, sig)))
    with pytest.raises(b.Refused, match="SUBPROCESS_TIMEOUT"):
        b.bounded_run(["fake"], cwd=b.ROOT, capture_output=True, text=True, timeout=3, check=False)
    assert (77, 9) in state


@pytest.mark.parametrize("changes,wall", [
    ({"first_failure": "BIZ03_EVIDENCE_IO"}, 100), ({"cleanup": "INCOMPLETE"}, 100),
    ({"root_attempts": 0}, 100), ({"root_attempts": 2}, 100), ({}, 391),
    ({}, float("nan")), ({"status": "INCOMPLETE"}, 100),
])
def test_failure_cleanup_missing_root_and_overrun_never_become_pass(changes, wall):
    receipt = dict(status="MEASURED_CLEANUP_PENDING", root_attempts=1,
                   cleanup="COMPLETE", first_failure=None)
    assert b.completion_status(receipt, 100) == "COMPLETE_DIAGNOSTIC_ONLY"
    receipt.update(changes)
    assert b.completion_status(receipt, wall) == "INCOMPLETE"


def test_approved_seventh_entry_preserves_all_original_inventory_checks():
    import ast

    path = "tests/unit/test_a4_ci_governance.py"
    name = "test_inventory_covers_every_workflow_and_no_hidden_trigger_chain"
    original = ast.parse(b.git("show", b.protocol()["business_baseline"] + ":" + path))
    current = ast.parse((b.ROOT / path).read_text())
    before = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == name)
    after = copy.deepcopy(next(n for n in current.body
                               if isinstance(n, ast.FunctionDef) and n.name == name))
    addition = after.body.pop(1)
    assert ast.unparse(addition) == "single_diagnostic = {'biz-perf-03-b-once.yml'}"
    comparison = after.body[1].test.comparators[0]
    assert isinstance(comparison, ast.BinOp) and comparison.right.id == "single_diagnostic"
    after.body[1].test.comparators[0] = comparison.left
    assert isinstance(after.body[-1], ast.For) and after.body[-1].iter.id == "single_diagnostic"
    after.body.pop()
    assert ast.dump(before) == ast.dump(after)


def test_watchdog_interrupts_and_restores_without_executing_workload(monkeypatch):
    registered = []
    timers = []
    monkeypatch.setattr(b.signal, "getsignal", lambda _: "previous")
    monkeypatch.setattr(b.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(b.signal, "signal", lambda kind, handler: registered.append(handler))
    monkeypatch.setattr(b.signal, "setitimer", lambda *args: timers.append(args))
    with b.watchdog(100):
        assert b.WATCHDOG_ACTIVE
        with pytest.raises(b.Refused, match="ABSOLUTE_DEADLINE"):
            registered[0](None, None)
    assert not b.WATCHDOG_ACTIVE and registered[-1] == "previous"
    assert timers[-1] == (b.signal.ITIMER_REAL, 0)


def test_timed_out_command_removes_descendants_even_after_entry_process_exits(monkeypatch):
    calls = []

    def communicate(timeout):
        raise subprocess.TimeoutExpired("private-command", timeout)

    monkeypatch.setattr(b.subprocess, "Popen", lambda *a, **k:
        SimpleNamespace(pid=77, communicate=communicate, returncode=0, poll=lambda: 0))
    monkeypatch.setattr(b.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    with pytest.raises((b.Refused, subprocess.TimeoutExpired)):
        b.bounded_run(["fake"], cwd=b.ROOT, capture_output=True, text=True, timeout=3, check=False)
    assert calls == [(77, 9)]


def test_failure_prefix_preserves_known_completed_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "network_inode", lambda: 99)
    channel = b.Channel(tmp_path / "phase.json")
    channel.begin_root()
    channel.emit("root", stage_seconds={"factors.compute": 2.5}, sql_counts={"SELECT": 3})
    channel.fail("BIZ03_EXECUTION_FAILED")
    value = b.read_json(channel.path)
    assert value["stage_seconds"] == {"factors.compute": 2.5}
    assert value["sql_counts"] == {"SELECT": 3}


@pytest.mark.parametrize("bad", [None, "unknown", "oversize", "raw-error"])
def test_export_gate_never_uploads_unregistered_or_oversized_raw_evidence(
        authorization, spec, tmp_path, bad):
    env, _ = authorization
    directory = tmp_path / "biz-perf-03-b/123/1/public"
    directory.mkdir(parents=True)
    value = dict(status="INCOMPLETE", head_sha=env["GITHUB_SHA"], run_id="123", attempt="1",
                 performance_eligible=False, capacity_ready=False, production_read_authorized=False)
    if bad == "raw-error":
        value["error_message"] = "password=private-error"
    b.write_json(directory / "receipt.json", value)
    if bad == "unknown":
        b.write_json(directory / "private-sql.json", {"Query Text": "secret-sql"})
    if bad == "oversize":
        spec = {**spec, "maximum_artifact_bytes": 1}
    assert b.prepare_export(env, spec) is (bad is None)
    output = b.read_json(directory.parent / "export/receipt.json")
    assert "password" not in json.dumps(output)
    assert "private-error" not in json.dumps(output)
    if bad:
        assert output["first_failure"] == "BIZ03_EXPORT_CONTRACT_FAILED"
        assert output["status"] == "INCOMPLETE"
    assert (directory / "receipt.json").exists()  # Original failed evidence stays private.
