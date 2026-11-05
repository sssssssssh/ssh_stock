"""Offline budget boundaries: fake clocks, timers and resources; never a live run."""

import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import yaml

from scripts import biz_perf_03_b_once as b

PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
}


def check_actions(value):
    uses = [step["uses"] for job in value["jobs"].values()
            for step in job["steps"] if "uses" in step]
    assert len(uses) == 4
    for use in uses:
        name, ref = use.rsplit("@", 1)
        assert re.fullmatch(r"[0-9a-f]{40}", ref)
        assert PINS[name] == ref


def test_new_workflow_external_actions_have_official_full_commit_pins():
    value = yaml.safe_load((b.ROOT / ".github/workflows/biz-perf-03-b-once.yml").read_text())
    check_actions(value)
    assert "steps.export.outcome == 'success'" in value["jobs"]["evidence"]["steps"][6]["if"]


@pytest.mark.parametrize("ref", ["v4", "main", "11d5960", "0" * 40])
def test_action_contract_refuses_floating_short_and_unreviewed_pins(ref):
    value = yaml.safe_load((b.ROOT / ".github/workflows/biz-perf-03-b-once.yml").read_text())
    value["jobs"]["evidence"]["steps"][1]["uses"] = "actions/checkout@" + ref
    with pytest.raises(AssertionError):
        check_actions(value)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    now = [120.0]
    timers = []
    handlers = []
    fake_signal = SimpleNamespace(
        ITIMER_REAL=1, SIGALRM=2, getsignal=lambda _: "previous",
        getitimer=lambda _: (0.0, 0.0), signal=lambda kind, handler: handlers.append(handler),
        setitimer=lambda *args: timers.append(args),
        handlers=handlers,
    )
    monkeypatch.setattr(b, "signal", fake_signal)
    monkeypatch.setattr(b.time, "monotonic", lambda: now[0])
    env = dict(BIZ03_T0_NS="100000000000", GITHUB_SHA="a" * 40,
               GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1", GITHUB_JOB="evidence")
    lab = b.Lab(env, b.protocol(), tmp_path, clock=lambda: now[0])
    from scripts.business_sql_snapshot import build

    snap = build({"SELECT": 1}, head_sha=env["GITHUB_SHA"],
                 root_job_id="00000000-0000-0000-0000-000000000001", started=110, ended=119)
    lab.receipt.update(status="MEASURED_CLEANUP_PENDING", root_attempts=1,
        last_phase=dict(phase="result", failure_code=None,
                        sql_counts=snap["counts"], sql_snapshot=snap))
    b.write_json(tmp_path / "public/measurement.json", dict(sql_snapshot=snap,
        head_sha=snap["head_sha"], root_job_id=snap["root_job_id"], root=dict(
            sql_counts=snap["counts"], job_status="SUCCESS", publication_state="PUBLISHED")))
    return lab, now, timers, env


@pytest.mark.parametrize("finished", [389.0, 390.0])
def test_cleanup_switches_watchdog_to_its_own_archive_window(harness, finished):
    lab, now, timers, _ = harness
    now[0] = lab.t0 + 330
    lab.container_intended = True

    def docker(*args, **kwargs):
        assert kwargs["deadline"] == lab.t0 + 390
        now[0] = lab.t0 + finished
        return ""  # Registered resource is already absent; no real Docker.

    lab.docker = docker
    with b.watchdog(lab.t0):
        lab.cleanup()
        assert lab.receipt["cleanup"] == "COMPLETE"
        assert lab.archive_deadline == lab.t0 + min(finished + 30, 420)
        assert timers[-1] == (b.signal.ITIMER_REAL, 30.0)
        assert lab.receipt["cleanup_finished_seconds"] == finished


def test_archive_can_complete_at_419_but_must_stop_at_420(harness):
    lab, now, _, _ = harness
    now[0] = lab.t0 + 390
    lab.receipt["cleanup"] = "COMPLETE"
    lab.receipt["cleanup_finished_seconds"] = 390
    lab.begin_archive()
    now[0] = lab.t0 + 419
    lab.begin_archive()
    assert b.completion_status(lab.receipt, 419, archive_limit=420) == "COMPLETE_DIAGNOSTIC_ONLY"
    now[0] = lab.t0 + 420
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        lab.begin_archive()
    assert b.completion_status(lab.receipt, 420, archive_limit=420) == "INCOMPLETE"


def test_early_cleanup_does_not_get_the_unused_total_budget(harness):
    lab, now, _, _ = harness
    now[0] = lab.t0 + 200
    lab.begin_archive()
    assert lab.archive_deadline == lab.t0 + 230
    now[0] = lab.t0 + 230
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        lab.begin_archive()


def test_archive_limit_is_anchored_to_cleanup_completion_not_later_entry(harness):
    lab, now, _, _ = harness
    lab.receipt["cleanup_finished_seconds"] = 389
    now[0] = lab.t0 + 390
    lab.begin_archive()
    assert lab.archive_deadline == lab.t0 + 419
    assert lab.receipt["archive_deadline_seconds"] == 419


def test_cleanup_overrun_cannot_be_complete(harness):
    lab, now, _, _ = harness
    now[0] = lab.t0 + 330
    lab.container_intended = True

    def docker(*args, **kwargs):
        now[0] = lab.t0 + 390.001
        return ""

    lab.docker = docker
    with pytest.raises(b.Refused, match="CLEANUP_TIMEOUT"):
        lab.cleanup()
    assert lab.receipt["cleanup"] != "COMPLETE"


@pytest.mark.parametrize("wall", [419, 420])
def test_failed_cleanup_never_becomes_success_during_archive(wall):
    receipt = dict(status="MEASURED_CLEANUP_PENDING", root_attempts=1,
                   cleanup="INCOMPLETE", first_failure="BIZ03_CLEANUP_INCOMPLETE")
    assert b.completion_status(receipt, wall, archive_limit=420) == "INCOMPLETE"


def test_archive_timeout_does_not_publish_a_complete_export(harness, tmp_path):
    lab, now, _, env = harness
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output")}
    directory = tmp_path / "biz-perf-03-b/123/1/public"
    directory.mkdir(parents=True)
    b.write_json(directory / "receipt.json", dict(status="INCOMPLETE",
        head_sha=env["GITHUB_SHA"], run_id="123", attempt="1",
        performance_eligible=False, production_read_authorized=False, capacity_ready=False))
    now[0] = lab.t0 + 420
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        b.prepare_export(env, b.protocol(), deadline=lab.t0 + 420, clock=lambda: now[0])
    assert not (directory.parent / "export").exists()
    assert not (tmp_path / "output").exists()


def test_original_initialization_root_and_protocol_budgets_are_unchanged():
    spec = b.protocol()
    assert [spec[k] for k in ("initialization_seconds", "root_seconds", "cleanup_seconds",
                              "total_seconds", "root_absolute_seconds", "archive_seconds")] == [
                                  180, 180, 60, 420, 330, 30]
    assert b.phase_deadline(100, {}) == 280
    assert b.phase_deadline(100, {"root_started": 110}) == 290
    assert b.phase_deadline(100, {"root_started": 280}) == 430


def test_final_manifest_can_finish_at_419_after_cleanup_at_390(harness):
    lab, now, timers, env = harness
    now[0] = lab.t0 + 390
    with b.watchdog(lab.t0):
        lab.cleanup()
        now[0] = lab.t0 + 419
        assert lab.finish_archive({"head_sha": env["GITHUB_SHA"]})
        assert timers[-1] == (b.signal.ITIMER_REAL, 1.0)
    assert lab.receipt["status"] == "COMPLETE_DIAGNOSTIC_ONLY"
    assert b.read_json(lab.directory / "public/manifest.json")["status"] == lab.receipt["status"]


def test_final_manifest_crossing_420_is_not_reported_or_exported_as_complete(
        harness, monkeypatch, tmp_path):
    lab, now, _, env = harness
    now[0] = lab.t0 + 390
    lab.cleanup()
    now[0] = lab.t0 + 419
    original_write = b.write_json

    def writing(path, value):
        original_write(path, value)
        if path.name == "manifest.json":
            now[0] = lab.t0 + 420

    monkeypatch.setattr(b, "write_json", writing)
    assert not lab.finish_archive({"head_sha": env["GITHUB_SHA"]})
    assert lab.receipt["status"] == "INCOMPLETE"
    assert lab.receipt["first_failure"] == "BIZ03_ARCHIVE_INCOMPLETE"
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output")}
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        b.prepare_export(env, b.protocol(), deadline=lab.archive_deadline, clock=lambda: now[0])
    assert not (tmp_path / "output").exists()


def test_failed_cleanup_keeps_first_error_through_final_archive(harness):
    lab, now, _, _ = harness
    now[0] = lab.t0 + 390
    lab.receipt.update(cleanup="INCOMPLETE", first_failure="BIZ03_CLEANUP_INCOMPLETE")
    assert not lab.finish_archive({})
    assert lab.receipt["status"] == "INCOMPLETE"
    assert b.read_json(lab.directory / "public/manifest.json")["status"] == "INCOMPLETE"
    assert lab.receipt["first_failure"] == "BIZ03_CLEANUP_INCOMPLETE"


def test_archive_watchdog_replaces_cleanup_timer_and_never_gains_extra_time(harness):
    lab, now, timers, _ = harness
    now[0] = lab.t0 + 390
    with b.watchdog(lab.t0):
        lab.cleanup()
        assert timers[-1] == (b.signal.ITIMER_REAL, 30.0)
        now[0] = lab.t0 + 419
        lab.begin_archive()
        assert timers[-1] == (b.signal.ITIMER_REAL, 1.0)
    assert timers[-1] == (b.signal.ITIMER_REAL, 0)


def test_queued_cleanup_alarm_does_not_abort_archive_but_real_expiry_does(harness):
    lab, now, timers, _ = harness
    with b.watchdog(lab.t0):
        handler = b.signal.handlers[0]
        now[0] = lab.t0 + 390
        lab.cleanup()
        now[0] = lab.t0 + 419
        handler(None, None)  # Old cleanup alarm, delivered after the phase switch.
        assert timers[-1] == (b.signal.ITIMER_REAL, 1.0)
        now[0] = lab.t0 + 420
        with pytest.raises(b.Refused, match="ABSOLUTE_DEADLINE"):
            handler(None, None)
    assert b.WATCHDOG_DEADLINE is None


def test_export_expiring_mid_validation_cannot_emit_an_artifact_path(
        harness, tmp_path, monkeypatch):
    lab, now, _, env = harness
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output")}
    directory = tmp_path / "biz-perf-03-b/123/1/public"
    directory.mkdir(parents=True)
    b.write_json(directory / "receipt.json", dict(status="INCOMPLETE",
        head_sha=env["GITHUB_SHA"], run_id="123", attempt="1",
        performance_eligible=False, production_read_authorized=False, capacity_ready=False))
    original_read = b.read_json
    now[0] = lab.t0 + 419

    def reading(path, *args):
        value = original_read(path, *args)
        now[0] = lab.t0 + 420
        return value

    monkeypatch.setattr(b, "read_json", reading)
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        b.prepare_export(env, b.protocol(), deadline=lab.t0 + 420, clock=lambda: now[0])
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("wall", [419, 420])
def test_export_cli_uses_archive_watchdog_not_initialization_timer(
        harness, monkeypatch, tmp_path, wall):
    lab, now, timers, env = harness
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output")}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(b.sys, "argv", ["once", "--check-export"])
    directory = tmp_path / "biz-perf-03-b/123/1/public"
    directory.mkdir(parents=True)
    b.write_json(directory / "receipt.json", dict(status="INCOMPLETE",
        head_sha=env["GITHUB_SHA"], run_id="123", attempt="1",
        archive_deadline_seconds=420, cleanup_finished_seconds=390,
        performance_eligible=False, production_read_authorized=False, capacity_ready=False))
    now[0] = lab.t0 + wall
    if wall == 420:
        with pytest.raises(SystemExit) as stopped:
            b.main()
        assert stopped.value.code == 1
        assert not (tmp_path / "output").exists()
    else:
        b.main()
        assert (b.signal.ITIMER_REAL, 1.0) in timers
        assert timers[-1] == (b.signal.ITIMER_REAL, 0)
        assert b.read_json(directory.parent / "export/receipt.json")["status"] == "INCOMPLETE"


def test_expiry_after_output_write_still_fails_the_export_step(harness, tmp_path, monkeypatch):
    lab, now, _, env = harness
    output = tmp_path / "output"
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output)}
    directory = tmp_path / "biz-perf-03-b/123/1/public"
    directory.mkdir(parents=True)
    b.write_json(directory / "receipt.json", dict(status="INCOMPLETE",
        head_sha=env["GITHUB_SHA"], run_id="123", attempt="1",
        performance_eligible=False, production_read_authorized=False, capacity_ready=False))
    now[0] = lab.t0 + 419
    original_open = b.Path.open

    @contextmanager
    def output_stream(path, *args, **kwargs):
        with original_open(path, *args, **kwargs) as stream:
            yield stream
        now[0] = lab.t0 + 420

    def opening(path, *args, **kwargs):
        if path == output:
            return output_stream(path, *args, **kwargs)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(b.Path, "open", opening)
    with pytest.raises(b.Refused, match="ARCHIVE_TIMEOUT"):
        b.prepare_export(env, b.protocol(), deadline=lab.t0 + 420, clock=lambda: now[0])
    # An output written by a failed step is never enough to authorize final upload.
    value = yaml.safe_load((b.ROOT / ".github/workflows/biz-perf-03-b-once.yml").read_text())
    assert "steps.export.outcome == 'success'" in value["jobs"]["evidence"]["steps"][6]["if"]


@pytest.mark.parametrize("cleanup_failed,finished,expected", [
    (False, 419, True), (True, 419, False), (False, 420, False),
])
def test_controller_uses_archive_phase_after_cleanup_without_live_effects(
        harness, tmp_path, monkeypatch, cleanup_failed, finished, expected):
    original_lab, now, _, env = harness
    env = {**env, "RUNNER_TEMP": str(tmp_path), "GITHUB_EVENT_PATH": str(tmp_path / "event")}
    b.write_json(tmp_path / "event", {"inputs": {}})
    identity = dict(head_sha=env["GITHUB_SHA"], run_id="123", attempt="1")
    monkeypatch.setattr(b, "authorize", lambda *args: identity)
    monkeypatch.setattr(b, "source_check", lambda *args: None)
    monkeypatch.setattr(b, "api", lambda *args: {
        "private": False, "commit": {"sha": env["GITHUB_SHA"]}})
    monkeypatch.setattr(b, "check_environment", lambda *args: None)
    monkeypatch.setattr(b, "resource_check", lambda *args: {})
    monkeypatch.setattr(b, "dependency_versions", lambda *args: {})
    monkeypatch.setitem(b.sys.modules, "scripts.source_contract_governance", SimpleNamespace(
        development_receipt=lambda *args, **kwargs: {"tree_sha": "b" * 40}))
    root_calls = []
    lab_type = type(original_lab)

    def factory(env, spec, directory):
        lab = lab_type(env, spec, directory, clock=lambda: now[0])
        lab.command = lambda *args: ""
        lab.provision = lambda: None

        def root():
            root_calls.append(1)
            lab.receipt.update(status="MEASURED_CLEANUP_PENDING", root_attempts=1,
                               last_phase=original_lab.receipt["last_phase"])
            b.write_json(directory / "public/measurement.json",
                         b.read_json(original_lab.directory / "public/measurement.json"))

        cleanup, finish = lab.cleanup, lab.finish_archive

        def clean():
            now[0] = lab.t0 + 390
            if cleanup_failed:
                raise b.Refused("BIZ03_CLEANUP_TIMEOUT")
            cleanup()

        def archive(identity):
            now[0] = lab.t0 + finished
            return finish(identity)

        lab.run_root, lab.cleanup, lab.finish_archive = root, clean, archive
        return lab

    monkeypatch.setattr(b, "Lab", factory)
    with b.watchdog(original_lab.t0):
        assert b.execute(env) is expected
    assert root_calls == [1]
