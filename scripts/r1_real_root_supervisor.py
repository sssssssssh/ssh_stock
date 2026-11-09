"""Offline injectable external-supervision algorithm; never launches OS processes."""

from copy import deepcopy

from scripts.r1_real_root_protocol import (
    BUDGET,
    StateMachine,
    digest,
    require,
    validate_request,
)

SPAWN_TEMPLATE = {
    "interpreter": "APPROVED_PY312_IDENTITY_PENDING",
    "module": "scripts.r1_real_root_adapter",
    "argv": ["--execute-fixed-r1"],
    "shell": False,
    "new_session": True,
    "environment": {"LLM_ENABLED": "false"},
    "real_spawn": "DISABLED",
}


class Supervisor:
    """Tick-driven; fake interfaces must return, never block inside a test tick.

    A blocking real syscall cannot be rescued by this Python algorithm. There is
    no real ProcessHandle implementation or executable spawn bridge in this slice.
    """

    def __init__(self, request, source_hashes, owner, process, clock, receipts):
        validate_request(request, source_hashes)
        require(getattr(process, "evidence_kind", None) == "OFFLINE_FAKE_PROCESS", "R1_PROCESS")
        self.request, self.binding = deepcopy(request), digest(request)
        self.owner, self.process, self.clock, self.receipts = owner, process, clock, receipts
        self.machine = StateMachine()
        self.start = clock()
        self.setup_deadline, self.outer_deadline = self.start + 180, self.start + 390
        self.root_deadline = self.cleanup_deadline = None
        self.handle = None
        self.burned = self.term_sent = self.kill_sent = False
        self.root = self.exit = self.cleanup = None
        self.fencing = "NOT_REQUESTED"
        self.next_issued = False
        self.cleanup_done = False

    def owned(self):
        if self.handle is None or not self.process.owned(self.handle, self.binding):
            return False
        fact = self.process.identity(self.handle)
        expected = {
            "binding": self.binding,
            "domain_ref": self.request["process_domain_ref"],
            "host_ref": self.request["host_lease_ref"],
            "pg_ref": self.request["pg_resource_ref"],
        }
        if type(fact) is not dict or set(fact) != set(expected) | {
            "pid",
            "pgid",
            "sid",
            "creation",
        }:
            return False
        if any(fact[k] != v for k, v in expected.items()):
            return False
        if not all(type(fact[k]) is int and fact[k] > 0 for k in ("pid", "pgid", "sid")):
            return False
        if fact["pid"] != fact["pgid"] or fact["pid"] != fact["sid"]:
            return False
        return self.owner.confirm_handle(self.binding, self.handle, fact) == "OFFLINE_HANDLE_ACK"

    def fail(self, code, *, uncertain=True):
        self.machine.fail(code, self.clock(), uncertain=uncertain)
        if uncertain:
            self.fencing = "FENCING_PENDING"

    def start_once(self):
        require(not self.burned, "R1_REPLAY")
        self.burned = True
        try:
            require(self.owner.reserve(self.binding) == "OFFLINE_RESERVED", "R1_OWNER_UNKNOWN")
            require(
                self.owner.confirm(self.binding, "BEFORE_SPAWN") == "OFFLINE_ACK",
                "R1_OWNER_UNKNOWN",
            )
            require(self.owner.record_intent(self.binding) == "OFFLINE_ACK", "R1_OWNER_UNKNOWN")
            self.machine.move("REGISTERED", self.clock())
            if self.clock() >= self.setup_deadline:
                self.fail("SETUP_TIMEOUT")
                return
            self.machine.move("SPAWN_REQUESTED", self.clock())
            self.handle = self.process.spawn(deepcopy(SPAWN_TEMPLATE), self.binding)
            if not self.owned():
                self.fail("SPAWN_UNCERTAIN")
                return
            self.machine.move("SPAWN_CONFIRMED", self.clock())
            if self.clock() >= self.setup_deadline:
                self.fail("SETUP_TIMEOUT")
        except Exception:
            self.fail("SPAWN_UNCERTAIN")

    def cleanup_request(self):
        if self.cleanup_deadline is None:
            self.cleanup_deadline = min(self.clock() + BUDGET["cleanup"], self.outer_deadline)
        if self.machine.state not in ("INCOMPLETE", "CLEANUP_UNCERTAIN"):
            self.machine.move("CLEANUP_REQUESTED", self.clock())

    def tick(self):
        # Sticky failure: a late actor SUCCESS/DONE cannot change the first cause.
        if self.cleanup_done or self.machine.state in ("CLEANUP_CONFIRMED", "CLEANUP_UNCERTAIN"):
            return self.summary()
        try:
            now = self.clock()
            require(now >= self.machine.last_time, "R1_CLOCK")
            if self.owner.confirm(self.binding, "LEASE") != "OFFLINE_ACK":
                self.fail("FENCING_PENDING")
                return self.summary()
            if not self.owned():
                self.fail("DOMAIN_MISMATCH")
                return self.summary()
            event = self.process.poll(self.handle)
            now = self.clock()  # Returning late must not use a stale pre-syscall timestamp.
            if event == "SYSCALL_BLOCKED":
                self.fail("SYSCALL_UNCERTAIN")
                return self.summary()
            if self.machine.state == "SPAWN_CONFIRMED":
                if now >= self.setup_deadline:
                    self.fail("SETUP_TIMEOUT", uncertain=False)
                    self.cleanup_request()
                elif event == "ROOT_STARTED":
                    self.root_deadline = min(now + 180, self.start + 360)
                    self.machine.move("ROOT_STARTED", now)
            elif self.machine.state == "ROOT_STARTED":
                if now >= self.root_deadline:
                    self.fail("ROOT_TIMEOUT", uncertain=False)
                    self.cleanup_request()
                elif event == "DONE":
                    self.root = self.receipts.root(self.binding)
                    if self.root != "OFFLINE_TERMINAL_FROZEN":
                        self.fail("ROOT_INCOMPLETE", uncertain=False)
                    else:
                        self.machine.move("ROOT_TERMINAL_OBSERVED", now)
                        self.machine.move("OUTPUT_FROZEN", now)
                    self.cleanup_request()
            if self.cleanup_deadline is not None:
                if now >= self.cleanup_deadline:
                    self.fail("CLEANUP_TIMEOUT")
                    return self.summary()
                self.exit = self.process.exit_receipt(self.handle, self.binding)
                now = self.clock()
                if now >= self.cleanup_deadline:
                    self.fail("CLEANUP_TIMEOUT")
                    return self.summary()
                if self.exit is None:
                    # Recheck exact opaque handle ownership before each signal.
                    require(self.owned(), "R1_DOMAIN")
                    if not self.term_sent:
                        self.process.signal(self.handle, "TERM", self.binding)
                        self.term_sent, self.term_time = True, now
                    elif not self.kill_sent and now >= self.term_time + 5:
                        self.process.signal(self.handle, "KILL", self.binding)
                        self.kill_sent = True
                elif self.exit == "OFFLINE_EXIT_ZERO":
                    self.cleanup = self.receipts.cleanup(self.binding)
                    if self.cleanup != "OFFLINE_CLEANUP_ACK":
                        self.fail("CLEANUP_UNKNOWN")
                    elif self.owner.confirm(self.binding, "CLEANUP") != "OFFLINE_ACK":
                        self.fail("ACK_UNKNOWN")
                    elif self.clock() >= self.cleanup_deadline:
                        self.fail("CLEANUP_TIMEOUT")
                    elif self.machine.first_error is None:
                        self.machine.move("CLEANUP_CONFIRMED", now)
                        self.cleanup_done = True
                    else:
                        self.cleanup_done = True
                else:
                    self.fail("OS_UNKNOWN")
        except Exception:
            self.fail("SYSCALL_UNCERTAIN")
        return self.summary()

    def summary(self):
        return {
            "evidence_kind": "OFFLINE_SUPERVISOR_CONTRACT_ONLY",
            "decision": "NO_GO",
            "state": self.machine.state,
            "first_error": self.machine.first_error,
            "fencing": self.fencing,
            "root_receipt": "OFFLINE_TERMINAL_FROZEN"
            if self.root == "OFFLINE_TERMINAL_FROZEN"
            else "UNKNOWN",
            "os_exit": "OFFLINE_EXIT_ZERO" if self.exit == "OFFLINE_EXIT_ZERO" else "UNKNOWN",
            "cleanup": "OFFLINE_CLEANUP_ACK"
            if self.cleanup == "OFFLINE_CLEANUP_ACK"
            else "UNKNOWN",
            "complete": False,
            "offline_model_complete": self.machine.state == "CLEANUP_CONFIRMED"
            and self.machine.first_error is None,
            "risks": {
                x: "NOT_PROVEN"
                for x in (
                    "FIRST_SPAWN",
                    "WATCHDOG_SYSCALLS",
                    "UNINTERRUPTIBLE_D_STATE",
                    "DURABLE_TRUST",
                    "REAL_RECLAMATION",
                )
            },
        }

    def next_arm(self):
        require(not self.next_issued, "R1_REPLAY")
        require(
            self.request["requested_arm"] == "OFF1" and self.summary()["offline_model_complete"],
            "R1_OFF_INCOMPLETE",
        )
        require(self.owner.confirm(self.binding, "NEXT_ARM") == "OFFLINE_ACK", "R1_OWNER_UNKNOWN")
        self.next_issued = True
        request = deepcopy(self.request)
        request["requested_arm"] = "ON1"
        request["flags"]["perf_diagnostics_enabled"] = True
        # Separate reservation required: this object cannot spawn another arm.
        request["owner_reservation_ref"] = "new-reservation-required"
        return request


def main(_argv=None):
    print("R1_REAL_EXECUTION_NOT_AUTHORIZED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
