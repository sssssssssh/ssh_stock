"""Real overlay mutations and inert Python entry checks; no container or DB operations."""

import ast
import builtins
import io
import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import biz_perf_p1_04_w05_worker_gate as gate

ROOT = Path(__file__).absolute().parents[2]
SCRIPT = ROOT / "scripts/biz_perf_p1_04_w05_worker_gate.py"
SPEC = ROOT / "infra/biz_perf_w05/compose.worker.yaml"
# Invented syntax-only value; never supplied to an engine or recommended as a real image.
IMAGE = "example.invalid/w05-worker@sha256:" + "a" * 64


def document():
    return json.loads(SPEC.read_bytes())


def assert_inert(result):
    assert result["execution_available"] is False
    assert result["real_network_verified"] is False
    assert result["root_attempts"] == 0
    assert result["B_GATE"] == result["TARGETED_PG17_GATE"] == "NOT_APPROVED"
    assert result["AUTHORIZATION"] == "AUTHORIZATION_PENDING"
    assert result["BUDGET"] == "DRAFT_NOT_APPROVED"
    assert result["REAL_PG17"] == result["REAL_WORKER"] == "NOT_RUN"
    assert result["HOTSPOT"] == "NONE_PROVEN"


def test_real_overlay_only_adds_worker_on_existing_project_private_network():
    spec = document()
    pg = json.loads((ROOT / "infra/biz_perf_w05/compose.pg17.yaml").read_bytes())
    assert set(spec) == {"name", "services"}
    assert spec["name"] == pg["name"] == "w05-${W05_RUN_UUID:?missing}"
    assert set(spec["services"]) == {"w05_worker"}
    worker = spec["services"]["w05_worker"]
    assert worker["networks"] == ["private"]
    assert pg["networks"]["private"]["internal"] is True
    assert worker["image"] == "${W05_WORKER_PINNED_IMAGE:?missing}"
    assert worker["pull_policy"] == "never"
    assert worker["entrypoint"] == [
        "python", "-B", "-m", "scripts.biz_perf_p1_04_w05_worker_gate"]
    assert worker["command"] == ["review-offline"]
    assert worker["environment"] == {
        "W05_DB_HOST": "pg17", "W05_DB_PORT": "5432",
        "W05_DB_NAME": "w05_lab_test", "W05_DB_USER": "w05_lab_worker"}
    result = gate.review()
    assert result["status"] == "TOPOLOGY_SPEC_REVIEWABLE_ONLY"
    assert result["spec_structure_valid"] is True
    assert_inert(result)


@pytest.mark.parametrize(("path", "bad"), [
    (("name",), "production"),
    (("include",), ["../../docker-compose.yml"]),
    (("volumes",), {"pgdata": {}}),
    (("secrets",), {"password": {"file": ".env"}}),
    (("networks",), {"private": {"external": True}}),
    (("services", "pg17"), {"image": "postgres:17"}),
    (("services", "scheduler"), {"command": "app.cli scheduler"}),
    (("services", "w05_worker", "ports"), ["5432:5432"]),
    (("services", "w05_worker", "expose"), ["5432"]),
    (("services", "w05_worker", "networks"), ["private", "default"]),
    (("services", "w05_worker", "network_mode"), "host"),
    (("services", "w05_worker", "privileged"), True),
    (("services", "w05_worker", "cap_add"), ["NET_ADMIN"]),
    (("services", "w05_worker", "devices"), ["/dev/sda"]),
    (("services", "w05_worker", "volumes"), ["./:/app"]),
    (("services", "w05_worker", "volumes"), ["/var/run/docker.sock:/run/docker.sock"]),
    (("services", "w05_worker", "env_file"), [".env"]),
    (("services", "w05_worker", "secrets"), ["pg_password"]),
    (("services", "w05_worker", "user"), "0:0"),
    (("services", "w05_worker", "user"), "appuser"),
    (("services", "w05_worker", "read_only"), False),
    (("services", "w05_worker", "read_only"), 1),
    (("services", "w05_worker", "cap_drop"), []),
    (("services", "w05_worker", "security_opt"), []),
    (("services", "w05_worker", "pids_limit"), -1),
    (("services", "w05_worker", "init"), 1),
    (("services", "w05_worker", "profiles"), []),
    (("services", "w05_worker", "restart"), "always"),
    (("services", "w05_worker", "depends_on"), ["pg17"]),
    (("services", "w05_worker", "mem_limit"), "4g"),
    (("services", "w05_worker", "memswap_limit"), "6g"),
    (("services", "w05_worker", "pull_policy"), "always"),
    (("services", "w05_worker", "build"), {"context": "../.."}),
    (("services", "w05_worker", "image"), "worker:latest"),
    (("services", "w05_worker", "image"), IMAGE),
    (("services", "w05_worker", "image"), "${W05_WORKER_PINNED_IMAGE:-worker:latest}"),
    (("services", "w05_worker", "entrypoint"), ["python", "-m", "app.cli", "worker"]),
    (("services", "w05_worker", "command"), ["execute"]),
    (("services", "w05_worker", "command"), ["python", "-m", "alembic", "upgrade", "head"]),
    (("services", "w05_worker", "healthcheck"), {"test": ["CMD", "seed"]}),
    (("services", "w05_worker", "post_start"), [{"command": "seed"}]),
    (("services", "w05_worker", "environment", "DATABASE_URL"), "PRIVATE-URI"),
    (("services", "w05_worker", "environment", "PGPASSWORD"), "PRIVATE-PASSWORD"),
    (("services", "w05_worker", "environment", "W05_DB_HOST"), "production-db"),
    (("services", "w05_worker", "environment", "W05_DB_PORT"), "5433"),
    (("services", "w05_worker", "environment", "W05_DB_NAME"), "postgres"),
    (("services", "w05_worker", "environment", "W05_DB_USER"), "w05_lab_owner"),
    (("services", "w05_worker", "environment", "APPROVED"), "true"),
    (("services", "w05_worker", "labels"), {"permit": "approved"}),
])
def test_each_structure_mutation_is_blocked_without_echo(monkeypatch, path, bad):
    spec = document()
    node = spec
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad
    result = gate.inspect_overlay(spec)
    assert result["status"] == "BLOCKED"
    assert result["spec_structure_valid"] is False
    assert "PRIVATE" not in json.dumps(result)
    assert_inert(result)
    monkeypatch.setattr(gate, "_read_fixed_spec", lambda: json.dumps(spec).encode())
    assert gate.review() == result


@pytest.mark.parametrize("field", ["image", "profiles", "user", "read_only", "entrypoint",
                                   "command", "pids_limit", "cap_drop", "security_opt"])
def test_missing_required_worker_fields_are_blocked(field):
    spec = document()
    del spec["services"]["w05_worker"][field]
    assert gate.inspect_overlay(spec)["status"] == "BLOCKED"


@pytest.mark.parametrize("spec", [None, [], {}, {"approved": True}, float("nan")])
def test_non_spec_and_self_approval_are_blocked(spec):
    result = gate.inspect_overlay(spec)
    assert result["status"] == "BLOCKED"
    assert_inert(result)


@pytest.mark.parametrize("image", ["worker:latest", "worker:1", "@sha256:" + "a" * 64,
                                  "worker@sha256:" + "A" * 64,
                                  "worker@sha256:" + "a" * 63,
                                  IMAGE + "\n", "https://" + IMAGE, "${IMAGE}", None, 1])
def test_resolved_image_syntax_is_checked_but_no_image_is_authenticated(image):
    result = gate.inspect_overlay(document(), pinned_image=image)
    assert result["status"] == "BLOCKED"
    assert_inert(result)


def test_invented_digest_only_meets_syntax_and_does_not_authorize():
    result = gate.inspect_overlay(document(), pinned_image=IMAGE)
    assert result["status"] == "TOPOLOGY_SPEC_REVIEWABLE_ONLY"
    assert result["image_authenticity_verified"] is False
    assert IMAGE not in json.dumps(result)
    assert_inert(result)


@pytest.mark.parametrize("raw", [b'{"name":1,"name":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                b'x: &x {a: 1}\nservices: *x', b'\xff', b'{}' * 20000,
                                b'[' * 1500, "{}"],
                         ids=["duplicate", "nan", "infinity", "yaml", "utf8", "oversize",
                              "recursive", "not-bytes"])
def test_fixed_json_parser_rejects_ambiguity_and_bad_input(monkeypatch, raw):
    monkeypatch.setattr(gate, "_read_fixed_spec", lambda: raw)
    result = gate.review()
    assert result["status"] == "BLOCKED"
    assert_inert(result)


@pytest.mark.parametrize("change", ["atime", "size", "inode", "mtime", "symlink",
                                   "ancestor_link", "reparse", "hardlink", "directory",
                                   "too_large", "missing", "unreadable"])
def test_fixed_reader_refuses_replacements_and_keeps_atime_harmless(monkeypatch, change):
    original = Path.lstat
    count = 0

    def observation(path):
        nonlocal count
        info = original(path)
        if path != SPEC and not (change == "ancestor_link" and path == SPEC.parent):
            return info
        if change == "missing":
            raise FileNotFoundError
        count += 1
        result = SimpleNamespace(**{key: getattr(info, key, 0) for key in (
            "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_atime_ns", "st_mode",
            "st_nlink", "st_file_attributes")})
        if change == "atime":
            result.st_atime_ns += count
        elif change in {"size", "inode", "mtime"} and count > 2:
            key = {"size": "st_size", "inode": "st_ino", "mtime": "st_mtime_ns"}[change]
            setattr(result, key, getattr(result, key) + 1)
        elif change in {"symlink", "ancestor_link"}:
            result.st_mode = stat.S_IFLNK | 0o777
        elif change == "reparse":
            result.st_file_attributes |= stat.FILE_ATTRIBUTE_REPARSE_POINT
        elif change == "hardlink":
            result.st_nlink = 2
        elif change == "directory":
            result.st_mode = stat.S_IFDIR | 0o755
        elif change == "too_large":
            result.st_size = gate.MAX_BYTES + 1
        return result

    monkeypatch.setattr(Path, "lstat", observation)
    if change == "unreadable":
        def unavailable(*args, **kwargs):
            raise PermissionError
        monkeypatch.setattr(builtins, "open", unavailable)
    result = gate.review()
    assert result["status"] == ("TOPOLOGY_SPEC_REVIEWABLE_ONLY" if change == "atime"
                                else "BLOCKED")
    assert_inert(result)


@pytest.mark.parametrize("args", [None, [], ["review-offline"], ["execute"], ["run-live"],
                                 ["run"], ["up"], ["start"], ["cleanup"], ["permit"],
                                 ["force"], ["review-offline", "--permit", "PRIVATE"],
                                 {"approved": True}, object()])
def test_main_is_fixed_refusal_before_any_spec_or_environment_read(monkeypatch, capsys, args):
    def forbidden(*args, **kwargs):
        pytest.fail("main attempted an external action")

    with monkeypatch.context() as m:
        m.setattr(gate, "review", forbidden)
        m.setattr(builtins, "open", forbidden)
        m.setattr(os, "getenv", forbidden)
        m.setattr(socket, "socket", forbidden)
        m.setattr(subprocess, "Popen", forbidden)
        assert gate.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "EXECUTION_NOT_AVAILABLE"
    assert result["spec_structure_valid"] is False
    assert "PRIVATE" not in json.dumps(result)
    assert_inert(result)


def test_in_process_import_inspection_and_review_only_read_fixed_spec(monkeypatch):
    source, spec = SCRIPT.read_bytes(), document()
    original_open = builtins.open
    reads = []

    def read_only(path, mode="r", *args, **kwargs):
        assert Path(path) == SPEC and mode == "rb"
        reads.append(path)
        return original_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("external action during import or pure inspection")

    namespace = {"__file__": str(SCRIPT), "__name__": "isolated_worker_gate"}
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", forbidden)
        m.setattr(io, "open", forbidden)
        m.setattr(socket, "socket", forbidden)
        m.setattr(subprocess, "Popen", forbidden)
        m.setattr(os, "system", forbidden)
        m.setattr(os, "getenv", forbidden)
        exec(compile(source, str(SCRIPT), "exec"), namespace)
        assert namespace["inspect_overlay"](spec)["spec_structure_valid"] is True
        m.setattr(builtins, "open", read_only)
        assert namespace["review"]()["spec_structure_valid"] is True
    assert reads == [SPEC]


def test_source_is_small_stdlib_only_without_live_or_write_api():
    source = SCRIPT.read_text("utf-8")
    tree = ast.parse(source)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"json", "re", "stat", "sys", "pathlib"}
    assert not any(isinstance(node, (ast.While, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)}
    assert not calls & {"connect", "run", "Popen", "write", "write_bytes", "write_text",
                        "unlink", "mkdir", "getenv", "system", "create_engine", "get"}
    assert len(source.splitlines()) <= 220


def test_subprocess_entry_under_no_socket_no_app_no_write_audit():
    probe = r'''
import builtins, contextlib, io, json, os, sys
from pathlib import Path
path = Path(sys.argv[1])
source = path.read_bytes()
real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in {'app','sqlalchemy','psycopg','dotenv','docker','subprocess','socket'}:
        raise AssertionError('forbidden import')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system','os.mkdir'):
        raise AssertionError('external action')
    if event == 'open':
        name, mode, flags = args
        if isinstance(name, str) and name.endswith(('.env', '.yaml')):
            raise AssertionError('entry read forbidden')
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            raise AssertionError('file write')
sys.addaudithook(audit)
namespace = {'__file__':str(path), '__name__':'worker_probe'}
exec(compile(source, str(path), 'exec'), namespace)
assert not any(n.split('.')[0] in {'app','sqlalchemy','psycopg','dotenv','docker'}
               for n in sys.modules)
expected = None
for args in (None, [], ['review-offline'], ['execute'], ['up'], ['cleanup'],
             ['review-offline','--approved','true'], {'approved':True}):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert namespace['main'](args) == 2
    result = json.loads(output.getvalue())
    assert result['status'] == 'EXECUTION_NOT_AVAILABLE'
    assert result['root_attempts'] == 0 and result['execution_available'] is False
    assert expected is None or result == expected
    expected = result
# Exercise the actual __main__ guard; it too exits 2 without opening the spec.
with contextlib.redirect_stdout(io.StringIO()):
    try:
        exec(compile(source, str(path), 'exec'),
             {'__file__':str(path), '__name__':'__main__'})
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError('missing refusal exit')
print('INERT_ENTRY_VERIFIED')
'''
    result = subprocess.run([sys.executable, "-B", "-c", probe, str(SCRIPT)], cwd=ROOT,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "INERT_ENTRY_VERIFIED"
