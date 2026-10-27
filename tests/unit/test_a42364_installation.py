"""Unsigned installation plans/negative records only, no host changes."""

import json
from pathlib import Path

import pytest

from scripts.a42363_contract import DOMAINS, Fault
from scripts.a42364_bootstrap_builder import build_source_archive, verify_uid_maps
from scripts.a42364_installation_verify import InstallationPackage, validate_document
from tests.unit.test_a42364_owner import identity

ROOT = Path(__file__).resolve().parents[2]


def document():
    principals = {name: 2000 + n for n, name in enumerate((*DOMAINS, "worker", "runtime"))}
    principals["controller"] = identity().scope.controller_uid
    return dict(
        version="a42364.installation.v3",
        service_domain="root_manager",
        scope=identity().scope.model_dump(),
        principals=principals,
        binary_sha256={n: "1" * 64 for n in ("python", "worker", "podman", "collector", "openssl")},
        code_archive_sha256="2" * 64,
        image_manifest_sha256="3" * 64,
        custody_review_sha256="4" * 64,
        public_keys={"OWNER": {"owner": "1" * 64}, "SAFETY_PLATFORM": {"safety": "2" * 64}},
        revoked_kids=(),
        openssl_version="OpenSSL 3.OFFLINE_MODEL",
        expires_at=200,
    )


def test_AT33_pure_installation_schema_does_not_create_capabilities():
    result = validate_document(document(), 100)
    assert result.principals["controller"] == 1002
    assert len(set(result.principals.values())) == 9


@pytest.mark.parametrize(
    "field", ["same_uid", "expired", "same_signer", "test_key", "missing_binary"]
)
def test_AT08_AT33_invalid_identity_custody_or_binary_rejected(field):
    value = document()
    if field == "same_uid":
        value["principals"]["worker"] = value["principals"]["controller"]
    elif field == "expired":
        value["expires_at"] = 99
    elif field == "same_signer":
        value["public_keys"]["SAFETY_PLATFORM"] = {"safety": "1" * 64}
    elif field == "test_key":
        value["public_keys"]["OWNER"] = {
            "owner": "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
        }
    else:
        del value["binary_sha256"]["worker"]
    with pytest.raises(Fault):
        validate_document(value, 100)


def test_AT33_installer_plan_neither_starts_units_nor_accepts_arbitrary_files():
    files = {
        n: b"OFFLINE"
        for n in (
            "root_manager.service",
            "worker.service",
            "read_only_auditor.service",
            "source.zip",
            "entry.py",
            "installation.json",
        )
    }
    result = InstallationPackage(files).plan()
    assert result["auto_start_g1"] is False
    with pytest.raises(Fault):
        InstallationPackage(dict(files, **{"arbitrary.sh": b"bad"}))


def test_AT05_installed_archive_is_reproducible_and_secret_free():
    first = build_source_archive(ROOT)
    assert first == build_source_archive(ROOT)
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(first)) as z:
        assert "scripts/a42364_entry.py" in z.namelist()
        assert not any(".env" in n or "tests/" in n for n in z.namelist())


@pytest.mark.parametrize(
    "uid,gid,owner",
    [
        (1001, 1002, (1001, 1002, 0o770)),
        (1003, 1002, (1001, 1002, 0o770)),
        (1001, 1002, (1001, 1002, 0o777)),
    ],
)
def test_AT07_keepid_mapping_and_socket_must_match(uid, gid, owner):
    if uid == 1001 and owner[-1] == 0o770:
        assert verify_uid_maps("999 1001 1", "999 1002 1", uid, gid, owner)["qualifies"] is False
    else:
        with pytest.raises(Fault):
            verify_uid_maps("999 1001 1", "999 1002 1", uid, gid, owner)


def test_AT33_schema_file_matches_runtime_contract():
    from scripts.a42364_installation_verify import document_schema

    assert (
        json.loads((ROOT / "infra/g1_manager/install_manifest.schema.json").read_text())
        == document_schema()
    )
