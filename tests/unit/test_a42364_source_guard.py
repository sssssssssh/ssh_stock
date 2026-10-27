"""Eighth exact layer, all prior manifests and only one reviewed old function edit."""

import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from scripts import a42364_source_guard as g
from scripts.a4235_calibration_adapter_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "infra/g1_pg17_image/extra.sh",
        "scripts/extra.py",
        "backend/extra.py",
        "tests/unit/unreviewed.py",
        ".github/workflows/g1.yml",
    ],
)
def test_AT01_exact_paths_do_not_grant_prefix_permissions(path):
    with pytest.raises(Fault):
        g.validate_paths(g.STAGE_PATHS | {path})
    with pytest.raises(Fault):
        g.validate_paths(g.STAGE_PATHS - {g.MANIFEST})


def test_AT02_history_and_all_committed_pins_match_final_stage():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)

    def tree(sha):
        result = {}
        for row in git("ls-tree", "-r", "-z", sha).split(b"\0"):
            if row:
                meta, path = row.split(b"\t", 1)
                result[path.decode()] = meta.split()[2]
        return result

    current, old = tree("HEAD"), tree(g.BASELINE)
    ids = sorted(set(current.values()) | set(old.values()))
    p = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=b"\n".join(ids) + b"\n",
        cwd=ROOT,
        stdout=subprocess.PIPE,
        check=True,
    )
    stream = io.BytesIO(p.stdout)
    blobs = {}
    for oid in ids:
        actual, kind, size = stream.readline().split()
        assert actual == oid and kind == b"blob"
        blobs[oid] = stream.read(int(size))
        assert stream.read(1) == b"\n"
    manifest = json.loads(blobs[current[g.MANIFEST]])
    assert manifest["stage_paths"] == sorted(g.STAGE_PATHS)
    paths, pins = g.cumulative()
    assert manifest["cumulative_paths"] == sorted(paths) and set(manifest["patch_sha256"]) == pins
    for name, expected in manifest["patch_sha256"].items():
        assert hashlib.sha256(blobs[current[name]]).hexdigest() == expected
    for name in g.HISTORICAL:
        assert blobs[current[name]] == blobs[old[name]]
    for name, oid in old.items():
        if name.startswith("tests/"):
            if name == g.ALLOWED_TEST:
                g.verify_test_adaptation(blobs[oid], blobs[current[name]])
            else:
                assert blobs[current[name]] == blobs[oid]
    delta = {name for name in set(old) | set(current) if old.get(name) != current.get(name)}
    g.validate_paths(delta)


def test_AT03_normalization_preserves_everything_but_one_literal():
    value = b"COMPLETE_MANIFEST_SHA = '" + b"a" * 64 + b"'\nORIGINAL=True\n"
    assert g.normalized(value) != g.normalized(value.replace(b"True", b"False"))
    with pytest.raises(ValueError):
        g.normalized(value + value)


def test_AT03_only_explicitly_reviewed_function_can_change():
    before = (
        "def " + g.ALLOWED_FUNCTION + "():\n    assert True\n\ndef untouched():\n    assert True\n"
    ).encode()
    after = before.replace(b"assert True", b"assert 1 == 1", 1)
    g.verify_test_adaptation(before, after)
    with pytest.raises(Fault):
        g.verify_test_adaptation(before, after.replace(b"untouched", b"renamed"))


def test_AT04_production_and_frozen_sql_never_enter_this_stage():
    paths = [
        "backend",
        "frontend",
        "migrations",
        "config",
        ".github",
        "requirements.lock",
        "requirements-dev.txt",
        "pyproject.toml",
        "scripts/a42361_live_probe_worker.py",
        "scripts/a4236_g1_probe.py",
        "docs/acceptance/evidence",
    ]
    assert not subprocess.check_output(
        ["git", "diff", "--name-only", g.BASELINE, "--", *paths], cwd=ROOT
    ).strip()
