"""A4236 fixed refusal contracts: run RED first, keep these assertions for GREEN."""

import pytest

from scripts.a4236_g1_harness_contract import Fault
from scripts.a4236_mock import refusal_case


@pytest.mark.parametrize(
    "threat",
    [
        "forged_grant",
        "replay",
        "pid_drift",
        "cache_key",
        "false_join",
        "false_cleanup",
        "sql_budget",
        "history_write",
    ],
)
def test_a4236_RED_AT07_AT08_AT21_AT25_AT30_AT15_AT17_AT03(threat):
    # Returning NOT_AUTHORIZED is not sufficient for contradictory input: fixed Fault.
    with pytest.raises(Fault, match="^A4236_"):
        refusal_case(threat)


def test_AT09_AT14_mock_chain_positive_never_becomes_physical():
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import FakeHarness, validate_cleanup, validate_creation
    from scripts.a4236_grant_verifier import FakeAtomicConsumer, FakeIssuer

    g, consumer = m.grant(), FakeAtomicConsumer()
    verification = FakeIssuer(g).verify(g, 2)
    assert verification.signature_verified is False
    consumed = consumer.consume(verification)
    assert consumed.persistent_verified is False
    harness = FakeHarness(m.fixture())
    receipts = harness.create(consumed)
    assert validate_creation(m.fixture(), *receipts)["physical_status"] == "PHYSICAL_NOT_PROVEN"
    assert validate_cleanup(m.fixture(), harness.destroy(m.fixture()))["mock_destroyed"] is True
    assert not harness.created
    with pytest.raises(Fault, match="FIXTURE_REUSE"):
        harness.create(consumed)  # Destroying a model resource never reopens its grant.


@pytest.mark.parametrize(
    "field,bad",
    [
        ("host", "localhost"),
        ("host", "0.0.0.0"),
        ("host", "127.0.0.2"),
        ("host", "db.example"),
        ("host", "postgresql://SECRET_A4236"),
        ("database", "postgres"),
        ("database", "existing_business"),
        ("fresh", False),
        ("shared_existing", True),
        ("public_ports", True),
        ("production_route", True),
        ("privileged", True),
        ("host_pid", True),
        ("host_proc_mount", True),
        ("root", True),
        ("sensitive_volumes", True),
        ("pg_major", 18),
        ("cpu_millicores", 2000),
        ("pids_limit", 64),
        ("rss_mib", 1024),
        ("limits_approved", True),
        ("socket_owner_sha256", "e" * 64),
    ],
)
def test_AT11_AT12_fixture_access_and_limits_reject(field, bad):
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import validate_fixture

    f = m.fixture()
    with pytest.raises(Fault) as error:
        validate_fixture(f.model_copy(update={field: bad}), f)
    assert "SECRET_A4236" not in str(error.value)


@pytest.mark.parametrize(
    "field",
    [
        "superuser",
        "createdb",
        "createrole",
        "bypassrls",
        "replication",
        "maintain",
        "ddl",
        "dml",
        "business_read",
        "arbitrary_extension",
        "pg_read_all_stats",
    ],
)
def test_AT13_no_role_escalation(field):
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import validate_fixture

    f = m.fixture()
    with pytest.raises(Fault):
        validate_fixture(
            f.model_copy(update={"privileges": f.privileges.model_copy(update={field: True})}), f
        )


@pytest.mark.parametrize(
    "change",
    [
        "same-owner",
        "inherited-admin",
        "socket-unknown",
        "system",
        "container",
        "namespace",
        "marker",
        "nonce",
    ],
)
def test_AT12_AT13_ownership_and_physical_drift_never_create(change):
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import validate_fixture

    f = m.fixture()
    value = f
    if change == "same-owner":
        value = f.model_copy(update={"probe_role_sha256": f.owner_sha256})
    elif change == "inherited-admin":
        value = f.model_copy(
            update={"privileges": f.privileges.model_copy(update={"inherited_roles": ("admin",)})}
        )
    elif change == "socket-unknown":
        value = f.model_copy(update={"host": "UNIX"})
    elif change in ("marker", "nonce"):
        value = f.model_copy(
            update={
                "context": f.context.model_copy(
                    update={
                        "marker_sha256" if change == "marker" else "nonce": "f" * 64
                        if change == "marker"
                        else f.context.fixture_uuid
                    }
                )
            }
        )
    else:
        key = dict(
            system="system_identifier_sha256",
            container="container_sha256",
            namespace="namespace_sha256",
        )[change]
        value = f.model_copy(update={key: "f" * 64})
    with pytest.raises(Fault):
        validate_fixture(value, f)


@pytest.mark.parametrize(
    "change",
    ["same-domain", "same-issuer", "wrong-hash", "wrong-context", "self-signed", "wrong-event"],
)
def test_AT14_two_json_copies_are_not_independent_proof(change):
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import FakeHarness, validate_creation

    h = FakeHarness(m.fixture())
    a = h.attest("MOCK_PG", "CREATED", 1)
    b = h.attest("MOCK_ORCHESTRATOR", "CREATED", 2)
    update = {
        "same-domain": {"domain": a.domain},
        "same-issuer": {"issuer_sha256": a.issuer_sha256},
        "wrong-hash": {"fixture_sha256": "f" * 64},
        "wrong-context": {"context": a.context.model_copy(update={"marker_sha256": "f" * 64})},
        "self-signed": {"signature_status": "REAL_VERIFIED"},
        "wrong-event": {"event": "DESTROYED"},
    }
    with pytest.raises(Fault):
        validate_creation(m.fixture(), a, b.model_copy(update=update[change]))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("profile", "G3"),
        ("token_id_sha256", "f" * 64),
        ("issuer_sha256", "f" * 64),
        ("key_id_sha256", "f" * 64),
        ("mock_signature_sha256", "f" * 64),
        ("allowlist_sha256", "f" * 64),
        ("approval_record_sha256", "f" * 64),
        ("revoked", True),
        ("algorithm", "SELF_SIGNED_REAL"),
        ("issued_ns", 5),
        ("expires_ns", 2),
        ("unknown", "SECRET_A4236"),
    ],
)
def test_AT07_AT08_forged_expired_and_unknown_grants_reject(field, bad):
    from scripts import a4236_mock as m
    from scripts.a4236_grant_verifier import FakeIssuer

    g = m.grant()
    with pytest.raises(Fault) as error:
        FakeIssuer(g).verify(g.model_copy(update={field: bad}), 2)
    assert "SECRET_A4236" not in str(error.value)


@pytest.mark.parametrize(
    "field,bad",
    [("head_sha", "2" * 40), ("run_id", "12345"), ("attempt", 2), ("source_sha256", "f" * 64)],
)
def test_AT05_grant_binds_head_run_attempt_source(field, bad):
    from scripts import a4236_mock as m
    from scripts.a4236_grant_verifier import FakeIssuer

    g = m.grant()
    other = g.model_copy(
        update={
            "context": g.context.model_copy(
                update={"identity": g.context.identity.model_copy(update={field: bad})}
            )
        }
    )
    with pytest.raises(Fault):
        FakeIssuer(g).verify(other, 2)


@pytest.mark.parametrize("winner", ["A", "B"])
def test_AT09_atomic_interleaving_and_crash_model_once_only(winner):
    from scripts import a4236_mock as m
    from scripts.a4236_grant_verifier import FakeAtomicConsumer, FakeIssuer

    g = m.grant()
    verified = {p: FakeIssuer(g).verify(g, 2) for p in ("A", "B")}
    model = FakeAtomicConsumer()
    # Both processes verified PENDING; a single modeled CAS commits before either creates.
    won = model.consume(verified[winner])
    assert won.audit_sequence == 1 and won.persistent_verified is False
    with pytest.raises(Fault, match="GRANT_ALREADY_CONSUMED"):
        model.consume(verified["B" if winner == "A" else "A"])
    restarted = FakeAtomicConsumer.recover(model.snapshot())
    with pytest.raises(Fault, match="GRANT_ALREADY_CONSUMED"):
        restarted.consume(verified[winner])
    # Lost ACK/post-commit crash does NOT refund. This remains a model, not real persistence.
    assert restarted.sequence == 1


def test_AT08_AT09_nonce_reuse_snapshot_detached_and_before_commit_crash():
    from scripts import a4236_mock as m
    from scripts.a4236_grant_verifier import FakeAtomicConsumer, FakeIssuer

    g = m.grant()
    v = FakeIssuer(g).verify(g, 2)
    empty = FakeAtomicConsumer.recover(FakeAtomicConsumer().snapshot())
    empty.consume(v)  # Pre-CAS crash: no commitment existed and no fixture was created.
    snapshot = empty.snapshot()
    snapshot["states"][g.token_id_sha256]["context"]["marker_sha256"] = "f" * 64
    assert empty.snapshot()["states"][g.token_id_sha256]["context"]["marker_sha256"] != "f" * 64
    second = g.model_copy(update={"token_id_sha256": "f" * 64})
    with pytest.raises(Fault):
        empty.consume(FakeIssuer(second).verify(second, 2))


@pytest.mark.parametrize(
    "entry,code",
    [
        ("issuer", "ISSUER_NOT_CONFIGURED"),
        ("consumer", "PERSISTENT_CONSUMER_UNAVAILABLE"),
        ("harness-create", "HARNESS_NOT_CONFIGURED"),
        ("harness-destroy", "HARNESS_NOT_CONFIGURED"),
        ("live", "G1_NOT_RUN_NOT_AUTHORIZED"),
    ],
)
def test_AT06_AT10_unconfigured_real_services_no_mock_fallback(entry, code):
    from scripts.a4236_g1_harness_contract import TrustedHarness
    from scripts.a4236_g1_probe import run_live
    from scripts.a4236_grant_verifier import IndependentVerifier, PersistentConsumer

    calls = dict(
        issuer=IndependentVerifier().verify,
        consumer=PersistentConsumer().consume,
        **{"harness-create": TrustedHarness().create, "harness-destroy": TrustedHarness().destroy},
        live=run_live,
    )
    with pytest.raises(Fault, match=code):
        calls[entry](approved=True, token="SECRET_A4236", event="push")


@pytest.mark.parametrize("change", ["missing-absence", "same-issuer", "order", "wrong-owner"])
def test_AT15_destroy_only_owned_fixture_and_independent_absence(change):
    from scripts import a4236_mock as m
    from scripts.a4236_g1_harness_contract import FakeHarness, validate_cleanup
    from scripts.a4236_grant_verifier import FakeAtomicConsumer, FakeIssuer

    h, g = FakeHarness(m.fixture()), m.grant()
    h.create(FakeAtomicConsumer().consume(FakeIssuer(g).verify(g, 2)))
    if change == "wrong-owner":
        with pytest.raises(Fault):
            h.destroy(m.fixture().model_copy(update={"owner_sha256": "f" * 64}))
        assert h.created
        return
    receipts = h.destroy(m.fixture())
    if change == "missing-absence":
        receipts.pop()
    elif change == "same-issuer":
        receipts[-1] = receipts[-1].model_copy(update={"issuer_sha256": receipts[0].issuer_sha256})
    else:
        receipts.reverse()
    with pytest.raises(Fault):
        validate_cleanup(m.fixture(), receipts)
