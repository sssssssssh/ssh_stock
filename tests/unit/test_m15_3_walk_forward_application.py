import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import app.services.walk_forward.application as application_module
import app.services.walk_forward.source as source_module
import pytest
from app.core.config import get_settings
from app.domain.walk_forward.windows import WindowPlanError
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardParameterStability,
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.experiment.application import ExperimentApplicationError
from app.services.performance.analytics_bundle import AnalyticsBundleError
from app.services.walk_forward.application import (
    WALK_FORWARD_VALIDATION_JOB_TYPE,
    WalkForwardApplicationError,
    WalkForwardApplicationService,
    WalkForwardCancelledError,
    WalkForwardConflictError,
    WalkForwardOwnershipError,
)
from app.services.walk_forward.orchestration import WindowProjection
from app.services.walk_forward.planner import WalkForwardPlanner
from app.services.walk_forward.source import (
    WalkForwardSourceError,
    WalkForwardValidationSource,
    WalkForwardValidationSourceProvider,
)


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.rows[0] if self.rows else None


class _FakeDb:
    def __init__(self, *, scalars=(), objects=None, scalar_rows=()):
        self.scalar_rows = list(scalar_rows)
        self.scalar_values = list(scalars)
        self.objects = objects or {}
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    def scalars(self, _statement):
        return _Rows(self.scalar_rows)

    def execute(self, _statement):
        return _Rows(self.scalar_rows)

    def get(self, model, identity):
        return self.objects.get((model, identity))

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid.uuid4()
        self.refreshed.append(value)


def _study() -> PortfolioWalkForwardStudy:
    now = datetime(2026, 10, 8, tzinfo=UTC)
    return PortfolioWalkForwardStudy(
        id=uuid.uuid4(),
        name="unit-study",
        walk_forward_version="walk_forward_v1",
        mode="ROLLING",
        exchange="SSE",
        requested_start_date=date(2026, 1, 1),
        requested_end_date=date(2026, 1, 6),
        train_trade_days=2,
        test_trade_days=2,
        step_trade_days=2,
        window_count=1,
        unused_tail_trade_days=0,
        calendar_hash="c" * 64,
        initial_cash=Decimal("1000000"),
        benchmark_code="000300.SH",
        parameter_space={
            "candidate.min_score": ["70"],
            "candidate.top_n": [20],
            "construction.max_positions": [5],
            "construction.max_single_position_weight": ["0.2"],
            "construction.min_cash_ratio": ["0.1"],
            "construction.max_new_positions_per_day": [2],
        },
        parameter_space_hash="p" * 64,
        train_policy_snapshot={},
        train_policy_hash="q" * 64,
        base_algo_version="algo",
        base_source_strategy_config_hash="a" * 64,
        base_opportunity_calc_version="opp",
        base_opportunity_config_hash="b" * 64,
        base_portfolio_version="portfolio_v3",
        base_portfolio_config_hash="d" * 64,
        base_execution_version="execution_v3",
        base_execution_config_hash="e" * 64,
        base_accounting_version="accounting_v3",
        base_accounting_config_hash="f" * 64,
        base_backtest_engine_version="backtest_v7",
        base_config_snapshot={},
        definition_hash="g" * 64,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
    )


def _window(study_id: uuid.UUID) -> PortfolioWalkForwardWindow:
    return PortfolioWalkForwardWindow(
        study_id=study_id,
        window_no=1,
        train_start_date=date(2026, 1, 1),
        train_end_date=date(2026, 1, 2),
        test_start_date=date(2026, 1, 3),
        test_end_date=date(2026, 1, 4),
        train_trade_days=2,
        test_trade_days=2,
        train_trade_dates=["2026-01-01", "2026-01-02"],
        test_trade_dates=["2026-01-03", "2026-01-04"],
        train_date_hash="t" * 64,
        test_date_hash="o" * 64,
    )


def _service(*, db=None, repository=None) -> WalkForwardApplicationService:
    service = object.__new__(WalkForwardApplicationService)
    service.db = db or _FakeDb()
    service.settings = get_settings()
    service.config = service.settings.walk_forward_config
    service.repository = repository or SimpleNamespace()
    service.experiments = SimpleNamespace()
    service.evaluations = SimpleNamespace()
    service.bundle_resolver = SimpleNamespace()
    service.source_provider = SimpleNamespace()
    service.before_terminal_hook = None
    service._study_lock = lambda _study_id: None
    service._validation_lock = lambda *_args: None
    return service


def _report(study_id: uuid.UUID) -> PortfolioWalkForwardValidationReport:
    report = PortfolioWalkForwardValidationReport(
        id=uuid.uuid4(), study_id=study_id, walk_forward_version="walk_forward_v1",
        walk_forward_config_hash="w" * 64,
        policy_identity_version="policy_v1",
        validation_policy_snapshot={"version": "walk_forward_validation_policy_v1"},
        validation_policy_hash="w" * 64, source_hash="s" * 64,
        status="SUCCESS", window_count=1, total_oos_trade_days=2,
        stitched_oos_final_nav=Decimal("1"), stitched_oos_cumulative_return=Decimal("0"),
        stitched_oos_annualized_return=Decimal("0"), stitched_oos_max_drawdown=Decimal("0"),
        stitched_oos_annualized_volatility=None, stitched_oos_sharpe_ratio=None,
        stitched_benchmark_final_nav=Decimal("1"),
        stitched_benchmark_cumulative_return=Decimal("0"),
        stitched_excess_cumulative_return=Decimal("0"), positive_oos_window_count=0,
        positive_oos_window_rate=Decimal("0"), mean_oos_annualized_return=Decimal("0"),
        median_oos_annualized_return=Decimal("0"), mean_return_degradation=Decimal("0"),
        median_return_degradation=Decimal("0"), mean_drawdown_worsening=Decimal("0"),
        median_drawdown_worsening=Decimal("0"), unique_selected_parameter_hash_count=1,
        dominant_parameter_hash="h" * 64, dominant_parameter_hash_count=1,
        dominant_parameter_hash_rate=Decimal("1"), transition_count=0,
        switch_count=0, switch_rate=None, warnings=[], result_summary={},
    )
    report.calculated_at = datetime(2026, 10, 8, tzinfo=UTC)
    report.created_at = report.calculated_at
    report.updated_at = report.calculated_at
    return report


def test_application_read_pages_and_serializers() -> None:
    study = _study()
    window = _window(study.id)
    report = _report(study.id)
    window_result = PortfolioWalkForwardWindowValidation(
        validation_id=report.id, study_id=study.id, window_no=1,
        train_experiment_id=uuid.uuid4(), train_evaluation_id=uuid.uuid4(),
        selected_trial_id=uuid.uuid4(), selected_train_run_id=uuid.uuid4(),
        train_performance_id=uuid.uuid4(), train_risk_id=uuid.uuid4(),
        train_trade_id=uuid.uuid4(), train_period_id=uuid.uuid4(),
        selected_parameter_hash="h" * 64, selected_parameter_values={},
        train_date_hash="t" * 64, test_date_hash="o" * 64,
        identity_snapshot={"schema_version": "walk_forward_window_validation_identity_v1"},
        oos_run_id=uuid.uuid4(),
        oos_performance_id=uuid.uuid4(), oos_risk_id=uuid.uuid4(),
        oos_trade_id=uuid.uuid4(), oos_period_id=uuid.uuid4(),
        train_annualized_return=Decimal("0"), train_max_drawdown_abs=Decimal("0"),
        train_sharpe_ratio=None, train_annualized_turnover=Decimal("0"),
        oos_cumulative_return=Decimal("0"), oos_annualized_return=Decimal("0"),
        oos_max_drawdown_abs=Decimal("0"), oos_sharpe_ratio=None,
        oos_annualized_turnover=Decimal("0"), oos_total_cost_to_initial_capital=Decimal("0"),
        oos_win_rate=None, oos_profit_factor=None, return_degradation=Decimal("0"),
        sharpe_degradation=None, drawdown_worsening=Decimal("0"),
        turnover_change=Decimal("0"),
    )
    stability = PortfolioWalkForwardParameterStability(
        validation_id=report.id, study_id=study.id, parameter_name="candidate.top_n",
        parameter_value="20", selected_window_count=1, selected_rate=Decimal("1"),
        transition_count=0, adjacent_value_switch_count=0,
        adjacent_value_switch_rate=None,
    )
    repository = SimpleNamespace(
        get=lambda requested: study if requested == study.id else None,
        list_windows=lambda _study_id: [window],
        get_validation=lambda _study_id, _validation_id: report,
        validation_history=lambda _study_id, **_kwargs: ([report], 1),
        window_validation_page=lambda _validation_id, **_kwargs: ([window_result], 1),
        stability=lambda _validation_id: [stability],
    )
    service = _service(repository=repository)

    detail = service.get(study.id)
    rows, total = service.windows(study.id, state="TRAIN_PLANNED", limit=10, offset=0)
    history, history_total = service.validation_history(study.id, limit=10, offset=0)
    window_rows, window_total = service.validation_windows(study.id, report.id, limit=10, offset=0)
    stability_rows = service.validation_stability(study.id, report.id)

    assert detail["progress"]["state_counts"] == {"TRAIN_PLANNED": 1}
    assert total == 1 and rows[0]["window_no"] == 1
    assert history_total == 1 and history[0]["identity"]["validation_id"] == str(report.id)
    assert window_total == 1 and window_rows[0]["window_no"] == 1
    assert stability_rows[0]["parameter_name"] == "candidate.top_n"
    assert service.validation_detail(study.id, report.id)["status"] == "SUCCESS"
    with pytest.raises(WalkForwardApplicationError, match="study not found"):
        service._study(uuid.uuid4())


def test_cancel_sets_gate_then_cancels_active_children(monkeypatch) -> None:
    study = _study()
    window = _window(study.id)
    experiment_id, run_id = uuid.uuid4(), uuid.uuid4()
    window.train_experiment_id = experiment_id
    window.oos_run_id = run_id
    db = _FakeDb(objects={
        (PortfolioExperiment, experiment_id): SimpleNamespace(id=experiment_id),
        (PortfolioBacktestRun, run_id): SimpleNamespace(id=run_id, status="RUNNING"),
    })
    repository = SimpleNamespace(
        get_for_update=lambda _study_id: study, list_windows=lambda _study_id: [window]
    )
    service = _service(db=db, repository=repository)
    service._train_active = lambda _experiment_id: True
    train_cancelled, oos_cancelled = [], []
    service.experiments = SimpleNamespace(
        cancel=lambda requested: train_cancelled.append(requested)
    )

    class FakeBacktest:
        def __init__(self, _db, *, settings):
            assert settings is service.settings

        def cancel(self, requested):
            oos_cancelled.append(requested)

    monkeypatch.setattr(application_module, "BacktestApplicationService", FakeBacktest)
    result = service.cancel(study.id)
    assert study.cancel_requested is True and db.commits == 1
    assert train_cancelled == [experiment_id] and oos_cancelled == [run_id]
    assert {row["scope"] for row in result["cancelled_children"]} == {"TRAIN", "OOS"}


def test_validation_queue_conflict_cancel_and_success() -> None:
    study = _study()
    source = WalkForwardValidationSource(
        study=study, windows=(), source_hash="s" * 64,
        walk_forward_config_hash="w" * 64,
        policy_identity_version="policy_v1",
        validation_policy_snapshot={"version": "walk_forward_validation_policy_v1"},
        validation_policy_hash="w" * 64, annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0"),
    )
    active = SimpleNamespace(id=uuid.uuid4())
    repository = SimpleNamespace(get_for_update=lambda _study_id: study)
    service = _service(db=_FakeDb(scalars=[active]), repository=repository)
    service._load_source = lambda _study_id: source
    with pytest.raises(WalkForwardConflictError) as conflict:
        service.queue_validation(study.id)
    assert conflict.value.job_id == active.id

    study.cancel_requested = True
    with pytest.raises(WalkForwardApplicationError) as cancelled:
        service.queue_validation(study.id)
    assert cancelled.value.code == "WALK_FORWARD_CANCELLED"

    study.cancel_requested = False
    db = _FakeDb(scalars=[None])
    service.db = db
    job = service.queue_validation(study.id)
    assert job.status == "QUEUED" and job.job_metadata["source_hash"] == source.source_hash
    assert db.commits == 1 and db.refreshed == [job]


def test_validation_job_ownership_source_fence_and_terminal_success() -> None:
    study = _study()
    source = WalkForwardValidationSource(
        study=study, windows=(), source_hash="s" * 64,
        walk_forward_config_hash="w" * 64,
        policy_identity_version="policy_v1",
        validation_policy_snapshot={"version": "walk_forward_validation_policy_v1"},
        validation_policy_hash="w" * 64, annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0"),
    )
    report = _report(study.id)
    job = SimpleNamespace(
        id=uuid.uuid4(), job_type=WALK_FORWARD_VALIDATION_JOB_TYPE, status="RUNNING",
        worker_id="worker-1", job_metadata={
            "study_id": str(study.id), "source_hash": source.source_hash,
            "walk_forward_version": "walk_forward_v1",
            "walk_forward_config_hash": source.walk_forward_config_hash,
            "policy_identity_version": source.policy_identity_version,
            "validation_policy_snapshot": source.validation_policy_snapshot,
            "validation_policy_hash": source.validation_policy_hash,
        }, finished_at=None, step=None, row_count=0, cancel_requested=False,
    )
    db = _FakeDb(scalars=[job, job])
    repository = SimpleNamespace(
        get_for_update=lambda _study_id: study,
        find_validation=lambda **_kwargs: None,
        add_validation=lambda *_args: None,
    )
    service = _service(db=db, repository=repository)
    service._load_source = lambda _study_id: source
    service._build_validation_artifact = lambda _source, **_kwargs: SimpleNamespace(
        report=report, windows=[], stability=[]
    )
    terminal_calls = []
    service.before_terminal_hook = lambda seen_job, seen_report: terminal_calls.append(
        (seen_job.id, seen_report.id)
    )
    result, reused = service.run_validation_job(job.id)
    assert result is report and reused is False and job.status == "SUCCESS"
    assert terminal_calls == [(job.id, report.id)] and db.commits == 1

    invalid = SimpleNamespace(**{**job.__dict__, "status": "QUEUED"})
    service.db = _FakeDb(scalars=[invalid])
    with pytest.raises(WalkForwardOwnershipError):
        service.run_validation_job(invalid.id)

    changed = SimpleNamespace(**{**job.__dict__, "status": "RUNNING"})
    changed.job_metadata = {**job.job_metadata, "source_hash": "x" * 64}
    service.db = _FakeDb(scalars=[changed])
    with pytest.raises(WalkForwardApplicationError) as drift:
        service.run_validation_job(changed.id)
    assert drift.value.code == "WALK_FORWARD_SOURCE_CHANGED"

    running = SimpleNamespace(**{**job.__dict__, "status": "RUNNING"})
    running.job_metadata = {
        **job.job_metadata,
        "source_hash": source.source_hash,
        "stage": "RUNNING",
    }
    lost = SimpleNamespace(**{**running.__dict__, "worker_id": "replacement"})
    fenced_db = _FakeDb(scalars=[running, lost])
    service.db = fenced_db
    with pytest.raises(WalkForwardOwnershipError):
        service.run_validation_job(running.id)
    assert fenced_db.rollbacks == 1


def test_validation_job_allows_runtime_config_change_but_rejects_policy_change() -> None:
    study = _study()
    queued = WalkForwardValidationSource(
        study=study,
        windows=(),
        source_hash="s" * 64,
        walk_forward_config_hash="q" * 64,
        policy_identity_version="policy_v1",
        validation_policy_snapshot={"version": "walk_forward_validation_policy_v1"},
        validation_policy_hash="p" * 64,
        annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0"),
    )
    current = replace(queued, walk_forward_config_hash="c" * 64)
    job = SimpleNamespace(
        id=uuid.uuid4(),
        job_type=WALK_FORWARD_VALIDATION_JOB_TYPE,
        status="RUNNING",
        worker_id="worker-1",
        job_metadata={
            "study_id": str(study.id),
            "walk_forward_version": "walk_forward_v1",
            "walk_forward_config_hash": queued.walk_forward_config_hash,
            "policy_identity_version": queued.policy_identity_version,
            "validation_policy_snapshot": queued.validation_policy_snapshot,
            "validation_policy_hash": queued.validation_policy_hash,
            "source_hash": queued.source_hash,
        },
        finished_at=None,
        step=None,
        row_count=0,
        cancel_requested=False,
    )
    report = _report(study.id)
    captured: list[str | None] = []
    service = _service(
        db=_FakeDb(scalars=[job, job]),
        repository=SimpleNamespace(
            get_for_update=lambda _study_id: study,
            find_validation=lambda **_kwargs: None,
            add_validation=lambda *_args: None,
        ),
    )
    service._load_source = lambda _study_id: current

    def build(_source, *, audit_config_hash=None):
        captured.append(audit_config_hash)
        return SimpleNamespace(report=report, windows=[], stability=[])

    service._build_validation_artifact = build
    assert service.run_validation_job(job.id)[0] is report
    assert captured == [queued.walk_forward_config_hash]

    changed_policy = replace(
        current,
        validation_policy_snapshot={
            "version": "walk_forward_validation_policy_v1",
            "short_oos_warning_trade_days": 99,
        },
        validation_policy_hash="x" * 64,
    )
    running = SimpleNamespace(**{**job.__dict__, "status": "RUNNING"})
    service.db = _FakeDb(scalars=[running])
    service._load_source = lambda _study_id: changed_policy
    with pytest.raises(WalkForwardApplicationError) as policy_changed:
        service.run_validation_job(running.id)
    assert policy_changed.value.code == "WALK_FORWARD_VALIDATION_POLICY_CHANGED"


def test_validation_terminal_stop_gate_cancels_without_persisting_artifact() -> None:
    study = _study()
    source = WalkForwardValidationSource(
        study=study,
        windows=(),
        source_hash="s" * 64,
        walk_forward_config_hash="w" * 64,
        policy_identity_version="policy_v1",
        validation_policy_snapshot={"version": "walk_forward_validation_policy_v1"},
        validation_policy_hash="w" * 64,
        annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0"),
    )
    report = _report(study.id)
    job = SimpleNamespace(
        id=uuid.uuid4(),
        job_type=WALK_FORWARD_VALIDATION_JOB_TYPE,
        status="RUNNING",
        worker_id="worker-1",
        job_metadata={
            "study_id": str(study.id),
            "source_hash": source.source_hash,
            "walk_forward_version": "walk_forward_v1",
            "walk_forward_config_hash": source.walk_forward_config_hash,
            "policy_identity_version": source.policy_identity_version,
            "validation_policy_snapshot": source.validation_policy_snapshot,
            "validation_policy_hash": source.validation_policy_hash,
        },
        finished_at=None,
        step=None,
        row_count=0,
        cancel_requested=False,
    )
    persisted = []
    repository = SimpleNamespace(
        get_for_update=lambda _study_id: study,
        add_validation=lambda *_args: persisted.append(True),
    )
    db = _FakeDb(scalars=[job, job])
    service = _service(db=db, repository=repository)
    service._load_source = lambda _study_id: source
    service._build_validation_artifact = lambda _source, **_kwargs: SimpleNamespace(
        report=report, windows=[], stability=[]
    )
    service.before_terminal_hook = lambda *_args: setattr(
        study, "cancel_requested", True
    )

    with pytest.raises(WalkForwardCancelledError):
        service.run_validation_job(job.id)
    assert job.status == "CANCELLED"
    assert job.job_metadata["error_code"] == "WALK_FORWARD_CANCELLED"
    assert persisted == []
    assert db.commits == 1


def test_advance_queues_evaluation_freezes_selection_and_creates_oos(monkeypatch) -> None:
    study = _study()
    window = _window(study.id)
    experiment = SimpleNamespace(
        id=uuid.uuid4(),
        started_at=datetime.now(UTC),
        base_config_snapshot={
            "strategy": {},
            "opportunity": {},
            "execution": {},
            "accounting": {},
        },
    )
    window.train_experiment_id = experiment.id
    report = SimpleNamespace(
        id=uuid.uuid4(),
        selected_trial_id=uuid.uuid4(),
        selected_run_id=uuid.uuid4(),
    )
    repository = SimpleNamespace(
        get_for_update=lambda _study_id: study,
        get_window_for_update=lambda _study_id, _window_no: window,
        add_run=lambda _run: None,
    )
    db = _FakeDb(objects={(PortfolioExperiment, experiment.id): experiment})
    service = _service(db=db, repository=repository)
    service._frozen_experiment_service = lambda _study: SimpleNamespace()
    service._validate_train_experiment = lambda *_args: None
    service._train_active = lambda _experiment_id: False
    service._study_policy = lambda _study: SimpleNamespace()
    service._active_evaluation_job = lambda *_args: None

    queued_job = SimpleNamespace(id=uuid.uuid4())
    service.evaluations = SimpleNamespace(
        readiness=lambda _experiment_id: {"ready": True},
        resolve_current_artifact=lambda *_args: None,
        queue_calculation=lambda *_args: queued_job,
    )
    queued = service._advance_window(study.id, 1)
    assert queued["action"] == "QUEUE_TRAIN_EVALUATION"

    service.evaluations.resolve_current_artifact = lambda *_args: report
    def freeze(selected_window, _experiment, selected_report):
        selected_window.train_evaluation_id = selected_report.id
        selected_window.selected_trial_id = selected_report.selected_trial_id
        selected_window.selected_portfolio_config_snapshot = {"version": "portfolio_v3"}
        selected_window.selected_portfolio_config_hash = "z" * 64
    service._freeze_selection = freeze
    assert service._advance_window(study.id, 1)["action"] == "FREEZE_SELECTION"

    service._validate_frozen_selection = lambda *_args: None
    run = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        application_module.BacktestRunFactory, "build", staticmethod(lambda **_kwargs: run)
    )
    oos_job = SimpleNamespace(id=uuid.uuid4())
    class FakeBacktest:
        def __init__(self, _db, *, settings):
            assert settings is not None
        def execute(self, requested):
            assert requested == run.id
            return run, oos_job
    monkeypatch.setattr(application_module, "BacktestApplicationService", FakeBacktest)
    service._frozen_settings = lambda _study: service.settings
    created = service._advance_window(study.id, 1)
    assert created["action"] == "CREATE_AND_QUEUE_OOS_RUN"


def test_advance_existing_oos_pins_bundle_and_keeps_terminal_failures() -> None:
    study = _study()
    window = _window(study.id)
    experiment = SimpleNamespace(id=uuid.uuid4(), started_at=datetime.now(UTC))
    window.train_experiment_id = experiment.id
    window.train_evaluation_id = uuid.uuid4()
    window.selected_trial_id = uuid.uuid4()
    window.selected_portfolio_config_snapshot = {}
    window.oos_run_id = uuid.uuid4()
    run = SimpleNamespace(id=window.oos_run_id, status="FAILED")
    db = _FakeDb(objects={
        (PortfolioExperiment, experiment.id): experiment,
        (PortfolioBacktestRun, run.id): run,
    })
    repository = SimpleNamespace(
        get_for_update=lambda _study_id: study,
        get_window_for_update=lambda _study_id, _window_no: window,
    )
    service = _service(db=db, repository=repository)
    service._frozen_experiment_service = lambda _study: SimpleNamespace()
    service._validate_train_experiment = lambda *_args: None
    service._train_active = lambda _experiment_id: False
    service._study_policy = lambda _study: SimpleNamespace()
    service.evaluations = SimpleNamespace(
        readiness=lambda _id: {"ready": True},
        resolve_current_artifact=lambda *_args: SimpleNamespace(
            selected_trial_id=window.selected_trial_id,
            selected_run_id=uuid.uuid4(),
        ),
    )
    service._validate_frozen_selection = lambda *_args: None
    service._validate_oos_run = lambda *_args: None
    assert service._advance_window(study.id, 1) is None

    run.status = "SUCCESS"
    bundle = SimpleNamespace()
    service.bundle_resolver = SimpleNamespace(resolve=lambda *_args, **_kwargs: bundle)
    pinned = []
    service._pin_oos_bundle = lambda selected_window, selected: pinned.append(
        (selected_window, selected)
    )
    assert service._advance_window(study.id, 1)["action"] == "PIN_OOS_ANALYTICS"
    assert pinned == [(window, bundle)]


def test_selection_and_bundle_freeze_validate_rank_dates_and_immutability() -> None:
    study = _study()
    window = _window(study.id)
    experiment = SimpleNamespace(id=uuid.uuid4())
    trial = SimpleNamespace(
        id=uuid.uuid4(), experiment_id=experiment.id, run_id=uuid.uuid4(),
        parameter_hash="h" * 64, parameter_values={"candidate.top_n": 20},
        portfolio_config_hash="p" * 64,
        portfolio_config_snapshot={"version": "portfolio_v3"},
    )
    report = SimpleNamespace(
        id=uuid.uuid4(), experiment_id=experiment.id,
        selected_trial_id=trial.id, selected_run_id=trial.run_id,
    )
    evaluation = SimpleNamespace(
        experiment_id=experiment.id, status="EVALUATED", feasible=True,
        shortlisted=True, selection_rank=1,
    )
    db = _FakeDb(
        scalars=[evaluation], objects={(PortfolioExperimentTrial, trial.id): trial},
        scalar_rows=[date(2026, 1, 3), date(2026, 1, 4)],
    )
    service = _service(db=db)
    service._freeze_selection(window, experiment, report)
    assert window.train_evaluation_id == report.id

    bundle = SimpleNamespace(
        performance=SimpleNamespace(id=uuid.uuid4()), risk=SimpleNamespace(id=uuid.uuid4()),
        trade=SimpleNamespace(id=uuid.uuid4()), period=SimpleNamespace(id=uuid.uuid4()),
    )
    service._pin_oos_bundle(window, bundle)
    service._pin_oos_bundle(window, bundle)
    changed = SimpleNamespace(
        performance=SimpleNamespace(id=uuid.uuid4()), risk=bundle.risk,
        trade=bundle.trade, period=bundle.period,
    )
    with pytest.raises(WalkForwardApplicationError) as mismatch:
        service._pin_oos_bundle(window, changed)
    assert mismatch.value.code == "WALK_FORWARD_OOS_BUNDLE_MISMATCH"


def test_projection_required_actions_and_identity_guards() -> None:
    study = _study()
    service = _service()
    experiment_id, run_id = uuid.uuid4(), uuid.uuid4()
    service.evaluations = SimpleNamespace(readiness=lambda _id: {
        "missing_analytics": [{"run_id": str(run_id), "missing_stage": "risk"}]
    })
    service.bundle_resolver = SimpleNamespace(resolve=lambda *_args, **_kwargs: (
        _ for _ in ()
    ).throw(AnalyticsBundleError("INCOMPLETE", "trade artifact is missing")))
    required = service._required_actions(study, [
        {
            "window_no": 1,
            "state": "TRAIN_ANALYTICS_REQUIRED",
            "train_experiment_id": str(experiment_id),
        },
        {"window_no": 2, "state": "OOS_ANALYTICS_REQUIRED", "oos_run_id": str(run_id)},
    ])
    assert [row["missing_stage"] for row in required] == ["risk", "trade"]

    service.evaluations = SimpleNamespace(
        readiness=lambda _id: {"ready": True},
        resolve_current_artifact=lambda *_args: SimpleNamespace(selected_trial_id=None),
    )
    service._study_policy = lambda _study: SimpleNamespace()
    refined = service._refine_projection(
        study, _window(study.id), WindowProjection("TRAIN_TERMINAL"),
        SimpleNamespace(id=experiment_id), None,
    )
    assert refined.state == "TRAIN_NO_FEASIBLE_CANDIDATE" and refined.blocked

    incomplete = _window(study.id)
    with pytest.raises(WalkForwardApplicationError) as selection:
        service._validate_frozen_selection(incomplete, SimpleNamespace(id=experiment_id))
    assert selection.value.code == "WALK_FORWARD_SELECTION_NOT_FROZEN"

    incomplete.train_evaluation_id = uuid.uuid4()
    incomplete.selected_trial_id = uuid.uuid4()
    incomplete.selected_portfolio_config_snapshot = {}
    service.db = _FakeDb()
    with pytest.raises(WalkForwardApplicationError) as identity:
        service._validate_frozen_selection(incomplete, SimpleNamespace(id=experiment_id))
    assert identity.value.code == "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH"

    with pytest.raises(WalkForwardApplicationError) as oos:
        service._validate_oos_run(
            study, incomplete,
            SimpleNamespace(
                base_source_strategy_config_hash="a", base_opportunity_config_hash="b",
                base_execution_config_hash="c", base_accounting_config_hash="d",
            ),
            SimpleNamespace(start_date=date(2000, 1, 1)),
        )
    assert oos.value.code == "WALK_FORWARD_OOS_IDENTITY_MISMATCH"


def test_planner_rejects_reversed_range_and_missing_calendar() -> None:
    config = get_settings().walk_forward_config
    assert config is not None
    planner = WalkForwardPlanner(_FakeDb(), config)
    with pytest.raises(WindowPlanError) as reversed_range:
        planner.plan(
            requested_start_date=date(2026, 1, 2),
            requested_end_date=date(2026, 1, 1),
            mode="ROLLING",
            train_trade_days=2,
            test_trade_days=1,
            step_trade_days=1,
        )
    assert reversed_range.value.code == "WALK_FORWARD_CONFIG_INVALID"
    with pytest.raises(WindowPlanError) as missing:
        planner.plan(
            requested_start_date=date(2026, 1, 1),
            requested_end_date=date(2026, 1, 2),
            mode="ROLLING",
            train_trade_days=2,
            test_trade_days=1,
            step_trade_days=1,
        )
    assert missing.value.code == "WALK_FORWARD_CALENDAR_INCOMPLETE"


def test_source_readiness_preserves_fail_closed_diagnostics() -> None:
    config = get_settings().walk_forward_config
    assert config is not None
    provider = WalkForwardValidationSourceProvider(_FakeDb(), config)
    study_id = uuid.uuid4()

    provider.collect_readiness_blockers = lambda _study_id: [
        {
            "code": "WALK_FORWARD_SOURCE_CHANGED",
            "window_no": 3,
            "scope": "SOURCE",
            "missing_stage": "source_identity",
            "action": "NO_AUTOMATIC_REPAIR",
        }
    ]
    assert provider.readiness(study_id) == {
        "study_id": str(study_id),
        "ready": False,
        "error_code": "WALK_FORWARD_SOURCE_CHANGED",
        "window_no": 3,
        "scope": "SOURCE",
        "missing_stage": "source_identity",
        "action": "NO_AUTOMATIC_REPAIR",
        "details": {
            "window_no": 3,
            "scope": "SOURCE",
            "missing_stage": "source_identity",
            "action": "NO_AUTOMATIC_REPAIR",
        },
        "blockers": [
            {
                "code": "WALK_FORWARD_SOURCE_CHANGED",
                "window_no": 3,
                "scope": "SOURCE",
                "missing_stage": "source_identity",
                "action": "NO_AUTOMATIC_REPAIR",
            }
        ],
    }

    with pytest.raises(WalkForwardSourceError) as invalid:
        provider._invalid("changed without a window")
    assert invalid.value.details == {
        "scope": "SOURCE",
        "missing_stage": "source_identity",
        "action": "NO_AUTOMATIC_REPAIR",
    }

    with pytest.raises(WalkForwardSourceError) as invalid_oos:
        provider._validate_oos(
            _study(),
            _window(study_id),
            SimpleNamespace(
                base_config_snapshot={
                    "strategy": {},
                    "opportunity": {},
                    "execution": {},
                    "accounting": {},
                }
            ),
            SimpleNamespace(portfolio_config_snapshot={}),
            SimpleNamespace(status="FAILED"),
        )
    assert invalid_oos.value.code == "WALK_FORWARD_OOS_IDENTITY_MISMATCH"


def test_readiness_collects_all_window_blockers_in_stable_order(monkeypatch) -> None:
    config = get_settings().walk_forward_config
    assert config is not None
    study = _study()
    study.window_count = 2
    first = _window(study.id)
    second = _window(study.id)
    second.window_no = 2
    db = _FakeDb(scalars=[study, study], scalar_rows=[first, second])
    provider = WalkForwardValidationSourceProvider(db, config)
    monkeypatch.setattr(
        source_module, "_stored_definition_hash", lambda *_args: study.definition_hash
    )

    first_result = provider.readiness(study.id)
    second_result = provider.readiness(study.id)

    assert first_result == second_result
    assert first_result["ready"] is False
    assert len(first_result["blockers"]) == 16
    assert [
        (row["window_no"], row["scope"], row["missing_stage"])
        for row in first_result["blockers"]
    ] == [
        (window_no, scope, stage)
        for window_no in (1, 2)
        for scope, stage in (
            ("TRAIN", "train_experiment"),
            ("TRAIN", "train_evaluation"),
            ("TRAIN", "selection"),
            ("OOS", "oos_run"),
            ("OOS", "performance"),
            ("OOS", "risk"),
            ("OOS", "trade"),
            ("OOS", "period"),
        )
    ]
    assert db.commits == 0 and db.added == []


def test_readiness_collects_all_missing_train_analytics_with_run_identity(
    monkeypatch,
) -> None:
    config = get_settings().walk_forward_config
    assert config is not None
    study = _study()
    window = _window(study.id)
    window.train_experiment_id = uuid.uuid4()
    window.train_evaluation_id = uuid.uuid4()
    window.selected_trial_id = uuid.uuid4()
    window.selected_parameter_hash = "h" * 64
    window.selected_parameter_values = {"candidate.top_n": 20}
    window.selected_portfolio_config_hash = "p" * 64
    window.selected_portfolio_config_snapshot = {"version": "portfolio_v3"}
    window.oos_run_id = uuid.uuid4()
    window.oos_performance_id = uuid.uuid4()
    window.oos_risk_id = uuid.uuid4()
    window.oos_trade_id = uuid.uuid4()
    window.oos_period_id = uuid.uuid4()
    window.oos_bound_at = datetime.now(UTC)
    run_id = uuid.uuid4()
    trial = SimpleNamespace(run_id=run_id)
    trial_evaluation = SimpleNamespace(
        performance_id=None,
        risk_id=None,
        trade_id=None,
        period_id=None,
    )
    db = _FakeDb(
        scalars=[study, trial_evaluation],
        scalar_rows=[window],
        objects={(PortfolioExperimentTrial, window.selected_trial_id): trial},
    )
    provider = WalkForwardValidationSourceProvider(db, config)
    monkeypatch.setattr(
        source_module, "_stored_definition_hash", lambda *_args: study.definition_hash
    )

    blockers = provider.collect_readiness_blockers(study.id)

    assert [row["missing_stage"] for row in blockers] == [
        "performance",
        "risk",
        "trade",
        "period",
    ]
    assert all(row["scope"] == "TRAIN" for row in blockers)
    assert all(row["run_id"] == str(run_id) for row in blockers)
    assert db.commits == 0 and db.added == []


def test_readiness_reports_missing_study_without_side_effects() -> None:
    config = get_settings().walk_forward_config
    assert config is not None
    db = _FakeDb()
    provider = WalkForwardValidationSourceProvider(db, config)

    assert provider.collect_readiness_blockers(uuid.uuid4()) == [
        {
            "code": "WALK_FORWARD_NOT_FOUND",
            "window_no": None,
            "scope": "STUDY",
            "missing_stage": "study",
            "action": "CREATE_WALK_FORWARD",
        }
    ]
    assert db.commits == 0 and db.added == []


def test_application_configuration_policy_and_lookup_guards() -> None:
    settings = get_settings().model_copy(deep=True)
    settings.walk_forward_config = None
    with pytest.raises(RuntimeError, match="configuration is not loaded"):
        WalkForwardApplicationService(_FakeDb(), settings=settings)

    study = _study()
    service = _service(
        repository=SimpleNamespace(get_validation=lambda *_args: None)
    )
    study.train_policy_snapshot = {"unexpected": True}
    with pytest.raises(WalkForwardApplicationError) as invalid_policy:
        service._study_policy(study)
    assert invalid_policy.value.code == "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH"

    evaluation_config = get_settings().experiment_evaluation_config
    assert evaluation_config is not None
    study.train_policy_snapshot = evaluation_config.default_policy.model_dump(mode="json")
    service.evaluations = SimpleNamespace(
        normalize_policy=lambda _policy: ({}, "wrong-hash")
    )
    with pytest.raises(WalkForwardApplicationError) as changed_policy:
        service._study_policy(study)
    assert changed_policy.value.code == "WALK_FORWARD_SELECTION_IDENTITY_MISMATCH"

    service.evaluations = SimpleNamespace(
        normalize_policy=lambda _policy: ({}, study.train_policy_hash)
    )
    assert service._study_policy(study).primary_objective == "annualized_return"
    with pytest.raises(WalkForwardApplicationError, match="validation not found"):
        service._validation(study.id, uuid.uuid4())


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            WindowPlanError("WALK_FORWARD_INSUFFICIENT_WINDOWS", "short"),
            "WALK_FORWARD_INSUFFICIENT_WINDOWS",
        ),
        (
            ExperimentApplicationError("EXPERIMENT_CONFIG_INVALID", "bad base"),
            "WALK_FORWARD_CONFIG_INVALID",
        ),
        (ValueError("bad grid"), "WALK_FORWARD_CONFIG_INVALID"),
    ],
)
def test_create_normalizes_dependency_errors(failure, expected_code) -> None:
    service = _service()
    if isinstance(failure, WindowPlanError):
        service.planner = SimpleNamespace(
            plan=lambda **_kwargs: (_ for _ in ()).throw(failure)
        )
        service.experiments = SimpleNamespace()
    else:
        service.planner = SimpleNamespace(plan=lambda **_kwargs: (None, "c" * 64))
        service.experiments = SimpleNamespace(
            freeze_current_base=lambda **_kwargs: (_ for _ in ()).throw(failure)
        )
    service.evaluations = SimpleNamespace()
    with pytest.raises(WalkForwardApplicationError) as raised:
        service.create(
            name=None,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            mode="ROLLING",
            train_trade_days=2,
            test_trade_days=1,
            step_trade_days=1,
            initial_cash=None,
            benchmark_code=None,
            grid={},
            train_evaluation_policy=None,
        )
    assert raised.value.code == expected_code
