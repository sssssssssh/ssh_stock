"""Root provisioner interface to an unprivileged, read-only E delegation.

No writable FD or mutation method is exported to E. Actual mount creation and UID
mapping are not supplied by this receiver and remain explicit engineering gaps.
"""

import os
import stat

from scripts.a42363_contract import require, scope_hash
from scripts.a42364_collector import ReadOnlyDelegation


class ReadOnlyProvisioner:
    def __init__(self, scope, authority, journal, helper, expected):
        require(journal.domain == "root_manager", "PROVISIONER_ROOT_JOURNAL")
        self.scope, self.authority, self.journal = scope, authority, journal
        self.helper, self.expected = helper, dict(expected)

    def provision(self, channel, fds):
        """Hand off ALREADY root-provisioned RO mount/namespace/collector FDs.

        This does not create mounts. Never relabel ordinary directory descriptors
        as readonly mounts, and never use an RPC-provided helper to create them.
        """
        import array
        import socket

        from scripts.a42364_manager import peer_uid

        for kind in ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC"):
            self.authority.require(kind)
        require(os.getuid() == 0, "PROVISIONER_ROOT_REQUIRED")
        require(
            self.expected["observer_uid"] != self.scope.controller_uid
            and self.expected["scope_sha256"] == scope_hash(self.scope)
            and self.expected["epoch"] == self.scope.epoch,
            "PROVISIONER_SCOPE",
        )
        self.journal.append(self.scope, "RO_PROVISION_ATTEMPTED", dict(qualifies=False))
        require(type(fds) is tuple and len(fds) == 5, "RO_PROVISION_FDS")
        require(peer_uid(channel) == self.expected["observer_uid"], "AUDIT_DELEGATED_PRINCIPAL")
        for fd, name in zip(fds[:2], ("graph", "run"), strict=True):
            m = os.fstat(fd)
            require(
                stat.S_ISDIR(m.st_mode)
                and (m.st_dev, m.st_ino) == tuple(self.expected[name + "_identity"]),
                "AUDIT_STORE_IDENTITY",
            )
            require(os.fstatvfs(fd).f_flag & os.ST_RDONLY, "AUDIT_WRITABLE_DELEGATION")
        require(
            channel.sendmsg([b"F"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))])
            == 1,
            "RO_PROVISION_ACK_UNKNOWN",
        )
        return self.journal.append(self.scope, "RO_PROVISION_HANDED_OFF", dict(qualifies=False))

    def accept(self, graph_fd, run_fd, user_ns_fd, mount_ns_fd, collector_fd):
        # This runs in E after privilege drop; an O_RDONLY directory is insufficient.
        for fd, name in ((graph_fd, "graph"), (run_fd, "run")):
            m = os.fstat(fd)
            require(
                stat.S_ISDIR(m.st_mode)
                and (m.st_dev, m.st_ino) == tuple(self.expected[name + "_identity"]),
                "AUDIT_STORE_IDENTITY",
            )
            require(os.fstatvfs(fd).f_flag & os.ST_RDONLY, "AUDIT_WRITABLE_DELEGATION")
        d = ReadOnlyDelegation(
            self.scope, graph_fd, run_fd, user_ns_fd, mount_ns_fd, collector_fd, self.expected
        )
        d.verify()
        return d
