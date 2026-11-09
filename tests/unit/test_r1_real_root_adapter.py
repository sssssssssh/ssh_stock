"""Fake facade records real orchestration calls, with no business imports."""

import copy
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

from test_r1_real_root_protocol import request, sources

from scripts import r1_real_root_adapter as a
from scripts.r1_real_root_protocol import Refused


class FakeOwner:
    def __init__(self, fail_phase=None):
        self.fail_phase, self.calls, self.used = fail_phase, [], set()

    def reserve(self, binding):
        self.calls.append(("reserve", binding))
        if self.used or self.fail_phase == "reserve":
            return "UNKNOWN_ACK"
        self.used.add(binding)
        return "OFFLINE_RESERVED"

    def confirm(self, binding, phase):
        self.calls.append((phase, binding))
        return "UNKNOWN_ACK" if phase == self.fail_phase else "OFFLINE_ACK"

    def record_intent(self, binding):
        self.calls.append(("intent", binding))
        return "UNKNOWN_ACK" if self.fail_phase == "intent" else "OFFLINE_ACK"

    def confirm_handle(self, binding, handle, fact):
        self.calls.append(("handle", binding))
        expected = {
            "binding": binding,
            "domain_ref": "process-domain",
            "host_ref": "host-lease",
            "pg_ref": "pg-resource",
            "pid": 101,
            "pgid": 101,
            "sid": 101,
            "creation": "fake-owner-created-once",
        }
        return "OFFLINE_HANDLE_ACK" if fact == expected and binding in self.used else "UNKNOWN_ACK"


class FakeFacade(a.OfflineFacade):
    def __init__(self, fault=None, status="SUCCESS"):
        self.fault, self.status, self.calls = fault, status, []
        self.job = SimpleNamespace(
            id=UUID(int=1),
            status="QUEUED",
            worker_id=None,
            execution_token=None,
            _queue_deduplicated=False,
            job_type="recalculate",
            parent_job_id=None,
            depends_on_job_id=None,
            job_metadata={
                "start": "2026-02-23",
                "end": "2026-02-24",
                "evaluate_signals": False,
                "mode": "manual",
                "dirty_range_ids": [],
            },
        )
        self.info = {}

    @contextmanager
    def freeze(self, flags, hashes):
        self.calls.append(("freeze", copy.deepcopy(flags), copy.deepcopy(hashes)))
        yield

    @contextmanager
    def session(self):
        self.calls.append(("session",))
        yield self

    def create_recalculation_job(self, db, *, start, end, evaluate_signals, mode):
        self.calls.append(("create", db, start, end, evaluate_signals, mode))
        if self.fault == "deduplicated":
            self.job._queue_deduplicated = True
        return self.job

    def claim_next_job(self, db, worker_id):
        self.calls.append(("claim", db, worker_id))
        self.job.status = "RUNNING"
        self.job.worker_id = worker_id
        self.job.execution_token = UUID(int=2)
        self.info["data_claim"] = (self.job.id, worker_id, self.job.execution_token)
        return UUID(int=3) if self.fault == "wrong_root" else self.job.id

    def refresh(self, job):
        self.calls.append(("refresh",))
        if self.fault == "worker":
            job.worker_id = "foreign-worker"
        if self.fault == "token":
            job.execution_token = None
        if self.fault == "changed_token":
            job.execution_token = UUID(int=4)

    def execute_claimed_job(self, db, job_id, *, expected_worker, expected_token):
        self.calls.append(("execute", db, job_id, expected_worker, expected_token))
        if self.fault == "exception":
            raise RuntimeError("PRIVATE_DSN_AND_SQL")

    def expire_all(self):
        self.calls.append(("expire",))

    def observe(self, db, root_id):
        self.calls.append(("observe", root_id))
        return {
            "root_id": root_id,
            "worker_id": self.job.worker_id,
            "execution_token": self.job.execution_token,
            "status": self.status,
            "publication": "PUBLISHED" if self.status == "SUCCESS" else "ABORTED",
            "commit_ack": "UNKNOWN" if self.fault == "ack" else "KNOWN",
            "heartbeat_stopped": self.fault != "heartbeat",
            "publication_confirmed": self.fault != "self_reported",
        }


def context(arm="OFF1", owner=None):
    return a.OfflineContext(request(arm), sources(), owner or FakeOwner())


class AdapterTests(unittest.TestCase):
    def test_AC04_no_owner_no_session_or_business_binding(self):
        facade = FakeFacade()
        ctx = context()
        ctx.owner = None
        with self.assertRaises(Refused):
            a.execute_one_r1_root(ctx, facade, lambda _: None)
        self.assertEqual(facade.calls, [])
        with self.assertRaisesRegex(Refused, "R1_REAL_EXECUTION_NOT_AUTHORIZED"):
            a.BusinessFacade().claim_next_job(None, "private")

    def test_AC07_real_orchestration_create_claim_execute_exactly_once(self):
        facade, ctx, events = FakeFacade(), context(), []
        result = a.execute_one_r1_root(ctx, facade, events.append)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["evidence_kind"], "OFFLINE_SIMULATED")
        self.assertEqual(events, ["CREATE", "CLAIM", "EXECUTE", "OBSERVED"])
        for name in ("create", "claim", "execute"):
            self.assertEqual(sum(c[0] == name for c in facade.calls), 1)
        create = next(c for c in facade.calls if c[0] == "create")
        self.assertEqual(tuple(str(x) for x in create[2:4]), ("2026-02-23", "2026-02-24"))
        self.assertEqual(create[4:], (False, "manual"))
        execute = next(c for c in facade.calls if c[0] == "execute")
        self.assertEqual(execute[2:], (UUID(int=1), "perf03-r1-synthetic", UUID(int=2)))

    def test_AC08_wrong_claim_token_worker_and_repeated_execute_refused(self):
        for fault in ("wrong_root", "worker", "token", "changed_token", "deduplicated"):
            with self.subTest(fault=fault):
                facade, ctx = FakeFacade(fault), context()
                result = a.execute_one_r1_root(ctx, facade, lambda _: None)
                self.assertIsNotNone(result["first_error"])
                self.assertEqual(result["root_executions"], 0)
                with self.assertRaisesRegex(Refused, "R1_REPLAY"):
                    a.execute_one_r1_root(ctx, facade, lambda _: None)
                self.assertEqual(sum(c[0] == "create" for c in facade.calls), 1)
        shared = FakeOwner()
        a.execute_one_r1_root(context(owner=shared), FakeFacade(), lambda _: None)
        facade = FakeFacade()
        with self.assertRaises(Refused):
            a.execute_one_r1_root(context(owner=shared), facade, lambda _: None)
        self.assertEqual(facade.calls, [])
        for changed in (context("ON1", owner=shared), context(owner=shared)):
            if changed.request["requested_arm"] == "OFF1":
                changed.request["pair_id"] = "other-pair"
            facade = FakeFacade()
            with self.assertRaisesRegex(Refused, "R1_OWNER_UNKNOWN"):
                a.execute_one_r1_root(changed, facade, lambda _: None)
            self.assertEqual(facade.calls, [])

    def test_AC09_cancel_error_ack_and_residual_heartbeat_preserved(self):
        for status in ("FAILED", "CANCELLED"):
            result = a.execute_one_r1_root(context(), FakeFacade(status=status), lambda _: None)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["first_error"], "R1_" + status)
        for fault in ("exception", "ack", "heartbeat", "self_reported"):
            facade = FakeFacade(fault)
            result = a.execute_one_r1_root(context(), facade, lambda _: None)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIsNotNone(result["first_error"])
            self.assertEqual(sum(c[0] == "execute" for c in facade.calls), 1)

    def test_AC10_diagnostics_only_switch_changes(self):
        for arm in ("OFF1", "ON1"):
            facade = FakeFacade()
            a.execute_one_r1_root(context(arm), facade, lambda _: None)
            flags = facade.calls[0][1]
            self.assertIs(flags.pop("perf_diagnostics_enabled"), arm == "ON1")
            self.assertTrue(all(v is False for v in flags.values()))

    def test_AC11_adapter_never_commits_or_calls_worker_provider_scheduler(self):
        facade = FakeFacade()
        result = a.execute_one_r1_root(context(), facade, lambda _: None)
        self.assertEqual(result["root_executions"], 1)
        self.assertFalse(
            {"commit", "run_worker", "provider", "scheduler", "retry"}
            & {c[0] for c in facade.calls}
        )

    def test_AC30_failure_no_retry_or_private_exception_echo(self):
        facade = FakeFacade("exception")
        result = a.execute_one_r1_root(context(), facade, lambda _: None)
        self.assertEqual(result["first_error"], "R1_BUSINESS_EXCEPTION")
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(sum(c[0] == "create" for c in facade.calls), 1)
