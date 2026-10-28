"""Fixed production domain receiver; no RPC-supplied adapter, command or path.

The same receiver is exercised by isolated Unix/SQLite L1. That test installs no
service and proves neither distinct UIDs nor physical resource capabilities.
"""

import os
import select
import socket
import time

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Strict
from scripts.a42361_contract import canonical, checked, sha
from scripts.a42363_contract import require
from scripts.a42364_manager import peer_uid, read_frame, send_frame
from scripts.a42365_contract import safe_code, verify_envelope
from scripts.a42365_ipc import METHODS


class ReceiptRequest(Strict):
    event: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class EmptyRequest(Strict):
    pass


class RuntimeDomainServer:
    def __init__(self, binding, journal, endpoint):
        require(binding.domain in METHODS and journal.domain == binding.domain,
                "DOMAIN_SERVER_IDENTITY")
        self.binding, self.journal, self.endpoint = binding, journal, endpoint

    def dispatch(self, method, body):
        b = self.binding
        b.revalidate()
        require(method in self.endpoint.methods, "RUNTIME_METHOD")
        if method in ("receipt", "journal-read"):
            q = checked(ReceiptRequest, body)
            r = self.journal.maybe_read(b.scope, q.event)
            return dict(event=q.event, missing=True) if r is None else r.model_dump()
        checked(self.endpoint.contract(method), body)
        # Scope/body identity gives fixed idempotence across independent processes.
        key = "RPC_" + sha(canonical(dict(method=method, body=body)))[:40]
        require(self.journal.maybe_read(b.scope, key + "_ATTEMPTED") is None,
                "DOMAIN_ACK_UNKNOWN_NO_REPLAY")
        self.journal.append(b.scope, key + "_ATTEMPTED", dict(method=method, qualifies=False))
        try:
            result = self.endpoint.dispatch(method, body)
            require(type(result) is dict and result.get("qualifies") is False,
                    "RUNTIME_RECEIPT")
            b.revalidate()
            self.journal.append(b.scope, key + "_COMMITTED", dict(result=result, qualifies=False))
            return result
        except BaseException as error:
            if self.journal.maybe_read(b.scope, "DOMAIN_FIRST_ERROR") is None:
                self.journal.append(b.scope, "DOMAIN_FIRST_ERROR", dict(code=safe_code(error)))
            raise

    def serve_once(self, channel):
        b = self.binding
        b.revalidate()
        require(peer_uid(channel) == b.peer_uid, "RUNTIME_PEER_UID")
        channel.settimeout(0.2)
        held = os.fstat(channel.fileno())
        request = read_frame(channel, time.monotonic_ns() + 200_000_000)
        q = verify_envelope(request, b.scope, b.source, b.budget, b.domain, self.endpoint.methods)
        b.revalidate()
        require(os.fstat(channel.fileno()) == held and peer_uid(channel) == b.peer_uid,
                "RUNTIME_CHANNEL_CHANGED")
        result = self.dispatch(q.method, q.body)
        b.revalidate()
        require(os.fstat(channel.fileno()) == held and peer_uid(channel) == b.peer_uid,
                "RUNTIME_CHANNEL_CHANGED")
        send_frame(channel, result)

    def serve(self, channel):
        deadline = time.monotonic_ns() + 30_000_000_000
        for _ in range(128):
            self.binding.revalidate()
            require(time.monotonic_ns() < deadline, "DOMAIN_SERVER_DEADLINE")
            if not select.select([channel], [], [], 0.2)[0]:
                continue
            if channel.recv(1, socket.MSG_PEEK) == b"":
                return
            self.serve_once(channel)
        require(False, "DOMAIN_SERVER_REQUEST_LIMIT")


class ControllerEndpoint:
    methods = ("create", "reconcile", "receipt")

    def __init__(self, lifecycle):
        self.lifecycle = lifecycle

    def contract(self, method):
        return EmptyRequest

    def dispatch(self, method, body):
        from scripts.a42362_contract import resources

        life = self.lifecycle
        scope, journal = life.scope, life.journal
        if method == "create":
            for item in resources(scope):
                life.perform(item, "CREATE")
            life.perform(resources(scope)[3], "START")
            return journal.append(scope, "PREPARED", dict(qualifies=False)).model_dump()
        require(method == "reconcile", "RUNTIME_METHOD")
        journal.append(scope, "DESTROY_REQUESTED", dict(qualifies=False))
        result = life.recover()
        result.update(destroyed_ns=time.monotonic_ns(), original_digests={
            item.kind: journal.read(scope, item.kind + "_ORIGINAL").digest
            for item in resources(scope)
            if journal.maybe_read(scope, item.kind + "_ORIGINAL") is not None
        })
        return journal.append(scope, "RECONCILED", result).model_dump()


class ConsumerEndpoint:
    methods = ("consume", "stop", "receipt", "journal-read", "budget")

    def __init__(self, scope, authority, budget, journal):
        self.scope, self.authority, self.budget, self.journal = scope, authority, budget, journal

    def contract(self, method):
        from scripts.a42366_mediation import BudgetRequest

        return BudgetRequest if method == "budget" else EmptyRequest

    def dispatch(self, method, body):
        from scripts.a42366_mediation import reserve_request

        if method == "budget":
            return reserve_request(self.budget, body).model_dump()
        if method == "stop":
            return self.journal.append(self.scope, "BUDGET_STOPPED",
                                       dict(qualifies=False)).model_dump()
        require(method == "consume", "RUNTIME_METHOD")
        claim = self.authority.claim()
        self.budget.start()
        return self.journal.append(self.scope, "CONSUMED", dict(
            claim_digest=claim.digest, qualifies=False,
        )).model_dump()


class CapabilityBlockedEndpoint:
    """Fixed status/refusal endpoint, not a pretend working Owner/D/E adapter."""

    def __init__(self, methods, blocker):
        self.methods, self.blocker = tuple(methods), blocker

    def contract(self, method):
        return EmptyRequest

    def dispatch(self, method, body):
        require(False, self.blocker)


class AbsenceEndpoint:
    """Same original store observer; no empty output or C ACK is called absence.

    The installer must supply the independently delegated collector. The v5
    default factory intentionally refuses without that kernel RO handoff.
    """
    methods = ("absent", "receipt")

    def __init__(self, scope, journal, observer, consumer, controller):
        require(journal.domain == "absence_auditor", "AUDIT_WRITER_DOMAIN")
        self.scope, self.journal, self.observer = scope, journal, observer
        self.consumer, self.controller = consumer, controller

    def contract(self, method):
        return EmptyRequest

    def dispatch(self, method, body):
        from scripts.a42362_contract import resources
        from scripts.a42363_contract import scope_hash, verify_receipt

        require(method == "absent", "RUNTIME_METHOD")
        s = self.scope
        b = self.consumer.read(s, "CONSUMED")
        c = self.controller.read(s, "RECONCILED")
        requested = self.controller.read(s, "DESTROY_REQUESTED")
        verify_receipt(b, "consumer", s, "CONSUMED")
        verify_receipt(c, "controller", s, "RECONCILED")
        verify_receipt(requested, "controller", s, "DESTROY_REQUESTED")
        require(c.record.get("status") == "DESTROYED_PENDING_INDEPENDENT_E"
                and not c.record.get("first_error") and not c.record.get("cleanup_codes")
                and requested.sequence < c.sequence, "AUDIT_DESTRUCTION_CHANGED")
        originals = {item.kind: self.controller.read(s, item.kind + "_ORIGINAL")
                     for item in resources(s)}
        require(c.record.get("original_digests") == {k: v.digest for k, v in originals.items()},
                "AUDIT_ORIGINAL_SET")
        observations = []
        last = c.record.get("destroyed_ns")
        require(type(last) is int and last > 0, "AUDIT_DESTRUCTION_CHANGED")
        for round_no in (1, 2):
            self._fresh(b, c, requested)
            for item in resources(s):
                raw = self.observer.observe(item)
                require(type(raw) is dict and raw.get("resource") == item.model_dump()
                        and raw.get("result") == "ABSENT"
                        and raw.get("raw") == dict(status="ABSENT", code=1, identity=None)
                        and type(raw["raw"]["code"]) is int
                        and type(raw.get("observed_ns")) is int and raw["observed_ns"] > last,
                        "ABSENCE_UNKNOWN")
                last = raw["observed_ns"]
                observations.append(dict(raw, round=round_no,
                                         original_digest=originals[item.kind].digest))
            self._fresh(b, c, requested)
        return self.journal.append(s, "ABSENT", dict(
            scope_sha256=scope_hash(s), epoch=s.epoch, observations=observations,
            consumption_digest=b.digest, requested_digest=requested.digest,
            destruction_digest=c.digest, physical_proven=False, qualifies=False,
        )).model_dump()

    def _fresh(self, b, c, requested):
        s = self.scope
        require(self.consumer.read(s, "CONSUMED") == b
                and self.controller.read(s, "RECONCILED") == c
                and self.controller.read(s, "DESTROY_REQUESTED") == requested,
                "AUDIT_DESTRUCTION_CHANGED")
