"""Static infrastructure and offline controller/process failure models. No child killed."""

import copy
import signal
import subprocess
from types import SimpleNamespace as NS

import pytest

from scripts import a42361_fixture_controller as f
from scripts import a42361_one_shot_store as s
from scripts import a42361_watchdog as w
from scripts.a42361_contract import Fault
from scripts.a42361_deployment import validate_deployment
from tests.unit.test_a42361_store import model_grant
from tests.unit.test_a42361_trust import deployment_data


def test_AT16_AT17_isolation_config_static():
    data = deployment_data()
    data["keys"][0]["public_key_hex"] = "11" * 32
    data["keys"][0]["usage"] = "PRODUCTION_G1"
    config = validate_deployment(data, 110)
    assert config.network == "none" and not config.public_ports and config.fixture_count == 1


@pytest.mark.parametrize(
    "field,bad",
    [
        ("image", "postgres:17"),
        ("image", "postgres:latest"),
        ("network", "host"),
        ("host_pid", True),
        ("host_proc", True),
        ("privileged", True),
        ("sensitive_mounts", True),
        ("fixture_count", 2),
        ("root_directory", "/tmp/a42361-anywhere"),
    ],
)
def test_AT16_AT17_AT18_forbidden_runtime_configuration(field, bad):
    data = deployment_data()
    data["keys"][0]["public_key_hex"] = "11" * 32
    data["keys"][0]["usage"] = "PRODUCTION_G1"
    data[field] = bad
    with pytest.raises(Fault):
        validate_deployment(data, 110)


def inspection_case(monkeypatch):
    grant = model_grant()
    consumption = NS(grant=grant)
    config = NS(controller_uid=1005)
    monkeypatch.setattr(f, "installed", lambda _: config)
    labels = dict(
        a42361_owner="1005",
        a42361_fixture=grant.payload.binding.fixture_uuid,
        a42361_nonce=grant.payload.binding.nonce,
        a42361_payload=grant.payload_sha256,
    )
    value = dict(
        Name="a42361-offline",
        Config=dict(Labels=labels, User="999:999"),
        HostConfig=dict(
            NetworkMode="none",
            Privileged=False,
            PidMode="",
            PortBindings={},
            ReadonlyRootfs=True,
            CapDrop=["ALL"],
            SecurityOpt=["no-new-privileges"],
            PidsLimit=32,
            Memory=512 * 1024**2,
            NanoCpus=1_000_000_000,
        ),
        ImageDigest=grant.payload.image_digest,
        Mounts=[dict(Name="a42361-offline-data", Destination="/var/lib/postgresql/data")],
    )
    return f.FixtureController(object()), consumption, value


@pytest.mark.parametrize(
    "field,bad",
    [
        ("NetworkMode", "bridge"),
        ("Privileged", True),
        ("PidMode", "host"),
        ("PortBindings", {"5432": 1}),
        ("ReadonlyRootfs", False),
        ("CapDrop", []),
        ("SecurityOpt", []),
        ("PidsLimit", 33),
        ("Memory", 0),
        ("NanoCpus", 2_000_000_000),
    ],
)
def test_AT17_AT18_inspection_rejects_escalation(monkeypatch, field, bad):
    controller, consumption, value = inspection_case(monkeypatch)
    value["HostConfig"][field] = bad
    with pytest.raises(Fault):
        controller._validate_inspection(value, consumption, "a42361-offline", "a42361-offline-data")


@pytest.mark.parametrize("change", ["owner", "nonce", "image", "user", "mount"])
def test_AT19_AT20_dual_identity_or_mount_drift(monkeypatch, change):
    controller, consumption, value = inspection_case(monkeypatch)
    if change in ("owner", "nonce"):
        value["Config"]["Labels"]["a42361_" + change] = "foreign"
    elif change == "image":
        value["ImageDigest"] = "sha256:" + "0" * 64
    elif change == "user":
        value["Config"]["User"] = "0:0"
    else:
        value["Mounts"].append(dict(Destination="/proc"))
    with pytest.raises(Fault):
        controller._validate_inspection(value, consumption, "a42361-offline", "a42361-offline-data")


def test_AT19_OCI_image_labels_do_not_waive_ownership(monkeypatch):
    controller, consumption, value = inspection_case(monkeypatch)
    value["Config"]["Labels"]["org.opencontainers.image.version"] = "offline"
    assert controller._validate_inspection(
        value, consumption, "a42361-offline", "a42361-offline-data"
    )


def test_AT22_default_denies_before_resource_or_command(monkeypatch):
    monkeypatch.setattr(f.os, "mkdir", lambda *a, **k: pytest.fail("mkdir"))
    monkeypatch.setattr(w.subprocess, "Popen", lambda *a, **k: pytest.fail("Popen"))
    for method in (
        f.FixtureController().create_owned_fixture,
        f.FixtureController().destroy_owned,
        w.Watchdog().terminate_owned,
    ):
        with pytest.raises(Fault, match="DEPLOYMENT_NOT_CONFIGURED"):
            method(None)


def test_AT12_reservation_must_be_committed_before_mkdir(monkeypatch):
    controller, consumption, _ = inspection_case(monkeypatch)
    monkeypatch.setattr(f, "committed", lambda x: x)
    monkeypatch.setattr(
        f,
        "installed",
        lambda _: NS(
            controller_uid=1005,
            root_directory="/run/a42361-offline",
            image="docker.io/library/postgres@" + consumption.grant.payload.image_digest,
        ),
    )
    monkeypatch.setattr(f.LocalService, "call", lambda *a: dict(committed=False))
    monkeypatch.setattr(f.os, "mkdir", lambda *a, **k: pytest.fail("unreserved resource"))
    with pytest.raises(Fault, match="RESERVATION_UNPROVEN"):
        controller.create_owned_fixture(consumption)


class ModelProcess:
    pid = 987654

    def __init__(self, hang=False):
        self.hang = hang
        self.calls = []
        self.code = None

    def poll(self):
        return self.code

    def wait(self, timeout):
        self.calls.append(timeout)
        if len(self.calls) == 1 or self.hang:
            raise subprocess.TimeoutExpired("OFFLINE", timeout)
        self.code = -9
        return -9


def watchdog_case(monkeypatch, hang=False):
    authorization = NS(grant=NS(payload_sha256="a" * 64))
    monkeypatch.setattr(w, "installed", lambda _: object())
    monkeypatch.setattr(s, "committed", lambda _: authorization)
    monkeypatch.setattr(w.os, "getpgid", lambda pid: pid)
    signals = []
    monkeypatch.setattr(w.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    process = ModelProcess(hang)
    child = w.OwnedProcess(process, process.pid, "a" * 64, w._OWNED)
    return w.Watchdog(object(), authorization), child, signals


def test_AT26_model_TERM_KILL_reap_not_physical_proof(monkeypatch):
    watchdog, child, signals = watchdog_case(monkeypatch)
    result = watchdog.terminate_owned(child)
    assert signals == [(child.pid, signal.SIGTERM), (child.pid, signal.SIGKILL)]
    assert result["reaped"] and result["actual_proof"] == "REQUIRES_INDEPENDENT_AUDIT"


def test_AT26_nonterminable_model_is_not_proven(monkeypatch):
    watchdog, child, _ = watchdog_case(monkeypatch, hang=True)
    with pytest.raises(Fault, match="TERMINATION_NOT_PROVEN"):
        watchdog.terminate_owned(child)


@pytest.mark.parametrize("change", ["seal", "scope", "pid", "group"])
def test_AT26_no_foreign_PID_or_scope_kill(monkeypatch, change):
    watchdog, child, signals = watchdog_case(monkeypatch)
    if change == "seal":
        child = copy.copy(child)
        object.__setattr__(child, "_seal", object())
    elif change == "scope":
        object.__setattr__(child, "scope_sha256", "b" * 64)
    elif change == "pid":
        object.__setattr__(child, "pid", 999999)
    else:
        monkeypatch.setattr(w.os, "getpgid", lambda pid: 999999)
    with pytest.raises(Fault, match="OWNERSHIP_UNPROVEN"):
        watchdog.terminate_owned(child)
    assert signals == []
