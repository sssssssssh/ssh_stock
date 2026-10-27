"""Pure unsigned candidate/replay/accounting tests. No approval key is generated."""

import pytest

from scripts.a42363_contract import Fault, session_method
from scripts.a42363_proposals import InitializationCost
from scripts.a42364_costs import CandidateBudget, cost_plan
from scripts.a42364_protocol_decision import CandidateDecision, DecisionVerifier, validate_candidate
from tests.unit.test_a42364_owner import identity


def payload(**changes):
    value = dict(
        kind="BOOTSTRAP_AND_BUDGET",
        choice="FRESH_DYNAMIC",
        disposition="APPROVE",
        scope=identity().scope,
        proposal_sha256="1" * 64,
        installation_sha256="2" * 64,
        image_manifest_sha256="3" * 64,
        issued_at=100,
        expires_at=200,
        decision_nonce="52345678-1234-4234-8234-123456789012",
    )
    value.update(changes)
    return value


def test_AT13_active_limits_remain_blocked_despite_candidate():
    with pytest.raises(Fault):
        InitializationCost(12, 32, 30000).enforce_current()
    with pytest.raises(Fault, match="METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"):
        session_method()


@pytest.mark.parametrize("strategy", ["FRESH_DYNAMIC", "SINGLE_USE_PREBUILT"])
def test_AT14_AT16_every_cost_has_hash_and_prebuilt_is_not_free(strategy):
    plan = cost_plan(identity(), strategy)
    assert plan["total"]["sql"] == 12 and plan["total"]["commands"] == 32
    assert plan["baseline_declared"] == dict(sql=12, commands=26)
    assert all(len(op["template_sha256"]) == 64 for op in plan["operations"])
    assert plan["measured"] is False and plan["approved"] is False
    assert plan["cold_start_p95"] is None
    assert plan["transitive_exec_census"] == "NOT_RUN_REQUIRED_FOR_PINNED_IMAGE"


@pytest.mark.parametrize(
    "changes",
    [
        dict(disposition="REJECT"),
        dict(disposition="NEED_CHANGES"),
        dict(expires_at=99),
        dict(issued_at=200),
        dict(decision_nonce="not-uuid"),
        dict(proposal_sha256="4" * 64),
        dict(installation_sha256="4" * 64),
        dict(image_manifest_sha256="4" * 64),
        dict(kind="SAFE_VOLUME_DISPOSAL", choice="OWNER_DIRECTORY_V4"),
        dict(kind="TARGET_SESSION_GUC", choice="KEEP_CLOSED"),
    ],
)
def test_AT15_AT38_version_binding_expiry_and_decision_choices(changes):
    with pytest.raises(Fault):
        validate_candidate(
            CandidateDecision(**payload(**changes)),
            identity().scope,
            "1" * 64,
            "2" * 64,
            "3" * 64,
            150,
        )


def test_AT15_formally_shaped_record_is_not_an_approval():
    p = CandidateDecision(**payload())
    assert validate_candidate(p, identity().scope, "1" * 64, "2" * 64, "3" * 64, 150) == p
    with pytest.raises(Fault, match="INSTALLED_PACKAGE_REQUIRED"):
        DecisionVerifier().verify(
            {}, scope=identity().scope, proposal_sha256="1" * 64, image_manifest_sha256="3" * 64
        )


def test_AT14_candidate_budget_stops_at_exact_limits():
    from types import SimpleNamespace

    b = CandidateBudget(SimpleNamespace(require=lambda _: None), 1)
    for _ in range(12):
        b.reserve("SQL", 2)
    with pytest.raises(Fault, match="CANDIDATE_BOOTSTRAP_BUDGET"):
        b.reserve("SQL", 2)
    assert b.stopped and b.sql == 12


def test_AT14_expired_budget_is_sticky_even_if_clock_moves_back():
    from types import SimpleNamespace

    b = CandidateBudget(SimpleNamespace(require=lambda _: None), 1)
    with pytest.raises(Fault, match="DEADLINE"):
        b.reserve("COMMAND", 30_000_000_001)
    with pytest.raises(Fault, match="DEADLINE"):
        b.reserve("COMMAND", 2)
    assert b.stopped and b.commands == 0


def test_AT14_shared_named_budget_cannot_reset_by_restarting_owner():
    from types import SimpleNamespace

    from scripts.a42364_costs import PersistentBootstrapBudget
    from tests.unit.test_a42364_owner import MemoryJournal

    i = identity()
    j = MemoryJournal("consumer")
    a = SimpleNamespace(require=lambda _: None)
    one = PersistentBootstrapBudget(i, a, j, "OFFLINE_BOOT")
    one.start(1, 100)
    one.reserve_named("CREATE_DATABASE", 2, 101)
    two = PersistentBootstrapBudget(i, a, j, "OFFLINE_BOOT")
    with pytest.raises(Fault, match="ACK_UNKNOWN_NO_RETRY"):
        two.reserve_named("CREATE_DATABASE", 3, 102)
    with pytest.raises(Fault, match="NO_SECOND_START"):
        two.start(3, 102)
    with pytest.raises(Fault, match="DEADLINE"):
        two.reserve_named("REVOKE_SCHEMA", 31_000_000_001, 103)
    with pytest.raises(Fault, match="UNACCOUNTED"):
        two.reserve_named("HIDDEN_SQL", 4, 104)


def test_AT15_revocation_is_rechecked_at_each_use_without_minting_authority():
    from types import SimpleNamespace

    from scripts.a42364_protocol_decision import recheck_signers

    calls, revoked = [], set()

    def key(role, kid):
        calls.append((role, kid))
        if kid in revoked:
            raise Fault("A42363_INSTALL_KEY_REVOKED")
        return role.encode()

    installation = SimpleNamespace(signing_key=key)
    signers = (("OWNER", "owner"), ("SAFETY_PLATFORM", "safety"))
    recheck_signers(installation, signers)
    assert calls == list(signers)
    revoked.add("owner")
    with pytest.raises(Fault, match="KEY_REVOKED"):
        recheck_signers(installation, signers)
    assert calls[-1] == signers[0]


def test_AT15_signer_recheck_rejects_reused_keys_or_incomplete_roles():
    from types import SimpleNamespace

    from scripts.a42364_protocol_decision import recheck_signers

    install = SimpleNamespace(signing_key=lambda *a: b"OFFLINE_MODEL_PUBLIC_KEY")
    with pytest.raises(Fault, match="INDEPENDENT_SIGNERS"):
        recheck_signers(install, (("OWNER", "one"), ("SAFETY_PLATFORM", "two")))
    with pytest.raises(Fault, match="DECISION_SIGNERS"):
        recheck_signers(install, (("OWNER", "one"),))
