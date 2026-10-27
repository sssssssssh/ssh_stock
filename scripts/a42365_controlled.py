"""Explicit L1 installation: private files/SQLite and one fixed FD-only child.

Never installed by serve_installed, never reachable from RPC or an environment flag.
This models fixture preparation and absence; it does not manufacture live capability.
"""

import array
import os
import socket
import uuid

from scripts.a42361_contract import canonical, decode, sha
from scripts.a42362_contract import resources
from scripts.a42363_contract import require
from scripts.a42363_supervisor import bounded_child
from scripts.a42365_journal import DurableJournal
from scripts.a42365_lifecycle import ResourceLifecycle

_SEAL = object()


class ControlledInstallation:
    def __init__(self, scope, directory_fd, seal):
        require(seal is _SEAL, "CONTROLLED_INSTALLATION_INTERNAL_ONLY")
        self.scope, self.fd = scope, directory_fd


def controlled_installation(scope, directory_fd):
    m = os.fstat(directory_fd)
    require(m.st_uid == os.getuid() and m.st_mode & 0o077 == 0, "CONTROLLED_PRIVATE_DIRECTORY")
    return ControlledInstallation(scope, directory_fd, _SEAL)


class ControlledAuthority:
    def require(self, kind):
        require(
            kind in ("BOOTSTRAP_AND_BUDGET", "SAFE_VOLUME_DISPOSAL", "TARGET_SESSION_GUC"),
            "CONTROLLED_GATE",
        )
        return dict(approved=False, source="CONTROLLED_L1_ONLY", qualifies=False)


class ControlledBroker:
    def verify_all_writers(self, scope):
        return dict(physical_all_writer_proof=False, qualifies=False)


class ControlledFileDriver:
    def __init__(self, fd):
        self.fd = fd

    def create(self, item):
        fd = os.open(
            item.kind, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
        )
        try:
            raw = canonical(
                dict(
                    kind=item.kind,
                    name=item.name,
                    nonce=str(uuid.uuid4()),
                    scope=item.scope.model_dump(),
                    qualifies=False,
                )
            )
            require(os.write(fd, raw) == len(raw), "CONTROLLED_SHORT_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        return self.inspect(item)

    def inspect(self, item):
        fd = os.open(item.kind, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            m = os.fstat(fd)
            return dict(raw=decode(os.pread(fd, 65537, 0)), inode=[m.st_dev, m.st_ino])
        finally:
            os.close(fd)

    def verify(self, item, raw):
        require(
            raw["raw"]["name"] == item.name and raw["raw"]["scope"] == item.scope.model_dump(),
            "CONTROLLED_FOREIGN_FILE",
        )
        return sha(canonical(raw))

    def start(self, item, original):
        require(item.kind == "CONTAINER" and self.inspect(item) == original, "CONTROLLED_REPLACED")

    def stop(self, item, original):
        self.start(item, original)

    def remove(self, item, original):
        require(self.inspect(item) == original, "CONTROLLED_REPLACED")
        os.unlink(item.kind, dir_fd=self.fd)
        os.fsync(self.fd)


class ControlledDomain:
    def __init__(self, domain, scope, journal, context):
        self.domain, self.scope, self.journal, self.context = domain, scope, journal, context

    def call(self, method, body=None):
        s, c = self.scope, self.context
        if self.domain == "consumer":
            require(method == "consume", "CONTROLLED_METHOD")
            return self.journal.append(s, "CONSUMED", dict(qualifies=False)).model_dump()
        if self.domain == "pg_owner":
            require(method == "create", "CONTROLLED_METHOD")
            return self.journal.append(
                s, "MODELED_OWNER", dict(g1_sql=0, qualifies=False)
            ).model_dump()
        if self.domain == "controller":
            lifecycle = ResourceLifecycle(s, self.journal, c["driver"])
            if method == "create":
                for item in resources(s):
                    lifecycle.perform(item, "CREATE")
                lifecycle.perform(resources(s)[3], "START")
                return dict(status="MODELED_PREPARED", qualifies=False)
            require(method == "reconcile", "CONTROLLED_METHOD")
            return self.journal.append(s, "RECONCILED", lifecycle.recover()).model_dump()
        if self.domain == "supervisor":
            if method == "run":
                sender, receiver = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                output = os.open(
                    "controlled-worker",
                    os.O_RDWR | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=c["files_fd"],
                )
                try:
                    # FD is queued before the bounded child is released. This L1
                    # child can only write a fixed string; no G1 worker runs here.
                    sender.sendmsg(
                        [b"F"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [output]))]
                    )
                    self.journal.append(s, "CONTROLLED_CHILD_ARMED", dict(qualifies=False))

                    def child():
                        from scripts.a42364_manager import receive_fds

                        (fd,) = receive_fds(receiver, 1)
                        try:
                            os.write(fd, b"CONTROLLED_L1_ONLY\n")
                            os.fsync(fd)
                        finally:
                            os.close(fd)

                    bounded_child(child)
                    require(
                        os.pread(output, 128, 0) == b"CONTROLLED_L1_ONLY\n", "CONTROLLED_CHILD_ACK"
                    )
                finally:
                    os.close(output)
                    sender.close()
                    receiver.close()
                return self.journal.append(
                    s, "CONTROLLED_CHILD_REAPED", dict(qualifies=False)
                ).model_dump()
            require(method == "terminate", "CONTROLLED_METHOD")
            self.journal.read(s, "CONTROLLED_CHILD_REAPED")
            return self.journal.append(
                s,
                "CONTROLLED_TERMINATED",
                dict(scope_terminated=False, physical="NOT_RUN", qualifies=False),
            ).model_dump()
        require(self.domain == "absence_auditor" and method == "absent", "CONTROLLED_METHOD")
        observations = []
        before = c["consumer"].read(s, "CONSUMED")
        recovered = c["controller"].read(s, "RECONCILED")
        require(
            recovered.record["status"] == "DESTROYED_PENDING_INDEPENDENT_E", "CONTROLLED_RECOVERY"
        )
        for round_no in (1, 2):
            require(
                c["consumer"].read(s, "CONSUMED") == before
                and c["controller"].read(s, "RECONCILED") == recovered,
                "CONTROLLED_FACT_DRIFT",
            )
            for item in resources(s):
                try:
                    os.stat(item.kind, dir_fd=c["files_fd"], follow_symlinks=False)
                except FileNotFoundError:
                    observations.append(dict(round=round_no, kind=item.kind, modeled_absent=True))
                else:
                    require(False, "ABSENCE_UNKNOWN")
        return self.journal.append(
            s,
            "MODELED_ABSENT",
            dict(observations=observations, physical_independence=False, qualifies=False),
        ).model_dump()


def assemble(installation):
    from scripts.a42365_runtime import RuntimeCoordinator

    require(type(installation) is ControlledInstallation, "CONTROLLED_INSTALLATION_INTERNAL_ONLY")
    scope, parent = installation.scope, installation.fd
    fds, journals = [], {}
    try:
        for name in (
            "root_manager",
            "consumer",
            "controller",
            "pg_owner",
            "supervisor",
            "absence_auditor",
            "files",
        ):
            os.mkdir(name, 0o700, dir_fd=parent)
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(fd)
            if name != "files":
                journals[name] = DurableJournal(fd, name)
        context = dict(journals, files_fd=fds[-1], driver=ControlledFileDriver(fds[-1]))
        clients = {
            name: ControlledDomain(name, scope, j, context)
            for name, j in journals.items()
            if name != "root_manager"
        }
        runtime = RuntimeCoordinator(
            scope,
            ControlledAuthority(),
            journals["root_manager"],
            clients["consumer"],
            clients["pg_owner"],
            clients["controller"],
            clients["supervisor"],
            clients["absence_auditor"],
            ControlledBroker(),
        )
        runtime.controlled_fds = fds
        return runtime
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
