"""Offline image plan/source and supply-chain verification, never Podman build/start."""

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from scripts.a42361_contract import canonical, sha
from scripts.a42363_contract import require

IMAGE_FILES = ("Containerfile", "bootstrap.sh", "bootstrap.c", "pg_hba.template", "healthcheck.sh")
ENTRYPOINT = "/usr/local/libexec/space-g1-pg17-bootstrap"
HBA = (
    b"local all postgres scram-sha-256\nlocal all all scram-sha-256\n"
    b"host all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n"
)


def pinned_image(value):
    require(
        type(value) is str
        and re.fullmatch(r"[a-z0-9][a-z0-9./:_-]{1,200}@sha256:[0-9a-f]{64}", value) is not None
        and value[-64:] not in {"0" * 64, "f" * 64},
        "IMAGE_DIGEST_REQUIRED",
    )
    return value


def verify_uid_maps(uid_map, gid_map, runtime_uid, runtime_gid, socket_owner):
    def mapped(raw):
        require(type(raw) is str and len(raw) <= 4096, "IMAGE_UID_MAP")
        ranges = []
        for line in raw.splitlines():
            values = line.split()
            require(len(values) == 3 and all(v.isdecimal() for v in values), "IMAGE_UID_MAP")
            inside, outside, count = map(int, values)
            require(
                count > 0 and inside + count <= 2**32 and outside + count <= 2**32, "IMAGE_UID_MAP"
            )
            require(
                all(
                    (inside + count <= a or a + n <= inside)
                    and (outside + count <= b or b + n <= outside)
                    for a, b, n in ranges
                ),
                "IMAGE_UID_MAP_OVERLAP",
            )
            ranges.append((inside, outside, count))
        matches = [
            outside + 999 - inside
            for inside, outside, count in ranges
            if inside <= 999 < inside + count
        ]
        require(len(matches) == 1, "IMAGE_UID_MAP")
        return matches[0]

    require(
        mapped(uid_map) == runtime_uid
        and mapped(gid_map) == runtime_gid
        and socket_owner == (runtime_uid, runtime_gid, 0o770),
        "IMAGE_KEEP_ID_UNPROVEN",
    )
    return dict(container_uid=999, container_gid=999, mapping_verified=True, qualifies=False)


def validate_image_source(root):
    directory = Path(root) / "infra/g1_pg17_image"
    require(all(not p.is_symlink() for p in (directory, *directory.parents)), "IMAGE_SOURCE_PATH")
    for name in IMAGE_FILES:
        path = directory / name
        require(
            path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000,
            "IMAGE_SOURCE_PATH",
        )
    files = {n: (directory / n).read_bytes().replace(b"\r\n", b"\n") for n in IMAGE_FILES}
    require(files["pg_hba.template"] == HBA, "IMAGE_HBA_DRIFT")
    recipe = files["Containerfile"].decode("ascii")
    require(
        'ENTRYPOINT ["' + ENTRYPOINT + '"]' in recipe and "USER 999:999" in recipe,
        "IMAGE_ENTRYPOINT",
    )
    instructions = [line.split(None, 1)[0].upper() for line in recipe.splitlines() if line.strip()]
    require(
        set(instructions) <= {"ARG", "FROM", "WORKDIR", "COPY", "RUN", "USER", "ENTRYPOINT"}
        and instructions.count("RUN") == 1
        and instructions.count("FROM") == 2
        and instructions.count("ENTRYPOINT") == instructions.count("USER") == 1,
        "IMAGE_NETWORK_OR_HIDDEN_HEALTH",
    )
    require(
        [line for line in recipe.splitlines() if line.startswith("RUN ")]
        == [
            "RUN cc -std=c17 -O2 -Wall -Wextra -Werror -D_FORTIFY_SOURCE=2 "
            "-fstack-protector-strong -Wl,-z,relro,-z,now "
            "-o /src/bootstrap-native /src/bootstrap.c"
        ],
        "IMAGE_BUILD_COMMAND_DRIFT",
    )
    source = files["bootstrap.c"].decode("ascii")
    require(
        all(
            s in source
            for s in (
                "initdb",
                "--pwfile=/proc/self/fd/",
                "scram-sha-256",
                "listen_addresses=",
                "O_NOFOLLOW",
                "fsync",
                "mkdirat",
                "clearenv()",
            )
        ),
        "BOOTSTRAP_SOURCE",
    )
    return dict(
        bootstrap_image="SOURCE_IMPLEMENTED_UNDEPLOYED",
        files={n: sha(v) for n, v in files.items()},
        entrypoint=ENTRYPOINT,
        physical="NOT_RUN_NOT_AUTHORIZED",
        qualifies=False,
    )


def build_plan(root, builder_image, pg17_base):
    source = validate_image_source(root)
    builder_image, pg17_base = pinned_image(builder_image), pinned_image(pg17_base)
    return dict(
        source=source,
        version="a42364.image-plan.v1",
        approved=False,
        operation=(
            "podman",
            "build",
            "--pull=never",
            "--network=none",
            "--no-cache",
            "--build-arg",
            "BUILDER_IMAGE=" + builder_image,
            "--build-arg",
            "PG17_BASE=" + pg17_base,
            "--file",
            "infra/g1_pg17_image/Containerfile",
            "infra/g1_pg17_image",
        ),
        base_images=(builder_image, pg17_base),
        measured=False,
        physical="NOT_RUN_NOT_AUTHORIZED",
    )


def verify_bundle(directory, verifier):
    """Independent verifier must be installed/pinned; signature bytes are external input.

    No key/signature generator, downloads, CLI signer or digest-filling fallback.
    """
    directory = Path(directory)
    raw = (directory / "manifest.json").read_bytes()
    require(len(raw) <= 65536 and not (directory / "manifest.json").is_symlink(), "SUPPLY_MANIFEST")
    data = json.loads(raw)
    require(
        set(data) == {"version", "base_images", "image_digest", "source_sha256", "artifacts"}
        and data["version"] == "a42364.supply-chain.v1",
        "SUPPLY_SCHEMA",
    )
    require(len(data["base_images"]) == 2, "SUPPLY_BASE_IMAGES")
    for image in data["base_images"]:
        pinned_image(image)
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", data["image_digest"]) is not None, "SUPPLY_IMAGE")
    require(
        set(data["artifacts"]) == {"image.oci", "sbom.spdx.json", "source.tar"}, "SUPPLY_ARTIFACTS"
    )
    for name, expected in data["artifacts"].items():
        path = directory / name
        require(path.is_file() and not path.is_symlink(), "SUPPLY_ARTIFACT")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        require(digest.hexdigest() == expected, "SUPPLY_CHECKSUM")
    require(verifier is not None, "EXTERNAL_SUPPLY_SIGNATURE_REQUIRED")
    verifier.verify(canonical(data), (directory / "manifest.sig").read_bytes())
    return dict(
        status="OFFLINE_SIGNATURE_VERIFIED",
        manifest_sha256=sha(raw),
        qualifies=False,
        physical="NOT_RUN_NOT_AUTHORIZED",
    )


def build_source_archive(root):
    """Reproducible offline Python package; no database, wheel download or image build."""
    directory = Path(root) / "scripts"
    names = sorted(
        {"__init__.py", "a42_artifacts.py", *(path.name for path in directory.glob("a423*.py"))}
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = directory / name
            if name == "__init__.py":
                raw = b""  # Turn the repository's namespace package into an importable ZIP package.
            else:
                require(path.is_file() and not path.is_symlink(), "SOURCE_ARCHIVE_PATH")
                raw = path.read_bytes().replace(b"\r\n", b"\n")
            require(len(raw) <= 1_000_000, "SOURCE_ARCHIVE_SIZE")
            info = zipfile.ZipInfo("scripts/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100444 << 16
            archive.writestr(info, raw)
    return buffer.getvalue()


class InstalledSupplyVerifier:
    def __init__(self, package):
        from scripts.a42364_installation_verify import installed_package

        self.package = installed_package(package)

    def verify(self, raw, signatures):
        import base64

        from scripts.a42361_contract import checked
        from scripts.a42364_protocol_decision import ROLES, Signature

        data = json.loads(signatures)
        require(type(data) is list and len(data) == 2, "SUPPLY_SIGNATURE_SCHEMA")
        values = tuple(checked(Signature, s) for s in data)
        require({s.role for s in values} == ROLES, "SUPPLY_INDEPENDENT_SIGNATURES")
        require(
            sha(raw) == self.package.document.image_manifest_sha256, "SUPPLY_INSTALLATION_BINDING"
        )
        for signature in values:
            key = self.package.signing_key(signature.role, signature.kid)
            value = base64.b64decode(signature.signature_b64, validate=True)
            require(len(value) == 64, "SUPPLY_SIGNATURE")
            self.package.verifier.verify_signature(key, raw, value)


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", nargs=2)
    group.add_argument("--verify")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.plan:
        print(json.dumps(build_plan(root, *args.plan)))
        return 2  # A source plan is never a build/run permission.
    # Trust and registry are inherited administrator FDs, never CLI/env keys or approval flags.
    import os
    import socket

    from scripts.a42364_installation_verify import InstalledPackage
    from scripts.a42364_protocol_decision import RegistryChannel

    with socket.fromfd(6, socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        package = InstalledPackage.read(3, sha(os.pread(3, 65537, 0)), RegistryChannel(channel))
        print(json.dumps(verify_bundle(args.verify, InstalledSupplyVerifier(package))))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
