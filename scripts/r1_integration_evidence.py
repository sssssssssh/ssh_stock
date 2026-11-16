"""Versioned safe evidence helpers; digests never confer execution authority."""

import hashlib
import json
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


def verify_business_sources(*, version="r1.business-compare.v1"):
    """Read pinned text sources without importing application/settings code."""
    if version in (CURRENT_SOURCE_VERSION, SOURCE_V3_VERSION):
        return verify_current_business_sources(version=version)
    require(version == "r1.business-compare.v1", "INTEGRATION_SOURCE_VERSION")
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


CURRENT_SOURCE_VERSION = "r1.current-business-sources.v2"
CURRENT_SOURCE_BASELINE = "232baf9e13cd7b23731e59188c86e0e253c3a394"
CURRENT_MANIFEST_SHA256 = "9d7cd00c9883a04a65e147ef71611015340955503dce2b36227db940d1b799f6"


SOURCE_V3_VERSION = "r1.current-business-sources.v3"
SOURCE_V3_BASELINE = "bf7b6a35a453c7d82be363dec2e0f5157221db92"
SOURCE_V3_MANIFEST_SHA256 = "63138e0fdd785d2b614b5a9794134512220534b3edb7522be51a5efbc1fdf918"


def verify_current_business_sources(*, version=CURRENT_SOURCE_VERSION):
    """Offline integrity only; never an execution permit or a v1 fallback."""
    require(version in (CURRENT_SOURCE_VERSION, SOURCE_V3_VERSION), "INTEGRATION_SOURCE_VERSION")
    if version == SOURCE_V3_VERSION:
        manifest_path = "docs/acceptance/r1_current_business_sources_v3.json"
        manifest_sha, baseline = SOURCE_V3_MANIFEST_SHA256, SOURCE_V3_BASELINE
    else:
        manifest_path = "docs/acceptance/r1_current_business_sources_v2.json"
        manifest_sha, baseline = CURRENT_MANIFEST_SHA256, CURRENT_SOURCE_BASELINE
    root = Path(__file__).resolve().parents[1]

    def read(name):
        path = root / name
        for part in (path, *path.parents):
            if part == root:
                break
            require(not part.is_symlink() and not part.is_junction(), "INTEGRATION_SOURCE_LINK")
        require(path.is_file(), "INTEGRATION_SOURCE_MISSING")
        return path.read_bytes().replace(b"\r\n", b"\n")

    raw = read(manifest_path)
    require(hashlib.sha256(raw).hexdigest() == manifest_sha,
            "INTEGRATION_CURRENT_MANIFEST_DRIFT")
    manifest = json.loads(raw)
    require(set(manifest) == {"version", "baseline", "purpose", "execution_authorized", "sources"}
            and manifest["version"] == version
            and manifest["baseline"] == baseline
            and manifest["purpose"] == "OFFLINE_INTEGRITY_ONLY"
            and manifest["execution_authorized"] is False, "INTEGRATION_CURRENT_MANIFEST")
    # Read the immutable schema canonically here without changing v1's loader.
    schema_raw = read("docs/acceptance/r1_business_compare_schema_v1.json")
    require(hashlib.sha256(schema_raw).hexdigest() == SCHEMA_SHA256,
            "INTEGRATION_CURRENT_SCHEMA_DRIFT")
    expected = set(json.loads(schema_raw)["sources"]) | {
        "scripts/r1_integration_controller.py", "scripts/r1_integration_seed_loader.py"}
    sources = manifest["sources"]
    require(type(sources) is dict and set(sources) == expected, "INTEGRATION_CURRENT_PATHS")
    for name, digest in sources.items():
        require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                "INTEGRATION_CURRENT_HASH")
        require(hashlib.sha256(read(name)).hexdigest() == digest, "INTEGRATION_BUSINESS_DRIFT")
    return True
