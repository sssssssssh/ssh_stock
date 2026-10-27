"""Owner SQL rendering/authentication models; never a real connection or secret."""

from types import SimpleNamespace as NS

import pytest

from scripts.a42361_offline_cases import binding
from scripts.a42362_contract import Scope
from scripts.a42363_contract import Fault, receipt
from scripts.a42363_identity import FixtureIdentity, Installation
from scripts.a42364_owner import scram_verifier, statements, verify_owner_metadata


def identity():
    scope = Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=1002,
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )
    return FixtureIdentity.derive(scope, Installation(worker_uid=1003, socket_gid=1004))


class MemoryJournal:
    """Explicit OFFLINE_MODEL_ONLY, no formal trust or real persistence."""

    def __init__(self, domain="controller"):
        self.domain, self.values, self.count = domain, {}, 0

    def maybe_read(self, scope, event):
        return self.values.get(event)

    def read(self, scope, event):
        return self.values[event]

    def append(self, scope, event, record):
        if event in self.values:
            raise Fault("A42363_JOURNAL_COMMIT_UNKNOWN_NO_RETRY")
        self.count += 1
        self.values[event] = receipt(self.domain, scope, event, self.count, record)
        return self.values[event]


def test_AT09_actual_dynamic_identifiers_use_psycopg_rendering():
    i = identity()
    plan = statements(i, scram_verifier(b"OFFLINE_NOT_A_REAL_SECRET_" + b"x" * 40))
    assert len(plan) == 12
    rendered = [statement.as_string() for _, statement, _ in plan]
    assert rendered[0] == 'CREATE DATABASE "' + i.database + '" OWNER "postgres"'
    assert i.probe_role in rendered[3] and "CONNECTION LIMIT 1" in rendered[3]
    assert "SCRAM-SHA-256$4096:" in rendered[4]
    assert all("OFFLINE_NOT_A_REAL_SECRET" not in raw for raw in rendered)
    assert plan[9][2] == (i.probe_role,)


@pytest.mark.parametrize("password", [b"short", b"a" * 129, b"\x00" * 64, "not-bytes"])
def test_AT09_scram_accepts_only_manager_generated_ascii(password):
    with pytest.raises(Fault, match="SCRAM_CREDENTIAL"):
        scram_verifier(password)


def valid_metadata():
    i = identity()
    raw = [i.database, "postgres", "170009", "1234567890", *[False] * 6, 1, [], False, False, False]
    hba = [
        (1, "scram-sha-256", None),
        (2, "scram-sha-256", None),
        (3, "reject", None),
        (4, "reject", None),
    ]
    return raw, hba


def test_AT11_raw_role_and_hba_prove_config_not_target_guc():
    raw, hba = valid_metadata()
    result = verify_owner_metadata(identity(), raw, hba, [])
    assert result["target_session_settings_observed"] is False and result["qualifies"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        (0, "foreign_db"),
        (1, "foreign_role"),
        (2, "180000"),
        (3, ""),
        (4, True),
        (10, 2),
        (11, [42]),
        (14, True),
    ],
)
def test_AT11_AT12_empty_foreign_or_privileged_metadata_rejected(field, value):
    raw, hba = valid_metadata()
    raw[field] = value
    with pytest.raises((Fault, ValueError)):
        verify_owner_metadata(identity(), raw, hba, [])


def test_AT12_empty_metadata_is_not_ready():
    with pytest.raises(Fault, match="OWNER_RAW_METADATA"):
        verify_owner_metadata(identity(), None, [], [])


@pytest.mark.parametrize("row", [(1, "trust", None), (1, "scram-sha-256", "bad-rule")])
def test_AT11_auth_rules_must_be_actual_scram(row):
    raw, hba = valid_metadata()
    hba[0] = row
    with pytest.raises(Fault, match="OWNER_HBA_RULES"):
        verify_owner_metadata(identity(), raw, hba, [])


def test_AT10_create_ack_unknown_cannot_connect_again():
    from scripts.a42364_owner import OwnerInitializer

    i = identity()
    j = MemoryJournal("pg_owner")
    calls = []

    class Connections:
        def open(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("OFFLINE_ACK_LOSS")

    instance = OwnerInitializer(
        i,
        NS(require=lambda _: None),
        Connections(),
        j,
        NS(read=lambda *a: "OFFLINE_ASCII_" + "x" * 64),
        NS(reserve_named=lambda *a: None),
    )
    with pytest.raises(Fault, match="OWNER_ACK_UNKNOWN_NO_RETRY"):
        instance.initialize()
    with pytest.raises(Fault, match="OWNER_NO_SECOND_INITIALIZATION"):
        instance.initialize()
    assert len(calls) == 1


def test_AT09_AT12_fixed_owner_adapter_runs_all_twelve_steps_in_offline_model():
    from scripts.a42364_owner import OwnerInitializer

    i, j = identity(), MemoryJournal("pg_owner")
    raw, hba = valid_metadata()
    sql_calls, reservations, connections = [], [], []

    class Connection:
        def __init__(self, bootstrap, probe):
            self.info = NS(
                dbname="postgres" if bootstrap else i.database,
                user=i.probe_role if probe else i.owner_role,
                host=i.socket_host,
                port=5432,
                server_version=170009,
            )
            self.autocommit, self.closed = bootstrap or probe, False

        def execute(self, query, params):
            sql_calls.append(query.as_string())
            return NS(fetchone=lambda: raw, fetchall=lambda: hba if len(sql_calls) == 11 else [])

        def commit(self):
            assert len(sql_calls) == 12

        def close(self):
            assert not self.closed
            self.closed = True

    def connect(bootstrap=False, probe=False):
        c = Connection(bootstrap, probe)
        connections.append(c)
        return c

    result = OwnerInitializer(
        i,
        NS(require=lambda _: None),
        NS(open=connect),
        j,
        NS(read=lambda *a: "OFFLINE_ASCII_" + "x" * 64),
        NS(reserve_named=lambda name, now: reservations.append(name)),
    ).initialize()
    assert len(sql_calls) == len(reservations) == result.record["sql_count"] == 12
    assert len(connections) == 3 and all(c.closed for c in connections)
    assert result.record["qualifies"] is False
    assert result.record["target_session_settings_observed"] is False
    assert "SCRAM-SHA-256" not in str(j.values)


def test_AT10_failure_journal_loss_keeps_first_error_and_sanitizes_exception():
    from scripts.a42364_owner import OwnerInitializer

    class Journal(MemoryJournal):
        def append(self, scope, event, record):
            if event == "OWNER_V3_FAILED":
                raise RuntimeError("OFFLINE_PRIVATE_DRIVER_TEXT")
            return super().append(scope, event, record)

    def connect(**kwargs):
        raise RuntimeError("OFFLINE_PRIVATE_DRIVER_TEXT")

    with pytest.raises(Fault, match="^A42363_OWNER_ACK_UNKNOWN_NO_RETRY$") as caught:
        OwnerInitializer(
            identity(),
            NS(require=lambda _: None),
            NS(open=connect),
            Journal("pg_owner"),
            NS(read=lambda *a: "OFFLINE_ASCII_" + "x" * 64),
            NS(reserve_named=lambda *a: None),
        ).initialize()
    assert caught.value.cleanup_codes == ["A42363_OWNER_FAILURE_JOURNAL_UNKNOWN"]
