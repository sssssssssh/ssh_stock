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
