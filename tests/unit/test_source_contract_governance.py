"""Owner-authorized governance is static-only, with immutable history routing."""

import copy
from pathlib import Path

import pytest

from scripts import business_source_contract as business
from scripts import source_contract_governance as governance
from scripts.source_contract_history import run, validate_result, verify_test_sources

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("purpose", ["G1_EXECUTION", "CAPACITY", "RECOVERY", "PERFORMANCE"])
@pytest.mark.parametrize("version", [governance.DEVELOPMENT, governance.HISTORICAL])
def test_static_and_history_versions_cannot_authorize_any_high_risk_purpose(version, purpose):
    with pytest.raises(ValueError, match="NOT_EXECUTION_AUTHORITY"):
        governance.require_purpose(version, purpose)


def test_development_route_is_explicit_and_does_not_use_manifest_presence(monkeypatch):
    receipt = dict(contract_version=governance.DEVELOPMENT, purpose="DEVELOPMENT_STATIC_ONLY")
    monkeypatch.setattr(governance, "development_receipt", lambda *a, **k: receipt)
    monkeypatch.setattr(business, "verify_legacy", lambda *a: pytest.fail("legacy route used"))
    assert len(business.verify()) == 64


@pytest.mark.parametrize("version", ["", "latest", "a42366.source.v2", "development.source.v2"])
def test_unknown_versions_never_fall_back_to_current_or_history(version):
    with pytest.raises(ValueError, match="UNKNOWN_VERSION"):
        business.verify(version=version)


@pytest.mark.parametrize("expected", [None, "a" * 40, governance.HISTORICAL_SHA])
def test_historical_source_cannot_approve_current_checkout(expected):
    with pytest.raises(ValueError, match="HISTORICAL_(SHA_REQUIRED|SOURCE_MISMATCH)"):
        business.verify(version=governance.HISTORICAL, expected_sha=expected)


def test_all_eleven_historical_manifests_keep_original_git_bytes():
    rows = governance.historical_manifests(ROOT)
    assert len(rows) == 11
    for path, original in rows:
        assert business.git(ROOT, "show", "HEAD:" + path) == original


def test_history_route_is_exact_and_not_a_directory_or_version_wildcard(tmp_path):
    assert len(governance.HISTORICAL_NODES) == 1
    assert len(governance.HISTORICAL_MODULES) == 7
    with pytest.raises(ValueError, match="UNREGISTERED_HISTORICAL_NODE"):
        run(tmp_path, node="tests/unit/test_business_worker_02.py")


@pytest.mark.parametrize("damage", ["none", "head", "live", "missing"])
def test_history_execution_cannot_mask_a_changed_original_test(tmp_path, monkeypatch, damage):
    path = governance.HISTORICAL_MODULES[-1]
    current = tmp_path / path
    current.parent.mkdir(parents=True)
    if damage != "missing":
        current.write_bytes(b"changed" if damage == "live" else b"original")
    monkeypatch.setattr(business, "git", lambda root, *args:
                        b"changed" if damage == "head" and args[-1].startswith("HEAD:")
                        else b"original")
    if damage == "none":
        assert verify_test_sources(tmp_path, (path,)) is None
    else:
        with pytest.raises((ValueError, FileNotFoundError)):
            verify_test_sources(tmp_path, (path,))


def test_unregistered_historical_test_paths_are_rejected_before_git(tmp_path, monkeypatch):
    monkeypatch.setattr(business, "git", lambda *a: pytest.fail("must reject before Git"))
    with pytest.raises(ValueError, match="UNREGISTERED_HISTORICAL_TEST"):
        verify_test_sources(tmp_path, ("tests/unit/test_business_worker_02.py",))


@pytest.mark.parametrize("damage", ["exit", "count", "failure", "error", "skipped", "totals"])
def test_historical_subprocess_cannot_hide_failure_skip_or_missing_cases(damage):
    from xml.etree import ElementTree

    root = ElementTree.fromstring(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="history" name="original"/></testsuite></testsuites>')
    good = ElementTree.tostring(root)
    assert validate_result(0, good, 1)["passed"] == 1
    damaged = copy.deepcopy(root)
    suite = damaged.find("testsuite")
    if damage in ("failure", "error", "skipped"):
        ElementTree.SubElement(suite.find("testcase"), damage)
    elif damage == "totals":
        suite.set("failures", "1")
    elif damage == "count":
        suite.remove(suite.find("testcase"))
    with pytest.raises(ValueError, match="HISTORICAL_TEST_FAILED"):
        validate_result(1 if damage == "exit" else 0, ElementTree.tostring(damaged), 1)


def test_static_version_is_distinct_from_every_historical_contract():
    assert governance.DEVELOPMENT != governance.HISTORICAL
    assert governance.require_purpose(governance.DEVELOPMENT, "DEVELOPMENT_STATIC_ONLY") is None
    with pytest.raises(ValueError, match="NOT_EXECUTION_AUTHORITY"):
        governance.require_purpose(governance.HISTORICAL, "DEVELOPMENT_STATIC_ONLY")


def test_real_old_measurement_and_production_recovery_remain_denied():
    from scripts.a4235_calibration_adapter_contract import Fault
    from scripts.a42361_source_guard import independent_binding
    from scripts.ab_read_experiment_v14_a4_2 import source_contract
    from scripts.ab_read_profile_v14_a4 import source_receipt

    with pytest.raises(Fault, match="BUSINESS_SOURCE_IS_NOT_G1_GRANT"):
        independent_binding("local", 1, "fake", "fake", "fake")
    with pytest.raises(ValueError, match="UNCHANGED_PRODUCTION_SOURCE"):
        source_receipt()
    with pytest.raises(ValueError, match="PRODUCTION_TREE_CHANGED"):
        source_contract()
