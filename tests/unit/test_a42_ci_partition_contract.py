"""P1: derive old required keys independently from frozen source/workflow."""

import ast
import subprocess
from collections import Counter
from dataclasses import replace

import yaml

from scripts.a42_ci_contract import (
    BASELINE_SHA,
    CAPACITY_LEVELS,
    Group,
    as_json,
    legacy_groups,
    matrix,
    primary_groups,
    shards,
)


def frozen(path):
    return subprocess.check_output(["git", "show", f"{BASELINE_SHA}:{path}"], text=True)


def independent_legacy():
    tree = ast.parse(frozen("scripts/ab_read_experiment_v14_a4_2.py"))
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in {"CONTROLS", "SQL_VARIANTS"}}
    variants = constants["CONTROLS"] + constants["SQL_VARIANTS"]
    workflow = yaml.safe_load(frozen(".github/workflows/ab-read-a4-2.yml"))
    assert workflow["jobs"]["laboratory"]["strategy"]["matrix"]["phase"] == [
        "primary", "supplemental"]
    steps = workflow["jobs"]["laboratory"]["steps"]
    commands = "\n".join(s.get("run", "") for s in steps)
    assert "for coverage in partial a_only b_only high mismatched" in commands
    assert "for tombstones in 0 1 10" in commands
    expected = set()
    for scale in ("10k", "100k", "million"):
        reads = {Group(scale, "read", v, f, "full", repeat=r)
                 for v in variants for f in ("0.1", "1.0") for r in range(3)}
        reads |= {Group(scale, "read", "S3", f, "window_matrix", w, r)
                  for f in ("0.1", "1.0") for w in (None, 1, 3, 5, 10, 20)
                  for r in range(3)}
        reads |= {Group(scale, "read", v, "0.1", f"month_{m}", repeat=r)
                  for v in variants if v != "Q0_LEGACY_RAW"
                  for m in (1, 2, 3) for r in range(3)}
        expected |= reads | {replace(g, kind="plan", repeat=None) for g in reads}
    expected |= {Group("10k", "read", v, "0.1", "shape", repeat=r,
                       coverage=c, tombstones=t)
                 for c in ("partial", "a_only", "b_only", "high", "mismatched")
                 for t in (0, 1, 10) for v in (
                     "Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "S3_KEYS", "S4", "S5")
                 for r in range(3)}
    event_variants = ("Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "E3")
    expected |= {Group("100k", "read", v, f, "event_full", repeat=r)
                 for v in event_variants for f in ("0.1", "1.0") for r in range(3)}
    expected |= {Group("100k", "read", v, "0.1", f"event_month_{m}", repeat=r)
                 for v in event_variants for m in (1, 2, 3) for r in range(3)}
    expected |= {Group("million", "read", v, f, "readers", repeat=r, readers=2)
                 for v in ("Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "S3_KEYS", "S5")
                 for f in ("0.1", "1.0") for r in range(3)}
    return expected


def test_original_git_matrix_has_exactly_one_owner_no_lost_or_duplicate_groups():
    expected = independent_legacy()
    assigned = [g for cells in matrix().values() for g in cells if not g.auxiliary]
    assert set(assigned) == legacy_groups() == expected
    assert len(assigned) == len(set(assigned)) == 1002
    assert len({g.id for g in expected}) == len(expected)


def test_full_windows_and_months_have_all_fractions_widths_and_three_repeats():
    groups = primary_groups("million")
    assert Counter(g.kind for g in groups) == {"read": 177, "plan": 59}
    for scope in ("full", "window_matrix", "month_1", "month_2", "month_3"):
        keys = {(g.variant, g.fraction, g.window_days) for g in groups
                if g.kind == "read" and g.scope == scope}
        assert all({g.repeat for g in groups if g.kind == "read" and g.scope == scope
                    and (g.variant, g.fraction, g.window_days) == k} == {0, 1, 2} for k in keys)
    assert {g.window_days for g in groups if g.scope == "window_matrix"} == {
        None, 1, 3, 5, 10, 20}


def test_every_window_job_has_its_own_safe_comparator_not_a_cross_runner_baseline():
    for shard in shards():
        groups = matrix()[shard.job_id]
        if shard.scope == "million-window":
            controls = [g for g in groups if g.auxiliary]
            assert len(controls) == 3
            assert {g.repeat for g in controls} == {0, 1, 2}
            assert all(g.variant == "Q0_SAFETY_EQUIVALENT" for g in controls)
    assert all(0 < s.timeout_minutes <= 300 for s in shards())


def test_fifteen_shapes_e3_and_rr2_are_mandatory_not_optional_best_cases():
    groups = legacy_groups()
    assert len({(g.coverage, g.tombstones) for g in groups if g.scope == "shape"}) == 15
    assert sum(g.readers == 2 for g in groups) == 24
    assert any(g.variant == "E3" for g in groups)
    assert CAPACITY_LEVELS == {"L1": (10, 2), "L2": (5000, 20), "L3-scaled-10pct": (500, 120)}
    document = as_json()
    assert document["mandatory_group_count"] == 1002
    assert document["auxiliary_group_count"] == 6


def test_production_tree_and_original_a41_evidence_unchanged():
    from scripts.business_source_contract import HISTORICAL_SOURCE

    assert not subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            BASELINE_SHA,
            HISTORICAL_SOURCE,
            "--",
            "backend",
            "config",
            "migrations",
            "frontend",
        ]
    )

    from scripts.business_source_contract import verify as verify_current_business

    assert len(verify_current_business()) == 64
