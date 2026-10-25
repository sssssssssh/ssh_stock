"""Bounded owner-only offline artifacts. No self-reported field can establish real trust."""

import hashlib
import os
import stat
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from scripts.a4235_calibration_adapter_contract import Hash, Strict, digest
from scripts.a4235_capability_review import decode, encode, open_directory
from scripts.a4236_g1_harness_contract import (
    Attestation,
    Context,
    Counter,
    Fault,
    Fixture,
    Positive,
    Status,
    checked,
    require,
    validate_cleanup,
    validate_creation,
    validate_fixture,
)
from scripts.a4236_g1_probe import ALLOWLIST_SHA, Request, request
from scripts.a4236_grant_verifier import Consumption

NAMES = (
    "grant-audit.json",
    "fixture.json",
    "probe-events.json",
    "capability-review.json",
    "failure.json",
    "cleanup.json",
)
ALL_NAMES = frozenset((*NAMES, "manifest.json"))
Code = Annotated[str, Field(pattern=r"^A4236_[A-Z0-9_]{1,70}$")]


class Audit(Strict):
    context: Context
    issuer_status: Literal["ISSUER_NOT_CONFIGURED"] = "ISSUER_NOT_CONFIGURED"
    consumer_status: Literal["PERSISTENT_CONSUMER_UNAVAILABLE"] = "PERSISTENT_CONSUMER_UNAVAILABLE"
    mock_consumption: Consumption | None = None
    real_signature_verified: Literal[False] = False


class FixtureEvidence(Strict):
    context: Context
    physical_created: Literal[False] = False
    spec: Fixture | None = None
    mock_creation: tuple[Attestation, ...] = ()
    physical_status: Literal["PHYSICAL_NOT_PROVEN"] = "PHYSICAL_NOT_PROVEN"


class Event(Strict):
    context: Context
    request: Request
    request_sha256: Hash
    sequence: Counter
    started_ns: Positive
    finished_ns: Positive | None
    row_count: Counter | None
    failure_code: Code | None


class ProbeEvidence(Strict):
    context: Context
    events: Annotated[tuple[Event, ...], Field(max_length=16)] = ()
    allowlist_sha256: Hash = ALLOWLIST_SHA
    real_sql_executed: Literal[0] = 0
    capability_status: Literal["PARTIAL", "NOT_RUN"] = "NOT_RUN"
    termination_status: Literal["MODEL_ONLY_NOT_PROVEN"] = "MODEL_ONLY_NOT_PROVEN"


class Capability(Status):
    context: Context
    offline_contract_status: Literal["OFFLINE_DESIGN", "MOCK_ONLY"] = "OFFLINE_DESIGN"
    independent_harness_status: Literal["HARNESS_NOT_CONFIGURED"] = "HARNESS_NOT_CONFIGURED"


class Failure(Strict):
    context: Context
    first_error: Code | None
    cleanup_codes: Annotated[tuple[Code, ...], Field(max_length=4)] = ()
    cleanup_omitted: Counter = 0
    last_snapshot_sha256: Hash | None = None
    stage: Literal["LIVE_DENY", "MOCK_PROBE", "MOCK_CLEANUP", "ARTIFACT_IO"]


class Cleanup(Strict):
    context: Context
    physical_status: Literal["NOT_APPLICABLE_NO_FIXTURE"] = "NOT_APPLICABLE_NO_FIXTURE"
    mock_receipts: tuple[Attestation, ...] = ()
    mock_cleanup_complete: bool = False


class FileProof(Strict):
    sha256: Hash
    bytes: Annotated[int, Field(strict=True, ge=1, le=1_000_000)]


class Manifest(Strict):
    schema_version: Literal["a4236.offline-bundle.v1"] = "a4236.offline-bundle.v1"
    context: Context
    files: dict[str, FileProof]


MODELS = dict(
    zip(NAMES, (Audit, FixtureEvidence, ProbeEvidence, Capability, Failure, Cleanup), strict=True)
)


def failure(context, first, cleanup=(), snapshot=None, stage="MOCK_PROBE"):
    codes = list(dict.fromkeys(Fault(c).code for c in cleanup))
    return Failure(
        context=context,
        first_error=Fault(first).code if first else (codes[0] if codes else None),
        cleanup_codes=tuple(codes[:4]),
        cleanup_omitted=max(0, len(codes) - 4),
        last_snapshot_sha256=snapshot,
        stage=stage,
    )


def independent_expected(expected):
    from scripts import a4235_capability_guard as guard

    expected = checked(Context, expected)
    actual = guard.expected_identity(
        run_id=expected.identity.run_id, attempt=expected.identity.attempt
    )
    require(
        expected.identity == actual and expected.overlay_sha256 == guard.overlay_fingerprint(),
        "A4236_UNTRUSTED_EXPECTED",
    )
    return expected


def validate(documents, expected):
    expected = checked(Context, expected)
    require(type(documents) is dict and set(documents) == set(NAMES), "A4236_ARTIFACT_SET_INVALID")
    rows = {name: checked(model, documents[name]) for name, model in MODELS.items()}
    require(all(row.context == expected for row in rows.values()), "A4236_IDENTITY_MISMATCH")
    audit, fixture, probe, cap, first, cleanup = [rows[n] for n in NAMES]
    require(cap.offline_contract_status == expected.evidence_kind, "A4236_EVIDENCE_KIND_MISMATCH")
    require(probe.allowlist_sha256 == ALLOWLIST_SHA, "A4236_SQL_NOT_ALLOWLISTED")
    require(
        len(set(first.cleanup_codes)) == len(first.cleanup_codes)
        and set(first.cleanup_codes)
        <= {
            "A4236_CLEANUP_NOT_VERIFIED",
            "A4236_CLEANUP_TIMEOUT",
            "A4236_ABSENCE_NOT_VERIFIED",
            "A4236_JOIN_TIMEOUT",
            "A4236_CLEANUP_IDENTITY_DRIFT",
            "A4236_CLEANUP_AUDIT_UNAVAILABLE",
        }
        and (not first.cleanup_codes or first.first_error is not None)
        and (not first.cleanup_omitted or len(first.cleanup_codes) == 4),
        "A4236_FAILURE_CONTRADICTION",
    )
    require(not probe.events or probe.capability_status == "PARTIAL", "A4236_FALSE_COMPLETE")
    for i, event in enumerate(probe.events):
        require(
            event.context == expected
            and event.sequence == i
            and event.request == request(event.request.template)
            and event.request_sha256 == digest(event.request.model_dump()),
            "A4236_EVENT_INVALID",
        )
        if i:
            require(
                probe.events[i - 1].failure_code is None
                and probe.events[i - 1].finished_ns is not None
                and probe.events[i - 1].finished_ns <= event.started_ns,
                "A4236_EVENT_INVALID",
            )
        if event.failure_code is None:
            require(
                event.finished_ns is not None
                and event.started_ns <= event.finished_ns
                and event.finished_ns - event.started_ns <= 100_000_000
                and event.row_count is not None
                and event.row_count <= (8 if event.request.template == "PROJECTION" else 1),
                "A4236_EVENT_INVALID",
            )
        else:
            require(
                i == len(probe.events) - 1 and first.first_error == event.failure_code,
                "A4236_FIRST_ERROR_NOT_STICKY",
            )
            require(
                event.finished_ns is None or event.finished_ns >= event.started_ns,
                "A4236_EVENT_INVALID",
            )
    require(
        first.last_snapshot_sha256
        == (digest(probe.events[-1].model_dump()) if probe.events else None),
        "A4236_LAST_SNAPSHOT_MISMATCH",
    )
    if probe.events and all(e.failure_code is None for e in probe.events) and first.cleanup_codes:
        require(first.first_error == first.cleanup_codes[0], "A4236_FIRST_ERROR_NOT_STICKY")
    if probe.events and probe.events[-1].finished_ns is not None:
        if probe.events[-1].finished_ns - probe.events[0].started_ns > 2_000_000_000:
            require(first.first_error == "A4236_SQL_BUDGET_EXCEEDED", "A4236_EVENT_INVALID")
    if fixture.spec is not None:
        require(
            expected.evidence_kind == "MOCK_ONLY"
            and audit.mock_consumption is not None
            and audit.mock_consumption.context == expected,
            "A4236_UNTRUSTED_FIXTURE",
        )
        validate_fixture(fixture.spec, fixture.spec)
        require(
            fixture.spec.context == expected and len(fixture.mock_creation) == 2,
            "A4236_UNTRUSTED_FIXTURE",
        )
        validate_creation(fixture.spec, *fixture.mock_creation)
        require(
            fixture.mock_creation[0].observed_ns < fixture.mock_creation[1].observed_ns
            and (
                not probe.events
                or fixture.mock_creation[1].observed_ns <= probe.events[0].started_ns
            ),
            "A4236_EVENT_INVALID",
        )
        if cleanup.mock_cleanup_complete:
            validate_cleanup(fixture.spec, cleanup.mock_receipts)
            last_probe = (
                probe.events[-1].finished_ns or probe.events[-1].started_ns
                if probe.events
                else fixture.mock_creation[1].observed_ns
            )
            require(
                last_probe <= cleanup.mock_receipts[0].observed_ns
                and cleanup.mock_receipts[-1].observed_ns - cleanup.mock_receipts[0].observed_ns
                <= 2_000_000_000,
                "A4236_CLEANUP_CONTRADICTION",
            )
            require(
                not first.cleanup_codes and not first.cleanup_omitted, "A4236_CLEANUP_CONTRADICTION"
            )
        else:
            require(
                first.cleanup_codes and first.first_error is not None, "A4236_CLEANUP_NOT_VERIFIED"
            )
    else:
        require(
            not fixture.mock_creation
            and not cleanup.mock_receipts
            and not cleanup.mock_cleanup_complete
            and audit.mock_consumption is None
            and not probe.events
            and first.stage == "LIVE_DENY"
            and first.first_error == "A4236_G1_NOT_RUN_NOT_AUTHORIZED",
            "A4236_UNTRUSTED_FIXTURE",
        )
    return rows


def proof(raw):
    return FileProof(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def write_bundle(path, documents, expected):
    validate(documents, expected)
    path = Path(path)
    require(".." not in path.parts, "A4236_PATH_INVALID")
    parent = directory = None
    started = time.monotonic_ns()
    try:
        parent = open_directory(path.absolute().parent)
        os.mkdir(path.name, mode=0o700, dir_fd=parent)
        directory = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        marker = os.open(
            ".incomplete",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.close(marker)
        payload = {
            name: encode(checked(MODELS[name], documents[name]).model_dump()) for name in NAMES
        }
        manifest = Manifest(context=expected, files={n: proof(raw) for n, raw in payload.items()})
        payload["manifest.json"] = encode(manifest.model_dump())
        for name in ("failure.json", *[n for n in NAMES if n != "failure.json"], "manifest.json"):
            require(time.monotonic_ns() - started <= 2_000_000_000, "A4236_ARTIFACT_TIMEOUT")
            out = os.open(
                name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            with os.fdopen(out, "wb") as stream:
                stream.write(payload[name])
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(directory)
        os.fsync(parent)
        require(time.monotonic_ns() - started <= 2_000_000_000, "A4236_ARTIFACT_TIMEOUT")
        # Final commit operation: any prior failure leaves an extra marker and cannot
        # be accepted even if a manifest was written. Crash may cause safe false-negative.
        os.unlink(".incomplete", dir_fd=directory)
    except BaseException as error:
        raise Fault(
            error.code if isinstance(error, Fault) else "A4236_ARTIFACT_WRITE_FAILED"
        ) from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def review_bundle(path, expected):
    directory = None
    try:
        expected = independent_expected(expected)
        directory = open_directory(Path(path))
        require(
            os.fstat(directory).st_mode & 0o077 == 0 and os.fstat(directory).st_uid == os.getuid(),
            "A4236_PERMISSIONS_INVALID",
        )
        require(set(os.listdir(directory)) == ALL_NAMES, "A4236_ARTIFACT_SET_INVALID")
        raw = {}
        for name in sorted(ALL_NAMES):
            out = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(out, "rb") as stream:
                meta = os.fstat(stream.fileno())
                require(
                    stat.S_ISREG(meta.st_mode)
                    and meta.st_mode & 0o077 == 0
                    and meta.st_uid == os.getuid()
                    and meta.st_nlink == 1
                    and 0 < meta.st_size <= 1_000_000,
                    "A4236_UNSAFE_ARTIFACT",
                )
                raw[name] = stream.read(1_000_001)
                require(len(raw[name]) == meta.st_size, "A4236_UNSAFE_ARTIFACT")
        for value in raw.values():
            decode(value)  # Reject duplicate keys and nonfinite constants before model parsing.
        manifest = Manifest.model_validate_json(raw["manifest.json"])
        require(
            manifest.context == expected and set(manifest.files) == set(NAMES),
            "A4236_MANIFEST_INVALID",
        )
        require(
            all(manifest.files[n] == proof(raw[n]) for n in NAMES), "A4236_ARTIFACT_HASH_MISMATCH"
        )
        validate({name: MODELS[name].model_validate_json(raw[name]) for name in NAMES}, expected)
        return dict(
            **Status().model_dump(),
            context=expected.model_dump(),
            offline_contract_validated=True,
            physical_capabilities="NOT_PROVEN",
        )
    except BaseException as error:
        raise Fault(error.code if isinstance(error, Fault) else "A4236_ARTIFACT_INVALID") from None
    finally:
        if directory is not None:
            os.close(directory)
