"""Six independent source receipts; self-consistent hashes never establish authority."""

from scripts.a42363_contract import require, scope_hash, verify_receipt


class Reviewer:
    def __init__(self, receipt_set):
        self.receipt_set = receipt_set

    def review(self, scope, references):
        receipts = self.receipt_set.fetch(scope, references)
        for domain, value in receipts.items():
            verify_receipt(value, domain, scope)
        b, c, d, e = (
            receipts[x] for x in ("consumer", "controller", "supervisor", "absence_auditor")
        )
        require(
            b.event == "CONSUMED"
            and c.event == "RECONCILED"
            and d.event == "TERMINATED"
            and e.event == "ABSENT",
            "STATE_PREFIX",
        )
        require(
            c.record.get("status") == "DESTROYED_PENDING_INDEPENDENT_E"
            and c.record.get("scope_sha256") == scope_hash(scope),
            "DESTROY_FACTS",
        )
        require(e.record.get("destruction_digest") == c.digest, "DESTRUCTION_REFERENCE")
        require(
            set(c.record.get("resource_ids", {}))
            == {"SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"},
            "FOUR_RESOURCES_REQUIRED",
        )
        require(len(e.record.get("observations", [])) == 8, "E_TWO_ROUNDS")
        require(d.record.get("execution_scope_terminated") is True, "SCOPE_TERMINATION_UNPROVEN")
        require(
            not c.record.get("first_error") and not c.record.get("cleanup_codes"), "FIRST_ERROR"
        )
        # Even independently fetched controlled L1 records do not qualify as physical G1.
        return dict(
            status="OFFLINE_CROSS_DOMAIN_VERIFIED",
            qualifies=False,
            real_probe_sql_executed=0,
            g1_physical="NOT_RUN_NOT_AUTHORIZED",
            references={k: v.digest for k, v in receipts.items()},
            method_decision="METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION",
        )
