"""E04 offline protocol probes; no application or resource execution."""

import copy
import hashlib
import importlib.util
import os
import subprocess
import sys
import uuid

import pytest
from test_biz_perf_p1_04_e03_guard import g as g
from test_biz_perf_p1_04_e03_guard import plan as plan

from scripts import biz_perf_p1_04_diagnostic as d

SHA = "a" * 40


@pytest.fixture
def p():
    from scripts import biz_perf_p1_04_e04_packet

    return biz_perf_p1_04_e04_packet


@pytest.fixture
def bundle(p, plan, tmp_path):
    path = tmp_path / "admission"
    path.mkdir()
    subject = p.subject(plan)
    common = dict(schema=p.SCHEMA, evidence_kind="OFFLINE_FIXTURE", implementation_sha=SHA,
                  run_uuid=plan["preflight"]["run_uuid"], subject_sha256=subject)
    payloads = dict(ci=dict(status="SUCCESS", run_id=43545268807, attempt=1),
                    review={key: plan["review"][key]
                            for key in ("status", "reviewer_sha256", "implementer_sha256")},
                    resources=dict(expected=copy.deepcopy(plan["expected"]),
                                   observed=copy.deepcopy(plan["observed"]), observation_seq=1))
    entries = {}
    for role in p.ROLES:
        source = dict(kind="OFFLINE_MOCK_SOURCE", receipt_uuid=str(uuid.uuid4()),
                      scope="E04_OFFLINE_PROTOCOL")
        evidence = p.seal(dict(common, role=role, source=source, payload=payloads[role]))
        raw = d.encode(evidence)
        (path / f"{role}.json").write_bytes(raw)
        entries[f"{role}.json"] = dict(evidence_kind="OFFLINE_FIXTURE", bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    canonical_sha256=evidence["canonical_sha256"])
        if role in {"ci", "review"}:
            plan[role]["receipt_sha256"] = entries[f"{role}.json"]["sha256"]
    manifest = p.seal(dict(common, entries=entries))
    packet = p.seal(dict(common, manifest_sha256=manifest["canonical_sha256"], plan=plan))
    (path / "admission_packet.json").write_bytes(d.encode(packet))
    (path / "evidence_manifest.json").write_bytes(d.encode(manifest))
    return path, packet, manifest


class MockVerifier:
    def verify(self, packet, manifest, evidence):
        assert set(evidence) == {"ci", "review", "resources"}
        return dict(evidence_kind="OBSERVED_OFFLINE", status="OFFLINE_ATTESTED_MOCK_ONLY",
                    packet_sha256=packet["canonical_sha256"],
                    manifest_sha256=manifest["canonical_sha256"],
                    implementation_sha=packet["implementation_sha"], run_uuid=packet["run_uuid"])


def rewrite(p, bundle, name, value):
    """Rebind downstream digests, to exercise semantic refusals beyond hash mismatch."""
    path, packet, manifest = bundle
    value.pop("canonical_sha256", None)
    value = p.seal(value)
    raw = d.encode(value)
    (path / name).write_bytes(raw)
    if name in {"ci.json", "review.json", "resources.json"}:
        manifest["entries"][name] = dict(evidence_kind="OFFLINE_FIXTURE", bytes=len(raw),
                   sha256=hashlib.sha256(raw).hexdigest(),
                   canonical_sha256=value["canonical_sha256"])
        if name in {"ci.json", "review.json"}:
            packet["plan"][name[:-5]]["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest.pop("canonical_sha256", None)
        manifest = p.seal(manifest)
        (path / "evidence_manifest.json").write_bytes(d.encode(manifest))
        packet["manifest_sha256"] = manifest["canonical_sha256"]
    elif name == "evidence_manifest.json":
        packet["manifest_sha256"] = value["canonical_sha256"]
    if name != "admission_packet.json":
        packet.pop("canonical_sha256", None)
        (path / "admission_packet.json").write_bytes(d.encode(p.seal(packet)))


def test_declarations_and_explicit_mock_are_never_trust(p, bundle, capsys):
    path, packet, _ = bundle
    run = packet["run_uuid"]
    before = {f.name: f.read_bytes() for f in path.iterdir()}
    declared = p.load_bundle(path, SHA, run)
    assert declared["status"] == "OFFLINE_DECLARATIONS_ONLY"
    checked = p.load_bundle(path, SHA, run, verifier=MockVerifier())
    assert checked["status"] == "OFFLINE_ATTESTED_MOCK_ONLY"
    assert checked["root_attempts"] == 0
    assert checked["b_gate"] == checked["targeted_pg17_gate"] == "NOT_APPROVED"
    assert checked["budget"] == "DRAFT_NOT_APPROVED"
    assert {f.name: f.read_bytes() for f in path.iterdir()} == before
    with pytest.raises(p.Refused, match="ATTESTATION_REFUSED"):
        p.load_bundle(path, SHA, run, verifier=p.RefusedVerifier())
    assert p.main(["validate-offline", "--input-dir", str(path),
                   "--expected-implementation-sha", SHA, "--expected-run-uuid", run]) == 0
    assert d.decode(capsys.readouterr().out.encode())["status"] == "OFFLINE_DECLARATIONS_ONLY"


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                  b'{"x":1e999}', b'{"x":', b'[]', b' ' * (65536 + 1)],
                         ids=["duplicate", "nan", "inf", "overflow", "tail", "array", "size"])
def test_strict_json_and_schema(p, bundle, raw):
    path, packet, _ = bundle
    (path / "admission_packet.json").write_bytes(raw)
    with pytest.raises(p.Refused):
        p.load_bundle(path, SHA, packet["run_uuid"])


@pytest.mark.parametrize("name,trail,value", [
    ("admission_packet.json", ("implementation_sha",), "b" * 40),
    ("admission_packet.json", ("run_uuid",), str(uuid.UUID(int=99))),
    ("admission_packet.json", ("manifest_sha256",), "0" * 64),
    ("admission_packet.json", ("subject_sha256",), "0" * 64),
    ("admission_packet.json", ("permit",), True),
    ("admission_packet.json", ("plan", "preflight", "worktree"), "DIRTY"),
    ("ci.json", ("payload", "attempt"), True),
    ("ci.json", ("payload", "attempt"), 0),
    ("ci.json", ("payload", "attempt"), 2**100),
    ("ci.json", ("payload", "status"), "PENDING"),
    ("ci.json", ("source", "kind"), "GITHUB_AUTHENTICATED"),
    ("review.json", ("source", "scope"), "PRODUCTION"),
    ("review.json", ("source", "receipt_uuid"), "../ci.json"),
    ("review.json", ("payload", "reviewer_sha256"), "e" * 64),
    ("resources.json", ("payload", "observed", "kind"), "OBSERVED_LIVE"),
    ("resources.json", ("payload", "observed", "resources", "volume_sha256"), "9" * 64),
    ("resources.json", ("payload", "observation_seq"), True),
    ("evidence_manifest.json", ("entries", "admission_packet.json"), {}),
    ("evidence_manifest.json", ("entries", "../ci.json"), {}),
])
def test_forgery_and_self_reference_with_rehashed_envelopes(p, bundle, name, trail, value):
    path, packet, _ = bundle
    document = d.decode((path / name).read_bytes())
    target = document
    for key in trail[:-1]:
        target = target[key]
    target[trail[-1]] = value
    rewrite(p, bundle, name, document)
    with pytest.raises(p.Refused):
        p.load_bundle(path, SHA, packet["run_uuid"])


@pytest.mark.parametrize("name", ["ci.json", "review.json", "resources.json"])
def test_missing_or_changed_raw_evidence(p, bundle, name):
    path, packet, _ = bundle
    original = (path / name).read_bytes()
    (path / name).write_bytes(original + b" ")
    with pytest.raises(p.Refused, match="DIGEST_MISMATCH"):
        p.load_bundle(path, SHA, packet["run_uuid"])
    (path / name).unlink()
    with pytest.raises(p.Refused):
        p.load_bundle(path, SHA, packet["run_uuid"])


@pytest.mark.parametrize("bad", [True, {}, dict(status="LIVE_VERIFIED")])
def test_untrusted_verifier_result(p, bundle, bad):
    path, packet, _ = bundle

    class Bad:
        def verify(self, *_):
            return bad

    with pytest.raises(p.Refused, match="ATTESTATION_REJECTED"):
        p.load_bundle(path, SHA, packet["run_uuid"], verifier=Bad())


def test_mutating_port_and_path_replacement_are_rechecked(p, bundle):
    path, packet, _ = bundle

    class Mutates(MockVerifier):
        def verify(self, packet, manifest, evidence):
            result = super().verify(packet, manifest, evidence)
            evidence["ci"].clear()  # Its own copy cannot affect validation.
            return result

    assert p.load_bundle(path, SHA, packet["run_uuid"], verifier=Mutates())

    class Replaces(MockVerifier):
        def verify(self, *args):
            result = super().verify(*args)
            old = path / "ci.json"
            old.rename(path / "moved.json")
            old.write_bytes(b"{}")
            return result

    with pytest.raises(p.Refused, match="PATH_REJECTED"):
        p.load_bundle(path, SHA, packet["run_uuid"], verifier=Replaces())


def test_cross_identity_and_cycles(p, bundle):
    path, packet, _ = bundle
    for sha, run in (("b" * 40, packet["run_uuid"]), (SHA, str(uuid.UUID(int=77)))):
        with pytest.raises(p.Refused, match="IDENTITY_MISMATCH"):
            p.load_bundle(path, sha, run)
    value = {}
    value["cycle"] = value
    with pytest.raises(p.Refused):
        p.digest(value)


def test_execute_cannot_be_enabled_by_arguments_or_environment(p, monkeypatch, capsys):
    monkeypatch.setenv("E04_PERMIT", "SIGNED_APPROVAL")
    for args in (["execute"], ["execute", "--permit", "SIGNED_APPROVAL"],
                 ["execute", "--allow=true"], ["execute", "--ci=SUCCESS"]):
        assert p.main(args) == 2
        assert capsys.readouterr().out.strip() == "AUTHORIZATION_PENDING"
    assert p.main(["PRIVATE_DSN"]) == 2
    assert capsys.readouterr().out.strip() == "INPUT_REJECTED"


def test_same_bytes_replacement_during_attestation_is_rejected(p, bundle):
    path, packet, _ = bundle

    class Replacement(MockVerifier):
        def verify(self, *args):
            original = path / "ci.json"
            saved = original.read_bytes()
            original.rename(path.parent / "old-ci.json")
            original.write_bytes(saved)
            return super().verify(*args)

    with pytest.raises(p.Refused, match="PATH_REJECTED"):
        p.load_bundle(path, SHA, packet["run_uuid"], verifier=Replacement())


def test_evidence_hardlink_and_duplicated_sources_rejected(p, bundle, tmp_path):
    path, packet, _ = bundle
    os.link(path / "ci.json", tmp_path / "ci-link.json")
    with pytest.raises(p.Refused, match="PATH_REJECTED"):
        p.load_bundle(path, SHA, packet["run_uuid"])


def test_receipt_source_identity_may_not_be_reused(p, bundle):
    path, packet, _ = bundle
    review = d.decode((path / "review.json").read_bytes())
    ci = d.decode((path / "ci.json").read_bytes())
    review["source"]["receipt_uuid"] = ci["source"]["receipt_uuid"]
    rewrite(p, bundle, "review.json", review)
    with pytest.raises(p.Refused, match="EVIDENCE_REJECTED"):
        p.load_bundle(path, SHA, packet["run_uuid"])


@pytest.mark.parametrize("module", ["packet", "journal", "review"])
def test_every_e04_module_cli_denies_execute(module):
    result = subprocess.run([sys.executable, "-B", "-m", f"scripts.biz_perf_p1_04_e04_{module}",
                             "execute", "--permit=SIGNED"], capture_output=True, text=True,
                            check=False)
    assert result.returncode == 2 and result.stdout.strip() == "AUTHORIZATION_PENDING"


def test_e04_packet_contract_exists():
    assert importlib.util.find_spec("scripts.biz_perf_p1_04_e04_packet") is not None


def test_e04_execute_always_refuses():
    result = subprocess.run(
        [sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_e04_packet", "execute"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert result.stdout.strip() == "AUTHORIZATION_PENDING"


def test_e04_durable_journal_exists():
    assert importlib.util.find_spec("scripts.biz_perf_p1_04_e04_journal") is not None
