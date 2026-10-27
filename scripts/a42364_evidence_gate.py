"""Independent versioned model/receipt review. No physical or performance promotion."""

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import require, scope_hash, verify_receipt
from scripts.a42363_stores import ReceiptSet

VERSION = "a42364.cross-domain.v3"


class EvidenceGate:
    def __init__(self, sources):
        self.sources = ReceiptSet(sources)

    def review(self, scope, references):
        actual = self.sources.fetch(scope, references)
        for domain, value in actual.items():
            verify_receipt(value, domain, scope)
            require(value.record.get("protocol_version") == VERSION, "REVIEW_VERSION_REPLAY")
            require(
                value.record.get("evidence_kind") == "OFFLINE_MODEL_ONLY"
                and value.qualifies is False,
                "REVIEW_MODEL_BOUNDARY",
            )
            require(
                not value.record.get("first_error") and not value.record.get("cleanup_codes"),
                "REVIEW_FIRST_ERROR",
            )
        a, b, o, c, d, e = (
            actual[n]
            for n in (
                "approval",
                "consumer",
                "pg_owner",
                "controller",
                "supervisor",
                "absence_auditor",
            )
        )
        require(
            a.event == "MODEL_APPROVAL"
            and b.event == "MODEL_CONSUMED"
            and o.event == "MODEL_PG_PREPARED"
            and c.event == "MODEL_RECONCILED"
            and d.event == "MODEL_TERMINATED"
            and e.event == "MODEL_ABSENT",
            "REVIEW_STATE_PREFIX",
        )
        require(
            b.record.get("approval_digest") == a.digest
            and o.record.get("consumption_digest") == b.digest,
            "REVIEW_CONSUMPTION_BINDING",
        )
        require(
            d.record.get("owner_digest") == o.digest
            and c.record.get("supervisor_digest") == d.digest
            and e.record.get("destruction_digest") == c.digest,
            "REVIEW_CROSS_DOMAIN_BINDING",
        )
        require(
            c.record.get("status") == "DESTROYED_PENDING_INDEPENDENT_E"
            and set(c.record.get("resource_ids", {})) == {r.kind for r in resources(scope)},
            "REVIEW_FOUR_RESOURCES",
        )
        observations = e.record.get("observations")
        require(type(observations) is list and len(observations) == 8, "REVIEW_TWO_ROUNDS")
        for item, observation in zip(resources(scope) * 2, observations, strict=True):
            require(
                observation
                == dict(resource=item.model_dump(), result="ABSENT", source="OFFLINE_MODEL_ONLY"),
                "REVIEW_ABSENCE_FACTS",
            )
        require(
            o.record.get("target_session_settings_observed") is False,
            "MODEL_CANNOT_OBSERVE_SESSION",
        )
        return dict(
            status="OFFLINE_CROSS_DOMAIN_VERIFIED",
            qualifies=False,
            scope_sha256=scope_hash(scope),
            references={n: r.digest for n, r in actual.items()},
            real_probe_sql_executed=0,
            g1_physical="NOT_RUN_NOT_AUTHORIZED",
            effective_warmups_total=8,
            g3="NOT_AUTHORIZED",
            performance_eligible=False,
            capacity_ready=False,
            production_read_authorized=False,
            model_bundle_sha256=sha(canonical({n: r.model_dump() for n, r in actual.items()})),
        )
