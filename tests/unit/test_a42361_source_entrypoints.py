"""A42361 RED inventory: old default refusals are correct, real implementations absent."""

import pytest

from scripts.a42361_offline_cases import real_components


@pytest.mark.parametrize(
    "position,required",
    [
        (0, "verify_signature"),
        (1, "consume_transaction"),
        (2, "create_owned_fixture"),
        (3, "terminate_owned"),
    ],
)
def test_RED_four_real_implementation_gaps_not_fake_positive(position, required):
    # No adapter is constructed or called; this is a code-gap inventory, not G1 proof.
    assert callable(getattr(real_components()[position], required, None))


def test_AT01_AT02_AT04_actual_source_freeze_and_history():
    import hashlib

    from scripts import a4235_capability_guard as g
    from scripts import a42361_source_guard as live

    identity = g.expected_identity()
    assert identity.head_sha == g.git(g.ROOT, "rev-parse", "HEAD").decode().strip()
    assert len(identity.head_sha) == 40
    assert (
        identity.frozen_sha256 == "b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9"
    )
    assert g.path_sha(g.ROOT / g.NEXT_MANIFEST) == g.NEXT_MANIFEST_SHA
    assert g.path_sha(g.ROOT / g.OVERLAY_MANIFEST) == g.OVERLAY_MANIFEST_SHA
    assert not g.git(
        g.ROOT,
        "diff",
        "--name-only",
        live.BASELINE,
        "--",
        "backend",
        "config",
        "migrations",
        "frontend",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
    )
    # Only the specifically human-authorized test function changes. No other old
    # assertions/parametrizations disappear and no 308-case count is altered.
    import ast

    old = ast.parse(g.git(g.ROOT, "show", f"{live.BASELINE}:{live.OLD_TEST}"))
    new = ast.parse((g.ROOT / live.OLD_TEST).read_bytes())

    def functions(tree):
        return {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}

    before, after = functions(old), functions(new)
    assert before.keys() == after.keys()
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"test_AT03_actual_exact_26_path_delta_and_pinned_14_patch_blobs"}
    for path in g.NEXT_PATCH_PATHS - {live.OLD_TEST}:
        assert hashlib.sha256(
            g.git(g.ROOT, "show", f"{live.BASELINE}:{path}")
        ).hexdigest() == g.path_sha(g.ROOT / path)


@pytest.mark.parametrize(
    "path",
    [
        "infra/g1_harness/extra.json",
        "scripts/a42361_backdoor.py",
        ".github/workflows/g1.yml",
        "backend/app/new.py",
        "tests/unit/other.py",
    ],
)
def test_AT03_no_prefix_or_infra_directory_exemption(path):
    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        live.validate_paths(live.STAGE_PATHS | {path})
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        live.validate_paths(live.STAGE_PATHS - {live.MANIFEST})


@pytest.mark.parametrize("threat", ["manifest", "new_patch", "hidden_infra", "head_race"])
def test_AT03_new_layer_content_and_tree_tampering(monkeypatch, threat):
    from scripts import a4235_capability_guard as g
    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    original_git, original_sha = g.git, g.path_sha
    calls = 0

    def git(root, *args):
        nonlocal calls
        if args[:2] == ("rev-parse", "HEAD"):
            calls += 1
            if threat == "head_race" and calls > 1:
                return b"f" * 40
        if threat == "hidden_infra" and args[:2] == ("ls-tree", "-r") and args[-1] == "infra":
            return b"100644 blob " + b"0" * 40 + b"\tinfra/g1_control_plane/001_control.sql\n"
        return original_git(root, *args)

    def path_sha(path):
        if threat == "manifest" and str(path).endswith(live.MANIFEST):
            return "f" * 64
        if threat == "new_patch" and str(path).endswith("a42361_live_probe_worker.py"):
            return "f" * 64
        return original_sha(path)

    monkeypatch.setattr(g, "git", git)
    monkeypatch.setattr(g, "path_sha", path_sha)
    with pytest.raises(Fault, match="^A4235_"):
        g.overlay_fingerprint()


def test_AT03_symlink_rejection(tmp_path):
    from scripts.a4235_calibration_adapter_contract import Fault
    from scripts.a4235_capability_guard import path_sha

    source = tmp_path / "source"
    source.write_text("offline")
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(Fault, match="PATH_INVALID"):
        path_sha(link)


def test_AT27_AT28_all_default_entries_deny_before_side_effects(monkeypatch):
    import socket
    import subprocess

    import psycopg

    from scripts import a42361_control_service as c
    from scripts import a42361_fixture_controller as f
    from scripts import a42361_live_probe_worker as w
    from scripts import a42361_one_shot_store as s
    from scripts import a42361_trust_verifier as t
    from scripts.a42361_contract import Fault

    def deny(*a, **k):
        pytest.fail("side effect before trust bootstrap")

    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(psycopg, "connect", deny)
    monkeypatch.setenv("A42361_APPROVED", "true")
    monkeypatch.setenv("A42361_EXECUTE", "1")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    operations = [
        lambda: c.ControlService().run_approved(b"{}", {}),
        lambda: t.TrustVerifier().verify_signature(b"{}", {}),
        lambda: s.PostgresConsumer().consume_once(None),
        lambda: f.FixtureController().create_owned_fixture(None),
        lambda: w.ProbeWorker().run_owned(None),
    ]
    for operation in operations:
        with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
            operation()
    for args in ([], ["--execute"], ["--approve"], ["--token", "not-a-grant"]):
        assert c.main(args) != 0


def test_AT40_old_live_and_fake_stay_incapable():
    from scripts.a4236_g1_harness_contract import Fault
    from scripts.a4236_g1_probe import run_live
    from scripts.a4236_grant_verifier import FakeAtomicConsumer

    with pytest.raises(Fault, match="G1_NOT_RUN_NOT_AUTHORIZED"):
        run_live(approved=True, execute=True)
    assert not hasattr(FakeAtomicConsumer, "consume_once")


ROOT_FREEZE_FILES = (
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "Dockerfile",
    "Makefile",
    "alembic.ini",
    "docker-compose.yml",
    "requirements.txt",
)


def complete_overlay_model(tmp_path):
    """Independent byte-backed Git protocol fixture; no flags on the user's index.

    Its status/diff deliberately report clean (as assume-unchanged can). Real files,
    original Git blob IDs and source-layer checks must detect changes independently.
    """
    import hashlib
    import json
    from types import SimpleNamespace

    from scripts import a4235_capability_guard as g
    from scripts import a42361_source_guard as live

    root, head = tmp_path, "a" * 40
    snapshot = {name: b"baseline" for name in live.STAGE_PATHS - {live.MANIFEST}}
    snapshot.update({name: b"baseline-root" for name in ROOT_FREEZE_FILES})
    snapshot["docs/Chinese_中文\nname.txt"] = b"baseline-nul-path"
    snapshot[live.OLD_GUARD] = b"LIVE_MANIFEST_SHA = '" + b"0" * 64 + b"'\n"
    old = {live.OLD_GUARD: b"old-guard", live.OLD_TEST: b"old-test"}
    manifest = dict(
        schema_version="a42361.exact-overlay.v1",
        baseline_sha=live.BASELINE,
        stage_paths=sorted(live.STAGE_PATHS),
        patch_sha256={n: hashlib.sha256(snapshot[n]).hexdigest() for n in live.PINNED},
        old_sha256={n: hashlib.sha256(raw).hexdigest() for n, raw in old.items()},
        normalized_guard_sha256=hashlib.sha256(
            live.normalized_guard(snapshot[live.OLD_GUARD])
        ).hexdigest(),
    )
    raw = json.dumps(manifest).encode()
    snapshot[live.MANIFEST] = raw
    for name, data in snapshot.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)

    def row(name):
        raw = snapshot[name]
        oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
        return b"100644 blob " + oid + b"\t" + name.encode()

    calls = []

    def git(directory, *args):
        assert directory == root
        calls.append(args)
        if args[0] == "diff":
            return b"\0".join(n.encode() for n in sorted(live.STAGE_PATHS)) + b"\0"
        if args[0] == "show":
            commit, name = args[1].split(":", 1)
            return snapshot[name] if commit == head else old.get(name, b"baseline")
        if args[0] == "ls-tree":
            if args[-1] == "infra":
                return b"\n".join(row(n) for n in live.INFRA)
            return b"\0".join(row(n) for n in snapshot) + b"\0"
        if args[:2] == ("rev-parse", "HEAD"):
            return head.encode()
        if args[0] == "status":
            return b""
        pytest.fail("unregistered Git operation")

    guard = SimpleNamespace(
        require=g.require,
        path_sha=g.path_sha,
        git=git,
        LIVE_MANIFEST_SHA=hashlib.sha256(raw).hexdigest(),
    )
    return guard, root, head, calls


def test_AT03_full_tree_positive_preserves_nul_unicode_and_legacy_layer(tmp_path):
    from scripts import a42361_source_guard as live

    guard, root, head, _ = complete_overlay_model(tmp_path)
    assert live.validate(guard, root, head) == guard.LIVE_MANIFEST_SHA


@pytest.mark.parametrize("name", ROOT_FREEZE_FILES)
def test_RED_AT03_hidden_index_root_content_must_not_be_trusted(tmp_path, name):
    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    guard, root, head, _ = complete_overlay_model(tmp_path)
    (root / name).write_bytes(b"changed-despite-clean-status")
    with pytest.raises(Fault, match="HEAD_BYTES_MISMATCH"):
        live.validate(guard, root, head)


@pytest.mark.parametrize("threat", ["symlink", "missing", "mode"])
def test_RED_AT03_hidden_index_root_type_or_mode_must_not_be_trusted(tmp_path, threat):
    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    guard, root, head, _ = complete_overlay_model(tmp_path)
    path = root / "Dockerfile"
    if threat == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        if threat == "symlink":
            path.symlink_to(root / "Makefile")
    with pytest.raises(Fault, match="^A4235_"):
        live.validate(guard, root, head)


@pytest.mark.parametrize("threat", ["write", "replace", "symlink"])
def test_AT03_full_tree_read_race_rejected_with_held_descriptor(tmp_path, monkeypatch, threat):
    import os

    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    guard, root, head, _ = complete_overlay_model(tmp_path)
    path = root / "Dockerfile"
    inode = path.stat().st_ino
    original_read = os.read
    triggered = False

    def racing_read(fd, count):
        nonlocal triggered
        raw = original_read(fd, count)
        if not triggered and os.fstat(fd).st_ino == inode:
            triggered = True
            if threat == "write":
                path.write_bytes(b"changed-size-and-mtime")
            elif threat == "replace":
                replacement = root / "replacement"
                replacement.write_bytes(b"replacement")
                replacement.replace(path)
            else:
                path.unlink()
                path.symlink_to(root / "Makefile")
        return raw

    monkeypatch.setattr(os, "read", racing_read)
    with pytest.raises(Fault, match="HEAD_BYTES_MISMATCH"):
        live.verify_full_worktree(guard, root, head)
    assert triggered


@pytest.mark.parametrize("name", [b"../outside", b"/outside", b".git/config", b"a//b", b"\xff"])
def test_AT03_full_tree_untrusted_git_path_never_escapes_root(tmp_path, name):
    from scripts import a42361_source_guard as live
    from scripts.a4235_calibration_adapter_contract import Fault

    guard, root, head, _ = complete_overlay_model(tmp_path)
    guard.git = lambda *args: b"100644 blob " + b"0" * 40 + b"\t" + name + b"\0"
    with pytest.raises(Fault, match="HEAD_BYTES_MISMATCH"):
        live.verify_full_worktree(guard, root, head)
