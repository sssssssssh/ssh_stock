"""One durable run/reconcile/close state machine. Failures never release a token."""

from scripts.a42363_contract import require
from scripts.a42365_contract import GATES, nonqualifying, safe_code


class RuntimeCoordinator:
    def __init__(
        self, scope, authority, journal, consumer, owner, controller, supervisor, auditor, broker
    ):
        self.scope, self.authority, self.journal = scope, authority, journal
        self.consumer, self.owner, self.controller = consumer, owner, controller
        self.supervisor, self.auditor, self.broker = supervisor, auditor, broker

    def _stage(self, name, client, method):
        require(self.journal.maybe_read(self.scope, name + "_ATTEMPTED") is None,
                "RUNTIME_ACK_UNKNOWN_NO_REPLAY")
        self.journal.append(self.scope, name + "_ATTEMPTED", dict(qualifies=False))
        result = client.call(method)
        require(type(result) is dict and result.get("qualifies") is False, "RUNTIME_RECEIPT")
        return self.journal.append(
            self.scope, name + "_COMMITTED", dict(reply=result, qualifies=False)
        )

    def run_scope(self):
        for kind in GATES[:3]:
            self.authority.require(kind)  # includes separate G1_L2 authorization
        require(
            self.journal.maybe_read(self.scope, "CONSUMPTION_FROZEN") is None, "CONSUMPTION_FROZEN"
        )
        # Capability failure is before token consumption, PG, Podman or launch.
        self.broker.verify_all_writers(self.scope)
        self.journal.append(self.scope, "RUN_ATTEMPTED", dict(qualifies=False))
        first = None
        try:
            self._stage("B_CONSUME", self.consumer, "consume")
            self._stage("C_PREPARE", self.controller, "create")
            self._stage("O_PREPARE", self.owner, "create")
            self._stage("D_RUN", self.supervisor, "run")
        except BaseException as error:
            first = error
            if self.journal.maybe_read(self.scope, "RUN_FIRST_ERROR") is None:
                try:
                    self.journal.append(self.scope, "RUN_FIRST_ERROR", dict(code=safe_code(error)))
                except Exception:
                    error.cleanup_codes = ["A42363_FIRST_ERROR_JOURNAL_UNKNOWN"]
            raise
        finally:
            try:
                self.reconcile_scope()
            except BaseException as cleanup:
                if first is None:
                    raise
                first.cleanup_codes = [*getattr(first, "cleanup_codes", []), safe_code(cleanup)]
        return self.close_scope()

    def reconcile_scope(self):
        # Recovery is single attempt too. A crash/unknown ACK requires quarantine,
        # not retrying STOP/rm because a Python object has been reconstructed.
        require(
            self.journal.maybe_read(self.scope, "RECOVERY_ATTEMPTED") is None,
            "RECOVERY_ACK_UNKNOWN_NO_RETRY",
        )
        self.journal.append(self.scope, "RECOVERY_ATTEMPTED", dict(qualifies=False))
        cleanup = []
        for name, client, method in (
            ("D_TERMINATE", self.supervisor, "terminate"),
            ("C_RECONCILE", self.controller, "reconcile"),
        ):
            prepared = "D_RUN" if name == "D_TERMINATE" else "C_PREPARE"
            attempted = self.journal.maybe_read(self.scope, prepared + "_ATTEMPTED")
            committed = self.journal.maybe_read(self.scope, prepared + "_COMMITTED")
            if attempted is None:
                cleanup.append(prepared + "_NOT_ATTEMPTED")
                continue
            if committed is None:
                # Ownership after unknown preparation is not inferred from a name.
                cleanup.append(prepared + "_ACK_UNKNOWN")
                continue
            try:
                self._stage(name, client, method)
            except BaseException as error:
                cleanup.append(safe_code(error))
        return self.journal.append(
            self.scope,
            "RECOVERY_RESULT",
            dict(
                status="INCOMPLETE_QUARANTINED" if cleanup else "PENDING_INDEPENDENT_E",
                cleanup_codes=cleanup,
                qualifies=False,
            ),
        )

    def close_scope(self):
        result = self.journal.read(self.scope, "RECOVERY_RESULT")
        require(result.record["status"] == "PENDING_INDEPENDENT_E", "SCOPE_QUARANTINED")
        self._stage("E_AUDIT", self.auditor, "absent")
        # An RPC result is not the independent two-round Reviewer protocol.
        # The staging marker remains until fresh independent receipt verification.
        return nonqualifying(self.scope, "PENDING_INDEPENDENT_REVIEW")

    def stop(self):
        if self.journal.maybe_read(self.scope, "CONSUMPTION_FROZEN") is None:
            self.journal.append(self.scope, "CONSUMPTION_FROZEN", dict(qualifies=False))
        first = None
        try:
            self._stage("B_STOP", self.consumer, "stop")
        except BaseException as error:
            first = error
            if self.journal.maybe_read(self.scope, "RUN_FIRST_ERROR") is None:
                try:
                    self.journal.append(self.scope, "RUN_FIRST_ERROR", dict(code=safe_code(error)))
                except Exception:
                    error.cleanup_codes = [*getattr(error, "cleanup_codes", []),
                                           "A42363_FIRST_ERROR_JOURNAL_UNKNOWN"]
        try:
            result = self.reconcile_scope()
        except BaseException as cleanup:
            if first is None:
                raise
            first.cleanup_codes = [*getattr(first, "cleanup_codes", []), safe_code(cleanup)]
            raise first from None
        if first is not None:
            first.cleanup_codes = [*getattr(first, "cleanup_codes", []),
                                   *result.record.get("cleanup_codes", [])]
            raise first
        return result
