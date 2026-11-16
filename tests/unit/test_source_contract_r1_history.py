"""Classify the proposed R1 route without moving current behavioral assertions."""

from pathlib import Path

import pytest

from scripts import business_source_contract, source_contract_history
from scripts.r1_real_root_protocol import Refused

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_NODE = (
    "tests/unit/test_r1_integration_controller.py::ControllerTests::"
    "test_composed_real_adapters_fake_io_not_just_callback_labels"
)


@pytest.fixture
def current_controller(monkeypatch):
    # Match the original Linux checkout's schema bytes in Windows diagnostics.
    # Worker bytes and every original behavioral assertion remain current.
    original_read = Path.read_bytes

    def schema_lf(path):
        raw = original_read(path)
        return raw.replace(b"\r\n", b"\n") if path.name == (
            "r1_business_compare_schema_v1.json"
        ) else raw

    monkeypatch.setattr(Path, "read_bytes", schema_lf)
    monkeypatch.syspath_prepend(str(ROOT / "tests/unit"))
    from tests.unit.test_r1_integration_controller import ControllerTests

    return ControllerTests("test_composed_real_adapters_fake_io_not_just_callback_labels")


def test_legacy_history_rejects_r1_before_git(tmp_path, monkeypatch):
    def forbidden_git(*args, **kwargs):
        pytest.fail("unregistered R1 node reached Git")

    monkeypatch.setattr(business_source_contract, "git", forbidden_git)
    with pytest.raises(ValueError, match="SOURCE_CONTRACT_UNREGISTERED_HISTORICAL_NODE"):
        source_contract_history.run(tmp_path, node=CONTROLLER_NODE)


def test_composed_controller_still_exercises_current_adapters(current_controller):
    current_controller.test_composed_real_adapters_fake_io_not_just_callback_labels()


@pytest.mark.parametrize("method", ["preflight", "execute_fake_root"])
def test_current_controller_assertions_detect_behavior_damage(
    current_controller, monkeypatch, method,
):
    from scripts.r1_integration_controller import OfflineIntegrationComponents

    monkeypatch.setattr(OfflineIntegrationComponents, method, lambda self: {
        "fake_only": False, "status": "SYNTHETIC_BROKEN_CURRENT_BEHAVIOR",
    })
    with pytest.raises(AssertionError):
        current_controller.test_composed_real_adapters_fake_io_not_just_callback_labels()


def test_same_current_controller_refuses_proposed_worker_change(
    current_controller, monkeypatch,
):
    original_read = Path.read_bytes
    worker = ROOT / "backend/app/services/job_worker.py"
    raw = original_read(worker)
    changed = raw + b"\n# offline integrity tamper probe\n"

    def changed_worker(path):
        return changed if path == worker else original_read(path)

    monkeypatch.setattr(Path, "read_bytes", changed_worker)
    with pytest.raises(Refused, match="^INTEGRATION_BUSINESS_DRIFT$"):
        current_controller.test_composed_real_adapters_fake_io_not_just_callback_labels()


@pytest.mark.parametrize("version", ["", "unknown", None, "R1.CURRENT-BUSINESS-SOURCES.V2"])
def test_unknown_source_version_refuses_before_io(monkeypatch, version):
    from scripts.r1_integration_evidence import verify_business_sources

    monkeypatch.setattr(Path, "read_bytes", lambda p: pytest.fail("unexpected read"))
    with pytest.raises(Refused, match="^INTEGRATION_SOURCE_VERSION$"):
        verify_business_sources(version=version)


def test_v3_canonical_bytes_work_without_v1_schema_read_patch():
    from scripts.r1_integration_evidence import verify_business_sources

    assert verify_business_sources(version="r1.current-business-sources.v3") is True


def test_v2_manifest_still_refuses_tamper_before_business_drift(monkeypatch):
    from scripts.r1_integration_evidence import verify_business_sources

    original = Path.read_bytes
    target = ROOT / "docs/acceptance/r1_current_business_sources_v2.json"
    monkeypatch.setattr(Path, "read_bytes", lambda p: b"{}" if p == target else original(p))
    with pytest.raises(Refused, match="^INTEGRATION_CURRENT_MANIFEST_DRIFT$"):
        verify_business_sources(version="r1.current-business-sources.v2")


def test_v2_accepts_its_pinned_previous_source_tree(tmp_path, monkeypatch):
    import json

    from scripts import r1_integration_evidence as evidence

    sha = "bf7b6a35a453c7d82be363dec2e0f5157221db92"
    git = business_source_contract.git
    assert git(ROOT, "rev-parse", sha + "^{commit}").decode().strip() == sha
    manifest_path = "docs/acceptance/r1_current_business_sources_v2.json"
    manifest = json.loads(git(ROOT, "show", sha + ":" + manifest_path))
    paths = [*manifest["sources"], manifest_path,
             "docs/acceptance/r1_business_compare_schema_v1.json"]
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(ROOT, "show", sha + ":" + name))
    # Verify real files in a historical byte tree, never substitute old bytes
    # into current Controller/Seed execution or claim current v2 acceptance.
    monkeypatch.setattr(evidence, "__file__", str(tmp_path / "scripts/r1_integration_evidence.py"))
    assert evidence.verify_business_sources(version="r1.current-business-sources.v2") is True


def test_v1_v2_and_v3_remain_separate(current_controller, monkeypatch):
    from scripts.r1_integration_evidence import verify_business_sources

    assert verify_business_sources(version="r1.current-business-sources.v3") is True
    with pytest.raises(Refused, match="^INTEGRATION_BUSINESS_DRIFT$"):
        verify_business_sources(version="r1.current-business-sources.v2")
    # The original default still validates v1, independently of the new manifest.
    original = Path.read_bytes
    manifest = ROOT / "docs/acceptance/r1_current_business_sources_v3.json"
    monkeypatch.setattr(Path, "read_bytes", lambda p: b"{}" if p == manifest else original(p))
    with pytest.raises(Refused, match="^INTEGRATION_CURRENT_MANIFEST_DRIFT$"):
        verify_business_sources(version="r1.current-business-sources.v3")
    # Worker may legitimately differ after the production fix, so compare v1's
    # result to the unchanged schema rather than requiring current bytes to match.
    import hashlib

    from scripts.r1_business_snapshot_contract import load_schema

    expected = load_schema()["sources"]
    matches = all(hashlib.sha256(original(ROOT / p).replace(b"\r\n", b"\n")).hexdigest()
                  == v["sha256"] for p, v in expected.items())
    if matches:
        assert verify_business_sources() is True
    else:
        with pytest.raises(Refused, match="^INTEGRATION_BUSINESS_DRIFT$"):
            verify_business_sources()


@pytest.mark.parametrize("name", [
    "scripts/r1_integration_seed_loader.py", "scripts/r1_integration_controller.py",
    "backend/app/services/job_worker.py", "backend/app/services/data_publication.py",
])
def test_current_v3_covers_each_changed_source(current_controller, monkeypatch, name):
    from scripts.r1_integration_evidence import verify_business_sources

    original = Path.read_bytes
    target = ROOT / name
    monkeypatch.setattr(Path, "read_bytes", lambda p: original(p) + b"# tamper\n"
                        if p == target else original(p))
    with pytest.raises(Refused, match="^INTEGRATION_BUSINESS_DRIFT$"):
        verify_business_sources(version="r1.current-business-sources.v3")


@pytest.mark.parametrize("problem,code", [
    ("link", "INTEGRATION_SOURCE_LINK"), ("missing", "INTEGRATION_SOURCE_MISSING"),
])
@pytest.mark.parametrize("version", [
    "r1.current-business-sources.v2", "r1.current-business-sources.v3",
])
def test_current_versions_reject_link_and_missing_file(
    current_controller, monkeypatch, problem, code, version,
):
    from scripts.r1_integration_evidence import verify_business_sources

    target = ROOT / "backend/app/services/data_publication.py"
    attribute = "is_symlink" if problem == "link" else "is_file"
    original = getattr(Path, attribute)
    monkeypatch.setattr(Path, attribute, lambda p: problem == "link"
                        if p == target else original(p))
    with pytest.raises(Refused, match="^" + code + "$"):
        verify_business_sources(version=version)


def test_v3_rejects_unregistered_manifest_path(monkeypatch):
    import hashlib
    import json

    from scripts import r1_integration_evidence as evidence

    target = ROOT / "docs/acceptance/r1_current_business_sources_v3.json"
    original = Path.read_bytes
    manifest = json.loads(original(target))
    manifest["sources"]["../outside"] = manifest["sources"].pop(
        "backend/app/services/data_publication.py")
    raw = json.dumps(manifest, sort_keys=True).encode()
    # Independently exercise the path allowlist even with a bound document digest.
    monkeypatch.setattr(evidence, "SOURCE_V3_MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(Path, "read_bytes", lambda p: raw if p == target else original(p))
    with pytest.raises(Refused, match="^INTEGRATION_CURRENT_PATHS$"):
        evidence.verify_business_sources(version="r1.current-business-sources.v3")


@pytest.mark.parametrize("version,commit,path", [
    ("unknown", "232baf9e13cd7b23731e59188c86e0e253c3a394", "scripts/r1_real_root_protocol.py"),
    ("r1.historical-bytes.v1", "0" * 40, "scripts/r1_real_root_protocol.py"),
    ("r1.historical-bytes.v1", "232baf9e13cd7b23731e59188c86e0e253c3a394", "../outside"),
])
def test_historical_identity_rejected_before_git(monkeypatch, version, commit, path):
    monkeypatch.setattr(source_contract_history.subprocess, "check_output",
                        lambda *a, **k: pytest.fail("unregistered identity reached Git"))
    with pytest.raises(ValueError, match="^R1_HISTORY_UNREGISTERED_IDENTITY$"):
        source_contract_history.read_r1_historical_file(
            ROOT, path, version=version, commit=commit)


@pytest.mark.parametrize("failure", ["missing_object", "corrupt_blob", "wrong_tree"])
def test_historical_git_failures_refuse(monkeypatch, failure):
    original = source_contract_history.subprocess.check_output

    def git(args, **kwargs):
        if failure == "missing_object":
            raise source_contract_history.subprocess.CalledProcessError(128, args)
        raw = original(args, **kwargs)
        if failure == "corrupt_blob" and "cat-file" in args:
            return raw + b"tamper"
        if failure == "wrong_tree" and args[-1].endswith("^{tree}"):
            return b"0" * 40 + b"\n"
        return raw

    monkeypatch.setattr(source_contract_history.subprocess, "check_output", git)
    with pytest.raises(ValueError, match="^R1_HISTORY_(OBJECT_UNAVAILABLE|BLOB_IDENTITY|"
                            "OBJECT_IDENTITY)$"):
        source_contract_history.read_r1_historical_file(ROOT, "scripts/r1_real_root_protocol.py")


def test_current_t26_catches_oracle_damage(monkeypatch):
    from tests.unit import test_r1_reviewed_snapshot_v2 as current

    original = current.material

    def damaged(*args):
        import json

        packets, oracle, contract, provenance = original(*args)
        changed = json.loads(oracle)
        changed["approval"] = "APPROVED"
        return packets, json.dumps(changed).encode(), contract, provenance

    monkeypatch.setattr(current, "material", damaged)
    case = current.ReviewedEvidenceTests("test_T26_current_oracle_authorship_and_fixture_bytes")
    with pytest.raises(AssertionError):
        case.test_T26_current_oracle_authorship_and_fixture_bytes()


def test_r1_ac31_runs_original_in_isolated_child():
    from scripts.source_contract_governance import R1_HISTORICAL_NODE, R1_HISTORICAL_SHA

    result = source_contract_history.run(ROOT, node=R1_HISTORICAL_NODE)
    assert result["passed"] == 1 and result["failed"] == result["errors"] == result["skipped"] == 0
    assert result["source_sha"] == R1_HISTORICAL_SHA
    assert result["scope"] == "HISTORICAL_ONLY_NOT_CURRENT_AUTHORITY"
    assert result["lifecycle"] == ["setup", "body", "teardown"]
    assert result["performance_eligible"] is False and result["g1_authorized"] is False


def test_t26_original_hashes_and_current_assertions_preserved():
    import ast

    path = "tests/unit/test_r1_reviewed_snapshot_v2.py"
    old = ast.parse(source_contract_history.read_r1_historical_file(ROOT, path))
    current = ast.parse((ROOT / path).read_bytes())

    def frozen(tree):
        return next(n.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "FROZEN" for t in n.targets))

    assert ast.dump(frozen(old)) == ast.dump(frozen(current))
    original = next(n for n in ast.walk(old) if isinstance(n, ast.FunctionDef)
                    and n.name == "test_T26_all_frozen_boundaries_and_oracle_authorship")
    separated = next(n for n in ast.walk(current) if isinstance(n, ast.FunctionDef)
                     and n.name == "test_T26_current_oracle_authorship_and_fixture_bytes")
    assert [ast.dump(n) for n in original.body[1:]] == [ast.dump(n) for n in separated.body]
