"""Fixed-file offline spec review. Always BLOCKED; no live operations or permits.

The Compose document uses the JSON subset of YAML: no aliases, includes or
general YAML loader. Inputs are explicit memory values, never environment reads.
Trusted, stable repository ancestors are required; hostile filesystem races are
outside this limited static check. No secret reference is opened or exported.
"""

import json
import re
import stat
import sys
from pathlib import Path
from uuid import UUID

SPEC_PATH = Path(__file__).absolute().parents[1] / "infra/biz_perf_w05/compose.pg17.yaml"
MAX_BYTES = 32 * 1024
RUN_VAR = "${W05_RUN_UUID:?missing}"
IMAGE_VAR = "${W05_PG17_PINNED_IMAGE:?missing}"
SECRET_VAR = "${W05_PG17_PASSWORD_SECRET_FILE:?missing}"
PENDING = (
    "IMAGE_AUTHENTICITY", "LINUX_PG17_EXTERNAL_OBSERVATION", "OWNERSHIP_AND_FRESHNESS",
    "VOLUME_NETWORK_NAMES_ABSENT_BEFORE_CREATION", "SECRET_OUTSIDE_REPOSITORY_AND_PERMISSIONS",
    "PG17_MARKER_OFFLINE_ONLINE_SYSTEM_IDENTIFIER", "CGROUP_MEMORY_AND_DISK_IO_CPU_LIMITS",
    "REAL_EXECUTOR_AND_ROOT_POST_COLLECTION", "COST_AND_BUDGET_SIGNOFF",
    "NAMED_OPERATOR_AND_NEW_SINGLE_RUN_AUTHORIZATION", "MANUAL_STOP_AND_OWNED_CLEANUP",
)


def _expected_spec():
    """Small exact allowlist; unknown fields or changed variable structure fail."""
    labels = {"w05.run": RUN_VAR}
    return {
        "name": "w05-" + RUN_VAR,
        "services": {"pg17": {
            "image": IMAGE_VAR, "platform": "linux/amd64", "profiles": ["w05-manual"],
            "restart": "no", "stop_signal": "SIGINT", "stop_grace_period": "30s",
            "mem_limit": "4g", "memswap_limit": "4g",
            "environment": {
                "POSTGRES_DB": "w05_lab_test", "POSTGRES_USER": "w05_lab_owner",
                "POSTGRES_PASSWORD_FILE": "/run/secrets/pg_password",
                "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256 --auth-local=scram-sha-256",
                "PGDATA": "/var/lib/postgresql/data/pgdata",
            },
            "command": ["postgres", "-c", "v14.test_instance=" + RUN_VAR],
            "secrets": ["pg_password"],
            "volumes": [{"type": "volume", "source": "pgdata",
                         "target": "/var/lib/postgresql/data", "volume": {"nocopy": True}}],
            "networks": ["private"], "labels": labels,
        }},
        "volumes": {"pgdata": {"name": "w05-" + RUN_VAR + "-pgdata", "labels": labels}},
        "networks": {"private": {"name": "w05-" + RUN_VAR + "-private", "internal": True,
                                 "driver": "bridge", "labels": labels}},
        "secrets": {"pg_password": {"file": SECRET_VAR}},
    }


def _read_fixed_spec():
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
    # Reading can legitimately update atime. Compare content/identity fields,
    # retaining size, modification time, mode and link count checks.
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


def _load_spec():
    raw = _read_fixed_spec()
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=_reject_constant)


def _valid_inputs(values):
    if type(values) is not dict or set(values) != {
        "run_uuid", "pinned_image", "password_secret_file",
    } or any(type(value) is not str for value in values.values()):
        return False
    run = values["run_uuid"]
    try:
        identity = UUID(run)
        if str(identity) != run or identity.version != 4 or identity.int == 0:
            return False
    except ValueError:
        return False
    # Official repository + explicit major only. Digest existence, contents and
    # provenance are NOT authenticated, even when this format matches.
    image_ok = re.fullmatch(r"docker\.io/library/postgres:17@sha256:[0-9a-f]{64}",
                            values["pinned_image"]) is not None
    # Future Linux reference convention only; neither path nor content is read.
    secret_ok = values["password_secret_file"] == f"/run/w05-secrets/{run}/pg_password"
    return image_ok and secret_ok


def _report():
    return dict(
        mode="OFFLINE_LAB_SPEC_REVIEW", status="BLOCKED", live_resource_verified=False,
        root_attempts=0, B_GATE="NOT_APPROVED", TARGETED_PG17_GATE="NOT_APPROVED",
        authorization="AUTHORIZATION_PENDING", hotspot="NONE_PROVEN",
        REAL_PG17="NOT_RUN", REAL_WORKER="NOT_RUN", spec_structure_valid=False,
        input_format_valid=False, resources={}, pending_checks=list(PENDING),
        budget=dict(status="DRAFT_NOT_APPROVED", pg_ram_bytes=4 * 1024**3,
                    volume_draft_bytes=10 * 1024**3, memory="DECLARED_NOT_LIVE_VERIFIED",
                    disk_quota="NOT_ENFORCED", disk_io="NOT_ENFORCED",
                    cgroup="NOT_ENFORCED", cpu_capacity="NOT_ENFORCED"),
    )


def review(values=None):
    """Read only the fixed spec; self-declarations cannot clear live blockers.

    No environment lookup, signature/lease framework, execution adapter or
    evidence write. A correctly shaped invented digest still leaves BLOCKED.
    """
    result = _report()
    try:
        spec = _load_spec()
        # Canonical JSON also distinguishes booleans from integers.
        if json.dumps(spec, sort_keys=True) != json.dumps(_expected_spec(), sort_keys=True):
            result["pending_checks"].insert(0, "SPEC_STRUCTURE_REJECTED")
            return result
        result["spec_structure_valid"] = True
    except (OSError, ValueError, TypeError, RecursionError):
        result["pending_checks"].insert(0, "SPEC_READ_OR_STRUCTURE_REJECTED")
        return result
    if not _valid_inputs(values):
        result["pending_checks"].insert(0, "EXPLICIT_INPUT_MISSING_OR_REJECTED")
        return result
    result["input_format_valid"] = True
    prefix = "w05-" + values["run_uuid"]
    result["resources"] = dict(project=prefix, volume=prefix + "-pgdata",
                               network=prefix + "-private", database="w05_lab_test")
    return result


def main(argv=None):
    # No configurable path, environment substitution or operational CLI. Even
    # valid review returns 2 because ownership/cost/live sources remain unknown.
    args = sys.argv[1:] if argv is None else argv
    result = review() if args == ["review-offline"] else _report()
    if args != ["review-offline"]:
        result["pending_checks"].insert(0, "CLI_REJECTED")
    print(json.dumps(result, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
