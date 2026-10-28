"""Static source-only closure, never an execution or performance grant."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import a42366_source_guard as guard
from scripts import business_source_contract as business
from scripts.a42363_contract import Fault


@pytest.mark.parametrize("path", [
    "backend/app/new.py", "infra/new.c", ".github/workflows/ci.yml", "config/app.yaml",
    "migrations/new.py", "scripts/a42366_unreviewed.py", "tests/unit/test_a42365_runtime.py",
])
def test_AT_W09_exact_whitelist_rejects_unreviewed_source(path):
    with pytest.raises(Fault, match="A42366_UNREGISTERED_PATH"):
        guard.validate_paths({path})


def test_AT_W09_historical_manifests_and_all_original_tests_keep_their_blobs():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / guard.MANIFEST).read_bytes())
    histories = data["historical_manifest_sha256"]
    assert len(histories) == 10
    objects = business.git_blobs(root, [guard.BASELINE + ":" + path for path in histories])
    for path, digest in histories.items():
        original = objects[guard.BASELINE + ":" + path]
        # Git stores authoritative bytes; a Windows autocrlf checkout is not a
        # physical installation and is not used as a live source qualification.
        assert hashlib.sha256(original).hexdigest() == digest
        assert business.git(root, "show", "HEAD:" + path) == original
    assert not business.git(root, "diff", guard.BASELINE, "--name-only", "--", "tests").strip() \
        or all(path.startswith("tests/unit/test_a42366_") for path in
               business.git(root, "diff", guard.BASELINE, "--name-only", "--", "tests")
               .decode().splitlines())


def test_AT_W09_new_source_pin_does_not_normalize_executable_changes():
    raw = b"A42366_MANIFEST_SHA = '" + b"a" * 64 + b"'\nDENY = True\n"
    assert guard.normalized_dispatch(raw) != guard.normalized_dispatch(
        raw.replace(b"True", b"False")
    )
    with pytest.raises(ValueError, match="A42366_DISPATCH_PIN"):
        guard.normalized_dispatch(raw + raw)


def test_AT_W09_manifest_preserves_exact_unicode_path_names():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / guard.MANIFEST).read_bytes())
    guard.validate_paths(data["stage_paths"])
    assert set(data["patch_sha256"]) == set(data["stage_paths"]) - {guard.MANIFEST, guard.DISPATCH}
    assert guard.AUTHORITY <= set(data["stage_paths"])
    assert all("\ufffd" not in p for p in data["stage_paths"])
