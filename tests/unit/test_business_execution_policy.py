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
