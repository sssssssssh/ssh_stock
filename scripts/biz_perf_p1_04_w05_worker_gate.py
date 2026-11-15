"""Inert container entry and fixed-file offline topology inspection, never a permit.

main ignores all input and does no file/environment discovery. Only explicit
review() reads the fixed repository JSON overlay, never secrets or the PG spec.
Trusted stable repository ancestors are required; this is not a hostile-Python,
filesystem-race, image-authenticity or Compose-merge security boundary.
"""

import json
import re
import stat
from pathlib import Path

SPEC_PATH = Path(__file__).absolute().parents[1] / "infra/biz_perf_w05/compose.worker.yaml"
MAX_BYTES = 32 * 1024
_UNSET = object()


def _expected_overlay():
    return {
        "name": "w05-${W05_RUN_UUID:?missing}",
        "services": {"w05_worker": {
            "image": "${W05_WORKER_PINNED_IMAGE:?missing}", "pull_policy": "never",
            "platform": "linux/amd64", "profiles": ["w05-worker-manual"],
            "restart": "no", "init": True, "user": "10001:10001", "working_dir": "/app",
            "entrypoint": ["python", "-B", "-m", "scripts.biz_perf_p1_04_w05_worker_gate"],
            "command": ["review-offline"], "read_only": True, "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"], "pids_limit": 64,
            "mem_limit": "3g", "memswap_limit": "3g",
            "environment": {
                "W05_DB_HOST": "pg17", "W05_DB_PORT": "5432",
                "W05_DB_NAME": "w05_lab_test", "W05_DB_USER": "w05_lab_worker",
            },
            "networks": ["private"],
        }},
    }


def _report(status="BLOCKED", valid=False):
    return dict(
        status=status, spec_structure_valid=valid, execution_available=False,
        real_network_verified=False, image_authenticity_verified=False,
        root_attempts=0, B_GATE="NOT_APPROVED", TARGETED_PG17_GATE="NOT_APPROVED",
        AUTHORIZATION="AUTHORIZATION_PENDING", BUDGET="DRAFT_NOT_APPROVED",
        HOTSPOT="NONE_PROVEN", REAL_PG17="NOT_RUN", REAL_WORKER="NOT_RUN",
        credential="CREDENTIAL_NOT_WIRED",
    )


def inspect_overlay(spec: dict, *, pinned_image=_UNSET):
    """Exact template only; optional explicit image checks syntax, never provenance.

    No interpolation, environment, owner/approval inputs or mutable authorization.
    A matching invented digest cannot clear gates or attest the real image.
    """
    try:
        valid = type(spec) is dict and json.dumps(spec, sort_keys=True, allow_nan=False) == (
            json.dumps(_expected_overlay(), sort_keys=True, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        valid = False
    if not valid:
        return _report()
    if pinned_image is not _UNSET and (
        type(pinned_image) is not str or re.fullmatch(
            r"[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._:-]*)*@sha256:[0-9a-f]{64}",
            pinned_image) is None
    ):
        return _report(valid=True)
    return _report("TOPOLOGY_SPEC_REVIEWABLE_ONLY", valid=True)


def _read_fixed_spec():
    # No arbitrary input path or secret references. Reject links/reparse points
    # throughout the ancestry and identity changes observed across the read.
    for path in (SPEC_PATH, *SPEC_PATH.parents):
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError
    info = SPEC_PATH.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
        raise ValueError
    with open(SPEC_PATH, "rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    after = SPEC_PATH.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode", "st_nlink")
    if len(raw) > MAX_BYTES or any(getattr(after, key) != getattr(info, key) for key in fields):
        raise ValueError
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError


def review():
    """Explicit read-only inspection of the sole fixed file; never called by main."""
    try:
        raw = _read_fixed_spec()
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            return _report()
        return inspect_overlay(json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                          parse_constant=_reject_constant))
    except (OSError, ValueError, TypeError, RecursionError):
        return _report()


def main(argv=None):
    # Deliberately ignore argv, sys.argv and all self-declared authorization.
    # Even review-offline refuses before reading any spec, environment or DB.
    print(json.dumps(_report("EXECUTION_NOT_AVAILABLE"), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
