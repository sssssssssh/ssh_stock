"""Third exact overlay; history bytes and full committed trees stay independently bound."""

import hashlib
import json
import os
import re
import stat
from pathlib import PurePosixPath

from scripts.a42361_contract import BASELINE

SOURCES = tuple(
    f"scripts/a42361_{n}.py"
    for n in (
        "contract",
        "deployment",
        "trust_verifier",
        "one_shot_store",
        "fixture_controller",
        "live_probe_worker",
        "watchdog",
        "trusted_evidence",
        "control_service",
        "source_guard",
        "offline_cases",
    )
)
TESTS = tuple(
    f"tests/unit/test_a42361_{n}.py"
    for n in ("trust", "store", "controller_watchdog", "worker_evidence", "source_entrypoints")
)
DOCS = tuple(
    f"docs/acceptance/a42361_{n}.md"
    for n in (
        "baseline",
        "dependency_review",
        "trust_model",
        "approval_and_deploy_runbook",
        "capability_matrix",
        "unresolved_methods",
        "test_traceability",
        "closeout",
    )
)
INFRA = (
    "infra/g1_control_plane/001_control.sql",
    "infra/g1_control_plane/README.md",
    *(
        "infra/g1_harness/" + n
        for n in (
            "pg17-spec.json",
            "init_owner.sql",
            "probe_roles.sql",
            "runtime-lock.json",
            "deployment.example.json",
            "README.md",
        )
    ),
)
AUTHORITY = frozenset(
    (
        "README.md",
        "PROJECT_RULES.md",
        "docs/股票机会发现系统_PRD_V1.0.md",
        "docs/股票机会发现系统_系统设计_V1.0.md",
    )
)
OLD_TEST = "tests/unit/test_a4236_source_guard.py"
OLD_GUARD = "scripts/a4235_capability_guard.py"
MANIFEST = "docs/acceptance/a42361_overlay_manifest.json"
STAGE_PATHS = frozenset(
    (*SOURCES, *TESTS, *DOCS, *INFRA, *AUTHORITY, OLD_TEST, OLD_GUARD, MANIFEST)
)
PINNED = STAGE_PATHS - {OLD_GUARD, MANIFEST}


def normalized_guard(raw):
    # A manifest cannot contain its own digest through the guard. The one digest
    # literal is normalized; ALL other guard bytes are pinned. Raw bytes still must
    # match independently fetched HEAD, and the literal must match the manifest hash.
    pattern = rb"LIVE_MANIFEST_SHA = '[0-9a-f]{64}'"
    assert len(re.findall(pattern, raw)) == 1
    return re.sub(pattern, b"LIVE_MANIFEST_SHA = '" + b"0" * 64 + b"'", raw)


def validate_paths(actual):
    from scripts.a4235_calibration_adapter_contract import require

    require(set(actual) == STAGE_PATHS, "A4235_FROZEN_FILE_CHANGED")


def verify_full_worktree(g, root, head):
    """Independent full HEAD tree walk; never trusts index flags or status alone.

    Does not change PROTECTED or its historical tree digest. NUL records preserve
    Unicode/newlines; held no-follow directory/file FDs bind reads across rename races.
    Only tracked HEAD blobs are read; ignored .env and runtime files are not traversed.
    """
    from scripts.a4235_calibration_adapter_contract import Fault

    def integrity_meta(value):
        # A normal read can advance atime; it is not a content/ownership change.
        return tuple(
            getattr(value, key)
            for key in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_nlink",
                "st_uid",
                "st_gid",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        )

    root_fd = None
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_meta = os.fstat(root_fd)
        rows = g.git(root, "ls-tree", "-r", "-z", head)
        g.require(rows.endswith(b"\0"), "A4235_HEAD_BYTES_MISMATCH")
        seen = set()
        for row in rows[:-1].split(b"\0"):
            metadata, name = row.split(b"\t", 1)
            mode, kind, oid = metadata.split()
            relative = PurePosixPath(name.decode("utf-8", "strict"))
            g.require(
                mode in (b"100644", b"100755")
                and kind == b"blob"
                and re.fullmatch(b"[0-9a-f]{40}", oid) is not None
                and not relative.is_absolute()
                and relative.parts
                and not {"..", ".git"}.intersection(relative.parts)
                and str(relative).encode() == name
                and name not in seen,
                "A4235_HEAD_BYTES_MISMATCH",
            )
            seen.add(name)
            parent = os.dup(root_fd)
            descriptor = None
            try:
                for part in relative.parts[:-1]:
                    next_fd = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                    )
                    os.close(parent)
                    parent = next_fd
                descriptor = os.open(
                    relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                )
                before = os.fstat(descriptor)
                g.require(
                    stat.S_ISREG(before.st_mode)
                    and before.st_nlink == 1
                    and before.st_size <= 16_000_000
                    and bool(before.st_mode & stat.S_IXUSR) == (mode == b"100755"),
                    "A4235_HEAD_BYTES_MISMATCH",
                )
                raw = bytearray()
                while True:
                    chunk = os.read(descriptor, min(65536, 16_000_001 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    g.require(len(raw) <= 16_000_000, "A4235_HEAD_BYTES_MISMATCH")
                g.require(
                    len(raw) == before.st_size
                    and integrity_meta(os.fstat(descriptor)) == integrity_meta(before)
                    and integrity_meta(os.stat(relative.name, dir_fd=parent, follow_symlinks=False))
                    == integrity_meta(before),
                    "A4235_HEAD_BYTES_MISMATCH",
                )
                git_blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
                g.require(
                    hashlib.sha1(git_blob).hexdigest().encode() == oid
                    and g.path_sha(root.joinpath(*relative.parts))
                    == hashlib.sha256(raw).hexdigest(),
                    "A4235_HEAD_BYTES_MISMATCH",
                )
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                os.close(parent)
        g.require(
            integrity_meta(os.fstat(root_fd)) == integrity_meta(root_meta)
            and integrity_meta(root.stat()) == integrity_meta(root_meta),
            "A4235_HEAD_BYTES_MISMATCH",
        )
    except Fault:
        raise
    except Exception:
        raise Fault("A4235_HEAD_BYTES_MISMATCH") from None
    finally:
        if root_fd is not None:
            os.close(root_fd)


def validate(g, root, head):
    """Uses guard's independent git/path readers, so legacy tamper tests still apply."""
    if hasattr(g, "COMPLETE_MANIFEST_SHA"):
        from scripts.a42363_complete_guard import validate as validate_complete

        return validate_complete(g, root, head)
    if hasattr(g, "CLOSEOUT_MANIFEST_SHA"):
        from scripts.a42363_source_guard import validate as validate_closeout

        return validate_closeout(g, root, head)
    if hasattr(g, "SERVICE_MANIFEST_SHA"):
        from scripts.a42362_source_guard import validate as validate_service

        return validate_service(g, root, head)
    require = g.require
    validate_paths(
        set(
            g.git(root, "diff", "--no-ext-diff", "--name-only", "-z", BASELINE).decode().split("\0")
        )
        - {""}
    )
    require(g.path_sha(root / MANIFEST) == g.LIVE_MANIFEST_SHA, "A4235_LIVE_OVERLAY_INVALID")
    manifest = json.loads((root / MANIFEST).read_bytes())
    require(
        set(manifest)
        == {
            "schema_version",
            "baseline_sha",
            "stage_paths",
            "patch_sha256",
            "old_sha256",
            "normalized_guard_sha256",
        }
        and manifest["schema_version"] == "a42361.exact-overlay.v1"
        and manifest["baseline_sha"] == BASELINE
        and manifest["stage_paths"] == sorted(STAGE_PATHS)
        and set(manifest["patch_sha256"]) == PINNED
        and set(manifest["old_sha256"]) == {OLD_GUARD, OLD_TEST},
        "A4235_LIVE_OVERLAY_INVALID",
    )
    for name in STAGE_PATHS:
        raw = (root / name).read_bytes()
        current = g.path_sha(root / name)
        require(raw == g.git(root, "show", f"{head}:{name}"), "A4235_HEAD_BYTES_MISMATCH")
        if name in PINNED:
            require(current == manifest["patch_sha256"][name], "A4235_LIVE_OVERLAY_INVALID")
        if name in (OLD_GUARD, OLD_TEST):
            old = g.git(root, "show", f"{BASELINE}:{name}")
            require(
                hashlib.sha256(old).hexdigest() == manifest["old_sha256"][name],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name == OLD_GUARD:
            require(
                hashlib.sha256(normalized_guard(raw)).hexdigest()
                == manifest["normalized_guard_sha256"],
                "A4235_LIVE_OVERLAY_INVALID",
            )
        if name in AUTHORITY:
            require(
                raw.startswith(g.git(root, "show", f"{BASELINE}:{name}")),
                "A4235_FROZEN_FILE_CHANGED",
            )
    # Infra is intentionally NOT inserted in historic PROTECTED: doing so would
    # change its frozen tree digest. This separate full-tree read closes hidden index.
    for row in g.git(root, "ls-tree", "-r", head, "--", "infra").splitlines():
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.split()
        require(mode in {b"100644", b"100755"} and kind == b"blob", "A4235_HEAD_BYTES_MISMATCH")
        path = root / name.decode()
        g.path_sha(path)
        raw = path.read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
            == oid,
            "A4235_HEAD_BYTES_MISMATCH",
        )
    # Keep the historical first-error contract: a committed-byte substitution
    # against the six original immutable patch pins must still be classified as
    # OVERLAY_BYTES_MISMATCH, not masked by the additional HEAD tree comparison.
    # This duplicates (never waives) the old check; the complete byte walk follows.
    require(
        g.path_sha(root / g.OVERLAY_MANIFEST) == g.OVERLAY_MANIFEST_SHA,
        "A4235_OVERLAY_MANIFEST_INVALID",
    )
    legacy = json.loads((root / g.OVERLAY_MANIFEST).read_bytes())
    require(set(legacy["patch_sha256"]) == g.PATCH_PATHS, "A4235_OVERLAY_MANIFEST_INVALID")
    for name in g.PATCH_PATHS:
        require(
            g.path_sha(root / name) == legacy["patch_sha256"][name], "A4235_OVERLAY_BYTES_MISMATCH"
        )
    verify_full_worktree(g, root, head)
    require(
        head == g.git(root, "rev-parse", "HEAD").decode().strip()
        and not g.git(root, "status", "--porcelain").strip(),
        "A4235_DIRTY_TREE",
    )
    return g.LIVE_MANIFEST_SHA


def independent_binding(run_id, attempt, fixture_uuid, nonce, marker_sha256):
    from scripts import a4235_capability_guard as g
    from scripts.a42361_contract import Binding

    identity = g.expected_identity(run_id=run_id, attempt=attempt)
    return Binding(
        identity=identity,
        overlay_sha256=g.overlay_fingerprint(),
        fixture_uuid=fixture_uuid,
        nonce=nonce,
        marker_sha256=marker_sha256,
    )
