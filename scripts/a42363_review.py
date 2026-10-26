"""Six independent source receipts; self-consistent hashes never establish authority."""

from scripts.a42361_contract import Approval, checked
from scripts.a42361_one_shot_store import ConsumptionReceipt
from scripts.a42362_contract import resources
from scripts.a42362_pg_owner_service import verify_raw_owner_identity
from scripts.a42363_contract import require, scope_hash, verify_receipt


class Reviewer:
    def __init__(self, receipt_set):
        self.receipt_set = receipt_set

    def review(self, scope, references):
        receipts = self.receipt_set.fetch(scope, references)
        for domain, value in receipts.items():
            verify_receipt(value, domain, scope)
        approval = checked(Approval, receipts["approval"].record)
        consumption = checked(ConsumptionReceipt, receipts["consumer"].record)
        require(
            approval.binding == scope.binding
            and approval.payload_sha256 == scope.payload_sha256
            and approval.status == "APPROVED"
            and len(set(approval.approver_sha256)) == 2
            and consumption.token_id == scope.token_id
            and consumption.nonce == scope.binding.nonce
            and consumption.payload_sha256 == scope.payload_sha256
            and consumption.approval_id == approval.approval_id
            and consumption.head_sha == scope.binding.identity.head_sha
            and consumption.run_id == scope.binding.identity.run_id
            and consumption.attempt == scope.binding.identity.attempt,
            "APPROVAL_CONSUMPTION_BINDING",
        )
        verify_raw_owner_identity(receipts["pg_owner"].record["raw"], scope)
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
            d.record.get("scope_sha256") == scope_hash(scope)
            and d.record.get("epoch") == scope.epoch
            and type(d.record.get("cgroup_inode")) is int
            and d.record["cgroup_inode"] > 0,
            "ROOT_SCOPE_FACTS",
        )
        last_ns = c.record.get("destroyed_ns")
        require(type(last_ns) is int and last_ns > 0, "DESTROY_TIME")
        for item, observation in zip(resources(scope) * 2, e.record["observations"], strict=True):
            require(
                observation.get("resource") == item.model_dump()
                and observation.get("observer_uid") != scope.controller_uid
                and type(observation.get("observer_uid")) is int
                and observation["observer_uid"] > 0
                and observation.get("result") == "ABSENT"
                and observation.get("raw") == dict(status="ABSENT", code=1, identity=None)
                and observation.get("visibility", {}).get("epoch") == scope.epoch
                and observation["visibility"].get("namespace_sha256") == scope.namespace_sha256,
                "INDEPENDENT_E_FACTS",
            )
            require(
                type(observation.get("observed_ns")) is int
                and observation["observed_ns"] > last_ns,
                "INDEPENDENT_E_ORDER",
            )
            last_ns = observation["observed_ns"]
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
