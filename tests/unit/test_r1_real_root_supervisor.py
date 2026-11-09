"""Fault injection only: no subprocess, PID, signals or filesystem receipts."""

import unittest

from test_r1_real_root_adapter import FakeOwner
from test_r1_real_root_protocol import request, sources

from scripts import r1_real_root_supervisor as s
from scripts.r1_real_root_protocol import Refused


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


class Process:
    evidence_kind = "OFFLINE_FAKE_PROCESS"

    def __init__(self, owner):
        self.owner, self.calls = owner, []
        self.events = ["ROOT_STARTED", "DONE"]
        self.valid = True
        self.exit = "OFFLINE_EXIT_ZERO"
        self.spawn_fault = None
        self.facts = {}

    def spawn(self, template, binding):
        self.calls.append(("spawn", template, binding))
        assert any(c[0] == "intent" for c in self.owner.calls)
        if self.spawn_fault == "raise":
            raise RuntimeError("PRIVATE")
        return None if self.spawn_fault == "none" else "opaque-owned-handle"

    def owned(self, handle, binding):
        self.calls.append(("owned", handle, binding))
        return self.valid and handle == "opaque-owned-handle"

    def identity(self, handle):
        binding = next(c[2] for c in self.calls if c[0] == "spawn")
        return {
            "binding": binding,
            "domain_ref": "process-domain",
            "host_ref": "host-lease",
            "pg_ref": "pg-resource",
            "pid": 101,
            "pgid": 101,
            "sid": 101,
            "creation": "fake-owner-created-once",
            **self.facts,
        }

    def poll(self, handle):
        return self.events.pop(0) if self.events else "HEARTBEAT"

    def signal(self, handle, action, binding):
        assert self.valid and handle == "opaque-owned-handle"
        self.calls.append(("signal", action, binding))

    def exit_receipt(self, handle, binding):
        return self.exit


class Receipts:
    def __init__(self):
        self.root_value = "OFFLINE_TERMINAL_FROZEN"
        self.cleanup_value = "OFFLINE_CLEANUP_ACK"

    def root(self, binding):
        return self.root_value

    def cleanup(self, binding):
        return self.cleanup_value


def supervisor(owner=None):
    owner = owner or FakeOwner()
    proc, clock, receipts = Process(owner), Clock(), Receipts()
    model = s.Supervisor(request(), sources(), owner, proc, clock, receipts)
    return model, proc, clock, receipts


class SupervisorTests(unittest.TestCase):
    def test_AC12_absolute_budgets_and_no_heartbeat_extension(self):
        model, proc, clock, _ = supervisor()
        model.start_once()
        clock.now = 170
        model.tick()
        self.assertEqual(model.root_deadline, 350)
        proc.events = ["HEARTBEAT"]
        clock.now = 349
        model.tick()
        self.assertEqual(model.root_deadline, 350)
        clock.now = 350
        model.tick()
        self.assertEqual(model.machine.first_error, "ROOT_TIMEOUT")
        self.assertEqual(model.cleanup_deadline, 380)
        self.assertEqual(model.outer_deadline, 390)
        clock.now = 381
        model.tick()
        self.assertEqual(model.machine.first_error, "ROOT_TIMEOUT")
        self.assertFalse(model.summary()["offline_model_complete"])

    def test_AC13_intent_before_spawn_and_unknown_handle(self):
        for fault in ("raise", "none"):
            model, proc, _, _ = supervisor()
            proc.spawn_fault = fault
            model.start_once()
            self.assertEqual(model.machine.first_error, "SPAWN_UNCERTAIN")
            self.assertEqual(model.summary()["fencing"], "FENCING_PENDING")
            self.assertTrue(any(c[0] == "intent" for c in model.owner.calls))
            with self.assertRaises(Refused):
                model.start_once()
        model, proc, _, _ = supervisor(FakeOwner(fail_phase="BEFORE_SPAWN"))
        model.start_once()
        self.assertEqual(proc.calls, [])

    def test_AC14_unowned_reused_pid_pgid_sid_no_signal(self):
        for role in ("pid", "pgid", "sid", "foreign-child"):
            with self.subTest(role=role):
                model, proc, clock, _ = supervisor()
                model.start_once()
                if role == "foreign-child":
                    proc.valid = False
                else:
                    proc.facts[role] = 999
                clock.now = 181
                model.tick()
                self.assertEqual(model.machine.first_error, "DOMAIN_MISMATCH")
                self.assertFalse(any(c[0] == "signal" for c in proc.calls))

    def test_AC15_term_kill_late_done_and_missing_os_exit(self):
        model, proc, clock, _ = supervisor()
        model.start_once()
        model.tick()
        proc.exit = None
        clock.now = 180
        model.tick()
        self.assertEqual(model.machine.first_error, "ROOT_TIMEOUT")
        clock.now = 185
        model.tick()
        self.assertEqual([c[1] for c in proc.calls if c[0] == "signal"], ["TERM", "KILL"])
        proc.events = ["DONE"]
        proc.exit = "OFFLINE_EXIT_ZERO"
        clock.now = 186
        model.tick()
        self.assertEqual(model.machine.first_error, "ROOT_TIMEOUT")
        self.assertFalse(model.summary()["offline_model_complete"])
        model, proc, _, _ = supervisor()
        model.start_once()
        model.tick()
        proc.exit = None
        result = model.tick()
        self.assertFalse(result["complete"])
        self.assertFalse(result["offline_model_complete"])

    def test_AC16_syscall_lease_and_cleanup_uncertainty_fail_closed(self):
        for fault in ("syscall", "lease", "cleanup", "ack"):
            with self.subTest(fault=fault):
                model, proc, _, receipts = supervisor()
                model.start_once()
                if fault == "syscall":
                    proc.events = ["SYSCALL_BLOCKED"]
                if fault == "lease":
                    model.owner.fail_phase = "LEASE"
                if fault == "cleanup":
                    receipts.cleanup_value = "UNKNOWN_ACK"
                if fault == "ack":
                    model.owner.fail_phase = "CLEANUP"
                model.tick()
                result = model.tick()
                self.assertEqual(result["state"], "CLEANUP_UNCERTAIN")
                self.assertEqual(result["fencing"], "FENCING_PENDING")
                self.assertFalse(result["complete"])
                with self.assertRaises(Refused):
                    model.next_arm()

    def test_AC17_off_incomplete_never_generates_on_and_success_only_simulated(self):
        model, proc, _, receipts = supervisor()
        model.start_once()
        model.tick()
        receipts.root_value = "ACTOR_SELF_REPORTED_SUCCESS"
        model.tick()
        with self.assertRaises(Refused):
            model.next_arm()
        model, proc, _, _ = supervisor()
        model.start_once()
        model.tick()
        result = model.tick()
        self.assertTrue(result["offline_model_complete"])
        self.assertFalse(result["complete"])
        on = model.next_arm()
        self.assertEqual(on["requested_arm"], "ON1")
        self.assertEqual(on["owner_reservation_ref"], "new-reservation-required")
        self.assertTrue(all(v == "NOT_PROVEN" for v in result["risks"].values()))
        self.assertEqual(sum(c[0] == "spawn" for c in proc.calls), 1)

    def test_late_returning_poll_and_receipt_never_extend_deadline(self):
        model, proc, clock, receipts = supervisor()
        model.start_once()
        model.tick()

        def late_poll(handle):
            clock.now = 181
            return "DONE"

        proc.poll = late_poll
        model.tick()
        self.assertEqual(model.machine.first_error, "ROOT_TIMEOUT")
        self.assertFalse(model.summary()["offline_model_complete"])
        model, proc, clock, receipts = supervisor()
        model.start_once()
        model.tick()

        def late_cleanup(binding):
            clock.now = 31
            return "OFFLINE_CLEANUP_ACK"

        receipts.cleanup = late_cleanup
        model.tick()
        self.assertEqual(model.machine.first_error, "CLEANUP_TIMEOUT")
        self.assertFalse(model.summary()["offline_model_complete"])
