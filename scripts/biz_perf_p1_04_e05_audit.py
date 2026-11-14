"""Independent READ_ONLY_AUDIT of E04 mock evidence; no execution authority.

No adapter, callback, network, write port, checkpoint update or retry is exposed.
Self-consistency cannot establish CI/review provenance or real resource ownership.
An optional independently preserved checkpoint establishes relative differences
only. Administrators, malicious filesystems and cross-machine uniqueness remain
outside this reader's guarantees.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e04_packet as p
from scripts import biz_perf_p1_04_e04_review as r
from scripts import biz_perf_p1_04_e05_scan as s
from scripts.biz_perf_p1_04_e04_journal import OfflineLeaseJournal

STATES = frozenset({"PLANNED", "RESERVED", "UNKNOWN_ACK", "MOCK_RETURNED", "BLOCKED",
                    "MANUAL_REVIEW_REQUIRED"})
ERROR_CODES = s.CODES | p.CODES | {"WRITER_LOCK_PRESENT", "WRITER_LOCK_CORRUPT",
                                "UNKNOWN_OWNERSHIP", "RESOURCE_DRIFT", "BUDGET_EXPIRED"}
UNVERIFIED = (
    "CI_SOURCE_AUTHENTICITY", "APPROVAL_SOURCE_AUTHENTICITY", "EXTERNAL_CHECKPOINT_TRUST",
    "CROSS_MACHINE_UNIQUENESS", "REAL_RESOURCE_OWNERSHIP",
    "WINDOWS_DIRECTORY_POWER_LOSS_DURABILITY", "REAL_EXECUTION_RESULT",
    "HOSTILE_ADMIN_OR_FILESYSTEM", "SCAN_ABA_BETWEEN_OBSERVATIONS",
)


def classify_incident(state, *, error_code=None, locked=False, complete=False,
                      ownership="OFFLINE_MATCH_ONLY", resource_match=True, elapsed_ms=0):
    """Pure finite taxonomy. Every outcome forbids replay/retry/cleanup/release."""
    valid = (type(state) is str and state in STATES
             and (error_code is None or type(error_code) is str and error_code in ERROR_CODES)
             and type(locked) is bool and type(complete) is bool
             and type(resource_match) is bool and d.uint(elapsed_ms)
             and type(ownership) is str and ownership in {"UNKNOWN", "OFFLINE_MATCH_ONLY"})
    if not valid:
        state, error_code = "MANUAL_REVIEW_REQUIRED", "INPUT_REJECTED"
    elif ownership == "UNKNOWN":
        error_code = error_code or "UNKNOWN_OWNERSHIP"
    elif not resource_match:
        error_code = error_code or "RESOURCE_DRIFT"
    elif (elapsed_ms >= 1_200_000
          or state in {"RESERVED", "UNKNOWN_ACK"} and elapsed_ms >= 900_000):
        error_code = error_code or "BUDGET_EXPIRED"
    elif locked:
        error_code = error_code or "WRITER_LOCK_PRESENT"
    tamper = {"DIGEST_MISMATCH", "IDENTITY_MISMATCH", "SCAN_CHANGED", "PATH_REJECTED",
              "CHECKPOINT_MISMATCH", "CHECKPOINT_ROLLBACK", "RESOURCE_DRIFT"}
    status = "MANUAL_REVIEW_REQUIRED"
    if error_code in tamper:
        status = "EVIDENCE_TAMPER_SUSPECTED"
    elif error_code in {"INPUT_REJECTED", "CHECKPOINT_REJECTED", "FILE_IDENTITY_UNKNOWN"}:
        status = "AUDIT_REFUSED"
    elif error_code in {"EVIDENCE_MISSING", "EVIDENCE_INCOMPLETE"}:
        status = "OFFLINE_EVIDENCE_INCOMPLETE"
    elif error_code is None and state == "MOCK_RETURNED" and complete:
        status = "OFFLINE_EVIDENCE_CONSISTENT"
    suggestions = ["PRESERVE_EVIDENCE", "CHECK_OWNER_OUT_OF_BAND", "CHECK_ORIGINAL_CI_AT_SOURCE"]
    if state in {"RESERVED", "UNKNOWN_ACK", "MANUAL_REVIEW_REQUIRED"} or locked:
        suggestions.append("CHECK_ACK_OUT_OF_BAND")
    return dict(audit_status=status, incident_state=state, error_code=error_code,
                next_action="HOLD_FOR_MANUAL_REVIEW", no_replay=True, no_retry=True,
                no_cleanup=True, no_release=True, manual_check_codes=suggestions)


def _raw_check(snapshot, packet, sha, run_uuid):
    """Original frozen Replay validates prefixes and complete mock results."""
    contract_raw = snapshot["raw"]["raw/preflight.json"]
    events = snapshot["raw"]["raw/events.jsonl"]
    if contract_raw is None or events is None:
        return False, "EVIDENCE_MISSING"
    try:
        contract = d.preflight(d.decode(contract_raw), sha)
        s.require(contract == packet["plan"]["preflight"] and contract["run_uuid"] == run_uuid,
                  "EVIDENCE_INVALID")
        replay = d.Replay(contract)
        for line in events.splitlines(keepends=True):
            s.require(len(line) <= d.MAX_LINE_BYTES and line.endswith(b"\n"), "EVIDENCE_INVALID")
            replay.accept(d.decode(line))
        try:
            replay.summary()
        except d.Rejected:
            return False, "EVIDENCE_INCOMPLETE"
        return True, None
    except (d.Rejected, s.Refused, ValueError, TypeError, KeyError, RecursionError):
        return False, "EVIDENCE_INVALID"


def audit_bundle(expected_sha, run_uuid, bundle, journal_path, raw_dir, *,
                 checkpoint=None, elapsed_ms=0):
    """Only explicit caller SHA/UUID are roots of expected identity. No writes.

    Returned digests/states are observations, not provenance or a permit. Errors
    export finite codes only; paths, payloads, SQL and exceptions never escape.
    """
    result = dict(schema="biz-perf-p1-04.e05.audit.v1", mode="READ_ONLY_AUDIT",
                  evidence_kind="OFFLINE_ONLY", implementation_sha=None, run_uuid=None,
                  raw_evidence_digests={}, checkpoint_sha256=None,
                  checkpoint_comparison="NOT_SUPPLIED", checkpoint_trust="UNKNOWN",
                  file_identity="UNKNOWN", journal_state="MANUAL_REVIEW_REQUIRED",
                  writer_lock="UNKNOWN", observation=None, unverified=list(UNVERIFIED),
                  **p.GATES)
    state, code, locked, complete = "MANUAL_REVIEW_REQUIRED", None, False, False
    try:
        s.require(d.hex_value(expected_sha, 40) and d.uuid_value(run_uuid)
                  and d.uint(elapsed_ms))
        result.update(implementation_sha=expected_sha, run_uuid=run_uuid)
        before = s.scan(bundle, journal_path, raw_dir, run_uuid)
        result.update(raw_evidence_digests=before["files"], file_identity="OBSERVED_LOCAL_ONLY")
        proof = p.load_bundle(bundle, expected_sha, run_uuid)
        packet = p.decode(before["raw"]["bundle/admission_packet.json"])
        s.require(packet["canonical_sha256"] == proof["packet_sha256"], "SCAN_CHANGED")
        journal = OfflineLeaseJournal(journal_path)  # Constructor and inspect are read-only.
        report = journal.inspect(expected_sha, run_uuid, proof["packet_sha256"],
                                 proof["manifest_sha256"], elapsed_ms=elapsed_ms)
        state, code = report["state"], report["error_code"]
        result["journal_state"] = state
        lock_raw = before["raw"]["lease/writer.lock"]
        locked = lock_raw is not None
        result["writer_lock"] = "PRESENT" if locked else "ABSENT"
        if locked:
            try:
                s.require(p.decode(lock_raw) == dict(schema=p.SCHEMA,
                                                   evidence_kind="OFFLINE_FIXTURE"))
                code = code or "WRITER_LOCK_PRESENT"
            except (p.Refused, s.Refused):
                code = "WRITER_LOCK_CORRUPT"
        transitions = report["transitions"]
        raw_complete, raw_code = _raw_check(before, packet, expected_sha, run_uuid)
        output = {name: before["files"].get(f"raw/{name}")
                  for name in ("preflight.json", "events.jsonl")}
        if state == "MOCK_RETURNED":
            if all(output.values()) and transitions[-1]["evidence_sha256"] != p.digest(output):
                code = "DIGEST_MISMATCH"
            elif raw_code:
                code = code or raw_code
        else:
            code = code or raw_code
        receipt = r.review_receipt(bundle, journal, raw_dir, expected_sha, run_uuid,
                                   elapsed_ms=elapsed_ms)
        complete = raw_complete and receipt["status"] == "OFFLINE_EVIDENCE_REVIEWED_ONLY"
        observation = dict(implementation_sha=expected_sha, run_uuid=run_uuid,
                           packet_sha256=proof["packet_sha256"],
                           manifest_sha256=proof["manifest_sha256"],
                           journal_marker_sha256=before["files"]["journal/marker"],
                           seq=transitions[-1]["seq"] if transitions else 0,
                           chain_head=(transitions[-1]["canonical_sha256"]
                                       if transitions else "0" * 64),
                           output_sha256=p.digest(output),
                           snapshot_sha256=before["snapshot_sha256"])
        result["observation"] = observation
        if checkpoint is not None:
            result["checkpoint_comparison"] = "REFUSED"
            # Validate the supplied object before exporting even its digest. Its
            # own validity is separate from matching this scan; never authenticate it.
            s.require(type(checkpoint) is dict, "CHECKPOINT_REJECTED")
            s.compare_checkpoint(checkpoint, checkpoint.get("observation"))
            result["checkpoint_sha256"] = checkpoint["canonical_sha256"]
            result["checkpoint_trust"] = "UNVERIFIED_EXTERNAL_CHECKPOINT"
            result["checkpoint_comparison"] = s.compare_checkpoint(checkpoint, observation)
        after = s.scan(bundle, journal_path, raw_dir, run_uuid)
        s.require(before == after, "SCAN_CHANGED")
    except (s.Refused, p.Refused) as exc:
        code = exc.code
    except FileNotFoundError:
        code = "EVIDENCE_MISSING"
    except (d.Rejected, OSError):
        code = "PATH_REJECTED"
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        code = "INPUT_REJECTED"
    result.update(classify_incident(state, error_code=code, locked=locked,
                                   complete=complete, elapsed_ms=elapsed_ms))
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise s.Refused("INPUT_REJECTED")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "execute":
        return s.execute()
    parser = _Parser(description=__doc__)
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("--expected-implementation-sha", required=True)
    parser.add_argument("--expected-run-uuid", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--elapsed-ms", type=int, default=0)
    try:
        args = parser.parse_args(argv)
        checkpoint = None
        if args.checkpoint is not None:
            path = d.directory(args.checkpoint.parent) / args.checkpoint.name
            checkpoint = p.decode(d.read_file(path, 4096))
        result = audit_bundle(args.expected_implementation_sha, args.expected_run_uuid,
                              args.bundle, args.journal, args.raw,
                              checkpoint=checkpoint, elapsed_ms=args.elapsed_ms)
        print(d.encode(result).decode().strip())
        return 0 if result["audit_status"] == "OFFLINE_EVIDENCE_CONSISTENT" else 2
    except (s.Refused, p.Refused, d.Rejected, OSError, ValueError, RecursionError):
        # Use the same complete refusal envelope even when argument/file parsing
        # fails. Invalid identity stops before any evidence path can be touched.
        print(d.encode(audit_bundle(None, None, None, None, None)).decode().strip())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
