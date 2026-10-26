"""Portable RED-to-GREEN source regressions; never execute G1 or Linux adapters."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(name):
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_RED_AT57_lost_creation_ack_has_token_bound_recovery_path():
    tree = ast.parse(source("a42361_control_service.py"))
    assert any(isinstance(n, ast.Constant) and n.value == "reconcile" for n in ast.walk(tree))


def test_RED_AT50_direct_child_exit_cannot_short_circuit_scope_proof():
    tree = ast.parse(source("a42361_watchdog.py"))
    method = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "terminate_owned"
    )
    for node in ast.walk(method):
        if isinstance(node, ast.If) and "child.process.poll()" in ast.unparse(node.test):
            assert not any(isinstance(n, ast.Return) for s in node.body for n in ast.walk(s))


def test_RED_AT26_target_session_guc_method_is_explicitly_guarded():
    raw = source("a42361_live_probe_worker.py")
    assert "METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION" in raw
    assert "CONFIGURED_NOT_INDEPENDENTLY_OBSERVED" in raw
