"""A4236 pure contracts. No fixture/network/database/role creation implementation."""

import re
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Identity, Safety, Strict, digest

BASELINE = "af08f8724e988121402988b4e8fb70c8ef5b53f2"
UUID = Annotated[
    str, Field(pattern=(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"))
]
Counter = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, gt=0)]


class Fault(RuntimeError):
    def __init__(self, code: str):
        self.code = code if re.fullmatch(r"A4236_[A-Z0-9_]{1,70}", code) else "A4236_INTERNAL"
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise Fault(code)


def checked(model, value):
    try:

        def inspect(item):
            if isinstance(item, Strict):
                require(
                    not (set(item.__dict__) - set(type(item).model_fields))
                    and not item.__pydantic_extra__,
                    "A4236_SCHEMA_INVALID",
                )
                for child in item.__dict__.values():
                    inspect(child)
            elif type(item) in (list, tuple):
                for child in item:
                    inspect(child)
            elif type(item) is dict:
                for child in item.values():
                    inspect(child)

        if isinstance(value, Strict):
            require(type(value) is model, "A4236_SCHEMA_INVALID")
            inspect(value)
            value = value.model_dump(warnings="error")
        return model.model_validate(value)
    except Exception:
        raise Fault("A4236_SCHEMA_INVALID") from None


class Context(Strict):
    identity: Identity
    overlay_sha256: Hash
    fixture_uuid: UUID
    nonce: UUID
    marker_sha256: Hash
    evidence_kind: Literal["MOCK_ONLY", "OFFLINE_DESIGN"] = "MOCK_ONLY"
    source_trust: Literal["UNTRUSTED_TEST_ONLY"] = "UNTRUSTED_TEST_ONLY"
    capability_scope: Literal["G1_SYNTHETIC_CAPABILITY_ONLY"] = "G1_SYNTHETIC_CAPABILITY_ONLY"


class Status(Safety):
    implementation_status: Literal["PARTIAL_OFFLINE_TESTED"] = "PARTIAL_OFFLINE_TESTED"
    g1_authorization_status: Literal["NOT_APPROVED"] = "NOT_APPROVED"
    g1_probe_status: Literal["G1_NOT_RUN_NOT_AUTHORIZED"] = "G1_NOT_RUN_NOT_AUTHORIZED"
    physical_identity_status: Literal["PHYSICAL_NOT_PROVEN"] = "PHYSICAL_NOT_PROVEN"
    prepared_capability: Literal["NOT_RUN", "DRIVER_MODEL_ONLY"] = "NOT_RUN"
    cpu_availability: Literal["METRIC_UNAVAILABLE"] = "METRIC_UNAVAILABLE"
    cached_plan_structure: Literal["CACHED_PLAN_STRUCTURE_NOT_VERIFIED"] = (
        "CACHED_PLAN_STRUCTURE_NOT_VERIFIED"
    )
    cleanup_status: Literal["NOT_APPLICABLE_NO_FIXTURE"] = "NOT_APPLICABLE_NO_FIXTURE"
    g2_protocol_decision: Literal["PENDING"] = "PENDING"
    g3_formal_calibration: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"
    effective_warmups_total: Literal[8] = 8
    real_sql_executed: Literal[0] = 0


class Budget(Strict):
    max_sql: Literal[16] = 16
    per_sql_ms: Literal[100] = 100
    sql_window_ms: Literal[2000] = 2000
    max_rows: Literal[8] = 8
    authorization_ms: Literal[1000] = 1000
    initialization_ms: Literal[2000] = 2000
    cleanup_ms: Literal[2000] = 2000
    artifact_ms: Literal[2000] = 2000
    termination_ms: Literal[2000] = 2000
    approved: Literal[False] = False


class Privileges(Strict):
    superuser: Literal[False] = False
    createdb: Literal[False] = False
    createrole: Literal[False] = False
    bypassrls: Literal[False] = False
    replication: Literal[False] = False
    maintain: Literal[False] = False
    ddl: Literal[False] = False
    dml: Literal[False] = False
    business_read: Literal[False] = False
    arbitrary_extension: Literal[False] = False
    pg_read_all_stats: Literal[False] = False
    inherited_roles: tuple[()] = ()
    read_only: Literal[True] = True


class Fixture(Strict):
    context: Context
    host: Literal["127.0.0.1", "::1", "UNIX"]
    socket_owner_sha256: Hash | None = None
    socket_directory_sha256: Hash | None = None
    database: str
    owner_sha256: Hash
    probe_role_sha256: Hash
    system_identifier_sha256: Hash
    container_sha256: Hash
    image_digest: Hash
    namespace_sha256: Hash
    privileges: Privileges = Privileges()
    pg_major: Literal[17] = 17
    fresh: Literal[True] = True
    shared_existing: Literal[False] = False
    public_ports: Literal[False] = False
    production_route: Literal[False] = False
    privileged: Literal[False] = False
    host_pid: Literal[False] = False
    host_proc_mount: Literal[False] = False
    sensitive_volumes: Literal[False] = False
    root: Literal[False] = False
    cpu_millicores: Literal[1000] = 1000
    rss_mib: Literal[512] = 512
    pids_limit: Literal[32] = 32
    limits_approved: Literal[False] = False


class Attestation(Strict):
    context: Context
    fixture_sha256: Hash
    domain: Literal["MOCK_PG", "MOCK_ORCHESTRATOR", "MOCK_ABSENCE_AUDITOR"]
    issuer_sha256: Hash
    proof_reference_sha256: Hash
    event: Literal["CREATED", "DESTROY_REQUESTED", "DESTROYED", "ABSENT"]
    observed_ns: Positive
    signature_status: Literal["MOCK_NOT_A_SIGNATURE"] = "MOCK_NOT_A_SIGNATURE"


def validate_fixture(value, expected):
    value, expected = checked(Fixture, value), checked(Fixture, expected)
    require(value == expected, "A4236_FIXTURE_IDENTITY_DRIFT")
    c = value.context
    require(
        c.nonce != c.fixture_uuid
        and value.database == "a4236_" + c.fixture_uuid.replace("-", "")
        and value.owner_sha256 != value.probe_role_sha256,
        "A4236_FIXTURE_OWNERSHIP_INVALID",
    )
    require(
        (
            value.host == "UNIX"
            and value.socket_owner_sha256 == value.owner_sha256
            and value.socket_directory_sha256 is not None
        )
        or (
            value.host != "UNIX"
            and value.socket_owner_sha256 is None
            and value.socket_directory_sha256 is None
        ),
        "A4236_SOCKET_OWNERSHIP_UNPROVEN",
    )
    return value


def validate_creation(fixture, pg, orchestration):
    fixture = validate_fixture(fixture, fixture)
    pg, orchestration = checked(Attestation, pg), checked(Attestation, orchestration)
    require(
        pg.domain == "MOCK_PG"
        and orchestration.domain == "MOCK_ORCHESTRATOR"
        and pg.issuer_sha256 != orchestration.issuer_sha256
        and all(
            a.context == fixture.context
            and a.fixture_sha256 == digest(fixture.model_dump())
            and a.event == "CREATED"
            for a in (pg, orchestration)
        ),
        "A4236_INDEPENDENT_ATTESTATION_MISSING",
    )
    return dict(physical_status="PHYSICAL_NOT_PROVEN", mock_chain_valid=True)


def validate_cleanup(fixture, receipts):
    require(len(receipts) == 3, "A4236_CLEANUP_NOT_VERIFIED")
    receipts = [checked(Attestation, r) for r in receipts]
    require(
        [r.event for r in receipts] == ["DESTROY_REQUESTED", "DESTROYED", "ABSENT"]
        and [r.domain for r in receipts]
        == ["MOCK_ORCHESTRATOR", "MOCK_ORCHESTRATOR", "MOCK_ABSENCE_AUDITOR"]
        and receipts[0].observed_ns < receipts[1].observed_ns < receipts[2].observed_ns
        and receipts[0].issuer_sha256 == receipts[1].issuer_sha256
        and receipts[2].issuer_sha256 != receipts[0].issuer_sha256
        and all(
            r.context == fixture.context and r.fixture_sha256 == digest(fixture.model_dump())
            for r in receipts
        ),
        "A4236_CLEANUP_NOT_VERIFIED",
    )
    return dict(mock_destroyed=True, physical_cleanup="NOT_APPLICABLE_NO_FIXTURE")


@dataclass
class FakeClock:
    ns: int = 1

    def advance_ms(self, value):
        require(type(value) is int and value >= 0, "A4236_CLOCK_INVALID")
        self.ns += value * 1_000_000


@dataclass
class FakeHarness:
    fixture: Fixture
    created: bool = False
    receipts: list = field(default_factory=list)

    def create(self, consumption):
        from scripts.a4236_grant_verifier import Consumption

        consumption = checked(Consumption, consumption)
        require(
            consumption.context == self.fixture.context and consumption.state == "CONSUMED",
            "A4236_CONSUMPTION_REQUIRED",
        )
        require(not self.created and not self.receipts, "A4236_FIXTURE_REUSE")
        validate_fixture(self.fixture, self.fixture)
        self.created = True
        for i, domain in enumerate(("MOCK_PG", "MOCK_ORCHESTRATOR"), 3):
            self.receipts.append(self.attest(domain, "CREATED", i))
        validate_creation(self.fixture, *self.receipts)
        return tuple(self.receipts)

    def attest(self, domain, event, time_ns):
        return Attestation(
            context=self.fixture.context,
            fixture_sha256=digest(self.fixture.model_dump()),
            domain=domain,
            issuer_sha256=digest(["mock-issuer", domain]),
            proof_reference_sha256=digest(["mock-proof", domain, event]),
            event=event,
            observed_ns=time_ns,
        )

    def destroy(self, expected, observed_ns=5):
        require(self.created, "A4236_FIXTURE_NOT_CREATED")
        validate_fixture(self.fixture, expected)
        result = [
            self.attest("MOCK_ORCHESTRATOR", "DESTROY_REQUESTED", observed_ns),
            self.attest("MOCK_ORCHESTRATOR", "DESTROYED", observed_ns + 1),
            self.attest("MOCK_ABSENCE_AUDITOR", "ABSENT", observed_ns + 2),
        ]
        validate_cleanup(self.fixture, result)
        self.created = False
        return result


class TrustedHarness:
    """No Docker/DB implementation or credentials; deployment is a separate human decision."""

    def create(self, *args, **kwargs):
        raise Fault("A4236_HARNESS_NOT_CONFIGURED")

    def destroy(self, *args, **kwargs):
        raise Fault("A4236_HARNESS_NOT_CONFIGURED")
