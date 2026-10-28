"""Refusal/identity/recovery contracts, not PG/Podman/kernel qualification."""

import pytest
from pydantic import ValidationError

from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault, scope_hash
from scripts.a42365_budget import BudgetService
from scripts.a42365_writer_broker import InstalledWriterBroker
from scripts.a42366_mediation import BudgetRequest, reserve_request
from scripts.a42366_owner import RegisteredSessionSource, TargetSessionRegistry
from tests.unit.test_a42364_owner import identity
from tests.unit.test_a42366_publication import Journal
from tests.unit.test_a42366_services import L1Authority


def test_AT16_AT18_unproven_native_census_is_not_a_reservation_or_execution():
    s, j = identity().scope, Journal("consumer")
    b = BudgetService(identity(), L1Authority(s, j), j, "L1_BOOT")
    b.start()
    with pytest.raises(Fault, match="NATIVE_TRANSITIVE_CENSUS_UNPROVEN"):
        reserve_request(b, dict(operation="NATIVE", index=1))
    assert set(j.values) == {"BUDGET_STARTED"}
    assert b.report()["native_exec_census"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize("body", [dict(operation="NAMED", name="x", argv=[]),
                                  dict(operation="AUDIT", index=1, kind="SQL", name="x"),
                                  dict(operation="FILESYSTEM", step=True)])
def test_AT18_AT20_unknown_budget_fields_or_types_are_rejected(body):
    with pytest.raises(ValidationError):
        BudgetRequest.model_validate(body)


@pytest.mark.parametrize("field,value", [
    ("backend_pid", 901), ("backend_start", "replacement"), ("generation", 2),
    ("role", "postgres"), ("database", "foreign"), ("namespace_sha256", "f" * 64),
    ("scope_sha256", "e" * 64),
])
def test_AT21_AT24_target_registration_survives_reopen_and_rejects_drift(field, value):
    i, journal = identity(), Journal("pg_owner")
    raw = dict(backend_pid=900, backend_start="2026-10-28T00:00:00+00:00", role=i.probe_role,
               database=i.database, generation=1, namespace_sha256=i.scope.namespace_sha256,
               scope_sha256=scope_hash(i.scope))

    class Observer:
        def observe(self, pid):
            return dict(raw)

    auth = L1Authority(i.scope, journal)
    original = RegisteredSessionSource(TargetSessionRegistry(i, auth, journal, 1), Observer())
    assert original.observe(900) == raw
    raw[field] = value
    reopened = RegisteredSessionSource(TargetSessionRegistry(i, auth, journal, 1), Observer())
    with pytest.raises(Fault, match="OWNER_SESSION_DRIFT"):
        reopened.observe(900)
    assert journal.read(i.scope, "TARGET_SESSION_REGISTERED").record["session"][field] != value


@pytest.mark.parametrize("kind,verb", [
    (kind, verb) for kind in ("SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER")
    for verb in ("create", "inspect", "rm")
] + [("CONTAINER", "start"), ("CONTAINER", "stop")])
def test_AT11_AT15_unproven_all_writer_capability_has_zero_commands(tmp_path, kind, verb):
    i, journal = identity(), Journal("writer_broker")

    class Runner:
        def run(self, *args, **kwargs):
            pytest.fail("Unproven global writer lease executed a command")

    with (tmp_path / "held-object").open("w+b") as held:
        broker = InstalledWriterBroker(i.scope, L1Authority(i.scope, journal), journal,
                                       held.fileno(), held.fileno(), held.fileno(), Runner())
        item = next(item for item in resources(i.scope) if item.kind == kind)
        with pytest.raises(Fault, match="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY"):
            broker.dispatch(item, verb, None if verb == "create" else {})
    assert not journal.values

