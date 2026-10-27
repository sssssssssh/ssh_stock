"""Controlled lifecycle models. Fake capability never establishes kernel exclusion."""

from contextlib import nullcontext
from types import SimpleNamespace as NS

import pytest

from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault, scope_hash
from scripts.a42364_volume_exclusion import (
    ExclusiveStoreManager,
    OperationJournal,
    engineering_status,
    volume_delete_plan,
)
from tests.unit.test_a42364_owner import MemoryJournal, identity


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
@pytest.mark.parametrize("fault", ["action", "commit_ack"])
def test_AT25_AT29_attempts_persist_across_receiver_restart(kind, fault):
    s = identity().scope
    j = MemoryJournal()
    calls = []

    def action():
        calls.append(kind)
        if fault == "action":
            raise Fault("A42363_REMOVE_ACK_UNKNOWN")
        original = j.append

        def lose(scope, event, record):
            original(scope, event, record)
            if event.startswith("DONE_"):
                raise RuntimeError("OFFLINE_LOST_ACK")
            return j.read(scope, event)

        j.append = lose
        return dict(qualifies=False)

    with pytest.raises(Fault):
        OperationJournal(j).perform(s, kind, "REMOVE", "original", action)
    with pytest.raises(Fault, match="NO_REPLAY"):
        OperationJournal(j).perform(s, kind, "REMOVE", "original", action)
    assert calls == [kind]


@pytest.mark.parametrize("kind", ["SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER"])
def test_AT26_original_operation_key_changes_with_epoch_not_just_resource_name(kind):
    i = identity()
    s = i.scope
    changed = s.model_copy(update={"epoch": "62345678-1234-4234-8234-123456789012"})
    assert OperationJournal.key(s, kind, "CREATE", "x") != OperationJournal.key(
        changed, kind, "CREATE", "x"
    )


def model_manager(inspects, *, capability_failure=False):
    s = identity().scope
    item = resources(s)[1]
    calls = []
    original = dict(
        Name=item.name,
        MountCount=0,
        StorageID="OFFLINE_STORAGE_ID",
        Labels=dict(a42363_scope=scope_hash(s), a42363_epoch=s.epoch),
    )

    def verify(scope):
        if capability_failure:
            raise Fault("A42363_SAFE_DELETE_UNPROVEN")

    cap = NS(verify=verify, transaction=lambda scope: nullcontext())

    def inspect(_):
        return inspects(original)

    def run(argv):
        calls.append(argv)
        return 0, b""

    m = ExclusiveStoreManager(
        s, cap, NS(require=lambda _: None), OperationJournal(MemoryJournal()), NS(run=run), inspect
    )
    return m, item, original, calls


def test_AT21_fixed_manager_model_uses_exact_name_not_storageid():
    m, item, raw, calls = model_manager(lambda r: r)
    result = m.remove_volume(item, raw)
    assert calls == [("volume", "rm", item.name)] and result.qualifies is False
    assert "OFFLINE_STORAGE_ID" not in calls[0]


@pytest.mark.parametrize("change", ["replacement", "mount", "epoch", "writer"])
def test_AT21_AT24_aba_mounted_foreign_or_writer_never_reaches_rm(change):
    def inspect(raw):
        if change == "replacement":
            return dict(raw, StorageID="REPLACED")
        if change == "mount":
            return dict(raw, MountCount=1)
        if change == "epoch":
            return dict(raw, Labels={})
        return raw

    m, item, raw, calls = model_manager(inspect, capability_failure=change == "writer")
    with pytest.raises(Fault):
        m.remove_volume(item, raw)
    assert calls == []


def test_AT22_global_writer_gap_is_engineering_not_an_approval_switch():
    result = engineering_status()
    assert result["safe_volume_disposal"] == "ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY"
    assert result["global_writer_broker"].startswith("NOT_IMPLEMENTED")
    assert (
        volume_delete_plan("a42361-" + "a" * 32 + "-data")["requires"]
        == "EXCLUSIVE_ALL_WRITERS_CAPABILITY"
    )


@pytest.mark.parametrize("name", ["prefix*", "foreign", "--all", "/store/path", "StorageID"])
def test_AT23_names_storageids_and_prefixes_cannot_be_arbitrary(name):
    with pytest.raises(Fault):
        volume_delete_plan(name)
