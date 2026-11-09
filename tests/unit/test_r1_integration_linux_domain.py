"""Platform parsing/ownership faults offline; no process is spawned here."""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from scripts import r1_integration_linux_domain as l


def stat_line(pid=100, pgid=100, sid=100, start=77, state="S"):
    # /proc/<owned pid>/stat fields 1..22, command may include spaces/parens.
    return f"{pid} (owned (child)) {state} 1 {pgid} {sid} " + "0 " * 15 + str(start)


class DomainTests(unittest.TestCase):
    def test_AC25_proc_identity_pid_reuse_and_foreign_domain(self):
        fact = l.parse_owned_stat(stat_line())
        self.assertEqual(fact, {"pid": 100, "pgid": 100, "sid": 100, "start": 77, "state": "S"})
        handle = l.OwnedIdentity(100, 100, 100, 77)
        self.assertTrue(l.matches(handle, stat_line()))
        for line in (stat_line(start=78), stat_line(pgid=101), stat_line(sid=101)):
            self.assertFalse(l.matches(handle, line))
        with self.assertRaises(l.DomainError):
            l.parse_owned_stat("not a proc record")

    def test_AC26_fixed_command_environment_and_public_deny(self):
        with patch.object(l.subprocess, "Popen") as spawn:
            with self.assertRaises(l.DomainError):
                l.LinuxProcessDomain(None).spawn("anything", "shell string")
            spawn.assert_not_called()
        self.assertEqual(l.public_main(["authorized=true"]), 2)
        self.assertEqual(set(l.minimal_environment()), {"LC_ALL", "LANG", "PYTHONHASHSEED"})

    def test_AC27_deadlines_watchdog_unknown_and_sticky_failure(self):
        subject = l.DomainDeadlines(10.0)
        self.assertEqual(subject.setup, 190.0)
        self.assertEqual(subject.start_root(100.0), 280.0)
        self.assertEqual(subject.begin_cleanup(275.0), 305.0)
        self.assertEqual(subject.begin_cleanup(290.0), 305.0)
        with self.assertRaises(l.DomainError):
            subject.start_root(101.0)
        self.assertFalse(l.PLATFORM_FENCING_PROVEN)
        self.assertEqual(
            l.classify_receipt(
                root="SUCCESS", os_exit=0, teardown=False, durable_ack=False, fencing=False
            ),
            "INCOMPLETE",
        )

    def test_spawn_intent_failure_and_pid_reuse_never_signals(self):
        import io
        import tempfile

        from tests.unit.test_r1_integration_durable_owner import owner

        for failed_create, wrong_identity in ((True, False), (False, True)):
            with self.subTest(create=failed_create), tempfile.TemporaryDirectory() as directory:
                authority = owner(directory)
                authority.reserve("binding")
                process = SimpleNamespace(pid=100, stdin=io.BytesIO())
                with ExitStack() as stack:
                    stack.enter_context(
                        patch.object(l, "verify_lab", return_value=("fixed", "module"))
                    )
                    created = stack.enter_context(patch.object(l.subprocess, "Popen"))
                    created.side_effect = OSError("private") if failed_create else None
                    created.return_value = process
                    stack.enter_context(
                        patch.object(
                            l, "capture_identity", return_value=l.OwnedIdentity(100, 100, 100, 77)
                        )
                    )
                    stack.enter_context(
                        patch.object(l.os, "pidfd_open", return_value=999, create=True)
                    )
                    stack.enter_context(patch.object(l, "matches", return_value=not wrong_identity))
                    stack.enter_context(patch.object(l, "owned_stat", return_value=stat_line()))
                    signaler = stack.enter_context(
                        patch.object(l.signal, "pidfd_send_signal", create=True)
                    )
                    subject = l.LinuxProcessDomain(SimpleNamespace(), authority)
                    with self.assertRaisesRegex(l.DomainError, "SPAWN_UNCERTAIN"):
                        subject.spawn("binding", "success")
                    self.assertEqual(authority.read_events()[1]["event"], "SPAWN_INTENT")
                    self.assertEqual(authority.read_events()[-1]["event"], "FENCED")
                    signaler.assert_not_called()

    def test_watchdog_failure_and_foreign_handle_cannot_be_success(self):
        import io
        import tempfile

        from tests.unit.test_r1_integration_durable_owner import owner

        with tempfile.TemporaryDirectory() as directory:
            authority = owner(directory)
            authority.reserve("binding")
            authority.record_intent_before_first_spawn("binding")
            identity = l.OwnedIdentity(100, 100, 100, 77)
            authority.bind_handle("binding", identity.__dict__)
            process = SimpleNamespace(stdout=io.BytesIO(), stderr=io.BytesIO(), returncode=2)
            handle = l.DomainHandle(process, identity, 999, "binding", 0.0)
            subject = l.LinuxProcessDomain(None, authority)
            with self.assertRaisesRegex(l.DomainError, "HANDLE_NOT_OWNED"):
                subject.wait(handle)
            subject.handles.append(handle)
            original_close = l.os.close
            with (
                patch.object(l, "collect_supervisor", return_value=(b"{}", b"")),
                patch.object(
                    l.os, "close", side_effect=lambda fd: None if fd == 999 else original_close(fd)
                ),
            ):
                with self.assertRaisesRegex(l.DomainError, "CLEANUP_UNCERTAIN"):
                    subject.wait(handle)
            self.assertEqual(authority.read_events()[-1]["event"], "FENCED")

    def test_signal_pidfd_rechecks_identity_and_never_uses_killpg(self):
        process = SimpleNamespace(pid=100, poll=lambda: None)
        identity = l.OwnedIdentity(100, 100, 100, 77)
        with (
            patch.object(l, "owned_stat", return_value=stat_line(start=78)),
            patch.object(l.signal, "pidfd_send_signal", create=True) as sent,
        ):
            with self.assertRaisesRegex(l.DomainError, "PID_REUSED_OR_UNCONFIRMED"):
                l.signal_owned(process, identity, 999, 15)
            sent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
