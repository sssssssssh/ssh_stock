"""Sixth overlay exactness; no historical assertion counts or pin bytes are removed."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import a4235_capability_guard as g
from scripts import a42363_complete_guard as guard
from scripts.a4235_calibration_adapter_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "backend/unsafe.py",
        "scripts/a42363_unregistered.py",
        ".github/workflows/unsafe.yml",
        "infra/g1_harness/unsafe.sql",
    ],
)
def test_CF_AT02_exact_registered_paths_not_prefixes(path):
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        guard.validate_paths(guard.STAGE_PATHS | {path})
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        guard.validate_paths(guard.STAGE_PATHS - {guard.MANIFEST})


def test_CF_AT01_AT02_all_five_manifests_and_full_current_identity():
    for path in guard.HISTORICAL:
        raw = subprocess.check_output(["git", "show", f"{guard.BASELINE}:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == raw
    assert len(g.overlay_fingerprint()) == 64
    assert g.path_sha(ROOT / guard.MANIFEST) == g.COMPLETE_MANIFEST_SHA


def test_CF_AT03_normalization_only_excludes_new_self_reference():
    raw = b"COMPLETE_MANIFEST_SHA = '" + b"a" * 64 + b"'\nOLD = True\n"
    assert b"OLD = True" in guard.normalized(raw)
    assert (
        hashlib.sha256(guard.normalized(raw)).digest()
        != hashlib.sha256(guard.normalized(raw.replace(b"True", b"False"))).digest()
    )
    with pytest.raises(ValueError):
        guard.normalized(b"missing")


def test_CF_AT05_AT21_production_templates_and_old_authorizations_are_unchanged():
    from scripts.business_source_contract import HISTORICAL_SOURCE

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
        "scripts/a42361_live_probe_worker.py",
        "infra/g1_control_plane/003_closeout.sql",
    ]
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", guard.BASELINE, HISTORICAL_SOURCE, "--", *protected],
        cwd=ROOT,
    ).strip()

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64
