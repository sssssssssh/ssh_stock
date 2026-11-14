"""Offline spec mutations; invented inputs never attest a real image or resource."""

import ast
import builtins
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import biz_perf_p1_04_w05_lab_plan as lab

ROOT = Path(__file__).absolute().parents[2]
RUN = "12345678-1234-4234-8234-123456789abc"
# Deliberately invented format-only digest, never a usable image recommendation.
IMAGE = "docker.io/library/postgres:17@sha256:" + "a" * 64


def values():
    return dict(run_uuid=RUN, pinned_image=IMAGE,
                password_secret_file=f"/run/w05-secrets/{RUN}/pg_password")


def document():
    return json.loads((ROOT / "infra/biz_perf_w05/compose.pg17.yaml").read_text("utf-8"))


def test_valid_format_stays_blocked_and_names_are_only_proposals():
    result = lab.review(values())
    assert result["spec_structure_valid"] is True
    assert result["input_format_valid"] is True
    assert result["status"] == "BLOCKED"
    assert result["mode"] == "OFFLINE_LAB_SPEC_REVIEW"
    assert result["live_resource_verified"] is False
    assert result["root_attempts"] == 0
    assert result["B_GATE"] == result["TARGETED_PG17_GATE"] == "NOT_APPROVED"
    assert result["authorization"] == "AUTHORIZATION_PENDING"
    assert result["resources"] == dict(project=f"w05-{RUN}", volume=f"w05-{RUN}-pgdata",
                                        network=f"w05-{RUN}-private", database="w05_lab_test")
    assert {"IMAGE_AUTHENTICITY", "OWNERSHIP_AND_FRESHNESS", "COST_AND_BUDGET_SIGNOFF"} <= set(
        result["pending_checks"])
    assert result["budget"]["disk_quota"] == "NOT_ENFORCED"
    assert result["budget"]["cpu_capacity"] == "NOT_ENFORCED"


def test_missing_values_are_blocked():
    result = lab.review()
    assert result["spec_structure_valid"] is True
    assert result["input_format_valid"] is False
    assert result["resources"] == {}


@pytest.mark.parametrize("image", [
    "postgres:latest", "postgres:17", "postgres:16@sha256:" + "a" * 64,
    "docker.io/library/postgres:18@sha256:" + "a" * 64,
    "evil.example/postgres:17@sha256:" + "a" * 64,
    "docker.io/library/postgres:17@sha256:" + "a" * 63,
    "docker.io/library/postgres:17@sha256:" + "g" * 64,
    "docker.io/library/postgres:17@sha256:" + "a" * 64 + "\n",
    "docker.io/library/postgres@sha256:" + "a" * 64,
    "${DOCKER_DATABASE_URL}", 17, None,
])
def test_image_format_refuses_unreviewed_repositories_versions_and_floating_tags(image):
    request = values()
    request["pinned_image"] = image
    assert lab.review(request)["input_format_valid"] is False


@pytest.mark.parametrize("run", ["", "../old", RUN.upper(), "0" * 36,
                                 "00000000-0000-0000-0000-000000000000", None, 1])
def test_invalid_uuid(run):
    request = values()
    request["run_uuid"] = run
    result = lab.review(request)
    assert result["input_format_valid"] is False
    assert result["resources"] == {}


@pytest.mark.parametrize("secret", [".env", "/repo/.env", "/run/docker.sock", "../secret",
                                    "password", "https://secret",
                                    "/run/w05-secrets/old/pg_password",
                                    f"/run/w05-secrets/{RUN}/../pg_password", None,
                                    f"/run/w05-secrets/{RUN}/pg_password\n"])
def test_bad_secret_references_are_never_opened_or_echoed(secret):
    request = values()
    request["password_secret_file"] = secret
    result = lab.review(request)
    assert result["input_format_valid"] is False
    assert result["resources"] == {}
    assert "password_secret_file" not in result


@pytest.mark.parametrize("key", ["new_volume", "approval", "system_identifier", "permit",
                                 "owner", "cost_approved", "password", "compose_path"])
def test_self_attestation_unknown_keys_cannot_raise_status(key):
    request = values()
    request[key] = "PRIVATE-UNTRUSTED"
    result = lab.review(request)
    assert result["input_format_valid"] is False
    assert result["status"] == "BLOCKED"
    assert "PRIVATE-UNTRUSTED" not in json.dumps(result)


@pytest.mark.parametrize(("path", "bad"), [
    (("services", "pg17", "env_file"), [".env"]),
    (("services", "pg17", "ports"), ["5432:5432"]),
    (("services", "pg17", "network_mode"), "host"),
    (("services", "pg17", "privileged"), True),
    (("services", "pg17", "devices"), ["/dev/sda"]),
    (("services", "pg17", "volumes"), ["/var/run/docker.sock:/var/run/docker.sock"]),
    (("services", "pg17", "volumes"), ["./data:/var/lib/postgresql/data"]),
    (("services", "pg17", "restart"), "always"),
    (("services", "pg17", "profiles"), []),
    (("services", "pg17", "image"), "postgres:17"),
    (("services", "pg17", "command"), "python -m app.cli worker"),
    (("services", "pg17", "environment", "POSTGRES_HOST_AUTH_METHOD"), "trust"),
    (("services", "pg17", "environment", "DATABASE_URL"), "${DOCKER_DATABASE_URL}"),
    (("services", "pg17", "environment", "POSTGRES_PASSWORD"), "PRIVATE-PASSWORD"),
    (("services", "pg17", "environment", "PGHOST"), "production-db"),
    (("services", "pg17", "environment", "PGDATA"), "/existing"),
    (("services", "pg17", "mem_limit"), "8g"),
    (("services", "worker"), {"image": "app"}),
    (("services", "scheduler"), {"image": "app"}),
    (("services", "migration"), {"image": "app"}),
    (("networks", "private", "external"), True),
    (("networks", "private", "internal"), False),
    (("volumes", "pgdata", "external"), True),
    (("volumes", "pgdata", "name"), "old-volume"),
    (("volumes", "pgdata", "driver_opts"), {"device": "/existing"}),
    (("secrets", "pg_password", "file"), ".env"),
    (("include",), ["../../docker-compose.yml"]),
])
def test_dangerous_or_unexpected_spec_mutations_fail_closed(monkeypatch, path, bad):
    spec = document()
    target = spec
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    monkeypatch.setattr(lab, "_load_spec", lambda: spec)
    result = lab.review(values())
    assert result["spec_structure_valid"] is False
    assert result["status"] == "BLOCKED"
    assert "PRIVATE-PASSWORD" not in json.dumps(result)


def test_duplicate_keys_and_yaml_expansion_are_refused(monkeypatch):
    for raw in (b'{"services": {}, "services": {}}', b'x: &x {a: 1}\nservices: *x',
                b'{}' * 20000, b'\xff', b'{"x": NaN}'):
        monkeypatch.setattr(lab, "_read_fixed_spec", lambda raw=raw: raw)
        assert lab.review(values())["spec_structure_valid"] is False


@pytest.mark.parametrize("change", ["access_time", "content_size", "symlink", "hardlink"])
def test_fixed_read_handles_access_time_but_refuses_changed_content_or_links(monkeypatch, change):
    original = Path.lstat
    count = 0

    def observation(path):
        nonlocal count
        info = original(path)
        if path != lab.SPEC_PATH:
            return info
        count += 1
        result = SimpleNamespace(**{name: getattr(info, name) for name in (
            "st_mode", "st_file_attributes", "st_nlink", "st_size", "st_dev", "st_ino",
            "st_mtime_ns", "st_atime_ns") if hasattr(info, name)})
        if change == "access_time":
            result.st_atime_ns += count
        elif change == "content_size" and count > 2:
            result.st_size += 1
        elif change == "symlink":
            result.st_mode = 0o120777
        elif change == "hardlink":
            result.st_nlink = 2
        return result

    monkeypatch.setattr(Path, "lstat", observation)
    if change == "access_time":
        assert lab._read_fixed_spec().startswith(b"{")
    else:
        with pytest.raises(ValueError):
            lab._read_fixed_spec()


@pytest.mark.parametrize("args", [[], ["execute"], ["up"], ["cleanup"], ["--help"],
                                  ["review-offline", "--allow"], ["review-offline", "--force"],
                                  ["review-offline", "--permit", "anything"],
                                  ["review-offline", "--input", ".env"]])
def test_cli_rejection_precedes_every_read(monkeypatch, capsys, args):
    def forbidden():
        pytest.fail("rejected CLI attempted a read")
    monkeypatch.setattr(lab, "_load_spec", forbidden)
    assert lab.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
    assert result["root_attempts"] == 0


def test_cli_offline_review_has_no_live_path(capsys):
    assert lab.main(["review-offline"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["spec_structure_valid"] is True
    assert result["status"] == "BLOCKED"


def test_import_and_review_without_network_subprocess_environment_or_writes(monkeypatch):
    source = (ROOT / "scripts/biz_perf_p1_04_w05_lab_plan.py").read_bytes()
    reads = []
    original_open = builtins.open

    def guarded_open(path, mode="r", *args, **kwargs):
        assert Path(path) == lab.SPEC_PATH
        assert mode == "rb"
        reads.append(Path(path))
        return original_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("forbidden external operation")

    spec = importlib.util.spec_from_loader("isolated_lab_safe_import", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ROOT / "scripts/biz_perf_p1_04_w05_lab_plan.py")
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", forbidden)
        m.setattr(socket, "socket", forbidden)
        m.setattr(socket, "create_connection", forbidden)
        m.setattr(subprocess, "Popen", forbidden)
        m.setattr(os, "system", forbidden)
        m.setattr(os, "getenv", forbidden)
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        m.setattr(builtins, "open", guarded_open)
        result = module.review(values())
    assert result["spec_structure_valid"] is True
    assert reads == [lab.SPEC_PATH]


def test_source_ast_has_only_stdlib_imports_and_no_execution_or_write_api():
    source = (ROOT / "scripts/biz_perf_p1_04_w05_lab_plan.py").read_text("utf-8")
    tree = ast.parse(source)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"json", "re", "stat", "sys", "pathlib", "uuid"}
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)}
    assert not calls & {"connect", "run", "Popen", "write", "write_text", "write_bytes",
                        "unlink", "mkdir", "getenv", "system", "create_engine"}
    assert len(source.splitlines()) <= 250


def test_root_compose_unchanged():
    raw = (ROOT / "docker-compose.yml").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == ROOT_COMPOSE_SHA256


ROOT_COMPOSE_SHA256 = "9c67276868fe2daff1a9d88772f0e070b538830cf28554d261a4e2ac2f6fcf9e"
