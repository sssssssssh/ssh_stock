"""Exact overlay/identity checks; physical source-FD race coverage remains in legacy Linux tests."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import a42362_source_guard as g
from scripts.a4235_calibration_adapter_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name",
    [
        "scripts/extra.py",
        "infra/g1_harness/other.sql",
        "backend/app/unsafe.py",
        ".github/workflows/other.yml",
        "tests/unit/other.py",
    ],
)
def test_AT02_no_directory_or_prefix_exemptions(name):
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        g.validate_paths(g.STAGE_PATHS | {name})
    with pytest.raises(Fault, match="FROZEN_FILE_CHANGED"):
        g.validate_paths(g.STAGE_PATHS - {g.MANIFEST})


def test_AT01_AT06_final_commit_has_exact_paths_and_historical_manifests_unchanged():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    changed = set(
        subprocess.check_output(["git", "diff", "--name-only", "-z", g.BASELINE, head], cwd=ROOT)
        .decode()
        .split("\0")
    ) - {""}
    g.validate_paths(changed)
    for name in (
        "docs/acceptance/a42351_reviewer_overlay_manifest.json",
        "docs/acceptance/a4236_overlay_manifest.json",
        "docs/acceptance/a42361_overlay_manifest.json",
    ):
        assert subprocess.check_output(
            ["git", "show", f"{head}:{name}"], cwd=ROOT
        ) == subprocess.check_output(["git", "show", f"{g.BASELINE}:{name}"], cwd=ROOT)
    manifest = json.loads(
        subprocess.check_output(["git", "show", f"{head}:{g.MANIFEST}"], cwd=ROOT)
    )
    assert manifest["stage_paths"] == sorted(g.STAGE_PATHS)
    assert set(manifest["patch_sha256"]) == g.PINNED
    for name in g.PINNED:
        actual = subprocess.check_output(["git", "show", f"{head}:{name}"], cwd=ROOT)
        assert hashlib.sha256(actual).hexdigest() == manifest["patch_sha256"][name]


def test_AT04_normalization_excludes_only_the_new_self_reference_literal():
    old = b"OLD_ASSERTION = True\nSERVICE_MANIFEST_SHA = '" + b"a" * 64 + b"'\n"
    value = g.normalize_guard(old)
    assert b"OLD_ASSERTION = True" in value and b"0" * 64 in value
    assert g.normalize_guard(old.replace(b"True", b"False")) != value
    with pytest.raises(ValueError):
        g.normalize_guard(b"unrecognized source")


def test_AT70_no_production_migrations_workflows_dependencies_or_old_protocol_changes():
    protected = [
        "backend",
        "config",
        "frontend",
        "migrations",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "docs/acceptance/evidence",
        "scripts/a42341_calibration_runner.py",
        "scripts/a42341_calibration_review.py",
        "docs/acceptance/v14_a4_2_3_4_calibration_protocol.md",
    ]
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", g.BASELINE, "--", *protected], cwd=ROOT
    ).strip()
