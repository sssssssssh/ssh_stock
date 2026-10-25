"""Actual process-group termination code, default unconfigured; OS proof NOT_RUN.

Offline tests inject process/clock operations. They do not kill or start G1 workers.
"""

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass

from scripts.a42361_contract import Fault, require
from scripts.a42361_deployment import checked_executable, installed

_OWNED = object()


@dataclass(frozen=True)
class OwnedProcess:
    process: object
    pid: int
    scope_sha256: str
    _seal: object


class Watchdog:
    def __init__(self, deployment=None, authorization=None):
        self.deployment, self.authorization = deployment, authorization

    def terminate_owned(self, child, timeout_ms=2000):
        installed(self.deployment)  # No kill for arbitrary user objects or PID arguments.
        from scripts.a42361_one_shot_store import committed

        authorization = committed(self.authorization)
        require(
            type(child) is OwnedProcess
            and child._seal is _OWNED
            and child.pid == child.process.pid
            and child.pid > 1
            and child.pid != os.getpid()
            and child.scope_sha256 == authorization.grant.payload_sha256
            and timeout_ms == 2000,
            "A42361_PROCESS_OWNERSHIP_UNPROVEN",
        )
        started = time.monotonic_ns()
        try:
            if child.process.poll() is not None:
                return dict(terminated=True, reaped=True, actual_proof="REQUIRES_INDEPENDENT_AUDIT")
            # An unreaped direct child cannot have its PID reused; never target a received PID.
            require(os.getpgid(child.pid) == child.pid, "A42361_PROCESS_OWNERSHIP_UNPROVEN")
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                remaining = 2 - (time.monotonic_ns() - started) / 1_000_000_000
                require(remaining > 0, "A42361_TERMINATION_NOT_PROVEN")
                child.process.wait(timeout=remaining)
            require(
                child.process.poll() is not None and time.monotonic_ns() - started <= 2_000_000_000,
                "A42361_TERMINATION_NOT_PROVEN",
            )
            return dict(terminated=True, reaped=True, actual_proof="REQUIRES_INDEPENDENT_AUDIT")
        except Fault:
            raise
        except BaseException:
            raise Fault("A42361_TERMINATION_NOT_PROVEN") from None

    def _run_command(
        self, executable, expected_sha, arguments, scope_sha256, timeout_ms, input_bytes=None
    ):
        """PRIVATE controller primitive; callers construct fixed commands, never external SQL/argv.

        This runs only inside an independently installed actor with no business environment.
        Its output is bounded before parsing and never copied to error/log fields.
        """
        installed(self.deployment)
        from scripts.a42361_one_shot_store import committed

        authorization = committed(self.authorization)
        require(scope_sha256 == authorization.grant.payload_sha256, "A42361_PROCESS_SCOPE_MISMATCH")
        require(
            0 < timeout_ms <= 2000
            and type(arguments) is tuple
            and all(type(v) is str and "\0" not in v for v in arguments)
            and (input_bytes is None or type(input_bytes) is bytes and len(input_bytes) <= 65536),
            "A42361_PROCESS_REQUEST_INVALID",
        )
        executable = checked_executable(executable, expected_sha)
        process = None
        try:
            process = subprocess.Popen(
                [executable, *arguments],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={},
                start_new_session=True,
            )
            child = OwnedProcess(process, process.pid, scope_sha256, _OWNED)
            try:
                stdout = self._bounded_communicate(process, input_bytes, timeout_ms)
            except BaseException as error:
                self.terminate_owned(child)
                raise Fault(
                    error.code if isinstance(error, Fault) else "A42361_PROCESS_TIMEOUT_NO_RETRY"
                ) from None
            require(len(stdout) <= 65536, "A42361_PROCESS_OUTPUT_TOO_LARGE")
            return process.returncode, stdout
        except Fault:
            raise
        except BaseException:
            if process is not None and process.poll() is None:
                try:
                    self.terminate_owned(OwnedProcess(process, process.pid, scope_sha256, _OWNED))
                except Fault:
                    raise Fault("A42361_TERMINATION_NOT_PROVEN") from None
            raise Fault("A42361_PROCESS_FAILED") from None

    @staticmethod
    def _bounded_communicate(process, payload, timeout_ms):
        """Do not buffer arbitrary child output before enforcing the size/deadline cap."""
        deadline = time.monotonic_ns() + timeout_ms * 1_000_000
        output = bytearray()
        payload = memoryview(payload or b"")
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if payload:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
                require(remaining > 0, "A42361_PROCESS_TIMEOUT_NO_RETRY")
                for key, _ in selector.select(remaining):
                    if key.fileobj is process.stdin:
                        count = os.write(process.stdin.fileno(), payload[:4096])
                        payload = payload[count:]
                        if not payload:
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    else:
                        chunk = os.read(process.stdout.fileno(), 4096)
                        if not chunk:
                            selector.unregister(process.stdout)
                        output.extend(chunk)
                        require(len(output) <= 65536, "A42361_PROCESS_OUTPUT_TOO_LARGE")
            remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
            require(remaining > 0, "A42361_PROCESS_TIMEOUT_NO_RETRY")
            process.wait(timeout=remaining)
        return bytes(output)
