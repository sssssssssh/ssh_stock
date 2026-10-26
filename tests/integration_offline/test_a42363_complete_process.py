"""Real fork/AF_UNIX/SCM_RIGHTS, actual receivers, file DB/runtime models only.

All UIDs are the test process UID. Deployment/PG/Podman/cgroup are NOT_RUN. Crypto
factories are file-model dependencies here; inherited real Ed25519 tests remain intact.
"""

import array
import os
import socket
import struct
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import canonical, decode, sha
from scripts.a42361_offline_cases import payload
from scripts.a42363_contract import Fault, receipt, scope_hash
from scripts.a42363_review import Reviewer
from scripts.a42363_stores import ReceiptSet
from tests.integration_offline.test_a42363_process import (
    FileLedger,
    FileRuntime,
    FileStore,
    records,
)
from tests.unit.test_a42363_contracts import scope


def ipc(operation, tmp_path):
    """Kernel peer on Linux and actual FD transfer; never trusts payload-supplied UID."""
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    marker = tmp_path / "L1-fd"
    marker.touch(exist_ok=True)
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    pid = os.fork()
    if pid == 0:
        a.close()
        try:
            if sys.platform == "linux":
                _, peer, _ = struct.unpack(
                    "3i", b.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
            else:
                peer = os.getuid()  # Explicit portable model, Linux peer branch runs in CI.
            try:
                result, error = operation(peer), None
            except BaseException as e:
                result, error = None, getattr(e, "code", type(e).__name__)
            raw = canonical(dict(result=result, error=error, level="L1_DB_MODEL_ONLY"))
            b.sendmsg(
                [struct.pack("!I", len(raw))],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))],
            )
            b.sendall(raw)
            os._exit(0)
        except BaseException:
            os._exit(1)
    b.close()
    os.close(fd)
    a.settimeout(3)
    received = []
    try:
        prefix, ancillary, flags, _ = a.recvmsg(4, socket.CMSG_SPACE(4))
        assert flags == 0 and len(prefix) == 4
        for level, kind, raw in ancillary:
            assert (level, kind) == (socket.SOL_SOCKET, socket.SCM_RIGHTS)
            fds = array.array("i")
            fds.frombytes(raw)
            received.extend(fds)
        assert len(received) == 1 and os.fstat(received[0]).st_ino == marker.stat().st_ino
        size = struct.unpack("!I", prefix)[0]
        assert 0 < size <= 65536
        data = bytearray()
        while len(data) < size:
            chunk = a.recv(size - len(data))
            assert chunk
            data.extend(chunk)
        return decode(bytes(data))
    finally:
        a.close()
        for rfd in received:
            os.close(rfd)
        end = time.monotonic() + 2
        while True:
            observed, status = os.waitpid(pid, os.WNOHANG)
            if observed:
                assert status == 0
                break
            if time.monotonic() >= end:
                os.kill(pid, 9)  # Exact still-unreaped owned child, never request PID.
                os.waitpid(pid, 0)
                pytest.fail("L1 child incomplete")
            time.sleep(0.005)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "approval_ack",
        "consumer_ack",
        "owner_ack",
        "create_ack",
        "run_ack",
        "destroy_ack",
        "e_ack",
        "wrong_peer",
        "pg_not_ready",
        "missing_driver",
        "replaced_resource",
        "missing_e",
        "forged_source",
    ],
)
def test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review(tmp_path, monkeypatch, fault):
    from scripts import a42361_one_shot_store as bmod
    from scripts import a42361_source_guard as old_guard
    from scripts import a42361_trust_verifier as trust
    from scripts import a42362_service_host as policy_module
    from scripts import a42363_resources as cmod
    from scripts import a42363_services as hosts
    from scripts import a42363_supervisor as dmod
    from scripts.a42363_absence import AbsenceService, IndependentObserver
    from scripts.a42363_owner import RawOwnerBackend
    from scripts.a42363_resources import ControllerService

    authorized = payload()
    s = scope().model_copy(update={"payload_sha256": sha(canonical(authorized.model_dump()))})
    stores = {
        d: FileStore(tmp_path / d, d)
        for d in ("approval", "consumer", "pg_owner", "controller", "supervisor", "absence_auditor")
    }
    seed = records(s)
    uid = os.getuid()
    # One atomic file-model commit holds consumption AND its entire payload. The
    # independent receipt read checks that payload again, not a second side-file.
    base_store = stores["consumer"]

    class ConsumptionStore(FileStore):
        def append(self, s, event, record):
            value = receipt(self.domain, s, event, 1, record)
            data = dict(
                receipt=value.model_dump(),
                authorized_scope=s.model_dump(),
                authorized_payload=authorized.model_dump(),
            )
            with (self.path / (event + ".json")).open("xb") as stream:
                stream.write(canonical(data))
                stream.flush()
                os.fsync(stream.fileno())
            return self.read(s, event)

        def read(self, s, event):
            from scripts.a42363_contract import verify_receipt

            value = decode((self.path / (event + ".json")).read_bytes())
            assert value["authorized_scope"] == s.model_dump()
            assert sha(canonical(value["authorized_payload"])) == s.payload_sha256
            return verify_receipt(value["receipt"], self.domain, s, event)

    stores["consumer"] = ConsumptionStore(base_store.path, "consumer")
    committed_file = base_store.path / "CONSUMED.json"
    deployment = NS(
        schema_version="a42363.deployment.v2", **{d: NS(peer_uid=uid) for d in hosts.METHODS}
    )

    class Repo:
        def verify_scope(self, value):
            assert value == s
            stores["consumer"].read(s, "CONSUMED")

        def read(self, sql, args):
            assert "approval_records" in sql
            return seed["approval"].record, False if "EXISTS" in sql else 1

    class Consumer:
        def __init__(self, *_):
            pass

        def consume_once(self, grant):
            assert grant.payload_sha256 == s.payload_sha256
            assert grant.binding == s.binding
            assert stores["consumer"].maybe_read(s, "CONSUMED") is None
            stores["consumer"].append(s, "CONSUMED", seed["consumer"].record)
            if fault == "consumer_ack":
                raise Fault("A42363_CONSUMER_ACK_UNKNOWN")
            return NS(receipt_sha256=sha(canonical(seed["consumer"].record)))

        def read_receipt(self, token, payload):
            assert token == s.token_id and payload == s.payload_sha256
            return stores["consumer"].read(s, "CONSUMED").record

    monkeypatch.setattr(bmod, "PostgresConsumer", Consumer)
    monkeypatch.setattr(
        trust,
        "TrustVerifier",
        lambda *_: NS(
            verify_signature=lambda *_: NS(payload_sha256=s.payload_sha256, binding=s.binding)
        ),
    )
    monkeypatch.setattr(bmod, "TrustVerifier", trust.TrustVerifier)
    monkeypatch.setattr(old_guard, "independent_binding", lambda *_: s.binding)
    monkeypatch.setattr(bmod, "installed", lambda _: deployment)
    # Only file model resource/supervisor classes can pass these test-local gates.
    monkeypatch.setattr(cmod, "session_method", lambda: None)
    monkeypatch.setattr(dmod, "session_method", lambda: None)
    ledger, runtime = (
        FileLedger(tmp_path / "ledger.json"),
        FileRuntime(tmp_path / "runtime", "create_ack" if fault == "create_ack" else None),
    )
    controller = ControllerService(ledger, runtime, stores["controller"], Repo().verify_scope)
    raw = seed["pg_owner"].record["raw"]
    row = [170001, "L1_NOT_PG17", *([False] * 6), [], *([False] * 4)]
    owner_runtime = NS(
        verify_owner_connection=lambda *_: None,
        inspect_owner=lambda _: {
            k: raw[k]
            for k in raw
            if k
            in {
                "image_digest",
                "namespace_sha256",
                "marker_sha256",
                "fixture_uuid",
                "nonce",
                "container_id",
                "volume_id",
                "initialization_commands",
            }
        },
    )
    owner = RawOwnerBackend(
        lambda _: NS(
            execute=lambda _: NS(fetchone=lambda: row), commit=lambda: None, close=lambda: None
        ),
        owner_runtime,
        stores["pg_owner"],
    )

    class ManagerModel:
        def call(self, method, value):
            assert value == s
            if method == "run":
                if (tmp_path / "RUN_ATTEMPTED").exists():
                    raise Fault("A42363_NO_SECOND_WORKER")
                (tmp_path / "RUN_ATTEMPTED").write_bytes(b"L1_ONLY")
                if fault == "run_ack":
                    raise Fault("A42363_ROOT_ACK_UNKNOWN")
                return dict(status="RUNNING", scope_sha256=scope_hash(s))
            return dict(
                manager_uid=0,
                execution_scope_terminated=True,
                scope_sha256=scope_hash(s),
                epoch=s.epoch,
                cgroup_inode=1,
                proof_kind="L1_PRIVATE_FILE_NOT_CGROUP",
            )

    delegated = dmod.DelegatedExecution(ManagerModel(), s)
    supervisor = dmod.SupervisorService(
        delegated, None, delegated, stores["supervisor"], NS(publish=lambda _: None)
    )
    delegation = dict(store_sha256="a" * 64, collector_sha256="b" * 64)
    visibility = dict(
        **delegation,
        observer_uid=1007,
        controller_uid=s.controller_uid,
        namespace_sha256=s.namespace_sha256,
        epoch=s.epoch,
        readonly=True,
    )
    collector = NS(
        visibility=lambda _: visibility,
        read_exact=lambda item: dict(
            status="ABSENT" if runtime.absent(item) else "PRESENT",
            code=1 if runtime.absent(item) else 0,
            identity=None if runtime.absent(item) else "L1_FILE",
        ),
    )
    observer = IndependentObserver(1007, s.controller_uid, delegation, collector)
    auditor = AbsenceService(observer, stores["absence_auditor"], stores["controller"], ledger)

    def call(domain, method, body):
        def dispatch(peer):
            policy = NS(deployment=deployment)
            p = NS(uid=uid, domain=domain, read_uids=(uid,), operator_uid=uid)
            hosts.installation = lambda _: p
            policy_module.installation = lambda _: p
            hosts.installed = lambda _: deployment
            backends = {
                "repository": Repo(),
                "owner": owner,
                "controller": controller,
                "supervisor": supervisor,
                "absence_auditor": auditor,
            }
            host = hosts.ServiceHost(policy, backends)
            if fault == "wrong_peer":
                peer += 999
            return host.dispatch(peer, method, body)

        return ipc(dispatch, tmp_path)

    # Actual A approval receiver is exercised over its normal approval lookup before B.
    a = call("approval", "approval", dict(approval_id=seed["approval"].record["approval_id"]))
    if fault == "wrong_peer":
        assert a["error"] == "A42363_PEER_ACL" and not committed_file.exists()
        return
    assert a["error"] is None and a["result"]["status"] == "APPROVED"
    if fault == "approval_ack":
        assert not committed_file.exists()
        return  # Lost authorization reply cannot start B.
    consumed = call(
        "consumer",
        "consume",
        dict(envelope_hex="00", payload_sha256=s.payload_sha256, binding=s.binding.model_dump()),
    )
    assert stores["consumer"].read(s, "CONSUMED").record["committed"] is True
    if fault == "consumer_ack":
        assert consumed["error"] == "A42363_CONSUMER_ACK_UNKNOWN"
        assert (
            call(
                "consumer",
                "consume",
                dict(
                    envelope_hex="00",
                    payload_sha256=s.payload_sha256,
                    binding=s.binding.model_dump(),
                ),
            )["error"]
            is not None
        )
        assert not ledger.path.exists()
        return
    assert consumed["error"] is None
    body = dict(scope=s.model_dump())
    assert call("consumer", "committed-receipt", body)["error"] is None
    created = call("controller", "create", body)
    if fault == "create_ack":
        assert created["error"] and call("controller", "create", body)["error"]
        return
    assert created["error"] is None
    if fault in ("missing_driver", "pg_not_ready"):
        # Independently tested real OwnerRuntime preflight rejects these capabilities.
        from scripts.a42363_harness import PgFixtureRuntime
        from scripts.a42363_identity import FixtureIdentity, Installation

        h = PgFixtureRuntime(
            FixtureIdentity.derive(s, Installation(worker_uid=1010, socket_gid=1011)),
            None,
            None,
            None,
        )
        result = ipc(
            lambda _: h.prepare() if fault == "missing_driver" else h.readiness(), tmp_path
        )
        assert result["error"] and not (tmp_path / "RUN_ATTEMPTED").exists()
        return
    assert ipc(lambda _: owner.initialize(s), tmp_path)["error"] is None
    if fault == "owner_ack":
        assert stores["pg_owner"].read(s, "OWNER_RAW")
        assert not (tmp_path / "RUN_ATTEMPTED").exists()
        return
    run = call("supervisor", "run", body)
    if fault == "run_ack":
        assert run["error"] == "A42363_ROOT_ACK_UNKNOWN"
        assert call("supervisor", "run", body)["error"] == "A42363_NO_SECOND_WORKER"
        return
    assert run["error"] is None and call("supervisor", "terminate", body)["error"] is None
    if fault == "replaced_resource":
        (runtime.path / "SECRET").write_bytes(canonical(dict(id="FOREIGN", epoch=s.epoch)))
    destroyed = call("controller", "reconcile", body)
    assert destroyed["error"] is None
    if fault == "replaced_resource":
        assert destroyed["result"]["record"]["status"] == "INCOMPLETE_QUARANTINED"
        assert (runtime.path / "SECRET").exists()
        return
    if fault == "destroy_ack":
        repeated = call("controller", "reconcile", body)
        assert repeated == destroyed  # Durable receiver ACK recovery, no second removal.
    if fault != "missing_e":
        assert call("absence_auditor", "absent", body)["error"] is None
    if fault == "e_ack":
        assert call("absence_auditor", "receipt", body)["error"] is None
    event = dict(
        approval="APPROVED",
        consumer="CONSUMED",
        pg_owner="OWNER_RAW",
        controller="RECONCILED",
        supervisor="TERMINATED",
        absence_auditor="ABSENT",
    )
    # A was independently fetched, then committed to its separate L1 file journal.
    stores["approval"].append(s, "APPROVED", seed["approval"].record)
    references = {}
    for domain, name in event.items():
        if fault == "missing_e" and domain == "absence_auditor":
            continue
        result = ipc(
            lambda _, domain=domain, name=name: stores[domain].read(s, name).model_dump(), tmp_path
        )
        assert result["error"] is None
        references[domain] = result["result"]
    if fault == "forged_source":
        references["pg_owner"] = receipt(
            "pg_owner", s, "FORGED_PHASE", 99, references["pg_owner"]["record"]
        ).model_dump()
    if fault in ("missing_e", "forged_source"):
        with pytest.raises(Fault):
            Reviewer(ReceiptSet(stores)).review(s, references)
    else:
        result = Reviewer(ReceiptSet(stores)).review(s, references)
        assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED"
        assert result["qualifies"] is False and result["real_probe_sql_executed"] == 0
