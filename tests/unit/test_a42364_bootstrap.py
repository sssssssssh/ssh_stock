"""Static image/source contracts only; no image build, PG binaries or containers."""

import shutil
from pathlib import Path

import pytest

from scripts.a42363_contract import Fault
from scripts.a42364_bootstrap_builder import build_plan, pinned_image, validate_image_source

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "value",
    [
        "postgres:17",
        "postgres:latest",
        "postgres@sha256:" + "0" * 64,
        "postgres@sha256:" + "f" * 64,
        "--privileged",
        "",
    ],
)
def test_AT05_AT08_floating_or_placeholder_images_are_not_buildable(value):
    with pytest.raises(Fault, match="IMAGE_DIGEST_REQUIRED"):
        pinned_image(value)


def test_AT05_source_plan_does_not_execute_build(monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unexpected command"))
    result = build_plan(
        ROOT, "offline/compiler@sha256:" + "1" * 64, "offline/pg17@sha256:" + "2" * 64
    )
    assert result["approved"] is False and result["measured"] is False
    assert "--network=none" in result["operation"] and "--pull=never" in result["operation"]
    assert result["source"]["physical"] == "NOT_RUN_NOT_AUTHORIZED"


@pytest.mark.parametrize(
    "mutation", ["HBA_TRUST", "EXPOSE", "HEALTHCHECK", "ENTRYPOINT", "RUN_REPLACED"]
)
def test_AT06_AT08_image_policy_mutations_rejected(tmp_path, mutation):
    target = tmp_path / "infra/g1_pg17_image"
    shutil.copytree(ROOT / "infra/g1_pg17_image", target)
    if mutation == "HBA_TRUST":
        path = target / "pg_hba.template"
        path.write_text("local all all trust\n")
    else:
        path = target / "Containerfile"
        raw = path.read_text()
        if mutation == "RUN_REPLACED":
            raw = raw.replace("RUN cc ", "RUN curl https://untrusted.invalid/ && cc ")
            path.write_text(raw)
            with pytest.raises(Fault, match="IMAGE_BUILD_COMMAND_DRIFT"):
                validate_image_source(tmp_path)
            return
        raw = (
            raw.replace('space-g1-pg17-bootstrap"]', 'foreign"]')
            if mutation == "ENTRYPOINT"
            else raw + "\n" + mutation + " 5432\n"
        )
        path.write_text(raw)
    with pytest.raises(Fault):
        validate_image_source(tmp_path)


def test_AT07_native_source_keeps_passwords_out_of_env_and_argv():
    raw = (ROOT / "infra/g1_pg17_image/bootstrap.c").read_text()
    assert "--pwfile=/proc/self/fd/" in raw and "clearenv()" in raw
    assert "PGPASSWORD" not in raw and "CREATE DATABASE" not in raw
    assert 'mkdirat(parent, "pgdata", 0700)' in raw
    assert "O_EXCL" in raw and "listen_addresses=" in raw


def test_AT05_l1_compiler_has_only_fixed_search_path_and_locale():
    import ast

    source = ast.parse((ROOT / "tests/integration_offline/test_a42364_process.py").read_text())
    function = next(n for n in source.body if isinstance(n, ast.FunctionDef))
    calls = [
        n
        for n in ast.walk(function)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "run"
    ]
    compile_call = calls[0]
    args = compile_call.args[0]
    assert args.elts[0].value == "/usr/bin/cc"
    values = [ast.literal_eval(k.value) for k in compile_call.keywords if k.arg == "env"]
    assert values == [{"PATH": "/usr/bin:/bin", "LC_ALL": "C"}]
    assert "-Werror" in [n.value for n in args.elts if isinstance(n, ast.Constant)]
