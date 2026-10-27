"""Linux L1/static native checks. No PG/Podman/cgroup creation, credentials or cloud."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.a42363_contract import Fault

ROOT = Path(__file__).resolve().parents[2]


def test_AT05_AT08_native_bootstrap_compiles_and_unprivileged_entry_cannot_initialize(tmp_path):
    target = tmp_path / "bootstrap-native"
    result = subprocess.run(
        [
            "/usr/bin/cc",
            "-std=c17",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-D_FORTIFY_SOURCE=2",
            str(ROOT / "infra/g1_pg17_image/bootstrap.c"),
            "-o",
            str(target),
        ],
        capture_output=True,
        timeout=20,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    if result.returncode != 0:
        # Fixed nonsecret diagnostic survives the existing CI redaction plugin.
        code = (
            "A42331_NATIVE_COMPILER_HELPER_LOOKUP_FAILED"
            if b"cannot execute" in result.stderr or b"not found" in result.stderr
            else "A42331_NATIVE_COMPILER_FAILED"
        )
        raise RuntimeError(code)
    assert os.getuid() != 999  # Never run initdb, even if a future runner uses that UID.
    rejected = subprocess.run([str(target)], env={}, capture_output=True, timeout=2)
    assert rejected.returncode == 78 and rejected.stdout == b""
    assert rejected.stderr == b"A42363_BOOTSTRAP_INCOMPLETE\n"


@pytest.mark.parametrize(
    "name", ["bootstrap.sh", "healthcheck.sh", "build_offline.sh", "verify_supply_chain.sh"]
)
def test_AT05_static_posix_shell_syntax_not_execution(name):
    result = subprocess.run(
        ["sh", "-n", str(ROOT / "infra/g1_pg17_image" / name)],
        env={},
        capture_output=True,
        timeout=2,
    )
    assert result.returncode == 0


def test_AT05_shellcheck_all_fixed_entry_scripts_without_execution():
    names = ("bootstrap.sh", "healthcheck.sh", "build_offline.sh", "verify_supply_chain.sh")
    result = subprocess.run(
        ["shellcheck", "--shell=sh", *(str(ROOT / "infra/g1_pg17_image" / n) for n in names)],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()


@pytest.mark.parametrize("fault", ["fsync", "pipe", "exec"])
def test_AT33_AT35_private_child_fault_is_bounded_without_claiming_kernel_scope(tmp_path, fault):
    import time

    from scripts.a42363_supervisor import bounded_child

    marker = tmp_path / ".incomplete"
    marker.write_text("OFFLINE_MODEL_ONLY")

    def child():
        if fault == "exec":
            os.execve("/not/a/real/private-test-program", ["test"], {})
        if fault == "fsync":
            os.fsync = lambda fd: time.sleep(60)
            os.fsync(1)
        else:
            read_fd, write_fd = os.pipe()
            try:
                os.read(read_fd, 1)
            finally:
                os.close(read_fd)
                os.close(write_fd)

    start = time.monotonic()
    with pytest.raises(Fault):
        bounded_child(child, timeout_ms=150)
    assert time.monotonic() - start < 3 and marker.exists()
    assert not (tmp_path / "manifest.json").exists()


def test_AT33_entry_does_not_import_or_activate_from_cli_or_env():
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/a42364_entry.py"), "--execute"],
        env={"G1_APPROVED": "true", "PGPASSWORD": "OFFLINE_NOT_REAL"},
        capture_output=True,
        timeout=2,
    )
    assert result.returncode == 78 and result.stdout == result.stderr == b""


def test_AT17_AT20_real_candidate_parser_stays_nonqualifying_for_model_rows():
    from scripts.a42363_proposals import TARGET_OIDS
    from scripts.a42364_session import validate_offline_projection

    result = validate_offline_projection(
        [("100ms", True, None, None, None, None, None)], TARGET_OIDS
    )
    assert result["candidate_vectors_valid"] is True
    assert result["target_session_settings_observed"] is False and result["qualifies"] is False


@pytest.mark.parametrize(
    "oids,rows",
    [
        ((25,), [("100ms", True, None, None, None, None, None)]),
        ((25, 16, 25, 1028, 16, 20, 20), [("0", True, None, None, None, None, None)]),
        ((25, 16, 25, 1028, 16, 20, 20), []),
    ],
)
def test_AT18_bad_target_projection_metadata_rejected(oids, rows):
    from scripts.a42364_session import validate_offline_projection

    with pytest.raises(Fault):
        validate_offline_projection(rows, oids)
