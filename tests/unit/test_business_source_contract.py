"""Historical proofs never become new business performance or a live G1 identity."""

import ast
import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import business_source_contract as contract

ROOT = Path(__file__).resolve().parents[2]


def test_old_a4_hash_is_preserved_and_current_source_has_a_different_version():
    from scripts.publication_lookup_tail_review_a423 import C0_SOURCE

    path = "backend/app/services/data_publication.py"
    value = contract.source_versions([path])
    assert value["historical_source"]["files"][path] == C0_SOURCE
    assert (
        value["current_source"]["files"][path]
        == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    )
    assert value["current_source"]["files"] != value["historical_source"]["files"]
    assert (
        value["capacity_ready"] is value["g1_authorized"] is value["performance_eligible"] is False
    )


def test_exact_function_compatibility_keeps_negative_cases_signatures_and_assertions():
    for path, names in contract.TEST_ADAPTATIONS.items():
        old = subprocess.check_output(["git", "show", contract.BASELINE + ":" + path], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        contract.verify_test_adaptation(old, current, names)
        assert {n.name for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)} == {
            n.name for n in ast.parse(current).body if isinstance(n, ast.FunctionDef)
        }


@pytest.mark.parametrize("damage", ["outside", "signature", "parameter", "assertion"])
def test_test_adaptation_cannot_waive_an_unreviewed_edit(damage):
    before = b"def allowed():\n    assert True\n\ndef negative():\n    assert False\n"
    after = before.replace(b"assert True", b"assert 1 == 1")
    if damage == "outside":
        after = after.replace(b"assert False", b"assert True")
    elif damage == "signature":
        after = after.replace(b"allowed()", b"allowed(unsafe)")
    elif damage == "parameter":
        after = b'@pytest.mark.parametrize("x",[])\n' + after
    else:
        after = after.replace(b"assert 1 == 1", b"pass")
    with pytest.raises(ValueError, match="BUSINESS_"):
        contract.verify_test_adaptation(before, after, {"allowed"})


def test_current_business_source_cannot_issue_old_g1_binding():
    from scripts.a4235_calibration_adapter_contract import Fault
    from scripts.a42361_source_guard import independent_binding

    # A manifest's mere presence is not a grant, even before any static check.
    with pytest.raises(Fault, match="BUSINESS_SOURCE_IS_NOT_G1_GRANT"):
        independent_binding("local", 1, "fake", "fake", "fake")


def test_frozen_real_measurement_entry_remains_closed():
    from scripts.ab_read_profile_v14_a4 import source_receipt

    with pytest.raises(ValueError, match="UNCHANGED_PRODUCTION_SOURCE"):
        source_receipt()
