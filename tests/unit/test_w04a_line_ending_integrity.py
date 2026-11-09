"""Exact LF/CRLF frozen bytes, including all 18 reports and protected paths."""

import hashlib
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit import test_perf03_lnx_w04a_offline_contract as w

PATHS = tuple(w.FROZEN_CONTENT)


def original(relative):
    # Validate real checkout bytes before any test-fixture transformation.
    w.assert_frozen_file(w.ROOT, relative)
    raw = (w.ROOT / relative).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest == w.FROZEN_CONTENT[relative][1]:
        raw = raw.replace(b"\r\n", b"\n")  # Validated fixture construction ONLY.
    assert hashlib.sha256(raw).hexdigest() == w.FROZEN_CONTENT[relative][0]
    return raw


def write(root, relative, raw):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


@pytest.mark.parametrize("relative", PATHS)
@pytest.mark.parametrize("crlf", [False, True], ids=["A01-LF", "A02-CRLF"])
def test_fixed_representation_accepts_only_reviewed_hash(tmp_path, relative, crlf):
    raw = original(relative)
    if crlf:
        raw = raw.replace(b"\n", b"\r\n")
    write(tmp_path, relative, raw)
    assert w.assert_frozen_file(tmp_path, relative) == w.FROZEN_CONTENT[relative][int(crlf)]


@pytest.mark.parametrize("mutation", [
    "mixed", "mixed-reverse", "character", "insert-space", "delete-space",
    "extra-newline", "missing-newline", "bom", "nul", "unexpected-cr",
])
def test_A03_A07_any_noncanonical_bytes_rejected_for_all_18(tmp_path, mutation):
    for relative in PATHS:
        raw = original(relative)
        assert raw.count(b"\n") > 1 and raw.endswith(b"\n") and b" " in raw
        match mutation:
            case "mixed":
                changed = raw.replace(b"\n", b"\r\n", 1)
            case "mixed-reverse":
                changed = raw.replace(b"\n", b"\r\n").replace(b"\r\n", b"\n", 1)
            case "character":
                index = next(i for i, value in enumerate(raw) if 65 <= value <= 90)
                changed = raw[:index] + bytes([65 if raw[index] != 65 else 66]) + raw[index+1:]
            case "insert-space":
                changed = raw.replace(b" ", b"  ", 1)
            case "delete-space":
                changed = raw.replace(b" ", b"", 1)
            case "extra-newline":
                changed = raw + b"\n"
            case "missing-newline":
                changed = raw[:-1]
            case "bom":
                changed = b"\xef\xbb\xbf" + raw
            case "nul":
                changed = b"\x00" + raw[1:]
            case "unexpected-cr":
                changed = b"\r" + raw
        write(tmp_path, relative, changed)
        with pytest.raises(AssertionError, match="^W04A_FROZEN_CONTENT_MISMATCH$"):
            w.assert_frozen_file(tmp_path, relative)


def test_A08_symlinks_rejected_even_when_target_bytes_match(tmp_path, monkeypatch, record_property):
    for index, relative in enumerate(PATHS):
        target = write(tmp_path, "target-" + str(index), original(relative))
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with monkeypatch.context() as context:
            try:
                path.symlink_to(target)
            except OSError as error:
                if getattr(error, "winerror", None) != 1314:
                    raise
                record_property("w04a_symlink_os_capability", "UNAVAILABLE_WINDOWS_PRIVILEGE")
                # Exercise the same rejection branch without requiring OS privilege.
                original_stat = Path.lstat
                context.setattr(Path, "lstat", lambda self, target=path, reader=original_stat, **kw:
                    SimpleNamespace(st_mode=stat.S_IFLNK) if self == target
                    else reader(self, **kw))
            with pytest.raises(AssertionError, match="^W04A_FROZEN_REGULAR_FILE_REQUIRED$"):
                w.assert_frozen_file(tmp_path, relative)


@pytest.mark.parametrize("crlf", [False, True])
def test_original_helper_works_for_all_18_checkout_representations(tmp_path, monkeypatch, crlf):
    baselines = {relative: original(relative) for relative in PATHS}
    for relative, raw in baselines.items():
        write(tmp_path, relative, raw.replace(b"\n", b"\r\n") if crlf else raw)
    monkeypatch.setattr(w, "ROOT", tmp_path)
    for relative, raw in baselines.items():
        assert original(relative) == raw


def test_symlink_privilege_failure_still_executes_all_rejection_assertions(tmp_path, monkeypatch):
    def denied(*a, **k):
        error = PermissionError("SIMULATED_WINDOWS_PRIVILEGE")
        error.winerror = 1314
        raise error
    monkeypatch.setattr(Path, "symlink_to", denied)
    observations = []
    test_A08_symlinks_rejected_even_when_target_bytes_match(
        tmp_path, monkeypatch, lambda k, v: observations.append((k, v)))
    assert len(observations) == 18
    assert all(v == "UNAVAILABLE_WINDOWS_PRIVILEGE" for _, v in observations)


def test_missing_directory_unknown_path_fail_closed(tmp_path):
    relative = PATHS[0]
    with pytest.raises(FileNotFoundError):
        w.assert_frozen_file(tmp_path, relative)
    (tmp_path / relative).mkdir(parents=True)
    with pytest.raises(AssertionError, match="^W04A_FROZEN_REGULAR_FILE_REQUIRED$"):
        w.assert_frozen_file(tmp_path, relative)
    with pytest.raises(AssertionError, match="^W04A_UNREGISTERED_FROZEN_PATH$"):
        w.assert_frozen_file(tmp_path, "unknown.py")


def test_A09_all_paths_and_historical_anchors_preserved_without_runtime_git(tmp_path, monkeypatch):
    assert len(PATHS) == 18
    assert set(PATHS) == set(w.PROTECTED) | set(w.REPORTS)
    assert len(w.PROTECTED) == 16 and len(w.REPORTS) == 2
    assert w.PROTECTION_BASELINE == "8443b7cd524a6964b24cecd60df5be5b6c46783b"
    monkeypatch.setattr("subprocess.check_output", lambda *a, **k: pytest.fail("runtime Git"))
    for relative, historical in (w.PROTECTED | w.REPORTS).items():
        assert historical in w.FROZEN_CONTENT[relative]
        write(tmp_path, relative, original(relative))
        w.assert_frozen_file(tmp_path, relative)
