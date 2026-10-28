"""FD-only domain construction boundary. Installation gaps are explicit refusals."""

import os
import socket
from dataclasses import replace
from typing import Literal

from scripts.a4235_calibration_adapter_contract import Hash
from scripts.a42361_contract import canonical, checked, decode, sha
from scripts.a42363_contract import require
from scripts.a42364_installation_verify import (
    PRINCIPALS,
    InstallDocument,
    installed_package,
    read_root_document,
)
from scripts.a42365_contract import GATES, HeldFile


class DomainBinding:
    def __init__(self, package, domain, authority, source, budget, namespace_fd):
        p = installed_package(package)
        require(domain in p.document.principals, "DOMAIN_INSTALLATION_PRINCIPAL")
        self.package, self.domain, self.authority = p, domain, authority
        self.scope, self.source, self.budget = p.document.scope, source.digest, budget
        self.archive, self.namespace_fd = source, namespace_fd
        self.namespace = os.fstat(namespace_fd)
        self.peer_uid = 0  # Only the inherited RootManager channel may mutate a domain.
        self.revalidate()

    def revalidate(self):
        p = self.package.revalidate()
        require(os.getuid() == p.document.principals[self.domain], "DOMAIN_INSTALLATION_UID")
        require(os.fstat(self.namespace_fd) == self.namespace, "DOMAIN_NAMESPACE_CHANGED")
        current = os.stat("/proc/self/ns/user")
        require((current.st_dev, current.st_ino) == (self.namespace.st_dev, self.namespace.st_ino),
                "DOMAIN_NAMESPACE_CHANGED")
        self.archive.revalidate()
        for kind in GATES[:3]:
            self.authority.require(kind)


class DomainInstallDocument(InstallDocument):
    version: Literal["a42366.installation.v5"]
    service_domain: Literal["root_manager", "consumer", "pg_owner", "controller",
                            "supervisor", "absence_auditor", "reviewer", "writer_broker"]
    companion_sha256: Hash


def validate_domain_document(raw, now):
    from scripts.a42364_installation_verify import validate_document

    d = checked(DomainInstallDocument, raw)
    require(set(d.principals) == set(PRINCIPALS) | {"reviewer", "writer_broker"}
            and len(set(d.principals.values())) == len(PRINCIPALS) + 2,
            "INSTALL_DISTINCT_UIDS")
    old = d.model_dump(exclude={"companion_sha256"})
    old.update(version="a42364.installation.v3", service_domain="root_manager",
               principals={k: d.principals[k] for k in PRINCIPALS})
    validate_document(old, now)  # Preserve every existing expiry/key/binary constraint.
    return d


def build_installed_domain(package):
    """Fixed FD factory; no dependency type, credentials, UID or path comes from RPC.

    B has an actual budget/claim endpoint. Missing native/kernel/RO/Reviewer
    capabilities in O/C/D/E remain explicit refusal endpoints, not READY models.
    """
    from scripts.a42363_identity import FixtureIdentity
    from scripts.a42364_protocol_decision import (
        DecisionVerifier,
        ExecutionAuthority,
        RegistryChannel,
    )
    from scripts.a42365_budget import BudgetService
    from scripts.a42365_ipc import METHODS, DomainClient, PeerJournal
    from scripts.a42365_journal import DurableJournal
    from scripts.a42365_protocol import proposal_hashes, runtime_budget_plan
    from scripts.a42366_services import (
        CapabilityBlockedEndpoint,
        ConsumerEndpoint,
        RuntimeDomainServer,
    )

    p = installed_package(package)
    require(type(p.document) is DomainInstallDocument, "DOMAIN_V5_DOCUMENT_REQUIRED")
    domain = p.document.service_domain
    require(domain in METHODS, "DOMAIN_V5_KERNEL_INSTALLATION_REQUIRED")
    archive = HeldFile.read(4, p.document.code_archive_sha256, owner=0, maximum=16000000)
    raw, _ = read_root_document(6, p.document.companion_sha256)
    d = decode(raw)
    require(type(d) is dict and set(d) == {
        "version", "installation_sha256", "source_archive_sha256", "scope_sha256",
        "budget_plan_sha256", "identity", "proposal_sha256",
    } and d["version"] == "a42366.domain-installation.v5", "RUNTIME_INSTALL_SCHEMA")
    from scripts.a42363_contract import scope_hash

    # Companion cannot hash the outer document (which pins the companion). Bind to
    # the outer document's stable source/image/scope triple instead, without a cycle.
    installation = sha(canonical(dict(
        source=p.document.code_archive_sha256, image=p.document.image_manifest_sha256,
        scope=scope_hash(p.document.scope),
    )))
    require(d["installation_sha256"] == installation
            and d["source_archive_sha256"] == p.document.code_archive_sha256
            and d["scope_sha256"] == scope_hash(p.document.scope), "RUNTIME_INSTALL_BINDING")
    i = checked(FixtureIdentity, d["identity"]).verify(p.document.scope)
    require(d["budget_plan_sha256"] == sha(canonical(runtime_budget_plan(i)))
            and d["proposal_sha256"] == proposal_hashes(i, installation),
            "RUNTIME_BUDGET_BINDING")
    # Detached signatures bind the outer installation digest. Keeping them in
    # the pinned companion would create a document/signature hash cycle.
    proof_raw = os.pread(9, 65537, 0)
    proof_raw, _ = read_root_document(9, sha(proof_raw))
    decisions = decode(proof_raw)
    require(type(decisions) is dict and set(decisions) == set(GATES),
            "FOUR_EXTERNAL_GATES_REQUIRED")
    registry_socket = socket.fromfd(7, socket.AF_UNIX, socket.SOCK_STREAM)
    p = replace(p, registry=RegistryChannel(registry_socket))
    client = None
    try:
        proofs = {kind: DecisionVerifier(p).verify(
            decisions[kind], scope=p.document.scope,
            proposal_sha256=d["proposal_sha256"][kind],
            image_manifest_sha256=p.document.image_manifest_sha256,
        ) for kind in GATES}
        require(os.getuid() == p.document.principals[domain], "DOMAIN_INSTALLATION_UID")
        j = DurableJournal(8, domain, owner=p.document.principals[domain])
        if domain == "consumer":
            consumption = j
        else:
            client = DomainClient(19, p.document.principals["consumer"], "consumer",
                                  p.document.scope, archive.digest, d["budget_plan_sha256"])
            consumption = PeerJournal(client)
        authority = ExecutionAuthority({k: proofs[k] for k in GATES[:3]},
                                       proofs[GATES[3]], p.document.scope, consumption)
        binding = DomainBinding(p, domain, authority, archive, d["budget_plan_sha256"], 18)
        if domain == "consumer":
            with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as boot:
                boot_id = boot.read(64).strip()
            endpoint = ConsumerEndpoint(p.document.scope, authority,
                                        BudgetService(i, authority, j, boot_id), j)
        else:
            blocker = dict(pg_owner="NATIVE_TRANSITIVE_CENSUS_UNPROVEN",
                           controller="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY",
                           supervisor="ROOT_V5_KERNEL_FDS_NOT_INSTALLED",
                           absence_auditor="AUDIT_RO_NAMESPACE_NOT_INSTALLED",
                           writer_broker="ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY")[domain]
            endpoint = CapabilityBlockedEndpoint(METHODS[domain], blocker)
        result = RuntimeDomainServer(binding, j, endpoint)
        result.installed_channels = [registry_socket, *([client] if client else [])]
        return result
    except BaseException:
        registry_socket.close()
        if client is not None:
            client.close()
        raise


def serve_installed_domain(package, listener_fd=5):
    p = installed_package(package)
    require(p.document.service_domain not in ("root_manager", "reviewer"),
            "DOMAIN_V5_KERNEL_INSTALLATION_REQUIRED")
    server = build_installed_domain(p)
    try:
        with socket.fromfd(listener_fd, socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            require(listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1,
                    "INSTALLED_LISTENER_REQUIRED")
            listener.settimeout(1)
            channel, _ = listener.accept()
        with channel:
            server.serve_once(channel)
    finally:
        for channel in server.installed_channels:
            channel.close()
