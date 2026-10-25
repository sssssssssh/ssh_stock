"""Rootless, exact-resource PG17 controller. No action occurs on import/construction."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.a42361_contract import Fault, canonical, require, sha
from scripts.a42361_deployment import LocalService, installed
from scripts.a42361_one_shot_store import committed
from scripts.a42361_watchdog import Watchdog

_CREATED = object()


@dataclass(frozen=True)
class CreatedFixture:
    consumption: object
    names: tuple[str, str, str]
    container_id: str
    controller_identity: dict
    pg_identity: dict
    socket_directory: str
    receipt_sha256: str
    _seal: object


def created(value):
    require(
        type(value) is CreatedFixture and value._seal is _CREATED,
        "A42361_TRUSTED_CREATION_REQUIRED",
    )
    committed(value.consumption)
    return value


class FixtureController:
    def __init__(self, deployment=None):
        self.deployment = deployment
        self._authorization = None
        self._commands = 0
        self._started = None

    def _command(self, arguments, payload=None, cleanup=False):
        config = installed(self.deployment)
        authorization = committed(self._authorization)
        require(os.getuid() == config.controller_uid, "A42361_CONTROLLER_PRINCIPAL_MISMATCH")
        if not cleanup:
            require(
                int(time.time()) < authorization.grant.payload.expires_at, "A42361_GRANT_EXPIRED"
            )
        self._commands += 1
        remaining = 2000 - (time.monotonic_ns() - self._started) // 1_000_000
        require(self._commands <= 12 and remaining > 0, "A42361_INFRA_BUDGET_EXCEEDED")
        result = Watchdog(self.deployment, authorization)._run_command(
            config.podman_path,
            config.podman_sha256,
            tuple(arguments),
            authorization.grant.payload_sha256,
            timeout_ms=min(2000, remaining),
            input_bytes=payload,
        )
        require(result[0] == 0, "A42361_CONTROLLER_OPERATION_FAILED")
        return result[1]

    def _inspect(self, name):
        raw = self._command(("container", "inspect", "--format", "{{json .}}", name), cleanup=True)
        try:
            value = json.loads(raw)
            require(type(value) is dict, "A42361_FIXTURE_IDENTITY_UNPROVEN")
            return value
        except Exception:
            raise Fault("A42361_FIXTURE_IDENTITY_UNPROVEN") from None

    def _validate_inspection(self, value, consumption, name, volume):
        p = consumption.grant.payload
        expected_labels = dict(
            a42361_owner=str(installed(self.deployment).controller_uid),
            a42361_fixture=p.binding.fixture_uuid,
            a42361_nonce=p.binding.nonce,
            a42361_payload=consumption.grant.payload_sha256,
        )
        require(
            value.get("Name") == name
            and {
                k: v
                for k, v in value.get("Config", {}).get("Labels", {}).items()
                if k.startswith("a42361_")
            }
            == expected_labels,
            "A42361_FIXTURE_OWNERSHIP_MISMATCH",
        )
        host = value.get("HostConfig", {})
        require(
            host.get("NetworkMode") == "none"
            and not host.get("Privileged")
            and host.get("PidMode") != "host"
            and not host.get("PortBindings")
            and host.get("ReadonlyRootfs") is True
            and "ALL" in host.get("CapDrop", [])
            and "no-new-privileges" in host.get("SecurityOpt", [])
            and host.get("PidsLimit") == 32
            and host.get("Memory") == 512 * 1024**2,
            "A42361_FIXTURE_ISOLATION_UNPROVEN",
        )
        require(
            host.get("NanoCpus") == 1_000_000_000
            or (
                type(host.get("CpuPeriod")) is int
                and host["CpuPeriod"] > 0
                and host.get("CpuQuota") == host["CpuPeriod"]
            ),
            "A42361_FIXTURE_CPU_LIMIT_UNPROVEN",
        )
        require(
            value.get("ImageDigest") == p.image_digest
            and value.get("Config", {}).get("User") == "999:999"
            and any(
                m.get("Name") == volume and m.get("Destination") == "/var/lib/postgresql/data"
                for m in value.get("Mounts", [])
            ),
            "A42361_FIXTURE_IDENTITY_UNPROVEN",
        )
        # Only the fresh data volume and this fixture's socket mount are permitted.
        require(
            all(
                m.get("Destination")
                in ("/var/lib/postgresql/data", "/run/postgresql", "/run/secrets/owner-init")
                for m in value.get("Mounts", [])
            ),
            "A42361_UNAPPROVED_MOUNT",
        )
        return expected_labels

    def create_owned_fixture(self, consumption):
        config = installed(self.deployment)
        consumption = committed(consumption)
        p = consumption.grant.payload
        require(p.image_digest == config.image.rsplit("@", 1)[-1], "A42361_IMAGE_NOT_PINNED")
        self._authorization, self._commands, self._started = consumption, 0, time.monotonic_ns()
        suffix = p.binding.fixture_uuid.replace("-", "")
        name, volume = "a42361-" + suffix, "a42361-" + suffix + "-data"
        secret = name + "-owner-init"
        socket_dir = Path(config.root_directory) / suffix
        journal = LocalService(self.deployment, "consumer")
        reservation = dict(
            event="CREATE_REQUESTED",
            token_id=p.token_id,
            payload_sha256=consumption.grant.payload_sha256,
            names=[name, volume, secret],
        )
        acknowledgement = journal.call("journal", reservation)
        require(
            acknowledgement
            == dict(
                event="CREATE_REQUESTED", committed=True, request_sha256=sha(canonical(reservation))
            ),
            "A42361_RESOURCE_RESERVATION_UNPROVEN",
        )
        try:
            rootless = self._command(("info", "--format", "{{.Host.Security.Rootless}}")).strip()
            require(rootless == b"true", "A42361_ROOTLESS_NOT_PROVEN")
            # No name-exists fallback: conflicts mean failure, never attachment/reuse.
            os.mkdir(socket_dir, 0o700)
            os.chown(socket_dir, config.controller_uid, config.socket_gid)
            os.chmod(socket_dir, 0o770)
            labels = tuple(
                x
                for pair in (
                    ("--label", "a42361_owner=" + str(config.controller_uid)),
                    ("--label", "a42361_fixture=" + p.binding.fixture_uuid),
                    ("--label", "a42361_nonce=" + p.binding.nonce),
                    ("--label", "a42361_payload=" + consumption.grant.payload_sha256),
                )
                for x in pair
            )
            self._command(("volume", "create", *labels, volume))
            # Empty fresh volume is initialized by a fixed, read-only image entrypoint.
            # Owner credentials/init are supplied by the independent PG owner through a
            # private service channel, not env inheritance, public ports or probe argv.
            owner = LocalService(self.deployment, "pg_owner").call(
                "create",
                dict(
                    token_id=p.token_id,
                    payload_sha256=consumption.grant.payload_sha256,
                    fixture_uuid=p.binding.fixture_uuid,
                    nonce=p.binding.nonce,
                    marker_sha256=p.binding.marker_sha256,
                    image_digest=p.image_digest,
                ),
            )
            require(
                type(owner) is dict
                and set(owner) == {"credential_reference", "init_sha256", "bootstrap_secret_hex"}
                and type(owner["bootstrap_secret_hex"]) is str
                and len(owner["bootstrap_secret_hex"]) == 64
                and all(c in "0123456789abcdef" for c in owner["bootstrap_secret_hex"])
                and sha(owner["bootstrap_secret_hex"].encode()) == owner["credential_reference"],
                "A42361_OWNER_NOT_CONFIGURED",
            )
            # New ephemeral secret goes through stdin, never argv/env/artifacts. It is
            # inaccessible to the worker and bound by an independently journaled ID.
            secret_id = (
                self._command(
                    ("secret", "create", secret, "-"),
                    payload=owner.pop("bootstrap_secret_hex").encode(),
                )
                .decode("ascii")
                .strip()
            )
            require(bool(secret_id) and len(secret_id) <= 64, "A42361_SECRET_ID_UNPROVEN")
            secret_record = dict(
                event="SECRET_CREATED",
                token_id=p.token_id,
                payload_sha256=consumption.grant.payload_sha256,
                secret_id=secret_id,
                names=[name, volume, secret],
            )
            require(
                journal.call("journal", secret_record)
                == dict(
                    event="SECRET_CREATED",
                    committed=True,
                    request_sha256=sha(canonical(secret_record)),
                ),
                "A42361_RESOURCE_RESERVATION_UNPROVEN",
            )
            raw = self._command(
                (
                    "run",
                    "--detach",
                    "--pull=never",
                    "--name",
                    name,
                    *labels,
                    "--network=none",
                    "--userns=keep-id:uid=999,gid=999",
                    "--user=999:999",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--cpus=1",
                    "--memory=512m",
                    "--pids-limit=32",
                    "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m",
                    "--secret=" + secret + ",type=mount,target=owner-init,uid=999,mode=0400",
                    "--env=POSTGRES_PASSWORD_FILE=/run/secrets/owner-init",
                    "--env=POSTGRES_USER=g1_owner",
                    "--env=POSTGRES_DB=a42361_" + suffix,
                    "-v",
                    volume + ":/var/lib/postgresql/data:U",
                    "--mount=type=bind,source=" + str(socket_dir) + ",target=/run/postgresql",
                    config.image,
                    "-c",
                    "listen_addresses=",
                    "-c",
                    "unix_socket_directories=/run/postgresql",
                    "-c",
                    "unix_socket_permissions=0770",
                )
            )
            container_id = raw.decode("ascii").strip()
            require(
                len(container_id) == 64 and all(c in "0123456789abcdef" for c in container_id),
                "A42361_FIXTURE_IDENTITY_UNPROVEN",
            )
            inspection = self._inspect(name)
            self._validate_inspection(inspection, consumption, name, volume)
            pg = LocalService(self.deployment, "pg_owner").call(
                "receipt",
                dict(
                    purpose="INITIALIZE_AND_ATTEST_PG17",
                    container_id=container_id,
                    token_id=p.token_id,
                    fixture_uuid=p.binding.fixture_uuid,
                    nonce=p.binding.nonce,
                    marker_sha256=p.binding.marker_sha256,
                    init_max_sql=8,
                    init_ms=2000,
                ),
            )
            require(
                type(pg) is dict
                and set(pg)
                == {
                    "pg_major",
                    "system_identifier_sha256",
                    "backend_start_sha256",
                    "fixture_uuid",
                    "nonce",
                    "marker_sha256",
                    "container_id",
                    "probe_role_sha256",
                    "owner_role_sha256",
                    "namespace_sha256",
                    "init_sql_count",
                    "init_completed",
                    "role_verified",
                    "credential_reference",
                },
                "A42361_PG_IDENTITY_UNPROVEN",
            )
            require(
                pg["pg_major"] == 17
                and pg["container_id"] == container_id
                and pg["fixture_uuid"] == p.binding.fixture_uuid
                and pg["nonce"] == p.binding.nonce
                and pg["marker_sha256"] == p.binding.marker_sha256
                and pg["init_completed"] is True
                and pg["role_verified"] is True
                and type(pg["init_sql_count"]) is int
                and 0 < pg["init_sql_count"] <= 8
                and pg["probe_role_sha256"] != pg["owner_role_sha256"],
                "A42361_PG_IDENTITY_UNPROVEN",
            )
            identity = dict(
                container_id=container_id,
                image_digest=p.image_digest,
                inspection_sha256=sha(canonical(inspection)),
                secret_id=secret_id,
            )
            require(
                time.monotonic_ns() - self._started <= 2_000_000_000, "A42361_INFRA_BUDGET_EXCEEDED"
            )
            return CreatedFixture(
                consumption,
                (name, volume, secret),
                container_id,
                identity,
                pg,
                str(socket_dir),
                sha(canonical(dict(controller=identity, pg=pg))),
                _CREATED,
            )
        except BaseException as error:
            # Partial creation is NOT a destroy receipt. Journal remains for the
            # independent owner to reconcile; never widen cleanup to an unproved target.
            try:
                journal.call(
                    "journal",
                    dict(
                        event="INCOMPLETE",
                        token_id=p.token_id,
                        payload_sha256=consumption.grant.payload_sha256,
                        names=[name, volume, secret],
                    ),
                )
            except Exception:
                pass
            raise Fault(
                error.code if isinstance(error, Fault) else "A42361_FIXTURE_CREATE_INCOMPLETE"
            ) from None

    def destroy_owned(self, fixture):
        config = installed(self.deployment)
        fixture = created(fixture)
        self._authorization = fixture.consumption
        self._commands, self._started = 0, time.monotonic_ns()
        name, volume, secret = fixture.names
        self._validate_inspection(self._inspect(name), fixture.consumption, name, volume)
        audit = LocalService(self.deployment, "absence_auditor")
        request = dict(
            fixture_uuid=fixture.consumption.grant.payload.binding.fixture_uuid,
            container_id=fixture.container_id,
            creation_sha256=fixture.receipt_sha256,
            payload_sha256=fixture.consumption.grant.payload_sha256,
            names=[name, volume, secret],
        )
        requested = audit.call("journal", dict(event="DESTROY_REQUESTED", **request))
        require(
            requested == dict(event="DESTROY_REQUESTED", **request), "A42361_CLEANUP_NOT_VERIFIED"
        )
        try:
            self._command(("stop", "--time=0", name), cleanup=True)
            self._command(("rm", name), cleanup=True)
            # Recheck volume labels independently before removal, not a broad prune.
            raw = self._command(
                ("volume", "inspect", "--format", "{{json .Labels}}", volume), cleanup=True
            )
            labels = json.loads(raw)
            p = fixture.consumption.grant.payload
            require(
                labels
                == dict(
                    a42361_owner=str(config.controller_uid),
                    a42361_fixture=p.binding.fixture_uuid,
                    a42361_nonce=p.binding.nonce,
                    a42361_payload=fixture.consumption.grant.payload_sha256,
                ),
                "A42361_FIXTURE_OWNERSHIP_MISMATCH",
            )
            self._command(("volume", "rm", volume), cleanup=True)
            secret_identity = json.loads(
                self._command(("secret", "inspect", "--format", "{{json .}}", secret), cleanup=True)
            )
            require(
                secret_identity.get("ID") == fixture.controller_identity["secret_id"]
                and secret_identity.get("Spec", {}).get("Name") == secret,
                "A42361_FIXTURE_OWNERSHIP_MISMATCH",
            )
            self._command(("secret", "rm", secret), cleanup=True)
            destroyed = audit.call("journal", dict(event="DESTROYED", **request))
            absent = audit.call("absent", request)
            require(
                destroyed == dict(event="DESTROYED", **request)
                and absent == dict(event="ABSENT", absent=True, **request),
                "A42361_CLEANUP_NOT_VERIFIED",
            )
            require(
                time.monotonic_ns() - self._started <= 2_000_000_000, "A42361_CLEANUP_NOT_VERIFIED"
            )
            return dict(requested=requested, destroyed=destroyed, absent=absent)
        except BaseException:
            raise Fault("A42361_CLEANUP_NOT_VERIFIED") from None
