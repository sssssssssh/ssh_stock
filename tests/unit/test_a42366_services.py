"""Production receiver contracts and actual nonprivileged Unix/SQLite processes."""

import os
import socket
from types import SimpleNamespace

import pytest

from scripts.a42361_contract import Fault as SchemaFault
from scripts.a42363_contract import Fault
from scripts.a42365_budget import BudgetService
from scripts.a42365_journal import DurableJournal
from scripts.a42366_services import ConsumerEndpoint, RuntimeDomainServer
from tests.unit.test_a42364_owner import identity
from tests.unit.test_a42366_publication import Journal


class L1Binding:
    """L1-only custody check; NOT InstalledPackage or a live authorization."""
    def __init__(self, scope, fd=None):
        self.scope, self.domain = scope, "consumer"
        self.source, self.budget = "a" * 64, "b" * 64
        self.peer_uid = os.getuid() if hasattr(os, "getuid") else 0
        self.fd = fd
        self.held = self._identity(fd) if fd is not None else None

    @staticmethod
    def _identity(fd):
        meta = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
        return tuple(getattr(meta, key) for key in fields)

    def revalidate(self):
        if self.fd is not None:
            assert self._identity(self.fd) == self.held


class L1Authority:
    def __init__(self, scope, journal):
        self.scope, self.journal = scope, journal

    def require(self, kind):
        return None  # L1 only; no ExecutionAuthority or physical capability is issued.

    def claim(self):
        return self.journal.append(self.scope, "L1_CLAIM", dict(qualifies=False))


def server(scope, journal, binding=None):
    auth = L1Authority(scope, journal)
    budget = BudgetService(identity(), auth, journal, "L1_BOOT")
    return RuntimeDomainServer(binding or L1Binding(scope), journal,
                               ConsumerEndpoint(scope, auth, budget, journal))


@pytest.mark.parametrize("body", [{"uid": 0}, {"path": "/tmp/x"}, {"dsn": "x"},
                                  {"command": "true"}, {"approved": True}])
def test_AT07_AT09_closed_production_request_rejects_capability_injection(body):
    s = identity().scope
    journal = Journal("consumer")
    with pytest.raises(SchemaFault, match="SCHEMA_INVALID"):
        server(s, journal).dispatch("consume", body)
    assert not journal.values


def test_AT08_AT10_restart_does_not_consume_or_reset_budget_twice():
    s, journal = identity().scope, Journal("consumer")
    original = server(s, journal).dispatch("consume", {})
    assert original["event"] == "CONSUMED"
    with pytest.raises(Fault, match="DOMAIN_ACK_UNKNOWN_NO_REPLAY"):
        server(s, journal).dispatch("consume", {})
    assert len([e for e in journal.values if e == "L1_CLAIM"]) == 1
    assert journal.read(s, "BUDGET_STARTED")


def test_AT07_AT10_actual_multi_process_unix_sqlite_receiver(tmp_path):
    # Required Linux source L1 node. Windows does not supply fork/SO_PEERCRED;
    # it is reported as unexecuted locally, never hidden behind skip/xfail.
    from scripts.a42365_ipc import DomainClient

    tmp_path.chmod(0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    scope = identity().scope
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    pid = None
    try:
        DurableJournal(fd, "consumer")
        pid = os.fork()
        if pid == 0:
            parent.close()
            try:
                own = DurableJournal(fd, "consumer")
                server(scope, own, L1Binding(scope, fd)).serve(child)
                os._exit(0)
            except BaseException:
                os._exit(1)
        child.close()
        client = DomainClient(parent.fileno(), os.getuid(), "consumer", scope, "a" * 64, "b" * 64)
        try:
            assert client.call("consume")["event"] == "CONSUMED"
            assert client.call("receipt", dict(event="BUDGET_STARTED"))["event"] == "BUDGET_STARTED"
        finally:
            client.close()
            parent.close()
        assert os.waitpid(pid, 0)[1] == 0
        pid = None
        reopened = DurableJournal(fd, "consumer")
        assert reopened.read(scope, "CONSUMED").committed
        with pytest.raises(Fault, match="DOMAIN_ACK_UNKNOWN_NO_REPLAY"):
            server(scope, reopened, L1Binding(scope, fd)).dispatch("consume", {})
    finally:
        if pid is not None:
            os.waitpid(pid, 0)
        parent.close()
        child.close()
        os.close(fd)


def test_AT09_peer_checked_before_frame_decode(monkeypatch):
    from scripts import a42366_services as module

    s = server(identity().scope, Journal("consumer"))
    monkeypatch.setattr(module, "peer_uid", lambda channel: s.binding.peer_uid + 1)
    monkeypatch.setattr(module, "read_frame", lambda *args: pytest.fail("decoded wrong peer"))
    with pytest.raises(Fault, match="RUNTIME_PEER_UID"):
        s.serve_once(SimpleNamespace())


@pytest.mark.parametrize("method", ["run", "terminate"])
def test_AT34_AT37_a_root_manager_shaped_object_is_not_a_kernel_installation(method):
    from scripts.a42365_supervisor import InstalledSupervisor

    i, j = identity(), Journal("supervisor")

    class FakeRoot:
        def dispatch(self, *args):
            pytest.fail("fake root launcher reached a side effect")

    supervisor = InstalledSupervisor(i.scope, L1Authority(i.scope, j), FakeRoot(), j)
    with pytest.raises(Fault, match="INSTALLED_KERNEL_LAUNCHER_REQUIRED"):
        getattr(supervisor, method)()
    assert not j.values
