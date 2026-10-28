"""Fixed installed root factory. No request/environment/CLI dependency injection.

FD6 is a root-held companion descriptor, FD7 the independent Registry channel.
All other descriptor numbers are source constants, not fields a caller can choose.
An incomplete installation returns an explicit engineering status with no effects.
"""

import os
import socket

from scripts.a42361_contract import checked, decode, sha
from scripts.a42363_contract import require, scope_hash
from scripts.a42363_identity import FixtureIdentity
from scripts.a42364_installation_verify import installed_package, read_root_document
from scripts.a42364_protocol_decision import DecisionVerifier, ExecutionAuthority, RegistryChannel
from scripts.a42365_contract import GATES, NO_ACTIONS, HeldFile, nonqualifying
from scripts.a42365_ipc import DomainClient, PeerJournal
from scripts.a42365_journal import DurableJournal
from scripts.a42365_runtime import RuntimeCoordinator
from scripts.a42365_writer_broker import InstalledWriterBroker

PEER_FDS = dict(consumer=19, pg_owner=20, absence_auditor=21, controller=22, supervisor=23)


class BlockedRuntime:
    def __init__(self, scope, code):
        self.scope, self.code = scope, code

    def status(self):
        return nonqualifying(
            self.scope,
            "PARTIAL_ENGINEERING_BLOCKED",
            runtime_backend="BLOCKED",
            blocker=self.code,
            actions=dict(NO_ACTIONS),
            live_gate="DENY",
        )

    def dispatch(self, *args):
        require(False, self.code)


def build_installed_runtime(package):
    from scripts.a42365_controlled import ControlledInstallation, assemble

    if type(package) is ControlledInstallation:
        return assemble(package)  # never constructed by the installed/RPC entrypoint
    p = installed_package(package)
    if p.document.service_domain != "root_manager":
        # The previous factory tried to construct RootManager dependencies for E.
        # E must never receive O/C credentials or a writable runtime journal.
        return BlockedRuntime(p.document.scope, "DOMAIN_V5_FD_CUSTODY_NOT_INSTALLED")
    try:
        raw = os.pread(6, 65537, 0)
    except OSError:
        return BlockedRuntime(p.document.scope, "RUNTIME_COMPANION_FD_REQUIRED")
    raw, _ = read_root_document(6, sha(raw))
    d = decode(raw)
    require(
        type(d) is dict
        and set(d)
        == {
            "version",
            "installation_sha256",
            "scope_sha256",
            "source_archive_sha256",
            "budget_plan_sha256",
            "identity",
            "proposal_sha256",
            "decisions",
        }
        and d["version"] == "a42365.runtime-installation.v4",
        "RUNTIME_INSTALL_SCHEMA",
    )
    require(
        d["installation_sha256"] == p.digest
        and d["scope_sha256"] == scope_hash(p.document.scope)
        and d["source_archive_sha256"] == p.document.code_archive_sha256,
        "RUNTIME_INSTALL_BINDING",
    )
    archive = HeldFile.read(4, p.document.code_archive_sha256, owner=0, maximum=16000000)
    from dataclasses import replace

    registry = RegistryChannel(socket.fromfd(7, socket.AF_UNIX, socket.SOCK_STREAM))
    p = replace(p, registry=registry)
    require(
        set(d["decisions"]) == set(GATES) and set(d["proposal_sha256"]) == set(GATES),
        "FOUR_EXTERNAL_GATES_REQUIRED",
    )
    identity = checked(FixtureIdentity, d["identity"]).verify(p.document.scope)
    from scripts.a42361_contract import canonical
    from scripts.a42365_protocol import proposal_hashes, runtime_budget_plan

    require(
        d["proposal_sha256"] == proposal_hashes(identity, p.digest), "RUNTIME_PROPOSAL_DOWNGRADE"
    )
    require(
        d["budget_plan_sha256"] == sha(canonical(runtime_budget_plan(identity))),
        "RUNTIME_BUDGET_BINDING",
    )
    verifier = DecisionVerifier(p)
    proofs = {
        kind: verifier.verify(
            d["decisions"][kind],
            scope=p.document.scope,
            proposal_sha256=d["proposal_sha256"][kind],
            image_manifest_sha256=p.document.image_manifest_sha256,
        )
        for kind in GATES
    }
    require(
        proofs["BOOTSTRAP_AND_BUDGET"].payload.choice == "FRESH_DYNAMIC", "PREBUILT_NOT_IMPLEMENTED"
    )
    require(
        p.document.service_domain == "root_manager" and os.getuid() == 0,
        "RUNTIME_ROOT_FACTORY_REQUIRED",
    )
    journal = DurableJournal(8, "root_manager", owner=0)
    clients = {}
    try:
        for domain, fd in PEER_FDS.items():
            clients[domain] = DomainClient(
                fd,
                p.document.principals[domain],
                domain,
                p.document.scope,
                d["source_archive_sha256"],
                d["budget_plan_sha256"],
            )
        authority = ExecutionAuthority(
            {k: proofs[k] for k in GATES[:3]},
            proofs["G1_L2_EXECUTION"],
            p.document.scope,
            PeerJournal(clients["consumer"]),
        )
        # Broker has its own root-owned journal FD24; graph/run/ns FDs16/17/18.
        broker = InstalledWriterBroker(
            p.document.scope,
            authority,
            DurableJournal(24, "writer_broker", owner=0),
            16,
            17,
            18,
            None,
        )
        runtime = RuntimeCoordinator(
            p.document.scope,
            authority,
            journal,
            clients["consumer"],
            clients["pg_owner"],
            clients["controller"],
            clients["supervisor"],
            clients["absence_auditor"],
            broker,
        )
        archive.revalidate()
        return InstalledBackend(p, runtime, clients)
    except BaseException:
        for client in clients.values():
            client.close()
        raise


class InstalledBackend:
    def __init__(self, package, runtime, clients):
        self.package, self.runtime, self.clients = package, runtime, clients

    def status(self):
        return nonqualifying(
            self.runtime.scope,
            "PARTIAL_ENGINEERING_BLOCKED",
            runtime_backend="ASSEMBLED_COORDINATOR",
            live_gate="DENY",
            broker=self.runtime.broker.status(),
            remaining=[
                "native bootstrap child accounting enforcement binding",
                "independent domain service installation and FD provisioning",
                "RootManager/RO provisioner installed helper handoff",
            ],
        )

    def dispatch(self, uid, method, body):
        self.package.revalidate()
        require(
            uid == self.package.document.principals["supervisor"]
            and body == dict(scope=self.runtime.scope.model_dump()),
            "ROOT_MANAGER_PEER_OR_SCOPE",
        )
        require(method in ("run", "terminate", "receipt"), "INSTALLED_SERVICE_METHOD")
        if method == "receipt":
            return self.status()
        return self.runtime.run_scope() if method == "run" else self.runtime.stop()
