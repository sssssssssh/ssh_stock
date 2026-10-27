"""Name-based Podman5.6.2 disposal behind a persistent manager, NEVER StorageID rm.

The kernel package must prove global writer exclusion. A flock/process census alone
does not instantiate that capability; lack of it remains an engineering blocker.
"""

import os
import re
import stat
from dataclasses import dataclass

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import Fault, require, scope_hash


def volume_delete_plan(name):
    require(
        type(name) is str and re.fullmatch(r"a42361-[0-9a-f]{32}-data", name) is not None,
        "VOLUME_EXACT_NAME",
    )
    return dict(
        operation=("volume", "rm", name),
        requires="EXCLUSIVE_ALL_WRITERS_CAPABILITY",
        version="podman-5.6.2-name-lookup",
        qualifies=False,
    )


class OperationJournal:
    """DomainStore unique event + fresh-connection ACK, not an in-memory attempted set."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def key(scope, kind, verb, original):
        require(
            kind in ("SOCKET_DIR", "VOLUME", "SECRET", "CONTAINER")
            and verb in ("CREATE", "START", "STOP", "REMOVE"),
            "OPERATION_KIND",
        )
        return sha(
            canonical(dict(scope=scope_hash(scope), kind=kind, verb=verb, original=original))
        )[:40]

    def perform(self, scope, kind, verb, original, operation):
        key = self.key(scope, kind, verb, original)
        require(
            self.store.maybe_read(scope, "OP_" + key) is None, "OPERATION_ACK_UNKNOWN_NO_REPLAY"
        )
        attempted = self.store.append(
            scope,
            "OP_" + key,
            dict(
                kind=kind,
                verb=verb,
                original=original,
                epoch=scope.epoch,
                scope_sha256=scope_hash(scope),
                qualifies=False,
            ),
        )
        # Never refund after a write/ACK uncertainty. Reconciliation uses independent E.
        try:
            result = operation()
            return self.store.append(
                scope,
                "DONE_" + key,
                dict(attempt_digest=attempted.digest, result=result, qualifies=False),
            )
        except BaseException as error:
            first = getattr(error, "code", "A42363_OPERATION_ACK_UNKNOWN")
            cleanup = []
            try:
                self.store.append(scope, "FAIL_" + key, dict(first_error=first, qualifies=False))
            except BaseException:
                cleanup.append("A42363_JOURNAL_COMMIT_UNKNOWN_NO_RETRY")
            fault = Fault(first)
            fault.first_error, fault.cleanup_codes = first, cleanup
            raise fault from None


@dataclass(frozen=True)
class StoreIdentity:
    scope_sha256: str
    epoch: str
    namespace_sha256: str
    graph_device: int
    graph_inode: int
    run_device: int
    run_inode: int
    runtime_uid: int
    runtime_gid: int
    controller_uid: int
    auditor_uid: int

    def verify(self, scope):
        require(
            self.scope_sha256 == scope_hash(scope)
            and self.epoch == scope.epoch
            and self.namespace_sha256 == scope.namespace_sha256
            and self.controller_uid == scope.controller_uid
            and len({0, self.runtime_uid, self.controller_uid, self.auditor_uid}) == 4,
            "STORE_PRINCIPAL_OR_SCOPE",
        )
        return self


class KernelStoreCapability:
    """Actual held-object verification, with an explicit missing mandatory capability.

    Root manager / dedicated runtime UID / private roots and process checks are necessary
    but not sufficient to prove all writers. The installed kernel writer-broker adapter
    is required and deliberately has NO boolean/config/TCB-flock substitute.
    """

    def __init__(self, identity, graph_fd, run_fd, namespace_fd, writer_broker=None):
        self.identity, self.graph_fd, self.run_fd = identity, graph_fd, run_fd
        self.namespace_fd, self.writer_broker = namespace_fd, writer_broker

    def verify(self, scope):
        i = self.identity.verify(scope)
        require(os.getuid() == 0, "ROOT_STORE_MANAGER_REQUIRED")
        for fd, device, inode in (
            (self.graph_fd, i.graph_device, i.graph_inode),
            (self.run_fd, i.run_device, i.run_inode),
        ):
            m = os.fstat(fd)
            require(
                stat.S_ISDIR(m.st_mode)
                and (m.st_dev, m.st_ino) == (device, inode)
                and m.st_uid == i.runtime_uid
                and m.st_gid == i.runtime_gid
                and stat.S_IMODE(m.st_mode) == 0o700,
                "STORE_FD_OR_PERMISSIONS",
            )
        ns = os.fstat(self.namespace_fd)
        current = os.stat("/proc/self/ns/user")
        require(
            (ns.st_dev, ns.st_ino) == (current.st_dev, current.st_ino)
            and sha(os.readlink("/proc/self/ns/user").encode()) == i.namespace_sha256,
            "STORE_NAMESPACE",
        )
        require(self.writer_broker is not None, "SAFE_DELETE_UNPROVEN")
        # This is a required kernel-enforced adapter, not a caller claim that C has a lock.
        self.writer_broker.verify_all_writers(scope, i)
        return self

    def transaction(self, scope):
        self.verify(scope)
        return self.writer_broker.exclusive(scope, self.identity)


class ExclusiveStoreManager:
    """Fixed exact-scope methods only. A new receiver cannot reset the durable attempts."""

    def __init__(self, scope, capability, authority, journal, runner, inspect):
        self.scope, self.capability, self.authority = scope, capability, authority
        self.journal, self.runner, self.inspect = journal, runner, inspect

    def remove_volume(self, item, original):
        require(item.scope == self.scope and item.kind == "VOLUME", "VOLUME_SCOPE")
        self.authority.require("SAFE_VOLUME_DISPOSAL")
        plan = volume_delete_plan(item.name)
        with self.capability.transaction(self.scope):
            observed = self.inspect(item)
            require(observed == original, "VOLUME_ABA_OR_REPLACEMENT")
            require(
                type(observed) is dict
                and observed.get("Name") == item.name
                and observed.get("MountCount") == 0
                and observed.get("Labels", {}).get("a42363_scope") == scope_hash(self.scope)
                and observed.get("Labels", {}).get("a42363_epoch") == self.scope.epoch,
                "VOLUME_IN_USE_OR_FOREIGN",
            )
            identity = sha(canonical(original))

            def remove():
                self.capability.verify(self.scope)
                require(self.inspect(item) == original, "VOLUME_ABA_OR_REPLACEMENT")
                code, raw = self.runner.run(plan["operation"])
                require(code == 0, "REMOVE_ACK_UNKNOWN")
                require(type(raw) is bytes and len(raw) <= 32768, "REMOVE_ACK_UNKNOWN")
                self.capability.verify(self.scope)
                return dict(removed_name=item.name, original_sha256=identity, qualifies=False)

            return self.journal.perform(self.scope, "VOLUME", "REMOVE", identity, remove)


def engineering_status():
    return dict(
        manager_interface="IMPLEMENTED",
        durable_operations="IMPLEMENTED",
        target_semantics="PODMAN_5_6_2_NAME_ONLY",
        global_writer_broker="NOT_IMPLEMENTED_KERNEL_POLICY_REQUIRED",
        safe_volume_disposal="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY",
        live_behavior="SAFE_DELETE_UNPROVEN",
        qualifies=False,
    )


def managed_driver(
    commands, socket_directory, secret_fd, observer, identity, operations, volume_manager
):
    from scripts.a42363_resources import ResourceDriver

    class ManagedResourceDriver(ResourceDriver):
        """Original creation facts and durable operations supplement, not replace, B."""

        def creation_command(self, item):
            command = list(super().creation_command(item))
            if item.kind == "CONTAINER":
                command = [value for value in command if not value.startswith("--health-cmd=")]
                command.append("--no-healthcheck")
                # Options belong before the final pinned image operand.
                command[-1], command[-2] = command[-2], command[-1]
                index = command.index("--secret") + 1
                command[index] += ",target=space-g1-owner,uid=999,gid=999,mode=0400"
            return tuple(command)

        def create(self, item):
            volume_manager.capability.verify(item.scope)
            box = {}

            def create():
                box["raw"] = super(ManagedResourceDriver, self).create(item)
                result = dict(
                    resource=item.model_dump(),
                    identity_sha256=self.verify(item, box["raw"]),
                    qualifies=False,
                )
                operations.store.append(item.scope, "CREATION_" + item.kind, result)
                return result

            operations.perform(item.scope, item.kind, "CREATE", item.model_dump(), create)
            return box["raw"]

        def remove(self, item, raw):
            original = operations.store.read(item.scope, "CREATION_" + item.kind)
            digest = self.verify(item, raw)
            require(
                original.record["identity_sha256"] == digest
                and original.record["resource"] == item.model_dump(),
                "CREATION_FACT_DRIFT",
            )
            if item.kind == "VOLUME":
                return volume_manager.remove_volume(item, raw)
            return operations.perform(
                item.scope,
                item.kind,
                "REMOVE",
                digest,
                lambda: super(ManagedResourceDriver, self).remove(item, raw),
            )

    return ManagedResourceDriver(commands, socket_directory, secret_fd, observer, identity)
