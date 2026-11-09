"""Linux OS adapter for owned, fixed, harmless synthetic programs ONLY.

The supervisor is a separate Python process. Neither internal mode imports any
business module, opens a socket, reads environment configuration, or runs a DB.
An independently verified, existing no-network Linux lab is required by the API.
The public CLI cannot mint that permit or execute a Worker.
"""

import hashlib
import json
import math
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PLATFORM_FENCING_PROVEN = False
SCENARIOS = frozenset(("success", "exception", "sleep", "ignore-term", "output-limit"))
MAX_OUTPUT = 65536


class DomainError(RuntimeError):
    pass


def need(condition, code):
    if not condition:
        raise DomainError(code)


def minimal_environment():
    return {"LC_ALL": "C", "LANG": "C", "PYTHONHASHSEED": "0"}


@dataclass(frozen=True)
class OwnedIdentity:
    pid: int
    pgid: int
    sid: int
    start: int


def parse_owned_stat(raw):
    try:
        lead, tail = raw.split(" (", 1)
        parts = tail.rsplit(") ", 1)[1].split()
        result = {
            "pid": int(lead),
            "state": parts[0],
            "pgid": int(parts[2]),
            "sid": int(parts[3]),
            "start": int(parts[19]),
        }
        need(
            all(type(result[k]) is int and result[k] > 0 for k in ("pid", "pgid", "sid", "start")),
            "PROCESS_IDENTITY_UNKNOWN",
        )
        return result
    except (ValueError, IndexError, KeyError):
        raise DomainError("PROCESS_IDENTITY_UNKNOWN") from None


def matches(handle, raw):
    try:
        current = parse_owned_stat(raw)
        return all(getattr(handle, k) == current[k] for k in ("pid", "pgid", "sid", "start"))
    except DomainError:
        return False


def owned_stat(pid):
    # Called only for Popen children this module created, never enumerates /proc.
    return Path(f"/proc/{pid}/stat").read_text("ascii")


def capture_identity(process):
    facts = parse_owned_stat(owned_stat(process.pid))
    need(facts["pgid"] == facts["sid"] == process.pid, "PROCESS_DOMAIN_MISMATCH")
    return OwnedIdentity(facts["pid"], facts["pgid"], facts["sid"], facts["start"])


def signal_owned(process, identity, pidfd, sig):
    need(
        type(identity) is OwnedIdentity and identity.pid == process.pid and pidfd is not None,
        "SIGNAL_TARGET_NOT_OWNED",
    )
    if process.poll() is not None:
        return
    try:
        need(matches(identity, owned_stat(process.pid)), "PID_REUSED_OR_UNCONFIRMED")
        # No killpg: pidfd targets one owned process even across a PID reuse race.
        signal.pidfd_send_signal(pidfd, sig)
    except ProcessLookupError:
        # An exit race is acceptable only if waitpid on our Popen handle confirms it.
        need(process.poll() is not None, "CLEANUP_UNCERTAIN")


class DomainDeadlines:
    def __init__(self, started):
        need(type(started) in (int, float) and math.isfinite(started), "CLOCK_UNKNOWN")
        self.started, self.setup, self.outer = started, started + 180, started + 390
        self.root = self.cleanup = None

    def start_root(self, now):
        need(self.root is None and self.started <= now < self.setup, "ROOT_START_REFUSED")
        self.root = min(now + 180, self.started + 360)
        return self.root

    def begin_cleanup(self, now):
        if self.cleanup is None:
            self.cleanup = min(now + 30, self.outer)
        return self.cleanup


@dataclass(frozen=True)
class LabPermit:
    """Supplied by independent lab operator, never read from JSON/environment.

    Verifier must bind host lease, network namespace isolation, executable/source
    digests and private directory. It is deliberately not implemented here.
    """

    interpreter: Path
    interpreter_sha256: str
    module_sha256: str
    private_directory: Path
    network_namespace: int
    host_lease: str
    verifier: object = field(repr=False)
    synthetic_stop_after: float = 10.0


def verify_lab(permit):
    need(type(permit) is LabPermit and callable(permit.verifier), "LAB_NOT_AUTHORIZED")
    need(
        sys.platform == "linux"
        and hasattr(os, "pidfd_open")
        and hasattr(signal, "pidfd_send_signal"),
        "LINUX_PIDFD_REQUIRED",
    )
    need(permit.verifier(permit) is True, "LAB_EXTERNAL_REVIEW_REQUIRED")
    executable, module = permit.interpreter, Path(__file__).resolve()
    need(
        type(executable) is type(module)
        and executable.is_absolute()
        and executable == executable.resolve()
        and executable.is_file(),
        "FIXED_INTERPRETER_REQUIRED",
    )
    for path, digest in ((executable, permit.interpreter_sha256), (module, permit.module_sha256)):
        for parent in (path, *path.parents):
            metadata = parent.stat()
            need(
                not parent.is_symlink()
                and metadata.st_uid in (0, os.getuid())
                and stat.S_IMODE(metadata.st_mode) & 0o022 == 0,
                "EXECUTABLE_SOURCE_UNSAFE",
            )
        need(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "EXECUTABLE_SOURCE_DRIFT")
    private = permit.private_directory
    need(
        private.is_absolute()
        and private == private.resolve()
        and private.is_dir()
        and private.stat().st_uid == os.getuid()
        and stat.S_IMODE(private.stat().st_mode) & 0o077 == 0,
        "LAB_DIRECTORY_UNSAFE",
    )
    need(
        os.stat("/proc/self/ns/net").st_ino == permit.network_namespace,
        "LAB_NETWORK_NAMESPACE_DRIFT",
    )
    need(
        type(permit.synthetic_stop_after) in (int, float)
        and math.isfinite(permit.synthetic_stop_after)
        and 0 < permit.synthetic_stop_after <= 10,
        "LAB_BUDGET_INVALID",
    )
    return (str(executable), str(module))


@dataclass(eq=False)
class DomainHandle:
    process: object = field(repr=False)
    identity: OwnedIdentity
    pidfd: int = field(repr=False)
    binding: str
    started: float
    consumed: bool = False


def collect_supervisor(process, deadline):
    """Bounded nonblocking byte capture; never returns raw child output to logs."""
    chunks, total = {"stdout": bytearray(), "stderr": bytearray()}, 0
    selector = selectors.DefaultSelector()
    try:
        for pipe, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        while selector.get_map():
            need(time.monotonic() < deadline, "SUPERVISOR_OUTER_TIMEOUT")
            for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                raw = os.read(key.fileobj.fileno(), 4096)
                if not raw:
                    selector.unregister(key.fileobj)
                else:
                    total += len(raw)
                    need(total <= MAX_OUTPUT, "SUPERVISOR_OUTPUT_LIMIT")
                    chunks[key.data].extend(raw)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return bytes(chunks["stdout"]), bytes(chunks["stderr"])
    finally:
        selector.close()


class LinuxProcessDomain:
    def __init__(self, permit, owner=None):
        self.permit, self.owner, self.handles = permit, owner, []

    def spawn(self, binding, scenario):
        started = time.monotonic()
        executable, module = verify_lab(self.permit)
        need(scenario in SCENARIOS and self.owner is not None, "SYNTHETIC_DOMAIN_ONLY")
        self.owner.confirm(binding)
        self.owner.record_intent_before_first_spawn(binding)
        process = None
        try:
            need(time.monotonic() < started + 180, "SETUP_TIMEOUT")
            # No caller-supplied argv, shell, environment, script, PID or module.
            process = subprocess.Popen(
                [executable, "-I", "-S", module, "--internal-synthetic-supervisor", scenario],
                shell=False,
                start_new_session=True,
                close_fds=True,
                env=minimal_environment(),
                cwd=self.permit.private_directory,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            identity = capture_identity(process)
            pidfd = os.pidfd_open(process.pid)
            need(matches(identity, owned_stat(process.pid)), "SPAWN_UNCERTAIN")
            facts = dict(identity.__dict__)
            self.owner.bind_handle(binding, facts)
            handle = DomainHandle(process, identity, pidfd, binding, started)
            self.handles.append(handle)
            # The fixed supervisor waits for this small handshake before spawning
            # its fixed child. Failure before durable handle binding spawns no child.
            payload = (
                json.dumps(
                    {
                        "synthetic_only": True,
                        "stop_after": self.permit.synthetic_stop_after,
                        "started": started,
                    }
                ).encode()
                + b"\n"
            )
            process.stdin.write(payload)
            process.stdin.flush()
            process.stdin.close()
            return handle
        except Exception:
            self.owner.fence(binding, "SPAWN_UNCERTAIN")
            # No guessed PID/group cleanup after uncertain first confirmation.
            # The blocked supervisor's stdin EOF exits without spawning a child.
            if process is not None and process.stdin is not None:
                process.stdin.close()
            raise DomainError("SPAWN_UNCERTAIN") from None

    def wait(self, handle):
        need(any(handle is h for h in self.handles) and not handle.consumed, "HANDLE_NOT_OWNED")
        handle.consumed = True
        try:
            self.owner.confirm_handle(handle.binding, dict(handle.identity.__dict__))
            out, err = collect_supervisor(handle.process, handle.started + 390)
            need(not err and handle.process.returncode == 0, "SUPERVISOR_FAILED")
            need(len(out) <= MAX_OUTPUT, "SUPERVISOR_OUTPUT_LIMIT")
            result = json.loads(out)
            need(
                type(result) is dict
                and set(result)
                == {
                    "root",
                    "os_exit",
                    "teardown",
                    "first_error",
                    "output_sha256",
                    "descendants",
                    "fencing",
                },
                "RECEIPT_INVALID",
            )
            need(
                result["fencing"] == "NOT_PROVEN"
                and result["descendants"] == "FIXED_NO_FORK_CHILD",
                "RECEIPT_INVALID",
            )
            if result["teardown"] is True:
                self.owner.cleanup_ack(
                    handle.binding, dict(handle.identity.__dict__), exited=True, teardown=True
                )
            else:
                self.owner.fence(handle.binding, "CLEANUP_UNCERTAIN")
            result["durable_ack"] = result["teardown"] is True
            result["status"] = classify_receipt(
                root=result["root"],
                os_exit=result["os_exit"],
                teardown=result["teardown"],
                durable_ack=result["durable_ack"],
                fencing=False,
            )
            if result["first_error"] is not None:
                result["status"] = "INCOMPLETE"
            return result
        except Exception:
            self.owner.fence(handle.binding, "SUPERVISOR_UNCERTAIN")
            # Watchdog/OS failure cannot be made safe merely by killing watchdog.
            # Stop the experiment, retain reservation, require external fencing.
            raise DomainError("CLEANUP_UNCERTAIN") from None
        finally:
            os.close(handle.pidfd)
            for pipe in (handle.process.stdout, handle.process.stderr):
                pipe.close()


def classify_receipt(*, root, os_exit, teardown, durable_ack, fencing):
    # L1 proves only our fixed synthetic child. Host/remote fencing is a separate
    # NOT_PROVEN field even when the lab-only OS lifecycle has been observed.
    if (
        root == "SUCCESS"
        and type(os_exit) is int
        and os_exit == 0
        and teardown is True
        and durable_ack is True
    ):
        return "LAB_OS_MOCK_VERIFIED"
    return "INCOMPLETE"


def _child(scenario):
    need(scenario in SCENARIOS, "SYNTHETIC_DOMAIN_ONLY")
    need(sys.stdin.buffer.readline(32) == b"OWNED_SYNTHETIC\n", "HANDSHAKE_INVALID")
    print("ROOT_READY", flush=True)
    if scenario == "exception":
        print("ROOT_FAILED", flush=True)
        return 7
    if scenario == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if scenario in ("sleep", "ignore-term"):
        time.sleep(400)
    if scenario == "output-limit":
        print("x" * (MAX_OUTPUT + 1), flush=True)
    print("ROOT_SUCCESS", flush=True)
    return 0


def _supervisor(scenario):
    """Independent process, no business imports. Only fixed non-forking child."""
    payload = sys.stdin.buffer.readline(1025)
    need(len(payload) <= 1024, "HANDSHAKE_INVALID")
    data = json.loads(payload)
    need(
        set(data) == {"synthetic_only", "stop_after", "started"}
        and data["synthetic_only"] is True
        and type(data["stop_after"]) in (int, float)
        and math.isfinite(data["stop_after"])
        and 0 < data["stop_after"] <= 10,
        "HANDSHAKE_INVALID",
    )
    started = data["started"]
    need(
        type(started) in (int, float)
        and math.isfinite(started)
        and 0 <= time.monotonic() - started < 180,
        "SETUP_TIMEOUT",
    )
    deadlines = DomainDeadlines(started)
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).resolve()),
            "--internal-synthetic-child",
            scenario,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=minimal_environment(),
        shell=False,
        start_new_session=True,
        close_fds=True,
    )
    pidfd, identity = None, None
    first_error, root, teardown = None, "UNKNOWN", False
    output, selector = bytearray(), selectors.DefaultSelector()
    cancel = [False]
    signal.signal(signal.SIGTERM, lambda *_: cancel.__setitem__(0, True))
    try:
        identity = capture_identity(process)
        pidfd = os.pidfd_open(process.pid)
        need(matches(identity, owned_stat(process.pid)), "SPAWN_UNCERTAIN")
        process.stdin.write(b"OWNED_SYNTHETIC\n")
        process.stdin.flush()
        process.stdin.close()
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            deadline = deadlines.root if deadlines.root is not None else deadlines.setup
            # A lab-only earlier stop never extends the frozen 180/180/30/390 caps.
            deadline = min(deadline, started + data["stop_after"])
            if cancel[0] or now >= deadline:
                first_error = first_error or "SYNTHETIC_DEADLINE"
                break
            for key, _ in selector.select(min(0.05, max(0, deadline - now))):
                raw = os.read(key.fileobj.fileno(), 4096)
                if not raw:
                    selector.unregister(key.fileobj)
                    continue
                need(len(output) + len(raw) <= MAX_OUTPUT, "CHILD_OUTPUT_LIMIT")
                output.extend(raw)
            if b"ROOT_READY\n" in output and deadlines.root is None:
                deadlines.start_root(time.monotonic())
        if first_error is None and process.poll() == 0 and output == b"ROOT_READY\nROOT_SUCCESS\n":
            root = "SUCCESS"
        else:
            first_error = first_error or "SYNTHETIC_ROOT_FAILED"
            root = "FAILED"
    except Exception:
        first_error = first_error or "SUPERVISOR_FAULT"
    finally:
        try:
            cleanup = deadlines.begin_cleanup(time.monotonic())
            if process.poll() is None:
                signal_owned(process, identity, pidfd, signal.SIGTERM)
                try:
                    process.wait(timeout=max(0.001, min(5.0, cleanup - time.monotonic())))
                except subprocess.TimeoutExpired:
                    need(time.monotonic() < cleanup, "CLEANUP_UNCERTAIN")
                    signal_owned(process, identity, pidfd, signal.SIGKILL)
                    process.wait(timeout=max(0.001, cleanup - time.monotonic()))
            teardown = process.poll() is not None and time.monotonic() < cleanup
        except Exception:
            first_error = first_error or "CLEANUP_UNCERTAIN"
        selector.close()
        if pidfd is not None:
            os.close(pidfd)
        for pipe in (process.stdout, process.stderr):
            pipe.close()
        if process.stdin is not None:
            process.stdin.close()
    print(
        json.dumps(
            {
                "root": root,
                "os_exit": process.poll(),
                "teardown": teardown,
                "first_error": first_error,
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "descendants": "FIXED_NO_FORK_CHILD",
                "fencing": "NOT_PROVEN",
            }
        ),
        flush=True,
    )
    return 0


def public_main(_argv=None):
    print("R1_REAL_EXECUTION_NOT_AUTHORIZED")
    return 2


def run_lab_synthetic(permit, owner, binding, scenario):
    """Explicit API for a future independent lab harness, no built-in permit."""
    domain = LinuxProcessDomain(permit, owner)
    return domain.wait(domain.spawn(binding, scenario))


if __name__ == "__main__":
    # These two internal modes can only execute the fixed harmless synthetic
    # program; no configuration/argument can select a business module or Worker.
    try:
        if (
            len(sys.argv) == 3
            and sys.argv[2] in SCENARIOS
            and sys.argv[1] == "--internal-synthetic-child"
        ):
            raise SystemExit(_child(sys.argv[2]))
        if (
            len(sys.argv) == 3
            and sys.argv[2] in SCENARIOS
            and sys.argv[1] == "--internal-synthetic-supervisor"
        ):
            raise SystemExit(_supervisor(sys.argv[2]))
        raise SystemExit(public_main())
    except (DomainError, ValueError, OSError):
        print("SYNTHETIC_DOMAIN_INCOMPLETE")
        raise SystemExit(2) from None
