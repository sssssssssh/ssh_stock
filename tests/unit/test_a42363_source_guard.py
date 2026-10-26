"""Fifth overlay contracts retain all old tests and independently frozen manifests."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import a4235_capability_guard as g
from scripts import a42363_source_guard as closeout
from scripts.a4235_calibration_adapter_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "scripts/a42363_extra.py",
        "infra/g1_harness/extra.sql",
        "backend/app/unsafe.py",
        ".github/workflows/new.yml",
    ],
)
def test_AT02_exact_paths_no_directory_exemptions(path):
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        closeout.validate_paths(closeout.STAGE_PATHS | {path})


def test_AT01_AT03_committed_manifest_full_guard_and_four_history_layers():
    for path in closeout.HISTORICAL:
        before = subprocess.check_output(["git", "show", f"{closeout.BASELINE}:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == before
    assert len(g.overlay_fingerprint()) == 64
    assert g.path_sha(ROOT / closeout.MANIFEST) == g.CLOSEOUT_MANIFEST_SHA
    assert len(g.expected_identity().head_sha) == 40


def test_AT04_only_closeout_literal_is_normalized():
    raw = b"CLOSEOUT_MANIFEST_SHA = '" + b"a" * 64 + b"'\nOLD_CHECK = True\n"
    assert b"OLD_CHECK = True" in closeout.normalized(raw)
    assert (
        hashlib.sha256(closeout.normalized(raw)).digest()
        != hashlib.sha256(closeout.normalized(raw.replace(b"True", b"False"))).digest()
    )
    with pytest.raises(ValueError):
        closeout.normalized(b"invalid")


def test_AT09_production_and_frozen_protocols_untouched():
    protected = [
        "backend",
        "frontend",
        "config",
        "migrations",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "docs/acceptance/evidence",
        "scripts/a4236_g1_probe.py",
        "scripts/a42341_calibration_runner.py",
    ]
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", closeout.BASELINE, "--", *protected], cwd=ROOT
    ).strip()
