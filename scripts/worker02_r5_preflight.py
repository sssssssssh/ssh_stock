"""Explicit local Linux toolchain/capability probe; no database, installer or workload."""

import argparse
import errno
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
from pathlib import Path

from scripts.a42_artifacts import atomic


def preflight():
    checks = {}
    checks["linux"] = sys.platform == "linux"
    checks["proc_self"] = Path("/proc/self/status").is_file()
    checks["pidfd"] = False
    pidfd_error = None
    if hasattr(os, "pidfd_open"):
        try:
            descriptor = os.pidfd_open(os.getpid(), 0)
        except OSError as error:
            pidfd_error = errno.errorcode.get(error.errno, "UNKNOWN_OS_ERROR")
        else:
            os.close(descriptor)
            checks["pidfd"] = True
    else:
        pidfd_error = "API_ABSENT"
    checks["peer_uid"] = False
    if hasattr(socket, "SO_PEERCRED"):
        try:
            left, right = socket.socketpair(socket.AF_UNIX)
            try:
                _, uid, _ = struct.unpack("3i", left.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                checks["peer_uid"] = uid == os.getuid()
            finally:
                left.close()
                right.close()
        except OSError:
            checks["peer_uid"] = False
    tools = {}
    for name in ("git", "cc", "node", "shellcheck"):
        executable = shutil.which(name)
        state = "MISSING"
        if executable:
            try:
                command = subprocess.run([executable, "--version"], capture_output=True,
                                         timeout=3, check=False)
                state = "AVAILABLE" if command.returncode == 0 else "FAILED_VERSION_PROBE"
            except (OSError, subprocess.TimeoutExpired):
                state = "FAILED_VERSION_PROBE"
        tools[name] = state
        checks[name] = state == "AVAILABLE"
    return {"schema": "worker02.r5.platform.v1", "kernel": platform.release(),
        "python": platform.python_version(), "checks": checks, "tools": tools,
        "pidfd_error": pidfd_error, "status": "PREREQUISITES_PRESENT_NOT_QUALIFIED" if all(
            checks.values()) else "PLATFORM_BLOCKED", "database_contacted": False,
        "performance_qualified": False, "workload_started": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = preflight()
    atomic(args.output, report)
    print(report["status"])
    return 2 if report["status"] == "PLATFORM_BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
