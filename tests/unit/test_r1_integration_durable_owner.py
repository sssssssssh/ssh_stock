"""Real local files; directory fsync injected on Windows only, never claimed durable."""

import copy
import os
import tempfile
import unittest
from pathlib import Path

from scripts import r1_integration_durable_owner as d
from scripts.r1_real_root_protocol import Refused


def owner(path, clock=None):
    options = {"clock": clock} if clock is not None else {}
    if os.name == "nt":
        options["directory_sync"] = lambda _fd: None
    return d.DurableOwner(Path(path), **options)


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_AC20_atomic_reserve_and_no_restart_reuse(self):
        first = owner(self.path)
        first.reserve("binding")
        with self.assertRaises(Refused):
            owner(self.path).reserve("other-binding")
        self.assertEqual(len(list(self.path.glob("*.json"))), 1)

    def test_AC21_intent_is_durable_before_handle(self):
        subject = owner(self.path)
        subject.reserve("binding")
        with self.assertRaises(Refused):
            subject.bind_handle("binding", {"pid": 1})
        subject.record_intent_before_first_spawn("binding")
        subject.bind_handle("binding", {"pid": 1, "start": "owned"})
        self.assertEqual(subject.confirm("binding"), "CONFIRMED")
        self.assertEqual(subject.read_events()[1]["event"], "SPAWN_INTENT")

    def test_AC22_lease_expiry_suspend_fence(self):
        now = [0.0]
        subject = owner(self.path, clock=lambda: now[0])
        subject.reserve("binding")
        now[0] = 391.0
        with self.assertRaises(Refused):
            subject.confirm("binding")
        subject.fence("binding", "LEASE_EXPIRED")
        self.assertEqual(subject.read_events()[-1]["event"], "FENCED")
        self.assertFalse(subject.external_fencing_proven)

    def test_AC23_crash_truncated_tampered_and_cleanup_ack(self):
        subject = owner(self.path)
        subject.reserve("binding")
        subject.record_intent_before_first_spawn("binding")
        handle = {"pid": 1}
        subject.bind_handle("binding", handle)
        wrong = copy.deepcopy(handle)
        wrong["pid"] = 2
        with self.assertRaises(Refused):
            subject.confirm_handle("binding", wrong)
        subject.cleanup_ack("binding", handle, exited=True, teardown=True)
        self.assertEqual(subject.read_events()[-1]["event"], "CLEANUP_ACK")
        with self.assertRaises(Refused):
            subject.confirm("binding")
        last = sorted(self.path.glob("*.json"))[-1]
        last.write_bytes(b"{")
        with self.assertRaises(Refused):
            subject.read_events()

    def test_AC24_failed_fsync_no_ack_and_no_unsafe_paths(self):
        def fail(_):
            raise OSError("private path")

        subject = d.DurableOwner(self.path, directory_sync=fail)
        with self.assertRaises(Refused):
            subject.reserve("binding")
        with self.assertRaises(Refused):
            subject.confirm("binding")
        with self.assertRaises(Refused):
            owner(self.path).reserve("../secret")


if __name__ == "__main__":
    unittest.main()
