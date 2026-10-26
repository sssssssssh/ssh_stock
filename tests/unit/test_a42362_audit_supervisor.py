"""Independent-domain failure models; no physical absence or G1 execution claim."""

import itertools
from types import SimpleNamespace as NS

import pytest

from scripts import a42362_service_host as host
from scripts.a42361_contract import Fault, canonical, sha
from scripts.a42361_offline_cases import binding
from scripts.a42362_absence_auditor import AbsenceAuditor, Observation
from scripts.a42362_contract import FailureLedger, Scope, State, resources
from scripts.a42362_reconcile import Reconciler
from scripts.a42362_supervisor_service import SupervisorService, terminate_scope


def scope():
    return Scope(
        token_id="32345678-1234-4234-8234-123456789012",
        binding=binding(),
        payload_sha256="1" * 64,
        image_digest="sha256:" + "2" * 64,
        controller_uid=1005,
        namespace_sha256="3" * 64,
        epoch="42345678-1234-4234-8234-123456789012",
    )


class Store:
    def __init__(self):
        self.writes = []

    def read_destruction(self, s):
        return dict(
            domain="CONTROLLER",
            scope_sha256=sha(canonical(s.model_dump())),
            requested_sequence=1,
            destroyed_sequence=2,
            destroyed_ns=1,
        )

    def append_absence(self, record):
        self.writes.append(record)
        return sha(canonical(record))

    def read_absence(self, s):
        r = self.writes[-1]
        return dict(record=r, raw_receipt_sha256=sha(canonical(r)), committed=True)


class Ledger:
    def scan(self, body):
        events = [dict(request=dict(resource=r.model_dump())) for r in resources(scope())]
        return dict(events=events, snapshot_sha256=sha(canonical(events)))


def auditor(monkeypatch, damage=None):
    policy = NS(domain="absence_auditor", uid=1007, controller_uid=1005, collector_sha256="b" * 64)
    if damage == "same_uid":
        policy.uid = 1005
    monkeypatch.setattr(host, "installation", lambda _: policy)
    counter = itertools.count(2)

    class Observer:
        def observe(self, item):
            if damage == "copy_controller":
                return dict(absent=True, event="ABSENT")
            return Observation(
                resource=item,
                observer_uid=policy.uid,
                namespace_sha256=item.scope.namespace_sha256,
                collector_sha256=policy.collector_sha256,
                observed_ns=next(counter),
                result="ABSENCE_UNKNOWN"
                if damage == "permission"
                else "PRESENT"
                if damage == "recreated"
                else "ABSENT",
                exit_code=125 if damage == "permission" else 1,
            )

    store = Store()
    a = AbsenceAuditor(object(), Ledger(), store, Observer())
    return a, store


def test_AT40_AT45_independent_model_observes_all_four_resources_twice(monkeypatch):
    a, store = auditor(monkeypatch)
    result = a.audit(scope())
    assert len(store.writes) == 1 and len(result["record"]["observations"]) == 8
    assert result["record"]["qualifies"] is False


@pytest.mark.parametrize("damage", ["same_uid", "copy_controller", "permission", "recreated"])
def test_AT40_AT46_untrusted_or_unobservable_negative_never_commits_absent(monkeypatch, damage):
    a, store = auditor(monkeypatch, damage)
    with pytest.raises(Fault):
        a.audit(scope())
    assert store.writes == []


def test_AT42_missing_resource_is_not_complete_absence(monkeypatch):
    a, store = auditor(monkeypatch)
    a.ledger.scan = lambda _: dict(events=[], snapshot_sha256=sha(canonical([])))
    with pytest.raises(Fault):
        a.audit(scope())
    assert store.writes == []


def test_AT59_first_error_remains_after_cleanup_errors():
    f = FailureLedger()
    f.fail("A42362_CREATE_ACK_UNKNOWN")
    f.fail("A42362_ABSENCE_UNKNOWN", cleanup=True)
    assert f.first_error == "A42362_CREATE_ACK_UNKNOWN"
    assert f.cleanup_codes == ["A42362_ABSENCE_UNKNOWN"]


def test_AT47_AT48_AT63_default_host_supervisor_and_reconciler_deny_before_side_effects():
    for operation in (
        lambda: host.service_main(),
        lambda: SupervisorService().dispatch(1000, "run", {}),
        lambda: Reconciler().create(scope()),
        lambda: Reconciler().recover(scope()),
        lambda: terminate_scope(NS(pid=12345)),
    ):
        with pytest.raises(Fault):
            operation()


@pytest.mark.parametrize("field", ["g1_approved", "execution_enabled", "force", "dsN"])
def test_AT70_AT71_unrecognized_execution_flags_cannot_open_gates(field):
    from scripts.a42361_contract import checked

    with pytest.raises(Fault):
        checked(State, {field: True})
    assert State().effective_warmups_total == 8
    assert State().capacity_ready is False and State().production_read_authorized is False
