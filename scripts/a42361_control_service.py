"""Private installed-service composition; no shell/CI/live command-line entrance.

Domain service deployment, credentials and independent auditor are NOT supplied by Git.
No file/env Boolean or in-process fake object confers service-manager authority.
"""

import os
import time

from scripts.a42361_contract import Binding, Fault, canonical, checked, require, sha
from scripts.a42361_deployment import LocalService, installed
from scripts.a42361_one_shot_store import ConsumptionReceipt, expected_receipt
from scripts.a42361_trust_verifier import TrustVerifier
from scripts.a42361_trusted_evidence import FailureLedger


class ControlService:
    def __init__(self, deployment=None):
        self.deployment = deployment

    def run_approved(self, envelope, expected):
        config = installed(self.deployment)  # First branch, before sockets/processes.
        require(os.getuid() == config.supervisor.peer_uid, "A42361_SERVICE_PRINCIPAL_MISMATCH")
        expected = checked(Binding, expected)
        from scripts.a42361_source_guard import independent_binding

        require(
            expected
            == independent_binding(
                expected.identity.run_id,
                expected.identity.attempt,
                expected.fixture_uuid,
                expected.nonce,
                expected.marker_sha256,
            ),
            "A42361_SOURCE_DRIFT",
        )
        grant = TrustVerifier(self.deployment).verify_signature(envelope, expected)
        common = dict(payload_sha256=grant.payload_sha256, binding=expected.model_dump())
        consumer = LocalService(self.deployment, "consumer")
        # B verifies original signature/approval itself, commits, and exposes a fresh
        # committed receipt. Forwarding a Python VerifiedGrant is NOT an RPC grant.
        response = consumer.call("consume", dict(envelope_hex=envelope.hex(), **common), 1000)
        require(
            type(response) is dict
            and set(response) == {"receipt_sha256", "committed"}
            and response["committed"] is True,
            "A42361_COMMIT_UNKNOWN_NO_RETRY",
        )
        receipt = consumer.call(
            "receipt", dict(token_id=grant.payload.token_id, payload_sha256=grant.payload_sha256)
        )
        receipt = checked(ConsumptionReceipt, receipt).model_dump()
        require(
            sha(canonical(receipt)) == response["receipt_sha256"]
            and receipt == expected_receipt(grant, config),
            "A42361_COMMIT_UNKNOWN_NO_RETRY",
        )
        require(int(time.time()) < grant.payload.expires_at, "A42361_GRANT_EXPIRED")
        ledger, creation, worker, cleanup = FailureLedger(), None, None, None
        controller = LocalService(self.deployment, "controller")
        try:
            creation = controller.call(
                "create", dict(consumption_sha256=response["receipt_sha256"], **common), 2000
            )
            require(
                type(creation) is dict
                and set(creation) == {"creation_sha256", "payload_sha256"}
                and creation["payload_sha256"] == grant.payload_sha256,
                "A42361_TRUSTED_CREATION_REQUIRED",
            )
            # Supervisor service must itself own a physically supervised worker. This
            # RPC contract alone does not certify kill, fsync or partial-create cleanup.
            worker = LocalService(self.deployment, "supervisor").call(
                "run", dict(creation_sha256=creation["creation_sha256"], **common), 2000
            )
            require(
                type(worker) is dict
                and worker.get("evidence_kind") == "SUPERVISOR_RECEIPT"
                and worker.get("payload_sha256") == grant.payload_sha256,
                "A42361_SUPERVISOR_RECEIPT_UNTRUSTED",
            )
        except BaseException as error:
            ledger.fail(error.code if isinstance(error, Fault) else "A42361_CONTROL_INCOMPLETE")
        finally:
            if creation is not None:
                try:
                    cleanup = controller.call(
                        "destroy", dict(creation_sha256=creation["creation_sha256"], **common), 2000
                    )
                    require(
                        type(cleanup) is dict
                        and set(cleanup) == {"requested", "destroyed", "absent"},
                        "A42361_CLEANUP_NOT_VERIFIED",
                    )
                    for key, event in (
                        ("requested", "DESTROY_REQUESTED"),
                        ("destroyed", "DESTROYED"),
                        ("absent", "ABSENT"),
                    ):
                        require(cleanup[key].get("event") == event, "A42361_CLEANUP_NOT_VERIFIED")
                    independent = LocalService(self.deployment, "absence_auditor").call(
                        "absent", dict(creation_sha256=creation["creation_sha256"], **common)
                    )
                    require(
                        independent == cleanup["absent"] and independent.get("absent") is True,
                        "A42361_CLEANUP_NOT_VERIFIED",
                    )
                except BaseException:
                    ledger.fail("A42361_CLEANUP_NOT_VERIFIED", cleanup=True)
            elif ledger.first_error is not None:
                # A timed-out create may have committed resources. Never label absent.
                ledger.fail("A42361_PARTIAL_CREATION_REQUIRES_OWNER_RECONCILIATION", cleanup=True)
        return dict(
            status="INCOMPLETE" if ledger.first_error else "PENDING_INDEPENDENT_G1_REVIEW",
            first_error=ledger.first_error,
            cleanup_codes=ledger.cleanup_codes,
            last_incomplete=ledger.last_incomplete,
            worker=worker,
            cleanup=cleanup,
            qualifies=False,
        )


def main(argv=None):
    # Even --execute/--approve, env tokens and workflow_dispatch are NOT deployment.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
