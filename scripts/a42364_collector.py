"""Fixed read-only E collector; a wrong/opaque store can never produce ABSENT."""

import os
import stat

from scripts.a42361_contract import sha
from scripts.a42362_contract import file_identity, resources
from scripts.a42363_contract import require, scope_hash


class ReadOnlyDelegation:
    def __init__(self, scope, graph_fd, run_fd, user_ns_fd, mount_ns_fd, collector_fd, expected):
        self.scope, self.fds, self.expected = (
            scope,
            (graph_fd, run_fd, user_ns_fd, mount_ns_fd, collector_fd),
            dict(expected),
        )
        self.identities = tuple(file_identity(os.fstat(fd)) for fd in self.fds)

    def verify(self):
        e = self.expected
        require(
            os.getuid() == e["observer_uid"]
            and os.getuid() != self.scope.controller_uid
            and e["scope_sha256"] == scope_hash(self.scope)
            and e["epoch"] == self.scope.epoch,
            "AUDIT_DELEGATED_PRINCIPAL",
        )
        for fd, identity in zip(self.fds, self.identities, strict=True):
            require(file_identity(os.fstat(fd))[:6] == identity[:6], "AUDIT_DELEGATION_CHANGED")
        for fd, label in zip(self.fds[:2], ("graph", "run"), strict=True):
            m = os.fstat(fd)
            require(
                stat.S_ISDIR(m.st_mode) and (m.st_dev, m.st_ino) == tuple(e[label + "_identity"]),
                "AUDIT_STORE_IDENTITY",
            )
            require(os.fstatvfs(fd).f_flag & os.ST_RDONLY, "AUDIT_WRITABLE_DELEGATION")
        for fd, name in zip(self.fds[2:4], ("user", "mnt"), strict=True):
            actual = os.stat("/proc/self/ns/" + name)
            held = os.fstat(fd)
            require((actual.st_dev, actual.st_ino) == (held.st_dev, held.st_ino), "AUDIT_NAMESPACE")
        require(
            sha(os.readlink("/proc/self/ns/user").encode()) == self.scope.namespace_sha256,
            "AUDIT_NAMESPACE",
        )
        collector = os.fstat(self.fds[4])
        require(
            stat.S_ISREG(collector.st_mode)
            and collector.st_uid == 0
            and collector.st_mode & 0o022 == 0
            and 0 < collector.st_size <= 1_000_000
            and sha(os.pread(self.fds[4], 1_000_001, 0)) == e["collector_sha256"],
            "AUDIT_COLLECTOR_BINARY",
        )
        return dict(
            observer_uid=e["observer_uid"],
            controller_uid=self.scope.controller_uid,
            namespace_sha256=self.scope.namespace_sha256,
            store_sha256=e["store_sha256"],
            collector_sha256=e["collector_sha256"],
            readonly=True,
            epoch=self.scope.epoch,
        )


class FixedReadOnlyCollector:
    """Runner has no mutating operation in this API. Permission errors remain unknown.

    A future root installer must provision readable read-only mounts for the separate E
    UID. We do not chmod a live store or pretend that an O_RDONLY directory FD is RO.
    """

    def __init__(self, delegation, runner, socket_parent_fd):
        self.delegation, self.runner, self.socket_parent_fd = delegation, runner, socket_parent_fd

    def visibility(self, expected):
        require(expected == self.delegation.expected, "AUDIT_DELEGATION_CHANGED")
        return self.delegation.verify()

    def read_exact(self, item):
        require(item in resources(self.delegation.scope), "AUDIT_FOREIGN_RESOURCE")
        before = self.delegation.verify()
        if item.kind == "SOCKET_DIR":
            try:
                m = os.stat(item.name, dir_fd=self.socket_parent_fd, follow_symlinks=False)
                result = dict(status="PRESENT", code=0, identity=str(m.st_ino))
            except FileNotFoundError:
                result = dict(status="ABSENT", code=1, identity=None)
        else:
            code, raw = self.runner.read((item.kind.lower(), "exists", item.name))
            require(raw == b"" and type(code) is int and code in (0, 1), "ABSENCE_UNKNOWN")
            result = dict(
                status="PRESENT" if code == 0 else "ABSENT",
                code=code,
                identity=item.name if code == 0 else None,
            )
        require(self.delegation.verify() == before, "AUDIT_DELEGATION_CHANGED")
        return result
