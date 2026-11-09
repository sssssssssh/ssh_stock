"""Exact LF/CRLF frozen bytes, including all 18 reports and protected paths."""

import hashlib

import pytest

from tests.unit import test_perf03_lnx_w04a_offline_contract as w

PATHS = tuple(w.FROZEN_CONTENT)


def original(relative):
    raw = (w.ROOT / relative).read_bytes()
    assert b"\r" not in raw
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


def test_A08_symlinks_rejected_even_when_target_bytes_match(tmp_path):
    for index, relative in enumerate(PATHS):
        target = write(tmp_path, "target-" + str(index), original(relative))
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        with pytest.raises(AssertionError, match="^W04A_FROZEN_REGULAR_FILE_REQUIRED$"):
            w.assert_frozen_file(tmp_path, relative)


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
