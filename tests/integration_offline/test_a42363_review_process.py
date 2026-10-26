"""L1 full actual receiver/orchestrator chain. File SQL/runtime are DB_MODEL_ONLY.

Every receiver call forks and transfers an actual FD; kernels supply Linux peers.
No physical PG, Podman, UID installation, signatures or cgroup are asserted here.
"""

import os
import time
from types import SimpleNamespace as NS

import pytest

from scripts.a42361_contract import canonical, decode, sha
from scripts.a42361_offline_cases import payload
from scripts.a42362_contract import resources
from scripts.a42363_contract import Fault, receipt, scope_hash
from scripts.a42363_identity import FixtureIdentity, Installation
from scripts.a42363_review import Reviewer
from scripts.a42363_stores import ReceiptSet
from tests.integration_offline.test_a42363_complete_process import ipc
from tests.integration_offline.test_a42363_process import FileRuntime, FileStore, records
from tests.unit.test_a42363_contracts import scope


class ApprovedMethodStub:
    """Test injection ONLY; never imported by scripts or any live entry point."""

    def __call__(self):
        return None


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "signature",
        "wrong_peer",
        "consumer_ack",
        "reservation_ack",
        "owner_acl",
        "owner_connection",
        "root_ack",
        "root_scope",
        "missing_e",
        "store",
        "permission",
        "artifact",
        "forged_source",
        "replay",
        "create_SOCKET_DIR",
        "create_VOLUME",
        "create_SECRET",
        "create_CONTAINER",
        "remove_SOCKET_DIR",
        "remove_VOLUME",
        "remove_SECRET",
        "remove_CONTAINER",
        "aba",
    ],
)
def test_RF_AT29_AT30_AT33_AT35_AT53_AT56_full_orchestrator_hosts(tmp_path, monkeypatch, fault):
    from scripts import a42361_one_shot_store as bmod
    from scripts import a42361_source_guard as binding_module
    from scripts import a42362_service_host as policy_module
    from scripts import a42363_contract as contract
    from scripts import a42363_resources as cmod
    from scripts import a42363_services as hosts
    from scripts import a42363_supervisor as dmod
    from scripts.a42363_absence import AbsenceService, IndependentObserver
    from scripts.a42363_owner import OwnerRuntime, RawOwnerBackend

    authorized = payload()
    s = scope().model_copy(update={"payload_sha256": sha(canonical(authorized.model_dump()))})
    i = FixtureIdentity.derive(s, Installation(worker_uid=1010, socket_gid=1011))
    seed = records(s)
    a = dict(seed["approval"].record, expires_at=int(time.time()) + 120)
    stores = {d: FileStore(tmp_path / d, d) for d in set(hosts.METHODS) - {"registry"}}
    stores["approval"].append(s, "APPROVED", a)
    uid = os.getuid()
    deployment = NS(
        schema_version="a42363.deployment.v2", **{d: NS(peer_uid=uid) for d in hosts.METHODS}
    )
    consume_file = tmp_path / "consumption.json"
    ledger_file, connects = tmp_path / "ledger.json", tmp_path / "connections"

    class Consumer:
        def __init__(self, *_):
            pass

        def consume_once(self, grant):
            assert grant.binding == s.binding and grant.payload_sha256 == s.payload_sha256
            # Exclusive atomic model transaction: full payload AND receipt in one file.
            with consume_file.open("xb") as stream:
                stream.write(
                    canonical(
                        dict(
                            payload=authorized.model_dump(),
                            scope=s.model_dump(),
                            receipt=seed["consumer"].record,
                        )
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            if fault == "consumer_ack":
                raise Fault("A42363_CONSUMER_ACK_UNKNOWN")
            return NS(receipt_sha256=sha(canonical(seed["consumer"].record)))

        def read_receipt(self, token, digest):
            value = decode(consume_file.read_bytes())  # independent open, not cached writer.
            assert token == s.token_id and digest == sha(canonical(value["payload"]))
            assert value["scope"] == s.model_dump()
            return value["receipt"]

    class Connection:
        def __init__(self, role):
            self.role, self.pending = role, None
            with connects.open("ab") as stream:
                stream.write((role + "\n").encode())

        def execute(self, sql, args):
            rows = decode(ledger_file.read_bytes()) if ledger_file.exists() else []
            if "FOR UPDATE" in sql:
                assert self.role == "consumer"
                row = (
                    s.payload_sha256,
                    s.binding.fixture_uuid,
                    s.binding.nonce,
                    s.binding.identity.head_sha,
                    s.binding.identity.run_id,
                    s.binding.identity.attempt,
                )
            elif "ORDER BY sequence DESC" in sql:
                old = [r for r in rows if r[0]["resource"]["kind"] == args[1]]
                row = (old[-1][0],) if old else None
            elif sql.startswith("INSERT"):
                assert self.role == "consumer"
                body = decode(args[5].encode())
                assert not any(r[0]["event_id"] == body["event_id"] for r in rows)
                self.pending = [body, len(rows) + 1, "DB_MODEL_ONLY"]
                row = (self.pending[1], self.pending[2])
            elif "WHERE event_id=" in sql:
                found = [r for r in rows if r[0]["event_id"] == args[0]]
                row = found[0] if found else None
            else:
                assert "ORDER BY sequence LIMIT 25" in sql and self.role == "receipt_reader"
                return NS(fetchall=lambda: rows)
            return NS(fetchone=lambda: row)

        def commit(self):
            if self.pending:
                rows = decode(ledger_file.read_bytes()) if ledger_file.exists() else []
                rows.append(self.pending)
                with ledger_file.open("wb") as stream:
                    stream.write(canonical(rows))
                    stream.flush()
                    os.fsync(stream.fileno())
                if fault == "reservation_ack" and self.pending[0]["event"] == "RESERVED":
                    raise Fault("A42363_FILE_COMMIT_ACK_UNKNOWN")

        def rollback(self):
            self.pending = None

        def close(self):
            pass

    class Repo:
        instance_sha256 = "b" * 64

        def __init__(self, *_):
            pass

        def verify_scope(self, value):
            assert value == s
            Consumer().read_receipt(s.token_id, s.payload_sha256)

        def read(self, sql, args):
            assert "approval_records" in sql
            return a, 1 if "a.registry_epoch" in sql else False

        def connect(self, role):
            self.verify_scope(s)
            return Connection(role)

        def verify(self, c, role):
            assert c.role == role and role in ("consumer", "receipt_reader")

    monkeypatch.setattr(bmod, "PostgresConsumer", Consumer)

    def signature(*_):
        if fault == "signature":
            raise Fault("A42363_SIGNATURE_REJECTED")
        return NS(binding=s.binding, payload_sha256=s.payload_sha256)

    monkeypatch.setattr(bmod, "TrustVerifier", lambda *_: NS(verify_signature=signature))
    monkeypatch.setattr(binding_module, "independent_binding", lambda *_: s.binding)
    monkeypatch.setattr(bmod, "installed", lambda _: deployment)
    monkeypatch.setattr(policy_module, "ControlRepository", Repo)
    stub = ApprovedMethodStub()
    for module in (contract, cmod, dmod):
        monkeypatch.setattr(module, "session_method", stub)

    class Runtime(FileRuntime):
        identity = i
        commands = NS(count=12)

        def create(self, item):
            # Source ledger must have committed CREATE_ATTEMPTED before this effect.
            rows = decode(ledger_file.read_bytes())
            assert rows[-1][0]["event"] == "CREATE_ATTEMPTED"
            raw = super().create(item)
            raw.update(ID="a" * 64, CreatedAt="DB_MODEL_ONLY")
            (self.path / item.kind).write_bytes(canonical(raw))
            if fault == "create_" + item.kind:
                raise Fault("A42363_MODEL_CREATE_ACK_UNKNOWN")
            return raw

        def remove(self, item, raw):
            super().remove(item, raw)
            if fault == "remove_" + item.kind:
                raise Fault("A42363_MODEL_REMOVE_ACK_UNKNOWN")

    runtime = Runtime(tmp_path / "runtime")

    class LedgerClient:
        def append(self, body):
            return call("consumer", "resource-append", body)

        def scan(self, body):
            return call("consumer", "resource-scan", body)

    ledger = LedgerClient()
    controller = cmod.ControllerService(ledger, runtime, stores["controller"], Repo().verify_scope)
    owner_runtime = OwnerRuntime(runtime, None, "DB_MODEL_ONLY", "b" * 64, identity=i)
    # This fixture is PREEXISTING FILE data, not a newly bootstrapped PG instance.
    # Stub supplies exactly the historic injected 8-SQL model route, not 9>8 permission.
    owner_runtime.initialization_plan = lambda _: None
    row = [170001, "FILE_NOT_POSTGRES", *([False] * 6), [], *([False] * 4)]
    if fault == "owner_acl":
        row[2] = True
    statements = tmp_path / "owner-statements"

    def execute(sql):
        assert "a42363_fixture" not in sql
        assert "a42363_probe LOGIN" not in sql and "a42363_probe SET" not in sql
        with statements.open("ab") as stream:
            stream.write((sql + "\n").encode())
        return NS(fetchone=lambda: row)

    owner = RawOwnerBackend(
        lambda _: NS(
            info=NS(
                dbname="WRONG" if fault == "owner_connection" else i.database,
                user=i.owner_role,
                host=i.socket_host,
                port=5432,
                server_version=170001,
            ),
            execute=execute,
            commit=lambda: None,
            close=lambda: None,
        ),
        owner_runtime,
        stores["pg_owner"],
    )

    class ManagerModel:
        def call(self, method, value):
            assert value == s
            if method == "run":
                if fault == "root_ack":
                    raise Fault("A42363_ROOT_ACK_UNKNOWN")
                return dict(status="RUNNING", scope_sha256=scope_hash(s))
            return dict(
                manager_uid=0,
                execution_scope_terminated=fault != "root_scope",
                scope_sha256=scope_hash(s),
                epoch=s.epoch,
                cgroup_inode=1,
                proof_kind="DB_MODEL_ONLY_NOT_CGROUP",
            )

    delegated = dmod.DelegatedExecution(ManagerModel(), s)
    artifact_path = tmp_path / "artifacts"
    artifact_path.mkdir(mode=0o700)

    def publish(value):
        if fault == "artifact":
            raise Fault("A42363_ARTIFACT_ACK_UNKNOWN")
        fd = os.open(artifact_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            return dmod.ArtifactPublisher(fd).publish(value)
        finally:
            os.close(fd)

    supervisor = dmod.SupervisorService(
        delegated, None, delegated, stores["supervisor"], NS(publish=publish)
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
    if fault == "store":
        visibility["store_sha256"] = "f" * 64
    collector = NS(
        visibility=lambda _: visibility,
        read_exact=lambda item: dict(
            status="UNKNOWN"
            if fault == "permission"
            else "ABSENT"
            if runtime.absent(item)
            else "PRESENT",
            code=125 if fault == "permission" else 1 if runtime.absent(item) else 0,
            identity=None if runtime.absent(item) else "FILE_MODEL",
        ),
    )
    observer = IndependentObserver(1007, s.controller_uid, delegation, collector)
    auditor = AbsenceService(observer, stores["absence_auditor"], stores["controller"], ledger)
    calls = []

    def call(domain, method, body):
        calls.append((domain, method))

        def dispatch(peer):
            p = NS(uid=uid, domain=domain, read_uids=(uid,), operator_uid=uid)
            hosts.installation = lambda _: p
            policy_module.installation = lambda _: p
            hosts.installed = lambda _: deployment
            backends = dict(
                repository=Repo(),
                owner=owner,
                controller=controller,
                supervisor=supervisor,
                absence_auditor=auditor,
            )
            if fault == "missing_e" and domain == "absence_auditor":
                raise Fault("A42363_E_UNAVAILABLE")
            if fault == "aba" and domain == "controller" and method == "reconcile":
                (runtime.path / "SECRET").write_bytes(canonical(dict(id="FOREIGN", epoch=s.epoch)))
            result = hosts.ServiceHost(NS(deployment=deployment), backends).dispatch(
                peer + (999 if fault == "wrong_peer" else 0), method, body
            )
            if fault == "forged_source" and domain == "pg_owner" and method == "receipt":
                result = receipt("pg_owner", s, "FORGED", 99, result["record"]).model_dump()
            return result

        result = ipc(dispatch, tmp_path)
        if result["error"]:
            raise Fault(
                result["error"]
                if result["error"].startswith("A423")
                else "A42363_MODEL_" + result["error"].upper()
            )
        return result["result"]

    class Source:
        def __init__(self, domain):
            self.domain = domain

        def read(self, value, event):
            assert value == s
            # Independent process reads the durable original, never supplied reference.
            r = ipc(lambda _: stores[self.domain].read(s, event).model_dump(), tmp_path)
            if r["error"]:
                raise Fault("A42363_INDEPENDENT_SOURCE_UNAVAILABLE")
            from scripts.a42363_contract import Receipt

            return Receipt.model_validate(r["result"])

    # B's independent source uses its immutable payload transaction, like its RPC reader.
    stores["consumer"].read = lambda value, event: receipt(
        "consumer", value, event, 1, Consumer().read_receipt(value.token_id, value.payload_sha256)
    )
    clients = {d: NS(call=lambda method, body, d=d: call(d, method, body)) for d in hosts.METHODS}
    reviewer = Reviewer(ReceiptSet({d: Source(d) for d in stores}))
    orchestrator = hosts.Orchestrator(clients, reviewer)
    request = dict(
        envelope_hex="00", payload_sha256=s.payload_sha256, binding=s.binding.model_dump()
    )
    if fault in ("signature", "wrong_peer", "consumer_ack", "forged_source"):
        with pytest.raises(Fault):
            orchestrator.execute(s, request, a["approval_id"])
    else:
        result = orchestrator.execute(s, request, a["approval_id"])
        if fault in (None, "replay"):
            assert result["status"] == "OFFLINE_CROSS_DOMAIN_VERIFIED", result
            assert result["qualifies"] is False and result["real_probe_sql_executed"] == 0
            assert (artifact_path / "evidence.json").exists()
            ledger_rows = decode(ledger_file.read_bytes())
            assert len(ledger_rows) == 20
            for item in resources(s):
                assert [
                    r[0]["event"] for r in ledger_rows if r[0]["resource"]["kind"] == item.kind
                ] == [
                    "RESERVED",
                    "CREATE_ATTEMPTED",
                    "OBSERVED_CREATED",
                    "REMOVE_ATTEMPTED",
                    "OBSERVED_ABSENT",
                ]
            assert connects.read_text().count("receipt_reader") > 24
            if fault == "replay":
                before = consume_file.read_bytes(), ledger_file.read_bytes()
                with pytest.raises(Fault):
                    orchestrator.execute(s, request, a["approval_id"])
                assert before == (consume_file.read_bytes(), ledger_file.read_bytes())
        else:
            assert result["status"] == "INCOMPLETE_QUARANTINED"
            assert result["first_error"] and result["qualifies"] is False
    if fault in ("signature", "wrong_peer"):
        assert not consume_file.exists() and not ledger_file.exists()
    if fault == "consumer_ack":
        assert consume_file.exists() and not ledger_file.exists()
    if fault == "artifact":
        assert stores["supervisor"].maybe_read(s, "TERMINATED") is None
        with pytest.raises(Fault, match="PUBLICATION_ACK_UNKNOWN_NO_RETRY"):
            call("supervisor", "terminate", dict(scope=s.model_dump()))
    assert not any(d == "registry" for d, _ in calls)


def test_RF_AT25_ApprovedMethodStub_is_not_a_real_entry_switch(monkeypatch):
    from scripts.a42363_services import METHODS, Orchestrator

    monkeypatch.setenv("A42363_APPROVED_METHOD", "ApprovedMethodStub")
    calls = []
    clients = {d: NS(call=lambda *_, d=d: calls.append(d)) for d in METHODS}
    with pytest.raises(Fault, match="METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION"):
        Orchestrator(clients, None).execute(scope(), {}, "fake")
    assert not calls
