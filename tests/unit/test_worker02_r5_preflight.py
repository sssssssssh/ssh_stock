"""A Python pidfd symbol is not proof of kernel support or execution authority."""

import errno
from types import SimpleNamespace as NS

from scripts import worker02_r5_preflight as probe


def test_missing_kernel_or_tools_remain_blocked_without_installing(monkeypatch):
    def unsupported(*_):
        raise OSError(errno.ENOSYS, "PRIVATE")

    monkeypatch.setattr(probe.os, "pidfd_open", unsupported, raising=False)
    monkeypatch.setattr(probe.shutil, "which", lambda _: None)
    value = probe.preflight()
    assert value["status"] == "PLATFORM_BLOCKED"
    assert value["pidfd_error"] == "ENOSYS" and not value["checks"]["pidfd"]
    assert set(value["tools"].values()) == {"MISSING"}
    assert not value["database_contacted"] and not value["workload_started"]
    assert not value["performance_qualified"] and "PRIVATE" not in str(value)


def test_version_failure_is_not_available_or_auto_installed(monkeypatch):
    commands = []
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/synthetic/" + name)

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["timeout"] == 3 and kwargs["capture_output"]
        return NS(returncode=1)

    monkeypatch.setattr(probe.subprocess, "run", run)
    value = probe.preflight()
    assert value["status"] == "PLATFORM_BLOCKED"
    assert set(value["tools"].values()) == {"FAILED_VERSION_PROBE"}
    assert all(command[-1] == "--version" for command in commands)


def test_valid_pidfd_is_closed_and_does_not_qualify_performance(monkeypatch):
    closed = []
    monkeypatch.setattr(probe.os, "pidfd_open", lambda *_: 12345, raising=False)
    monkeypatch.setattr(probe.os, "close", closed.append)
    monkeypatch.setattr(probe.shutil, "which", lambda _: None)
    value = probe.preflight()
    assert value["checks"]["pidfd"] and closed == [12345]
    assert not value["performance_qualified"]


def test_peer_uid_probe_failure_remains_blocked_without_exporting_exception(monkeypatch):
    def unavailable(*_):
        raise OSError("PRIVATE_SOCKET_DETAIL")

    monkeypatch.setattr(probe.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.setattr(probe.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(probe.socket, "socketpair", unavailable)
    monkeypatch.setattr(probe.shutil, "which", lambda _: None)
    value = probe.preflight()
    assert not value["checks"]["peer_uid"] and value["status"] == "PLATFORM_BLOCKED"
    assert "PRIVATE" not in str(value)
