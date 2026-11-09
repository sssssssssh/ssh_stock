"""Versioned safe evidence helpers; digests never confer execution authority."""

import hashlib
import math
import re
from pathlib import Path

from scripts.r1_business_snapshot_contract import SCHEMA_SHA256, frame
from scripts.r1_real_root_protocol import BASELINE, Refused, require

INTEGRATION_BASELINE = "8443b7cd524a6964b24cecd60df5be5b6c46783b"
VERSION = "r1.integration.offline.v1"
MODULES = tuple(
    "r1_integration_" + x + ".py"
    for x in (
        "pg_guard",
        "seed_loader",
        "pg_export",
        "durable_owner",
        "linux_domain",
        "controller",
        "evidence",
    )
)


def sha(value):
    """Streaming typed digest with explicit container framing (max 64 MiB)."""
    result, used = hashlib.sha256(), 0

    def put(raw):
        nonlocal used
        used += len(raw)
        require(used <= 64 * 1024 * 1024, "INTEGRATION_DIGEST_BUDGET")
        result.update(raw)

    def walk(v, depth=0):
        require(depth <= 32, "INTEGRATION_DIGEST_DEPTH")
        if type(v) in (dict, list, tuple):
            require(len(v) <= 20000, "INTEGRATION_DIGEST_BUDGET")
            put(frame((type(v).__name__, len(v))))
            if type(v) is dict:
                require(all(type(k) is str for k in v), "INTEGRATION_DIGEST_KEY")
                for k in sorted(v):
                    put(frame(k))
                    walk(v[k], depth + 1)
            else:
                for x in v:
                    walk(x, depth + 1)
        else:
            put(frame(v))

    walk(value)
    return result.hexdigest()


def label(value):
    require(
        type(value) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) is not None,
        "INTEGRATION_LABEL",
    )
    return value


def source_identity():
    root = Path(__file__).resolve().parents[1] / "scripts"
    hashes = {}
    for name in MODULES:
        p = root / name
        require(not p.is_symlink() and not p.is_junction(), "INTEGRATION_SOURCE_LINK")
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "version": VERSION,
        "integration_baseline": INTEGRATION_BASELINE,
        "fixture_business_baseline": BASELINE,
        "schema_sha256": SCHEMA_SHA256,
        "tool_hashes": hashes,
        "tool_digest": sha(hashes),
    }


def verify_business_sources():
    """Read pinned text sources without importing application/settings code."""
    from scripts.r1_business_snapshot_contract import load_schema

    root = Path(__file__).resolve().parents[1]
    for name, source in load_schema()["sources"].items():
        path = root / name
        require(not path.is_symlink() and not path.is_junction(), "INTEGRATION_SOURCE_LINK")
        # Git's text identity is LF; raw local bytes are protected independently
        # in the task's baseline manifest (CRLF checkouts must stay unchanged).
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        require(hashlib.sha256(raw).hexdigest() == source["sha256"], "INTEGRATION_BUSINESS_DRIFT")
    return True


def require_lineage(identity):
    require(identity == source_identity(), "INTEGRATION_SOURCE_DRIFT")


def finite_time(value):
    require(
        type(value) in (int, float) and math.isfinite(value) and value >= 0, "INTEGRATION_CLOCK"
    )
    return value


def deny_real(*_args, **_kwargs):
    raise Refused("R1_REAL_EXECUTION_NOT_AUTHORIZED")


def empty_measurements():
    return {
        name: "NOT_MEASURED"
        for name in (
            "external_stages",
            "sql",
            "fetch",
            "cpu",
            "rss",
            "overhead_3pct",
            "speedup_30pct",
        )
    }
