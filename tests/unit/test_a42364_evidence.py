"""Six independent offline stores; self-consistent models never qualify physical G1."""

import pytest

from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault
from scripts.a42364_evidence_gate import VERSION, EvidenceGate
from tests.unit.test_a42364_owner import MemoryJournal, identity


def chain():
    s = identity().scope
    sources = {
        n: MemoryJournal(n)
        for n in ("approval", "consumer", "pg_owner", "supervisor", "controller", "absence_auditor")
    }
    refs = {}

    def append(domain, event, **record):
        value = dict(protocol_version=VERSION, evidence_kind="OFFLINE_MODEL_ONLY", **record)
        refs[domain] = sources[domain].append(s, event, value)
        return refs[domain]

    a = append("approval", "MODEL_APPROVAL")
    b = append("consumer", "MODEL_CONSUMED", approval_digest=a.digest)
    o = append(
        "pg_owner",
        "MODEL_PG_PREPARED",
        consumption_digest=b.digest,
        target_session_settings_observed=False,
    )
    d = append("supervisor", "MODEL_TERMINATED", owner_digest=o.digest)
    c = append(
        "controller",
        "MODEL_RECONCILED",
        supervisor_digest=d.digest,
        status="DESTROYED_PENDING_INDEPENDENT_E",
        resource_ids={r.kind: "OFFLINE_ORIGINAL_" + r.kind for r in resources(s)},
    )
    append(
        "absence_auditor",
        "MODEL_ABSENT",
        destruction_digest=c.digest,
        observations=[
            dict(resource=r.model_dump(), result="ABSENT", source="OFFLINE_MODEL_ONLY")
            for r in resources(s) * 2
        ],
    )
    return s, sources, refs


def test_AT36_AT38_six_model_domains_are_nonqualifying_even_when_coherent():
    s, sources, refs = chain()
    result = EvidenceGate(sources).review(s, refs)
    assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED" and result["qualifies"] is False
    assert result["real_probe_sql_executed"] == 0 and result["performance_eligible"] is False


@pytest.mark.parametrize(
    "domain", ["approval", "consumer", "pg_owner", "supervisor", "controller", "absence_auditor"]
)
def test_AT37_missing_any_independent_receipt_rejected(domain):
    s, sources, refs = chain()
    del refs[domain]
    with pytest.raises(Fault):
        EvidenceGate(sources).review(s, refs)


@pytest.mark.parametrize(
    "mutation", ["version", "scope", "first_error", "cleanup", "guc", "recreate", "store"]
)
def test_AT30_AT38_rehashed_or_copied_tampering_still_rejected(mutation):
    from scripts.a42363_contract import receipt

    s, sources, refs = chain()
    domain = "pg_owner" if mutation == "guc" else "absence_auditor"
    old = refs[domain]
    record = dict(old.record)
    if mutation == "version":
        record["protocol_version"] = "LEGACY"
    elif mutation == "first_error":
        record["first_error"] = "A42363_CREATE_ACK_UNKNOWN"
    elif mutation == "cleanup":
        record["cleanup_codes"] = ["A42363_TERMINATION_NOT_PROVEN"]
    elif mutation == "guc":
        record["target_session_settings_observed"] = True
    elif mutation == "recreate":
        record["observations"] = record["observations"][:4]
    elif mutation == "store":
        record["observations"][0] = dict(record["observations"][0], source="FOREIGN_STORE")
    else:
        record["evidence_kind"] = "ACTUAL_G1"
    value = receipt(domain, s, old.event, old.sequence, record)
    refs[domain] = value
    sources[domain].values[old.event] = value
    with pytest.raises(Fault):
        EvidenceGate(sources).review(s, refs)


def test_AT37_reader_changed_after_reference_is_not_self_attested():
    s, sources, refs = chain()
    old = refs["approval"]
    sources["approval"].values[old.event] = old.model_copy(update={"digest": "f" * 64})
    with pytest.raises(Fault, match="INDEPENDENT_RECEIPT_MISMATCH"):
        EvidenceGate(sources).review(s, refs)


@pytest.mark.parametrize("code", [125, 126, 127, -9, True])
def test_AT30_AT32_collector_permissions_never_become_absent(code):
    from types import SimpleNamespace as NS

    from scripts.a42364_collector import FixedReadOnlyCollector

    scope = identity().scope
    delegation = NS(scope=scope, verify=lambda: {"readonly": True})
    collector = FixedReadOnlyCollector(delegation, NS(read=lambda _: (code, b"")), -1)
    with pytest.raises(Fault, match="ABSENCE_UNKNOWN"):
        collector.read_exact(resources(scope)[1])


def test_AT31_collector_rechecks_delegation_after_observation():
    from types import SimpleNamespace as NS

    from scripts.a42364_collector import FixedReadOnlyCollector

    scope = identity().scope
    values = iter([{"epoch": "original"}, {"epoch": "replacement"}])
    delegation = NS(scope=scope, verify=lambda: next(values))
    collector = FixedReadOnlyCollector(delegation, NS(read=lambda _: (1, b"")), -1)
    with pytest.raises(Fault, match="DELEGATION_CHANGED"):
        collector.read_exact(resources(scope)[1])
