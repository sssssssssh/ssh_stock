import uuid

from app.services.agent.chat.comparison_policy import ComparisonFactContext
from app.services.agent.chat.lineage import (
    ExperimentLineageResolver,
    LineageEndpoint,
    LineageLink,
    decide_lineage_link,
)


def _endpoint(role: str, *, run_id: uuid.UUID, performance_id: uuid.UUID):
    return LineageEndpoint(
        run_id=run_id,
        performance_id=performance_id,
        sample_role=role,
        tool_name="performance.summary",
    )


def _link(
    *,
    study_id: uuid.UUID,
    window_no: int,
    train_run_id: uuid.UUID,
    train_performance_id: uuid.UUID,
    oos_run_id: uuid.UUID,
    oos_performance_id: uuid.UUID,
    validation_id: uuid.UUID | None = None,
) -> LineageLink:
    return LineageLink(
        validation_id=validation_id or uuid.uuid4(),
        study_id=study_id,
        window_no=window_no,
        train_experiment_id=uuid.uuid4(),
        train_evaluation_id=uuid.uuid4(),
        selected_trial_id=uuid.uuid4(),
        train_run_id=train_run_id,
        train_performance_id=train_performance_id,
        oos_run_id=oos_run_id,
        oos_performance_id=oos_performance_id,
    )


def test_exact_study_window_train_oos_link_is_verified() -> None:
    study_id = uuid.uuid4()
    train_run, train_performance = uuid.uuid4(), uuid.uuid4()
    oos_run, oos_performance = uuid.uuid4(), uuid.uuid4()
    link = _link(
        study_id=study_id,
        window_no=2,
        train_run_id=train_run,
        train_performance_id=train_performance,
        oos_run_id=oos_run,
        oos_performance_id=oos_performance,
    )

    decision = decide_lineage_link(
        train=_endpoint("TRAIN", run_id=train_run, performance_id=train_performance),
        oos=_endpoint("OOS", run_id=oos_run, performance_id=oos_performance),
        links=[link],
        validation_id=link.validation_id,
    )

    assert decision.status == "VERIFIED"
    assert decision.study_id == str(study_id)
    assert decision.window_no == 2
    assert decision.validation_id == str(link.validation_id)


def test_different_study_and_window_are_rejected() -> None:
    train_run, train_performance = uuid.uuid4(), uuid.uuid4()
    oos_run, oos_performance = uuid.uuid4(), uuid.uuid4()
    train_link = _link(
        study_id=uuid.uuid4(),
        window_no=1,
        train_run_id=train_run,
        train_performance_id=train_performance,
        oos_run_id=uuid.uuid4(),
        oos_performance_id=uuid.uuid4(),
    )
    oos_link = _link(
        study_id=uuid.uuid4(),
        window_no=2,
        train_run_id=uuid.uuid4(),
        train_performance_id=uuid.uuid4(),
        oos_run_id=oos_run,
        oos_performance_id=oos_performance,
    )
    decision = decide_lineage_link(
        train=_endpoint("TRAIN", run_id=train_run, performance_id=train_performance),
        oos=_endpoint("OOS", run_id=oos_run, performance_id=oos_performance),
        links=[train_link, oos_link],
        validation_id=None,
    )
    assert decision.status == "MISMATCH"
    assert decision.reason_codes == ["STUDY_MISMATCH"]

    same_study_oos = _link(
        study_id=train_link.study_id,
        window_no=3,
        train_run_id=uuid.uuid4(),
        train_performance_id=uuid.uuid4(),
        oos_run_id=oos_run,
        oos_performance_id=oos_performance,
    )
    decision = decide_lineage_link(
        train=_endpoint("TRAIN", run_id=train_run, performance_id=train_performance),
        oos=_endpoint("OOS", run_id=oos_run, performance_id=oos_performance),
        links=[train_link, same_study_oos],
        validation_id=None,
    )
    assert decision.status == "MISMATCH"
    assert decision.reason_codes == ["WINDOW_MISMATCH"]


def test_historical_missing_or_ambiguous_lineage_is_unverifiable() -> None:
    train = _endpoint("TRAIN", run_id=uuid.uuid4(), performance_id=uuid.uuid4())
    oos = _endpoint("OOS", run_id=uuid.uuid4(), performance_id=uuid.uuid4())
    missing = decide_lineage_link(
        train=train,
        oos=oos,
        links=[],
        validation_id=None,
    )
    assert missing.status == "UNVERIFIABLE"
    assert missing.reason_codes == ["LINEAGE_ARTIFACT_MISSING"]

    first = _link(
        study_id=uuid.uuid4(),
        window_no=1,
        train_run_id=train.run_id,
        train_performance_id=train.performance_id,
        oos_run_id=oos.run_id,
        oos_performance_id=oos.performance_id,
    )
    second = _link(
        study_id=first.study_id,
        window_no=1,
        train_run_id=train.run_id,
        train_performance_id=train.performance_id,
        oos_run_id=oos.run_id,
        oos_performance_id=oos.performance_id,
    )
    ambiguous = decide_lineage_link(
        train=train,
        oos=oos,
        links=[first, second],
        validation_id=None,
    )
    assert ambiguous.status == "UNVERIFIABLE"
    assert ambiguous.reason_codes == ["VALIDATION_ID_REQUIRED"]


def test_wrong_performance_owner_and_aggregate_oos_are_rejected() -> None:
    train = _endpoint("TRAIN", run_id=uuid.uuid4(), performance_id=uuid.uuid4())
    oos = _endpoint("OOS", run_id=uuid.uuid4(), performance_id=uuid.uuid4())
    link = _link(
        study_id=uuid.uuid4(),
        window_no=1,
        train_run_id=train.run_id,
        train_performance_id=uuid.uuid4(),
        oos_run_id=oos.run_id,
        oos_performance_id=oos.performance_id,
    )
    mismatch = decide_lineage_link(
        train=train,
        oos=oos,
        links=[link],
        validation_id=link.validation_id,
    )
    assert mismatch.status == "MISMATCH"
    assert mismatch.reason_codes == ["PERFORMANCE_OWNER_MISMATCH"]

    aggregate = ComparisonFactContext(
        tool_name="walk_forward.summary",
        entity=str(uuid.uuid4()),
        trade_date="2026-10-11",
        path="records.0.returns.stitched_oos_cumulative_return",
        unit="decimal",
        sample_role="OOS",
        evidence={},
        identity={},
    )
    resolver = ExperimentLineageResolver(None)  # type: ignore[arg-type]
    decision = resolver.resolve_train_oos([aggregate], [])
    assert decision.status == "MISMATCH"
    assert decision.reason_codes == ["OOS_SCOPE_STUDY_AGGREGATE"]
