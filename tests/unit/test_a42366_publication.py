"""Publication safety regressions. Local journals below are NOT independent evidence."""

import os
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.a42361_contract import canonical, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault, receipt, scope_hash
from scripts.a42365_contract import runtime_receipt
from scripts.a42365_runtime import RuntimeCoordinator
from scripts.a42365_supervisor import StagedPublisher
from tests.unit.test_a42364_owner import identity


class Journal:
    def __init__(self, domain):
        self.domain, self.values = domain, {}

    def append(self, scope, event, record):
        assert event not in self.values
        factory = runtime_receipt if self.domain == "root_manager" else receipt
        value = factory(self.domain, scope, event, len(self.values) + 1, record)
        self.values[event] = value
        return value

    def maybe_read(self, scope, event):
        return self.values.get(event)

    def read(self, scope, event):
        value = self.maybe_read(scope, event)
        if value is None:
            raise Fault("A42363_COMMITTED_RECEIPT_MISSING")
        return value

    def events(self, scope):
        return list(self.values.values())


@pytest.fixture
def publication(tmp_path, monkeypatch):
    scope = identity().scope
    j, root, absence, reviewer = [
        Journal(domain)
        for domain in ("supervisor", "root_manager", "absence_auditor", "supervisor")
    ]
    evidence = canonical(dict(qualifies=False))
    manifest = canonical(dict(evidence_sha256=sha(evidence), qualifies=False))
    (tmp_path / "evidence.json").write_bytes(evidence)
    (tmp_path / "manifest.json").write_bytes(manifest)
    (tmp_path / ".incomplete").write_bytes(b"pending\n")
    j.append(scope, "ARTIFACT_STAGED", dict(
        evidence_sha256=sha(evidence), manifest_sha256=sha(manifest), qualifies=False,
        marker_identity=[(tmp_path / ".incomplete").stat().st_dev,
                         (tmp_path / ".incomplete").stat().st_ino],
    ))
    root.append(scope, "ROOT_V3_TERMINATED", dict(
        execution_scope_terminated=True, scope_sha256=scope_hash(scope), epoch=scope.epoch,
    ))
    # Exercise the actual legacy finalize function on Windows as well as Linux.
    # This fixture supplies no real kernel, authorization or independent Reviewer.
    real_open, real_unlink = os.open, os.unlink
    monkeypatch.setattr(os, "open", lambda name, flags, **kw: real_open(tmp_path / name, flags))
    monkeypatch.setattr(os, "unlink", lambda name, **kw: real_unlink(tmp_path / name))
    monkeypatch.setattr(os, "pread", lambda fd, count, offset: (
        os.lseek(fd, offset, os.SEEK_SET), os.read(fd, count)
    )[1], raising=False)
    monkeypatch.setattr(os, "fsync", lambda fd: None)
    monkeypatch.setattr(os, "O_NOFOLLOW", 0, raising=False)
    p = object.__new__(StagedPublisher)
    p.scope, p.fd, p.journal = scope, -1, j
    return SimpleNamespace(p=p, root=root, absence=absence, reviewer=reviewer, path=tmp_path)


def install_untrusted_review(f, observations):
    scope = f.p.scope
    absent = f.absence.append(scope, "ABSENT", dict(observations=observations))
    f.reviewer.append(scope, "REVIEWED", dict(
        terminated_digest=f.root.read(scope, "ROOT_V3_TERMINATED").digest,
        absence_digest=absent.digest, qualifies=False,
    ))


@pytest.mark.parametrize("damage", ["fabricated", "duplicated", "present", "unknown", "order"])
def test_AT01_AT02_AT03_forged_eight_observations_never_publish(publication, damage):
    f = publication
    rows = [dict(resource=r.model_dump(), result="ABSENT", observed_ns=n + 100)
            for n, r in enumerate(resources(f.p.scope) * 2)]
    if damage == "fabricated":
        rows = [{} for _ in range(8)]
    elif damage == "duplicated":
        rows = rows[:4] * 2
    elif damage in ("present", "unknown"):
        rows[6]["result"] = damage.upper()
    else:
        rows.reverse()
    install_untrusted_review(f, rows)
    with pytest.raises(Fault, match="PUBLICATION_"):
        f.p.finalize(f.root, f.absence, f.reviewer)
    assert (f.path / ".incomplete").exists()
    assert f.p.journal.maybe_read(f.p.scope, "PUBLISHED") is None


def test_AT04_supervisor_self_review_cannot_release_marker(publication):
    f = publication
    install_untrusted_review(f, [{}] * 8)
    with pytest.raises(Fault, match="PUBLICATION_"):
        f.p.finalize(f.root, f.absence, f.reviewer)
    assert (f.path / ".incomplete").exists()


def test_AT25_AT28_no_cleanup_of_never_prepared_resources():
    scope, journal, calls = identity().scope, Journal("root_manager"), []

    class Client:
        def call(self, method):
            calls.append(method)
            return dict(qualifies=False)

    client = Client()
    runtime = RuntimeCoordinator(scope, None, journal, client, client, client, client, client, None)
    result = runtime.reconcile_scope()
    assert calls == []
    assert result.record["status"] == "INCOMPLETE_QUARANTINED"


def test_AT28_stop_ack_loss_does_not_prevent_owned_cleanup_or_replay_stop():
    scope, journal, calls = identity().scope, Journal("root_manager"), []
    for name in ("D_RUN", "C_PREPARE"):
        journal.append(scope, name + "_ATTEMPTED", dict(qualifies=False))
        journal.append(scope, name + "_COMMITTED", dict(qualifies=False))

    class Client:
        def call(self, method):
            calls.append(method)
            if method == "stop":
                raise Fault("A42363_STOP_ACK_UNKNOWN")
            return dict(qualifies=False)

    client = Client()
    runtime = RuntimeCoordinator(scope, None, journal, client, client, client, client, client, None)
    with pytest.raises(Fault, match="STOP_ACK_UNKNOWN"):
        runtime.stop()
    assert calls == ["stop", "terminate", "reconcile"]
    assert journal.read(scope, "RUN_FIRST_ERROR").record["code"] == "A42363_STOP_ACK_UNKNOWN"
    with pytest.raises(Fault, match="RUNTIME_ACK_UNKNOWN_NO_REPLAY"):
        runtime.stop()
    assert calls == ["stop", "terminate", "reconcile"]


@pytest.mark.parametrize("event", ["AUDIT_VERIFIED", "PUBLISH_INTENT", "PUBLISHED", "FINALIZED"])
@pytest.mark.parametrize("after_commit", [False, True])
def test_AT05_AT06_crash_model_never_removes_marker_without_permanent_receipt(
    publication, monkeypatch, event, after_commit,
):
    from scripts.a42366_publication import _commit_finalization

    f = publication
    append = f.p.journal.append

    def crash(scope, current, record):
        if current == event and not after_commit:
            raise OSError("injected before commit")
        result = append(scope, current, record)
        if current == event:
            raise OSError("injected committed ACK loss")
        return result

    real_stat = os.stat
    monkeypatch.setattr(os, "stat", lambda name, **kw: real_stat(
        f.path / name if kw.get("dir_fd") == -1 else name,
        **{k: v for k, v in kw.items() if k != "dir_fd"},
    ))
    monkeypatch.setattr(f.p.journal, "append", crash)
    approval = dict(test_model_only=True, qualifies=False)
    with pytest.raises(OSError, match="injected"):
        _commit_finalization(f.p, approval)
    assert (f.path / ".incomplete").exists() or f.p.journal.read(f.p.scope, "PUBLISHED")
    monkeypatch.setattr(f.p.journal, "append", append)
    result = _commit_finalization(f.p, approval)
    assert result.event == "FINALIZED"
    assert not (f.path / ".incomplete").exists()
    assert _commit_finalization(f.p, approval) == result


def complete_facts(scope, root):
    """Explicit semantic model, never an independently signed physical receipt."""
    b, c, e = Journal("consumer"), Journal("controller"), Journal("absence_auditor")
    consumed = b.append(scope, "CONSUMED", dict(qualifies=False))
    originals = {}
    for item in resources(scope):
        raw = dict(kind=item.kind)
        originals[item.kind] = c.append(scope, item.kind + "_ORIGINAL", dict(
            raw=raw, raw_sha256=sha(canonical(raw)), identity_sha256="a" * 64,
        )).digest
    requested = c.append(scope, "DESTROY_REQUESTED", dict(qualifies=False))
    for item in resources(scope):
        c.append(scope, item.kind + "_REMOVE_DONE", dict(qualifies=False))
    destroyed = c.append(scope, "RECONCILED", dict(
        status="DESTROYED_PENDING_INDEPENDENT_E", destroyed_ns=50,
        first_error=None, cleanup_codes=[], original_digests=originals,
    ))
    visibility = dict(readonly=True, epoch=scope.epoch, namespace_sha256=scope.namespace_sha256,
                      controller_uid=scope.controller_uid, observer_uid=scope.controller_uid + 1)
    rows = [dict(
        resource=item.model_dump(), round=index // 4 + 1, result="ABSENT",
        raw=dict(status="ABSENT", code=1, identity=None), original_digest=originals[item.kind],
        observed_ns=100 + index, visibility=visibility, observer_uid=scope.controller_uid + 1,
    ) for index, item in enumerate(resources(scope) * 2)]
    absent = e.append(scope, "ABSENT", dict(
        observations=rows, scope_sha256=scope_hash(scope), epoch=scope.epoch,
        requested_digest=requested.digest, destruction_digest=destroyed.digest,
        consumption_digest=consumed.digest,
    ))
    return root.read(scope, "ROOT_V3_TERMINATED"), absent, b, c


@pytest.mark.parametrize("damage", ["present", "unknown", "copy", "order", "scope", "round",
                                  "identity", "time", "epoch", "visibility", "raw", "bool"])
def test_AT01_AT04_each_observation_and_fresh_original_is_checked(publication, damage):
    from scripts.a42366_publication import validate_absence

    f = publication
    terminated, absent, b, c = complete_facts(f.p.scope, f.root)
    assert validate_absence(f.p.scope, terminated, absent, b, c)
    bad = deepcopy(absent.record)
    rows = bad["observations"]
    if damage in ("present", "unknown"):
        rows[7]["result"] = damage.upper()
    elif damage == "copy":
        rows[4:] = deepcopy(rows[:4])
    elif damage == "order":
        rows.reverse()
    elif damage == "scope":
        rows[1]["resource"]["scope"]["payload_sha256"] = "f" * 64
    elif damage == "round":
        rows[4]["round"] = 1
    elif damage == "identity":
        rows[3]["original_digest"] = "f" * 64
    elif damage == "time":
        rows[0]["observed_ns"] = 49
    elif damage == "epoch":
        bad["epoch"] = "wrong"
    elif damage == "visibility":
        rows[7]["visibility"] = dict(rows[7]["visibility"], observer_uid=999999)
    elif damage == "raw":
        rows[0]["raw"]["code"] = 125
    else:
        rows[0]["raw"]["code"] = True
    altered = receipt("absence_auditor", f.p.scope, "ABSENT", absent.sequence, bad)
    with pytest.raises(Fault, match="PUBLICATION_"):
        validate_absence(f.p.scope, terminated, altered, b, c)


def test_AT04_valid_semantic_model_still_cannot_impersonate_independent_reviewer(publication):
    f = publication
    _, absent, b, c = complete_facts(f.p.scope, f.root)
    e = Journal("absence_auditor")
    e.values["ABSENT"] = absent
    with pytest.raises(Fault, match="PUBLICATION_INDEPENDENT_REVIEWER_REQUIRED"):
        f.p.finalize(f.root, e, f.reviewer, consumer_journal=b, controller_journal=c)
    assert (f.path / ".incomplete").exists()
