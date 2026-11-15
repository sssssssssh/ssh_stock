from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from app.services import calculation_policy, job_execution
from app.services.factors import service as factor_service
from app.services.job_execution import JobCancelled, JobExecutionUnconfirmed, JobOwnershipLost

from tests.unit.test_factor_engine import _fixture_data, _trade_status


@pytest.fixture
def unoptimized_service(monkeypatch):
    daily, adj, basic, index = _fixture_data()
    frames = (daily, adj, basic, _trade_status(daily), index)
    settings = SimpleNamespace(strategy={}, factor_cpu_optimization_enabled=False,
                               factor_input_reuse_enabled=False, ab_merge_read_enabled=False,
                               raw_preflight_batch_enabled=False, perf_diagnostics_enabled=False)
    monkeypatch.setattr(factor_service, "get_settings", lambda: settings)
    policy_token = calculation_policy.active_policy.set(None)
    db = SimpleNamespace(commits=0)

    def commit():
        db.commits += 1

    db.commit = commit
    service = factor_service.FactorService(db)
    for name, frame in zip(("_read_daily", "_read_adj_factor", "_read_stock_basic",
                            "_read_trade_status", "_read_index_daily"), frames, strict=True):
        monkeypatch.setattr(service, name, lambda *args, frame=frame: frame.copy(deep=True))
    writes = []

    def replace(db, model, rows, **kwargs):
        writes.append((model, rows, kwargs))
        return len(rows)

    monkeypatch.setattr(factor_service, "replace_slice_rows", replace)
    try:
        yield service, frames, writes
    finally:
        calculation_policy.active_policy.reset(policy_token)


@pytest.mark.parametrize("cancel_at", [1, 2, 3, 4, 5])
def test_default_factor_compute_cancels_before_any_candidate_write(
    monkeypatch, unoptimized_service, cancel_at,
):
    service, frames, writes = unoptimized_service
    checks = []
    cancelled = JobCancelled("JOB_CANCEL_REQUESTED")

    def checkpoint():
        checks.append(1)
        if len(checks) == cancel_at:
            raise cancelled

    monkeypatch.setattr(factor_service, "checkpoint", checkpoint)
    day = frames[0].trade_date.max()
    with pytest.raises(JobCancelled) as error:
        service.recalc(day, day, calc_run_id=uuid4())
    assert error.value is cancelled
    assert len(checks) == cancel_at
    assert writes == [] and service.db.commits == 0


@pytest.mark.parametrize("error_type", [JobOwnershipLost, JobExecutionUnconfirmed])
def test_default_factor_compute_preserves_execution_stop(
    monkeypatch, unoptimized_service, error_type,
):
    service, frames, writes = unoptimized_service
    failure = error_type("SYNTHETIC_EXECUTION_STOP")

    def checkpoint():
        raise failure

    monkeypatch.setattr(factor_service, "checkpoint", checkpoint)
    day = frames[0].trade_date.max()
    with pytest.raises(error_type) as error:
        service.recalc(day, day, calc_run_id=uuid4())
    assert error.value is failure
    assert writes == [] and service.db.commits == 0


@pytest.mark.parametrize("lost_owner", [False, True])
def test_default_factor_compute_observes_execution_after_raw_reads(
    monkeypatch, unoptimized_service, lost_owner,
):
    service, frames, writes = unoptimized_service
    root_id, token = uuid4(), uuid4()
    row = SimpleNamespace(status="RUNNING", worker_id="offline-worker", execution_token=token,
                          cancel_requested=False)
    observations = []

    class Observer:
        def __init__(self, *, bind):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement):
            observations.append(statement)
            return SimpleNamespace(one_or_none=lambda: row)

    original_read = service._read_index_daily

    def last_raw_read(*args):
        result = original_read(*args)
        if lost_owner:
            row.execution_token = uuid4()
        else:
            row.cancel_requested = True
        return result

    monkeypatch.setattr(service, "_read_index_daily", last_raw_read)
    monkeypatch.setattr(job_execution, "Session", Observer)
    execution_token = job_execution.current_execution.set(
        job_execution.Execution(root_id, "offline-worker", token, object()),
    )
    try:
        day = frames[0].trade_date.max()
        with pytest.raises(JobOwnershipLost if lost_owner else JobCancelled):
            service.recalc(day, day, calc_run_id=root_id)
    finally:
        job_execution.current_execution.reset(execution_token)
    assert len(observations) == 1
    assert writes == [] and service.db.commits == 0


def test_default_factor_compute_keeps_exact_factors_identity_and_scope(
    monkeypatch, unoptimized_service,
):
    service, frames, writes = unoptimized_service
    daily, adj, basic, status, index = frames
    originals = [frame.copy(deep=True) for frame in frames]
    day = daily.trade_date.max()
    run_id = uuid4()
    expected = factor_service.calculate_stock_factors(
        daily, adj, basic, index, "000300.SH", day, day,
        factor_service.FactorConfig.from_strategy(service.settings.strategy), trade_status=status,
    )
    checks = []
    monkeypatch.setattr(factor_service, "checkpoint", lambda: checks.append(1))
    count = service.recalc(day, day, calc_run_id=run_id)
    assert len(checks) == 5
    assert count == len(expected) == 3
    assert service.db.commits == 1 and len(writes) == 1
    model, rows, kwargs = writes[0]
    assert model is factor_service.StockFactorDaily
    metadata_keys = {"calc_version", "config_hash", "calc_run_id", "calculated_at"}
    assert [{key: value for key, value in row.items() if key not in metadata_keys}
            for row in rows] == [factor_service._clean_row(row)
                                for row in expected.to_dict("records")]
    assert all(row["calc_run_id"] == run_id and
               row["calc_version"] == factor_service.FACTOR_CALC_VERSION and
               row["config_hash"] == factor_service.analysis_strategy_hash(
                   service.settings.strategy) for row in rows)
    assert kwargs["key_columns"] == ["trade_date", "ts_code"]
    assert len(kwargs["scope_filters"]) == 2
    assert kwargs["scope_filters"][0].compare(model.trade_date >= day)
    assert kwargs["scope_filters"][1].compare(model.trade_date <= day)
    for actual, original in zip(frames, originals, strict=True):
        pd.testing.assert_frame_equal(actual, original, check_exact=True)
