"""Synthetic harness terminal SQL evidence, not a production SQL observer.

Counts SQLAlchemy cursor execution attempts, by legacy first token. WITH remains
WITH; direct-driver observer controls and implicit driver transactions are excluded.
"""

import hashlib
import json
import math
import re
import threading
import uuid
from collections import Counter

VERSION = "biz-perf-04-a.sql-snapshot.v1"
SCOPE = "create_claim_execute_including_worker_finally"
SOURCE = "sqlalchemy.before_cursor_execute.attempts.first_token.v1"


def require(value):
    if not value:
        raise ValueError("BIZ03_SQL_SNAPSHOT_INVALID")


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class RootCounts:
    def __init__(self):
        self._counts = Counter()
        self._lock = threading.Lock()
        self._frozen = False
        self._pending = 0

    def begin(self, operation):
        with self._lock:
            if self._frozen:
                return False
            self._counts[operation] += 1
            self._pending += 1
            return True

    def end(self):
        with self._lock:
            self._pending -= 1

    def copy(self):
        with self._lock:
            return dict(self._counts)

    def freeze(self):
        with self._lock:
            require(not self._frozen and self._pending == 0)
            self._frozen = True
            return dict(self._counts)


def build(counts, *, head_sha, root_job_id, started, ended):
    value = dict(version=VERSION, scope=SCOPE, source=SOURCE,
                 head_sha=head_sha, root_job_id=root_job_id,
                 started_monotonic_seconds=started, ended_monotonic_seconds=ended,
                 counts=dict(counts), total=sum(counts.values()), complete=True)
    value["snapshot_id"] = checksum(value)
    validate(value)
    return value


def validate(value):
    keys = {"version", "scope", "source", "head_sha", "root_job_id",
            "started_monotonic_seconds", "ended_monotonic_seconds", "counts",
            "total", "complete", "snapshot_id"}
    require(isinstance(value, dict) and set(value) == keys)
    require(value["version"] == VERSION and value["scope"] == SCOPE
            and value["source"] == SOURCE and value["complete"] is True)
    require(isinstance(value["head_sha"], str)
            and re.fullmatch(r"[0-9a-f]{40}", value["head_sha"]))
    try:
        require(str(uuid.UUID(value["root_job_id"])) == value["root_job_id"])
    except (ValueError, TypeError, AttributeError):
        require(False)
    times = [value[k] for k in ("started_monotonic_seconds", "ended_monotonic_seconds")]
    require(all(type(t) in (int, float) and math.isfinite(t) and t >= 0 for t in times)
            and times[1] >= times[0])
    counts = value["counts"]
    require(isinstance(counts, dict) and len(counts) <= 128
            and all(isinstance(k, str) and re.fullmatch(r"[A-Z_]{1,40}", k)
                    and type(v) is int and v >= 0 for k, v in counts.items()))
    require(type(value["total"]) is int and value["total"] == sum(counts.values()))
    require(value["snapshot_id"] == checksum({k: v for k, v in value.items()
                                            if k != "snapshot_id"}))


def validate_pair(phase, measurement, *, expected_head=None):
    """Current completion requires v1; legacy documents remain parseable separately."""
    snapshot = measurement.get("sql_snapshot")
    validate(snapshot)
    if expected_head is not None:
        require(snapshot["head_sha"] == expected_head)
    require(phase.get("phase") == "result" and phase.get("failure_code") is None
            and phase.get("sql_snapshot") == snapshot
            and phase.get("sql_counts") == snapshot["counts"]
            and measurement.get("root", {}).get("sql_counts") == snapshot["counts"]
            and measurement.get("head_sha") == snapshot["head_sha"]
            and measurement.get("root_job_id") == snapshot["root_job_id"]
            and measurement["root"].get("job_status") == "SUCCESS"
            and measurement["root"].get("publication_state") == "PUBLISHED")
