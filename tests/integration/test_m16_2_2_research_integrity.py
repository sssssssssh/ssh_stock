import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.domain.agent.contracts import WalkForwardWindowLineageInput
from app.domain.agent.policy import serialized_result
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.market_data import TradeCalendar
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.archive.projectors import validate_projection
from app.services.agent.chat.comparison_contract import (
    BacktestComparisonContractResolver,
)
from app.services.agent.chat.comparison_policy import (
    ComparisonEvidenceContext,
    ComparisonFactContext,
)
from app.services.agent.chat.lineage import ExperimentLineageResolver
from app.services.experiment_evaluation import ExperimentEvaluationApplicationService
from app.services.performance.period_application import (
    PerformancePeriodApplicationService,
)
from app.services.walk_forward import WalkForwardApplicationService
from m14_4_support import seed_analytics_case
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def _complete_bundle(db: Session, dates: tuple[date, ...]):
    case = seed_analytics_case(db, dates)
    period = (
        PerformancePeriodApplicationService(db)
        .calculate_now(
            case.run_id,
            performance_id=case.performance_id,
            risk_id=case.risk_id,
            trade_id=case.trade_id,
        )
        .report
    )
    return case, period


def _align_run_snapshot(
    db: Session,
    run_id: uuid.UUID,
    experiment: PortfolioExperiment,
    trial: PortfolioExperimentTrial,
) -> None:
    run = db.get(PortfolioBacktestRun, run_id)
    assert run is not None
    run.config_snapshot = {
        "strategy": experiment.base_config_snapshot["strategy"],
        "opportunity": experiment.base_config_snapshot["opportunity"],
        "portfolio": trial.portfolio_config_snapshot,
        "execution": experiment.base_config_snapshot["execution"],
        "accounting": experiment.base_config_snapshot["accounting"],
    }


def _fact(
    *,
    role: str,
    run_id: uuid.UUID,
    performance_id: uuid.UUID,
    risk_id: uuid.UUID,
    trade_id: uuid.UUID,
    period_id: uuid.UUID,
    trade_date: date,
) -> ComparisonFactContext:
    return ComparisonFactContext(
        tool_name="performance.summary",
        entity=str(run_id),
        trade_date=trade_date.isoformat(),
        path="records.0.performance.annualized_return",
        unit="decimal",
        sample_role=role,
        evidence={"calc_run_id": str(run_id), "evidence_id": f"{role}-evidence"},
        identity={
            "performance_id": str(performance_id),
            "risk_id": str(risk_id),
            "trade_id": str(trade_id),
            "period_id": str(period_id),
        },
    )


def test_persisted_walk_forward_lineage_and_m14_contract_are_enforced() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            dates = tuple(date(2089, 1, 2) + timedelta(days=index) for index in range(21))
            db.add_all(
                TradeCalendar(cal_date=value, is_open=True, exchange="SSE") for value in dates
            )
            db.flush()
            service = WalkForwardApplicationService(db)
            created = service.create(
                name="m16.2.2-lineage",
                start_date=dates[0],
                end_date=dates[-1],
                mode="ROLLING",
                train_trade_days=7,
                test_trade_days=7,
                step_trade_days=7,
                initial_cash=None,
                benchmark_code=None,
                grid={},
                train_evaluation_policy=None,
            )
            study_id = uuid.UUID(created["id"])
            study = db.get(PortfolioWalkForwardStudy, study_id)
            windows = list(
                db.scalars(
                    sa.select(PortfolioWalkForwardWindow)
                    .where(PortfolioWalkForwardWindow.study_id == study_id)
                    .order_by(PortfolioWalkForwardWindow.window_no)
                )
            )
            assert study is not None
            assert len(windows) == 2

            for window in windows:
                train_dates = tuple(date.fromisoformat(value) for value in window.train_trade_dates)
                train_case, _ = _complete_bundle(db, train_dates)
                experiment = service._frozen_experiment_service(study).create_from_frozen_base(
                    name=f"m16.2.2-train-{window.window_no}",
                    start_date=window.train_start_date,
                    end_date=window.train_end_date,
                    grid=study.parameter_space,
                    base_config_snapshot=study.base_config_snapshot,
                    base_identities={
                        name: getattr(study, name)
                        for name in (
                            "base_algo_version",
                            "base_source_strategy_config_hash",
                            "base_opportunity_calc_version",
                            "base_opportunity_config_hash",
                            "base_portfolio_version",
                            "base_portfolio_config_hash",
                            "base_execution_version",
                            "base_execution_config_hash",
                            "base_accounting_version",
                            "base_accounting_config_hash",
                            "base_backtest_engine_version",
                        )
                    },
                    commit=False,
                )
                window.train_experiment_id = experiment.id
                db.flush()
                trial = db.scalar(
                    sa.select(PortfolioExperimentTrial).where(
                        PortfolioExperimentTrial.experiment_id == experiment.id
                    )
                )
                assert trial is not None
                trial.run_id = train_case.run_id
                _align_run_snapshot(db, train_case.run_id, experiment, trial)
                db.commit()
                evaluation = (
                    ExperimentEvaluationApplicationService(db).calculate_now(experiment.id).report
                )
                service._freeze_selection(window, experiment, evaluation)

                oos_dates = tuple(date.fromisoformat(value) for value in window.test_trade_dates)
                oos_case, oos_period = _complete_bundle(db, oos_dates)
                _align_run_snapshot(db, oos_case.run_id, experiment, trial)
                window.oos_run_id = oos_case.run_id
                db.flush()
                oos_bundle = service.bundle_resolver.resolve(
                    oos_case.run_id,
                    performance_id=oos_case.performance_id,
                    risk_id=oos_case.risk_id,
                    trade_id=oos_case.trade_id,
                    period_id=oos_period.id,
                    require_period=True,
                )
                service._pin_oos_bundle(window, oos_bundle)
                db.commit()
            report, reused = service.calculate_now(study_id)
            assert reused is False
            persisted = db.get(
                PortfolioWalkForwardWindowValidation,
                {"validation_id": report.id, "window_no": 1},
            )
            assert persisted is not None
            window = windows[0]

            lineage_result = ResearchAgentAdapter(db).walk_forward_window_lineage(
                WalkForwardWindowLineageInput(
                    study_id=study_id,
                    validation_id=report.id,
                    limit=1,
                )
            )
            assert lineage_result.status == "READY"
            assert lineage_result.identity["total"] == 2
            assert lineage_result.identity["limit"] == 1
            assert len(lineage_result.records) == 1
            assert len(lineage_result.evidence) == 1
            assert lineage_result.records[0]["window_no"] == 1
            assert lineage_result.records[0]["train_run_id"] == persisted.selected_train_run_id
            assert lineage_result.records[0]["oos_run_id"] == persisted.oos_run_id
            assert lineage_result.records[0]["readiness"]["ready"] is True
            assert lineage_result.evidence[0].evidence_version == "v2"
            frozen = serialized_result(lineage_result, max_output_bytes=65536)
            assert (
                validate_projection(
                    frozen, frozen["evidence"][0], lineage_result.evidence[0]._archive_projection
                )
                == "records.0"
            )

            train_fact = _fact(
                role="TRAIN",
                run_id=persisted.selected_train_run_id,
                performance_id=persisted.train_performance_id,
                risk_id=persisted.train_risk_id,
                trade_id=persisted.train_trade_id,
                period_id=persisted.train_period_id,
                trade_date=window.train_end_date,
            )
            oos_fact = _fact(
                role="OOS",
                run_id=persisted.oos_run_id,
                performance_id=persisted.oos_performance_id,
                risk_id=persisted.oos_risk_id,
                trade_id=persisted.oos_trade_id,
                period_id=persisted.oos_period_id,
                trade_date=window.test_end_date,
            )
            evidence = [
                ComparisonEvidenceContext(
                    tool_name="walk_forward.summary",
                    evidence={"report_id": str(report.id)},
                    identity={
                        "study_id": str(study_id),
                        "validation_id": str(report.id),
                    },
                )
            ]
            lineage = ExperimentLineageResolver(db).resolve_train_oos(
                [train_fact, oos_fact], evidence
            )
            assert lineage.status == "VERIFIED"
            assert lineage.study_id == str(study_id)
            assert lineage.window_no == 1

            wrong_owner = _fact(
                role="OOS",
                run_id=persisted.oos_run_id,
                performance_id=persisted.train_performance_id,
                risk_id=persisted.oos_risk_id,
                trade_id=persisted.oos_trade_id,
                period_id=persisted.oos_period_id,
                trade_date=window.test_end_date,
            )
            mismatch = ExperimentLineageResolver(db).resolve_train_oos(
                [train_fact, wrong_owner], evidence
            )
            assert mismatch.status == "MISMATCH"
            assert mismatch.reason_codes == ["PERFORMANCE_OWNER_MISMATCH"]

            contract = BacktestComparisonContractResolver(db).resolve([train_fact, oos_fact])
            assert contract.state == "CONTEXT_REQUIRED"
            assert "DATE_RANGE_MISMATCH" in contract.reason_codes
            assert "TRADE_DATE_SET_MISMATCH" in contract.reason_codes

            incomplete = BacktestComparisonContractResolver(db).resolve([train_fact, wrong_owner])
            assert incomplete.state == "INCOMPATIBLE"
            assert incomplete.reason_codes == ("COMPARISON_CONTRACT_UNVERIFIABLE",)

            with pytest.raises(DBAPIError, match="append-only"):
                with db.begin_nested():
                    db.execute(
                        sa.update(PortfolioWalkForwardWindowValidation)
                        .where(
                            PortfolioWalkForwardWindowValidation.validation_id == report.id,
                            PortfolioWalkForwardWindowValidation.window_no == 1,
                        )
                        .values(selected_train_run_id=persisted.oos_run_id)
                    )
                    db.flush()
        transaction.rollback()
    engine.dispose()
