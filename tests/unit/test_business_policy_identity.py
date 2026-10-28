"""BIZ-POLICY-01: Git provenance is not the calculation content identity."""

import subprocess
from copy import deepcopy
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from app.services import calculation_policy as cp


def settings():
    return NS(**dict.fromkeys(cp.FLAGS, False))


def source():
    return dict(source_sha256="a" * 64, commit_sha="1" * 40, worktree="CLEAN")


@pytest.mark.parametrize("change", [dict(commit_sha="2" * 40), dict(worktree="DIRTY")])
def test_git_only_change_does_not_abort_frozen_policy(monkeypatch, change):
    value = settings()
    monkeypatch.setattr(cp, "get_settings", lambda: value)
    job = NS(id=uuid4(), job_metadata={})
    policy = cp.ExecutionPolicy.freeze(job, value, source=source())
    frozen = deepcopy(policy.record)
    monkeypatch.setattr(cp, "runtime_source", lambda: {**source(), **change})
    policy.verify_source()
    assert policy.record == frozen


@pytest.mark.parametrize("field", cp.FLAGS)
def test_policy_reason_for_actual_flag_change_is_safe_and_sticky(monkeypatch, field):
    value = settings()
    monkeypatch.setattr(cp, "get_settings", lambda: value)
    policy = cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), value, source=source())
    setattr(value, field, True)
    with pytest.raises(ValueError, match="^CALCULATION_POLICY_CHANGED$") as caught:
        policy.guard()
    assert caught.value.reason == "OPTIMIZATION_FLAGS_CHANGED"
    assert policy.snapshot()["policy_change"]["policy_change_reason"] == caught.value.reason


@pytest.mark.parametrize("directory,name", [("backend", "module.py"), ("config", "policy.yaml")])
def test_business_file_bytes_and_scan_failures_still_refuse(tmp_path, monkeypatch, directory, name):
    for folder, file in (("backend", "module.py"), ("config", "policy.yaml")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / file).write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(cp, "ROOT_DIR", tmp_path)
    value = settings()
    monkeypatch.setattr(cp, "get_settings", lambda: value)
    policy = cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), value)
    (tmp_path / directory / name).write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED") as caught:
        policy.verify_source()
    assert caught.value.reason == "BUSINESS_SOURCE_CHANGED"
    assert caught.value.diagnostics["frozen_source"]["source_sha256"] != \
        caught.value.diagnostics["observed_source"]["source_sha256"]
    (tmp_path / directory / name).unlink()
    (tmp_path / directory).rmdir()
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED") as missing:
        cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), value)
    assert missing.value.reason == "SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("damage", [
    "missing_hash", "bad_hash", "missing_flags", "numeric_flags", "missing_request",
    "wrong_version", "wrong_root", "null", "list",
])
def test_old_identity_malformed_or_mismatched_is_not_re_frozen(damage):
    value, job = settings(), NS(id=uuid4(), job_metadata={})
    cp.ExecutionPolicy.freeze(job, value, source=source())
    record = job.job_metadata["calculation_execution"]
    if damage == "missing_hash":
        record["source"].pop("source_sha256")
    elif damage == "bad_hash":
        record["source"]["source_sha256"] = "b" * 64
    elif damage == "missing_flags":
        record.pop("flags")
    elif damage == "numeric_flags":
        record["flags"] = dict.fromkeys(cp.FLAGS, 0)
    elif damage == "missing_request":
        record.pop("request")
    elif damage == "wrong_version":
        record["schema_version"] = "unknown"
    elif damage == "wrong_root":
        record["root_job_id"] = str(uuid4())
    else:
        job.job_metadata["calculation_execution"] = None if damage == "null" else []
    before = deepcopy(job.job_metadata)
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED") as caught:
        cp.ExecutionPolicy.freeze(job, value, source=source())
    assert caught.value.reason == "JOB_FROZEN_IDENTITY_MISMATCH"
    assert job.job_metadata == before


def test_source_failure_evidence_does_not_echo_untrusted_details(monkeypatch):
    value = settings()
    monkeypatch.setattr(cp, "get_settings", lambda: value)
    policy = cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), value, source=source())

    def unavailable():
        raise OSError("PRIVATE_SOURCE_FAILURE_SENTINEL")

    monkeypatch.setattr(cp, "runtime_source", unavailable)
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED") as caught:
        policy.verify_source()
    assert caught.value.reason == "SOURCE_UNAVAILABLE"
    assert "PRIVATE_SOURCE_FAILURE_SENTINEL" not in str(policy.snapshot())


def test_resident_worker_keeps_original_provenance_across_git_only_change(monkeypatch):
    original = source()
    token = cp.worker_source.set(original)
    monkeypatch.setattr(cp, "runtime_source", lambda: {**original, "commit_sha": "2" * 40})
    try:
        policy = cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), settings())
        assert policy.source == original
    finally:
        cp.worker_source.reset(token)


def test_old_job_git_provenance_is_never_re_frozen(monkeypatch):
    job, value = NS(id=uuid4(), job_metadata={}), settings()
    policy = cp.ExecutionPolicy.freeze(job, value, source=source())
    frozen = deepcopy(policy.record)
    restarted = cp.ExecutionPolicy.freeze(job, value, source={**source(), "worktree": "DIRTY"})
    assert restarted.record == frozen


def test_actual_git_docs_scripts_tests_and_untracked_file_are_audit_only(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True,
                              capture_output=True).stdout

    git("init")
    git("config", "user.name", "Policy Test")
    git("config", "user.email", "policy-test@example.invalid")
    for path in ("backend/app.py", "config/strategy.yaml", "docs/note.md",
                 "scripts/note.py", "tests/test_note.py"):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("initial\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial")
    monkeypatch.setattr(cp, "ROOT_DIR", tmp_path)
    value = settings()
    monkeypatch.setattr(cp, "get_settings", lambda: value)
    original = cp.runtime_source()
    policy = cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), value)
    for path in ("docs/note.md", "scripts/note.py", "tests/test_note.py"):
        (tmp_path / path).write_text("unrelated\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "non-business change")
    assert cp.runtime_source()["commit_sha"] != original["commit_sha"]
    assert cp.runtime_source()["source_sha256"] == original["source_sha256"]
    policy.verify_source()
    (tmp_path / ".codex_tmp").mkdir()
    (tmp_path / ".codex_tmp" / "progress.log").write_text("unrelated\n", encoding="utf-8")
    assert cp.runtime_source()["worktree"] == "DIRTY"
    policy.verify_source()
