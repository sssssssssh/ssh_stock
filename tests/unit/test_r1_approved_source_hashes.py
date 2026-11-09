"""Strict current-version identity; historical evidence never permits rollback."""

import copy
import hashlib
import socket
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit import test_r1_real_root_protocol as r

TARGET = "tests/unit/test_perf03_lnx_w04a_offline_contract.py"


def populate(root, crlf=False):
    for name in r.ORIGINALS:
        raw = (r.ROOT / name).read_bytes()
        if b"\r\n" in raw:
            raw = raw.replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == r.CURRENT_APPROVED_SOURCE_HASHES[name][0]
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw.replace(b"\n", b"\r\n") if crlf else raw)


@pytest.mark.parametrize("crlf", [False, True])
def test_current_exact_six_representations(tmp_path, crlf):
    populate(tmp_path, crlf)
    assert set(r.verify_approved_sources(tmp_path)) == set(r.ORIGINALS)


@pytest.mark.parametrize("mutation", ["character", "space", "newline", "bom", "nul",
                                     "cr", "mixed"])
def test_every_file_rejects_nonapproved_bytes(tmp_path, mutation):
    populate(tmp_path)
    for name in r.ORIGINALS:
        path = tmp_path / name
        raw = path.read_bytes()
        changes = {"character": b"X" + raw[1:], "space": raw + b" ",
                   "newline": raw + b"\n", "bom": b"\xef\xbb\xbf" + raw,
                   "nul": b"\x00" + raw, "cr": b"\r" + raw,
                   "mixed": raw.replace(b"\n", b"\r\n", 1)}
        path.write_bytes(changes[mutation])
        with pytest.raises(r.p.Refused, match="^R1_APPROVED_SOURCE_HASH$"):
            r.verify_approved_sources(tmp_path)
        path.write_bytes(raw)


def historical_fixture():
    # Reverse only the exact approved 60dacb8 test delta, never consult runtime Git.
    text = (r.ROOT / TARGET).read_bytes().replace(b"\r\n", b"\n").decode()
    text = text[:text.index("PROTECTION_BASELINE =")] + text[text.index("def cell(tag, value):"):]
    text = text.replace(
        '            self.assertIn(expected, FROZEN_CONTENT[relative])'
        '  # Retain historical byte identity.\n'
        '            self.assertIn(assert_frozen_file(ROOT, relative), FROZEN_CONTENT[relative])\n'
        '        self.assertEqual(set(FROZEN_CONTENT), set(REPORTS) | set(PROTECTED))\n',
        '            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),'
        ' expected)\n')
    raw = text.encode()
    assert hashlib.sha256(raw).hexdigest() == r.ORIGINALS[TARGET]
    return raw


@pytest.mark.parametrize("crlf", [False, True])
def test_old_version_is_provable_but_never_current(tmp_path, crlf):
    populate(tmp_path)
    raw = historical_fixture()
    if crlf:
        raw = raw.replace(b"\n", b"\r\n")
        assert hashlib.sha256(raw).hexdigest() == (
            "cdfb820f1833b41a1170f4f923d4f89a39354bcfb725c2c89d816081b97f359b")
    (tmp_path / TARGET).write_bytes(raw)
    with pytest.raises(r.p.Refused, match="^R1_APPROVED_SOURCE_HASH$"):
        r.verify_approved_sources(tmp_path)


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "parent-symlink"])
def test_missing_or_nonregular_path_refused(tmp_path, monkeypatch, record_property, kind):
    populate(tmp_path)
    name = TARGET
    path = tmp_path / name
    raw = path.read_bytes()
    path.unlink()
    if kind == "directory":
        path.mkdir()
    if kind == "symlink":
        target = tmp_path / "valid-target"
        target.write_bytes(raw)
        try:
            path.symlink_to(target)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314:
                raise
            record_property("symlink_os_capability", "UNAVAILABLE_WINDOWS_PRIVILEGE")
            original_stat = Path.lstat
            monkeypatch.setattr(Path, "lstat", lambda self, **kw:
                SimpleNamespace(st_mode=stat.S_IFLNK) if self == path
                else original_stat(self, **kw))
    if kind == "parent-symlink":
        folder = path.parent
        folder.rename(tmp_path / "escaped")
        try:
            folder.symlink_to(tmp_path / "escaped", target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314:
                raise
            record_property("symlink_os_capability", "UNAVAILABLE_WINDOWS_PRIVILEGE")
            original_stat = Path.lstat
            monkeypatch.setattr(Path, "lstat", lambda self, **kw:
                SimpleNamespace(st_mode=stat.S_IFLNK) if self == folder
                else original_stat(self, **kw))
    with pytest.raises(r.p.Refused, match="^R1_APPROVED_SOURCE_PATH$"):
        r.verify_approved_sources(tmp_path)


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "hash", "version",
                                    "mapping-extra", "mapping-missing"])
def test_manifest_and_commit_identity_cannot_drift(tmp_path, monkeypatch, change):
    populate(tmp_path)
    paths = list(r.ORIGINALS)
    if change == "extra":
        paths.append("unknown.py")
    elif change == "missing":
        paths.pop()
    elif change == "duplicate":
        paths[-1] = paths[0]
    elif change in ("hash", "mapping-extra", "mapping-missing"):
        bad = copy.deepcopy(r.CURRENT_APPROVED_SOURCE_HASHES)
        if change == "hash":
            bad[TARGET] = (r.ORIGINALS[TARGET],) * 2
        elif change == "mapping-extra":
            bad["unknown.py"] = ("0" * 64,) * 2
        else:
            bad.pop(TARGET)
        monkeypatch.setattr(r, "CURRENT_APPROVED_SOURCE_HASHES", bad)
    else:
        monkeypatch.setattr(r, "CURRENT_APPROVED_SOURCE_VERSION", "0" * 40)
    with pytest.raises(r.p.Refused):
        r.verify_approved_sources(tmp_path, paths)


def test_no_runtime_git_network_or_environment_identity(tmp_path, monkeypatch):
    populate(tmp_path)
    def forbidden(*a, **k):
        raise AssertionError("UNAUTHORIZED_RUNTIME_IDENTITY")
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    assert len(r.verify_approved_sources(tmp_path)) == 6
    with pytest.raises(r.p.Refused):
        r.verify_approved_sources(tmp_path, approved_version="0" * 40)
