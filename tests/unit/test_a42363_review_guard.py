"""Seventh exact overlay: no historical test or manifest rewrite."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import a4235_capability_guard as g
from scripts import a42363_complete_guard as facade
from scripts import a42363_review_guard as guard
from scripts.a4235_calibration_adapter_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "backend/x.py",
        "frontend/x.vue",
        "migrations/x.py",
        ".github/workflows/x.yml",
        "scripts/a42363_probe.py",
        "tests/unit/test_a4236_source_guard.py",
    ],
)
def test_RF_AT04_new_overlay_rejects_unregistered_path_and_missing_pin(path):
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        guard.validate_paths(guard.STAGE_PATHS | {path})
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        guard.validate_paths(guard.STAGE_PATHS - {guard.MANIFEST})


def test_RF_AT02_six_manifest_original_bytes_and_pins_are_all_preserved():
    assert len(guard.HISTORICAL) == 6
    for name, closing in guard.HISTORICAL.items():
        original = subprocess.check_output(["git", "show", guard.BASELINE + ":" + name], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original
        data = json.loads(original)
        for path, expected in data["patch_sha256"].items():
            raw = subprocess.check_output(["git", "show", closing + ":" + path], cwd=ROOT)
            assert hashlib.sha256(raw).hexdigest() == expected


def test_RF_AT03_full_guard_retains_only_one_self_reference_exception():
    raw = b"COMPLETE_MANIFEST_SHA = '" + b"a" * 64 + b"'\nOLD_SHA = 'old'\n"
    normalized = facade.normalized(raw)
    assert b"OLD_SHA = 'old'" in normalized
    assert normalized != facade.normalized(raw.replace(b"old", b"new"))
    with pytest.raises(ValueError):
        facade.normalized(raw + raw)


def test_RF_AT04_cumulative_facade_keeps_exact_new_stage_and_legacy_stage_separate():
    assert facade.STAGE_PATHS == facade.LEGACY_STAGE_PATHS | guard.STAGE_PATHS
    assert facade.PINNED == facade.LEGACY_PINNED | guard.PINNED
    assert facade.LEGACY_MANIFEST in guard.HISTORICAL
    assert facade.MANIFEST == guard.MANIFEST
    for name in guard.STAGE_PATHS:
        assert (ROOT / name).is_file()
    assert len(g.overlay_fingerprint()) == 64


def test_RF_AT57_all_original_tests_have_identical_git_blobs():
    rows = subprocess.check_output(
        ["git", "ls-tree", "-r", "-z", guard.BASELINE, "--", "tests"], cwd=ROOT
    ).split(b"\0")
    checked = 0
    for row in rows:
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        raw = (ROOT / name.decode()).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert actual == metadata.split()[2].decode()
        checked += 1
    assert checked > 200


def test_RF_AT59_candidate_cannot_change_sql_or_enable_protocol():
    from scripts.a42363_contract import Fault as CurrentFault
    from scripts.a42363_contract import session_method

    with pytest.raises(CurrentFault) as e:
        session_method()
    assert e.value.code == "A42363_METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"
    protected = [
        "backend",
        "frontend",
        "migrations",
        "config",
        ".github",
        "infra",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "scripts/a42361_live_probe_worker.py",
        "scripts/a4236_g1_probe.py",
        "docs/acceptance/evidence",
    ]
    from scripts import a42364_source_guard as engineering

    # Only the separately pinned new files are authorized; no infra directory waiver.
    infra_changes = set(subprocess.check_output(
        ["git", "diff", "--name-only", "-z", engineering.BASELINE, "--", "infra"], cwd=ROOT
    ).decode().split("\0")) - {""}
    assert infra_changes == engineering.INFRA
    protected.remove("infra")
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", guard.BASELINE, "--", *protected], cwd=ROOT
    ).strip()
