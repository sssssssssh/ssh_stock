"""Bounded offline declarations and injected mock attestations; never a permit.

The dependency graph is acyclic: subject (plan without receipt hashes) ->
evidence files -> manifest -> packet. Files have fixed names. Sources are mock
receipt identifiers, not URLs, paths, signatures or credentials to dereference.
All ancestors must be trusted and stable; this is not a hostile-filesystem sandbox.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
from pathlib import Path
from typing import Protocol

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e03_guard as g

SCHEMA = "biz-perf-p1-04.e04.offline.v1"
MAX_FILE = 64 * 1024
FILES = ("admission_packet.json", "evidence_manifest.json", "ci.json", "review.json",
         "resources.json")
ROLES = ("ci", "review", "resources")
GATES = dict(g.GATES, budget="DRAFT_NOT_APPROVED")
CODES = frozenset({
    "INPUT_REJECTED", "PACKET_REJECTED", "MANIFEST_REJECTED", "EVIDENCE_REJECTED",
    "DIGEST_MISMATCH", "IDENTITY_MISMATCH", "PATH_REJECTED", "EVIDENCE_MISSING",
    "ATTESTATION_REFUSED", "ATTESTATION_REJECTED", "AUTHORIZATION_PENDING",
    "JOURNAL_REJECTED", "RUN_UUID_REUSED", "JOURNAL_IO_FAILED", "JOURNAL_CORRUPT",
    "TRANSITION_REJECTED", "MANUAL_REVIEW_REQUIRED", "CLEANUP_BLOCKED",
    "BUDGET_REJECTED", "MOCK_ONLY", "MOCK_FAILED", "UNKNOWN_ACK", "EVIDENCE_INCOMPLETE",
})


class Refused(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in CODES else "INPUT_REJECTED"
        super().__init__(self.code)


def require(value, code="INPUT_REJECTED"):
    if not value:
        raise Refused(code)


def fields(value, keys, code="INPUT_REJECTED"):
    require(type(value) is dict and set(value) == set(keys), code)


def digest(value):
    try:
        return d.preflight_digest(value)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise Refused("INPUT_REJECTED") from None


def seal(body):
    require(type(body) is dict and "canonical_sha256" not in body)
    return dict(body, canonical_sha256=digest(body))


def unseal(value, keys, code):
    fields(value, {*keys, "canonical_sha256"}, code)
    body = {key: value[key] for key in keys}
    require(d.hex_value(value["canonical_sha256"], 64)
            and value["canonical_sha256"] == digest(body), "DIGEST_MISMATCH")
    return body


def subject(plan):
    """Receipt hashes are downstream, so never include them in their subject."""
    try:
        value = copy.deepcopy(plan)
        del value["ci"]["receipt_sha256"]
        del value["review"]["receipt_sha256"]
        return digest(value)
    except (KeyError, TypeError, RecursionError):
        raise Refused("PACKET_REJECTED") from None


def decode(raw):
    try:
        require(type(raw) is bytes and len(raw) <= MAX_FILE)
        return d.decode(raw)
    except (d.Rejected, ValueError, TypeError, RecursionError):
        raise Refused("INPUT_REJECTED") from None


class ReadOnlyVerifier(Protocol):
    def verify(self, packet: dict, manifest: dict, evidence: dict) -> dict: ...


class RefusedVerifier:
    def verify(self, packet, manifest, evidence):
        raise Refused("ATTESTATION_REFUSED")


def _bound(document, sha, run_uuid, subject_sha):
    require(document["schema"] == SCHEMA
            and document["evidence_kind"] == "OFFLINE_FIXTURE", "EVIDENCE_REJECTED")
    require(document["implementation_sha"] == sha and document["run_uuid"] == run_uuid
            and document["subject_sha256"] == subject_sha, "IDENTITY_MISMATCH")


def _evidence(document, role, plan, sha, run_uuid, subject_sha):
    body = unseal(document, {"schema", "evidence_kind", "implementation_sha", "run_uuid",
                             "subject_sha256", "role", "source", "payload"},
                  "EVIDENCE_REJECTED")
    _bound(body, sha, run_uuid, subject_sha)
    require(body["role"] == role, "EVIDENCE_REJECTED")
    source = body["source"]
    fields(source, {"kind", "receipt_uuid", "scope"}, "EVIDENCE_REJECTED")
    require(source["kind"] == "OFFLINE_MOCK_SOURCE"
            and d.uuid_value(source["receipt_uuid"])
            and source["receipt_uuid"] != run_uuid
            and source["scope"] == "E04_OFFLINE_PROTOCOL", "EVIDENCE_REJECTED")
    payload = body["payload"]
    if role == "ci":
        fields(payload, {"status", "run_id", "attempt"}, "EVIDENCE_REJECTED")
        require(payload["status"] == "SUCCESS"
                and d.uint(payload["run_id"]) and payload["run_id"] > 0
                and d.uint(payload["attempt"], 100) and payload["attempt"] > 0,
                "EVIDENCE_REJECTED")
    elif role == "review":
        fields(payload, {"status", "reviewer_sha256", "implementer_sha256"},
               "EVIDENCE_REJECTED")
        require(payload == {key: plan["review"][key] for key in payload},
                "EVIDENCE_REJECTED")
    else:
        fields(payload, {"expected", "observed", "observation_seq"}, "EVIDENCE_REJECTED")
        require(type(payload["observation_seq"]) is int and payload["observation_seq"] == 1
                and payload["expected"] == plan["expected"]
                and payload["observed"] == plan["observed"], "IDENTITY_MISMATCH")


def _validate(values, raw, expected_sha, expected_run_uuid):
    packet, manifest = values[FILES[0]], values[FILES[1]]
    p = unseal(packet, {"schema", "evidence_kind", "implementation_sha", "run_uuid",
                        "subject_sha256", "manifest_sha256", "plan"}, "PACKET_REJECTED")
    require(d.hex_value(expected_sha, 40) and d.uuid_value(expected_run_uuid),
            "IDENTITY_MISMATCH")
    subject_sha = subject(p["plan"])
    _bound(p, expected_sha, expected_run_uuid, subject_sha)
    plan = p["plan"]
    try:
        g.validate_plan(plan, expected_sha)
    except g.Refused:
        raise Refused("PACKET_REJECTED") from None
    require(plan["preflight"]["run_uuid"] == expected_run_uuid, "IDENTITY_MISMATCH")
    m = unseal(manifest, {"schema", "evidence_kind", "implementation_sha", "run_uuid",
                          "subject_sha256", "entries"}, "MANIFEST_REJECTED")
    _bound(m, expected_sha, expected_run_uuid, subject_sha)
    require(p["manifest_sha256"] == manifest["canonical_sha256"], "DIGEST_MISMATCH")
    fields(m["entries"], {f"{role}.json" for role in ROLES}, "MANIFEST_REJECTED")
    receipts = []
    for role in ROLES:
        name = f"{role}.json"
        item = m["entries"][name]
        fields(item, {"evidence_kind", "bytes", "sha256", "canonical_sha256"},
               "MANIFEST_REJECTED")
        require(item["evidence_kind"] == "OFFLINE_FIXTURE"
                and type(item["bytes"]) is int and item["bytes"] == len(raw[name])
                and item["sha256"] == hashlib.sha256(raw[name]).hexdigest()
                and item["canonical_sha256"] == values[name]["canonical_sha256"],
                "DIGEST_MISMATCH")
        _evidence(values[name], role, plan, expected_sha, expected_run_uuid, subject_sha)
        receipts.append(values[name]["source"]["receipt_uuid"])
        if role in {"ci", "review"}:
            require(plan[role]["receipt_sha256"] == item["sha256"], "DIGEST_MISMATCH")
    require(len(set(receipts)) == len(ROLES), "EVIDENCE_REJECTED")
    return packet, manifest


def load_bundle(path, expected_sha, expected_run_uuid, *, verifier=None):
    """Read twice around verification; no self-declared trust or file writes.

    An injected verifier is trusted synchronous test code. Even an exact mock
    receipt produces only OFFLINE_ATTESTED_MOCK_ONLY and cannot enable execute.
    """
    try:
        source = d.directory(Path(path))
        before = source.stat()
        require({entry.name for entry in source.iterdir()} == set(FILES), "PATH_REJECTED")
        inodes = {name: (source / name).lstat() for name in FILES}
        raw = {name: d.read_file(source / name, MAX_FILE) for name in FILES}
        values = {name: decode(data) for name, data in raw.items()}
        packet, manifest = _validate(values, raw, expected_sha, expected_run_uuid)
        status = "OFFLINE_DECLARATIONS_ONLY"
        if verifier is not None:
            try:
                result = verifier.verify(copy.deepcopy(packet), copy.deepcopy(manifest),
                                         {role: copy.deepcopy(values[f"{role}.json"])
                                          for role in ROLES})
            except Refused:
                raise
            except Exception:
                raise Refused("ATTESTATION_REJECTED") from None
            wanted = dict(evidence_kind="OBSERVED_OFFLINE", status="OFFLINE_ATTESTED_MOCK_ONLY",
                          packet_sha256=packet["canonical_sha256"],
                          manifest_sha256=manifest["canonical_sha256"],
                          implementation_sha=expected_sha, run_uuid=expected_run_uuid)
            require(type(result) is dict and result == wanted, "ATTESTATION_REJECTED")
            status = wanted["status"]
        d.directory(source)
        require(os.path.samestat(before, source.stat())
                and {entry.name for entry in source.iterdir()} == set(FILES), "PATH_REJECTED")
        require(all(os.path.samestat(inodes[name], (source / name).lstat())
                    and d.read_file(source / name, MAX_FILE) == data for name, data in raw.items()),
                "PATH_REJECTED")
        return dict(schema=SCHEMA, status=status, evidence_kind="OBSERVED_OFFLINE",
                    implementation_sha=expected_sha, run_uuid=expected_run_uuid,
                    packet_sha256=packet["canonical_sha256"],
                    manifest_sha256=manifest["canonical_sha256"],
                    files={name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
                    **GATES)
    except Refused:
        raise
    except FileNotFoundError:
        raise Refused("EVIDENCE_MISSING") from None
    except (d.Rejected, OSError):
        raise Refused("PATH_REJECTED") from None
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise Refused("INPUT_REJECTED") from None


def execute():
    print("AUTHORIZATION_PENDING")
    return 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused("INPUT_REJECTED")


def main(argv=None):
    # execute is a denial, including any attempted flags or signature strings.
    if argv is None:
        import sys

        argv = sys.argv[1:]
    if argv and argv[0] == "execute":
        return execute()
    parser = _Parser(description=__doc__)
    parser.add_argument("command", choices=("validate-offline",))
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--expected-implementation-sha", required=True)
    parser.add_argument("--expected-run-uuid", required=True)
    try:
        args = parser.parse_args(argv)
        result = load_bundle(args.input_dir, args.expected_implementation_sha,
                             args.expected_run_uuid)
        print(d.encode(result).decode().strip())
        return 0
    except Refused as exc:
        print(exc.code)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
