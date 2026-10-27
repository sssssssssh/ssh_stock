"""Job policy freeze is separate from financial identity and live G1 admission."""

from types import SimpleNamespace as NS
from uuid import uuid4

import pytest


def settings():
    return NS(
        factor_input_reuse_enabled=False,
        raw_preflight_batch_enabled=False,
        factor_cpu_optimization_enabled=False,
    )


@pytest.mark.parametrize(
    "field",
    [
        "factor_input_reuse_enabled",
        "raw_preflight_batch_enabled",
        "factor_cpu_optimization_enabled",
    ],
)
def test_job_switch_drift_fails_before_next_stage(field):
    from app.services.calculation_policy import ExecutionPolicy

    value = settings()
    job = NS(id=uuid4(), job_metadata={})
    policy = ExecutionPolicy.freeze(
        job, value, source={"source_sha256": "a" * 64, "commit_sha": None}
    )
    setattr(value, field, True)
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED"):
        policy.guard(value)


def test_restart_rejects_switch_or_code_drift_instead_of_re_freezing():
    from app.services.calculation_policy import ExecutionPolicy

    value, job = settings(), NS(id=uuid4(), job_metadata={})
    ExecutionPolicy.freeze(job, value, source={"source_sha256": "a" * 64, "commit_sha": None})
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED"):
        ExecutionPolicy.freeze(job, value, source={"source_sha256": "b" * 64, "commit_sha": None})


def test_child_inherits_root_policy_and_fixed_safe_fetch_counters():
    from app.services.calculation_policy import ExecutionPolicy

    value, root = settings(), NS(id=uuid4(), job_metadata={})
    parent = ExecutionPolicy.freeze(
        root, value, source={"source_sha256": "a" * 64, "commit_sha": None}
    )
    child = NS(id=uuid4(), job_metadata={})
    policy = ExecutionPolicy.freeze(child, value, source=parent.source, parent=parent)
    assert policy.record["root_job_id"] == str(root.id)
    policy.observe_fetch("factors.stock_daily", 5000, 0.2)
    assert policy.snapshot()["reads"]["factors.stock_daily"] == dict(
        rows=5000, fetches=1, seconds=0.2
    )
    assert not any(
        k in str(policy.snapshot()).lower() for k in ("postgresql://", "password", "dsn")
    )


def test_closed_policy_does_not_silently_enable_new_path():
    from app.services.calculation_policy import ExecutionPolicy

    value, root = settings(), NS(id=uuid4(), job_metadata={})
    p = ExecutionPolicy.freeze(root, value, source={"source_sha256": "a" * 64, "commit_sha": None})
    p.close()
    with pytest.raises(ValueError, match="CALCULATION_POLICY_CLOSED"):
        p.guard(value)


def test_daily_policy_keeps_its_single_day_and_child_counter_scope():
    from datetime import date

    from app.services.calculation_policy import ExecutionPolicy

    day = date(2025, 1, 2)
    job = NS(id=uuid4(), job_metadata={}, target_trade_date=day)
    policy = ExecutionPolicy.freeze(job, settings(), source={
        "source_sha256": "a" * 64, "commit_sha": None,
    })
    assert policy.record["request"] == {"start": "2025-01-02", "end": "2025-01-02"}
    assert policy.snapshot(metadata={}, target=day)["request"] == policy.record["request"]
    assert policy.snapshot()["counter_scope"] == "ROOT_CUMULATIVE_INCLUDING_CHILDREN"


def test_resident_worker_cannot_adopt_changed_source_for_a_new_job(monkeypatch):
    from app.services import calculation_policy as cp

    token = cp.worker_source.set({"source_sha256": "a" * 64, "commit_sha": None})
    monkeypatch.setattr(cp, "runtime_source", lambda: {
        "source_sha256": "b" * 64, "commit_sha": None,
    })
    try:
        with pytest.raises(ValueError, match="CALCULATION_POLICY_CHANGED"):
            cp.ExecutionPolicy.freeze(NS(id=uuid4(), job_metadata={}), settings())
    finally:
        cp.worker_source.reset(token)


def test_runtime_source_rejects_symlinked_module_directories(tmp_path, monkeypatch):
    from app.services import calculation_policy as cp

    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "module.py").write_text("changed = True\n")
    (tmp_path / "backend" / "app" / "services").symlink_to(tmp_path / "outside",
                                                           target_is_directory=True)
    monkeypatch.setattr(cp, "ROOT_DIR", tmp_path)
    with pytest.raises(ValueError, match="CALCULATION_SOURCE_UNTRUSTED"):
        cp.runtime_source()
