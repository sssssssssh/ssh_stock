"""Bounded, read-only filesystem observations and relative offline checkpoints.

No checkpoint is authenticated here. A saved observation detects relative change
only; a fabricated or rolled-back checkpoint cannot establish absolute freshness.
Trusted stable ancestors and an honest local filesystem remain prerequisites.
"""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime
from itertools import islice
from pathlib import Path

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_e04_packet as p

SCHEMA = "biz-perf-p1-04.e05.checkpoint.v1"
CODES = frozenset({"INPUT_REJECTED", "PATH_REJECTED", "SIZE_LIMIT", "SCAN_CHANGED",
                   "FILE_IDENTITY_UNKNOWN", "CHECKPOINT_REJECTED", "CHECKPOINT_MISMATCH",
                   "CHECKPOINT_ROLLBACK", "EVIDENCE_MISSING", "EVIDENCE_INVALID"})
OBSERVATION_KEYS = frozenset({
    "implementation_sha", "run_uuid", "packet_sha256", "manifest_sha256",
    "journal_marker_sha256", "seq", "chain_head", "output_sha256", "snapshot_sha256",
})


class Refused(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in CODES else "INPUT_REJECTED"
        super().__init__(self.code)


def require(value, code="INPUT_REJECTED"):
    if not value:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(info, *, ancestor=False):
    require(type(info.st_ino) is int and info.st_ino > 0, "FILE_IDENTITY_UNKNOWN")
    value = dict(device=info.st_dev, inode=info.st_ino, mode=info.st_mode)
    if not ancestor:
        value.update(size=info.st_size, mtime_ns=info.st_mtime_ns,
                     ctime_ns=info.st_ctime_ns, links=info.st_nlink)
    return value


def _names(path, maximum):
    # Bound iteration as well as bytes: never enumerate an unbounded directory.
    values = list(islice(path.iterdir(), maximum + 1))
    require(len(values) <= maximum, "SIZE_LIMIT")
    return {item.name for item in values}


def _directory(path, directories, label):
    path = Path(path)
    require(".." not in path.parts, "PATH_REJECTED")
    path = path.absolute()
    ancestors = []
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not parent.is_junction(), "PATH_REJECTED")
        ancestors.append(_identity(info, ancestor=True))
    try:
        info = path.lstat()
    except FileNotFoundError:
        directories[label] = dict(path_sha256=sha(os.fsencode(path)), ancestors=ancestors,
                                  identity=None, names=[])
        return path, set()
    require(stat.S_ISDIR(info.st_mode) and not path.is_junction(), "PATH_REJECTED")
    names = _names(path, 128 if label == "journal" else 8)
    directories[label] = dict(path_sha256=sha(os.fsencode(path)), ancestors=ancestors,
                              identity=_identity(info), names=sorted(names))
    return path, names


def _file(path, limit):
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None, None
    require(stat.S_ISREG(before.st_mode) and not path.is_junction()
            and before.st_nlink == 1, "PATH_REJECTED")
    identity = _identity(before)
    require(0 <= before.st_size <= limit, "SIZE_LIMIT")
    raw = d.read_file(path, limit)
    require(identity == _identity(path.lstat()), "SCAN_CHANGED")
    return raw, dict(identity=identity, sha256=sha(raw))


def _once(bundle, journal, raw_dir, run_uuid):
    directories, files, raw = {}, {}, {}
    bundle, names = _directory(bundle, directories, "bundle")
    require(names <= set(p.FILES), "PATH_REJECTED")
    journal, names = _directory(journal, directories, "journal")
    require(all(name == "journal.json" or d.uuid_value(name) for name in names),
            "PATH_REJECTED")
    lease, names = _directory(journal / run_uuid, directories, "lease")
    allowed = {f"{seq:02}.json" for seq in range(1, 7)} | {"writer.lock"}
    require(names <= allowed, "PATH_REJECTED")
    output, names = _directory(raw_dir, directories, "raw")
    require(names <= {"preflight.json", "events.jsonl"}, "PATH_REJECTED")
    targets = [(f"bundle/{name}", bundle / name, p.MAX_FILE) for name in p.FILES]
    targets += [("journal/marker", journal / "journal.json", 4096)]
    targets += [(f"lease/{seq:02}.json", lease / f"{seq:02}.json", 4096)
                for seq in range(1, 7)]
    targets += [("lease/writer.lock", lease / "writer.lock", 4096),
                ("raw/preflight.json", output / "preflight.json", d.MAX_LINE_BYTES),
                ("raw/events.jsonl", output / "events.jsonl", d.MAX_RAW_BYTES)]
    for label, path, limit in targets:
        raw[label], files[label] = _file(path, limit)
    projection = dict(platform=os.name, directories=directories, files=files)
    return dict(raw=raw, snapshot_sha256=p.digest(projection),
                files={key: value["sha256"] for key, value in files.items() if value is not None})


def scan(bundle, journal, raw_dir, run_uuid):
    """Two bounded observations, no writes, no atime/freshness guarantees.

    Metadata excludes atime because a read can update it. Ancestors are compared
    by identity, not unrelated directory activity. Evidence directories include
    their complete bounded name list and metadata. Inode absence refuses safely.
    """
    require(d.uuid_value(run_uuid))
    try:
        before = _once(bundle, journal, raw_dir, run_uuid)
        after = _once(bundle, journal, raw_dir, run_uuid)
        require(before == after, "SCAN_CHANGED")
        return before
    except Refused:
        raise
    except FileNotFoundError:
        raise Refused("EVIDENCE_MISSING") from None
    except (OSError, d.Rejected):
        raise Refused("PATH_REJECTED") from None
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise Refused("INPUT_REJECTED") from None


def validate_observation(value):
    require(type(value) is dict and set(value) == OBSERVATION_KEYS, "CHECKPOINT_REJECTED")
    require(d.hex_value(value["implementation_sha"], 40) and d.uuid_value(value["run_uuid"]),
            "CHECKPOINT_REJECTED")
    require(type(value["seq"]) is int and 0 <= value["seq"] <= 6, "CHECKPOINT_REJECTED")
    require(all(d.hex_value(value[key], 64) for key in OBSERVATION_KEYS
                - {"implementation_sha", "run_uuid", "seq"}), "CHECKPOINT_REJECTED")


def make_checkpoint(observation, *, check_time, scan_source="EXTERNAL_OFFLINE_COPY"):
    """Return an ordinary object for external preservation; never save or update it."""
    validate_observation(observation)
    require(type(check_time) is str and len(check_time) == 20, "CHECKPOINT_REJECTED")
    try:
        require(datetime.strptime(check_time, "%Y-%m-%dT%H:%M:%SZ").strftime(
            "%Y-%m-%dT%H:%M:%SZ") == check_time, "CHECKPOINT_REJECTED")
    except ValueError:
        raise Refused("CHECKPOINT_REJECTED") from None
    require(scan_source == "EXTERNAL_OFFLINE_COPY", "CHECKPOINT_REJECTED")
    return p.seal(dict(schema=SCHEMA, evidence_kind="OFFLINE_ONLY",
                       observation=dict(observation), check_time=check_time,
                       scan_source=scan_source, trust="UNVERIFIED_EXTERNAL_CHECKPOINT"))


def compare_checkpoint(checkpoint, observation):
    """Strict bounded schema; matching says relative consistency, never authority."""
    try:
        require(type(checkpoint) is dict and len(d.encode(checkpoint)) <= 4096,
                "CHECKPOINT_REJECTED")
        keys = {"schema", "evidence_kind", "observation", "check_time", "scan_source", "trust"}
        require(set(checkpoint) == keys | {"canonical_sha256"}, "CHECKPOINT_REJECTED")
        expected = make_checkpoint(checkpoint["observation"],
                                   check_time=checkpoint["check_time"],
                                   scan_source=checkpoint["scan_source"])
        require(checkpoint == expected, "CHECKPOINT_REJECTED")
        validate_observation(observation)
        previous = checkpoint["observation"]
        if observation["seq"] < previous["seq"]:
            raise Refused("CHECKPOINT_ROLLBACK")
        require(previous == observation, "CHECKPOINT_MISMATCH")
        return "RELATIVE_MATCH_ONLY"
    except Refused:
        raise
    except (p.Refused, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise Refused("CHECKPOINT_REJECTED") from None


def execute():
    print("AUTHORIZATION_PENDING")
    return 2


if __name__ == "__main__":
    raise SystemExit(execute())
