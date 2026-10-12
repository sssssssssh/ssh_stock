from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.agent.chat import LineageDecision
from app.models.experiment import PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentTrialEvaluation,
)
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.walk_forward import (
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)

if TYPE_CHECKING:
    from app.services.agent.chat.comparison_policy import (
        ComparisonEvidenceContext,
        ComparisonFactContext,
    )


LINEAGE_POLICY_VERSION = "m16.2.2-lineage-v1"


@dataclass(frozen=True)
class LineageEndpoint:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    sample_role: str
    tool_name: str


@dataclass(frozen=True)
class LineageLink:
    validation_id: uuid.UUID
    study_id: uuid.UUID
    window_no: int
    train_experiment_id: uuid.UUID
    train_evaluation_id: uuid.UUID
    selected_trial_id: uuid.UUID
    train_run_id: uuid.UUID
    train_performance_id: uuid.UUID
    oos_run_id: uuid.UUID
    oos_performance_id: uuid.UUID


def decide_lineage_link(
    *,
    train: LineageEndpoint,
    oos: LineageEndpoint,
    links: list[LineageLink],
    validation_id: uuid.UUID | None,
) -> LineageDecision:
    candidates = [
        link
        for link in links
        if validation_id is None or link.validation_id == validation_id
    ]
    exact = [
        link
        for link in candidates
        if link.train_run_id == train.run_id and link.oos_run_id == oos.run_id
    ]
    if len(exact) > 1:
        return _decision("UNVERIFIABLE", ["VALIDATION_ID_REQUIRED"])
    if not exact:
        if not links:
            return _decision("UNVERIFIABLE", ["LINEAGE_ARTIFACT_MISSING"])
        train_links = [link for link in links if link.train_run_id == train.run_id]
        oos_links = [link for link in links if link.oos_run_id == oos.run_id]
        if train_links and oos_links:
            train_owner = {(link.study_id, link.window_no) for link in train_links}
            oos_owner = {(link.study_id, link.window_no) for link in oos_links}
            code = (
                "WINDOW_MISMATCH"
                if {item[0] for item in train_owner}
                & {item[0] for item in oos_owner}
                else "STUDY_MISMATCH"
            )
            return _decision("MISMATCH", [code])
        return _decision("MISMATCH", ["TRAIN_OOS_RUN_RELATION_MISMATCH"])
    link = exact[0]
    if (
        train.performance_id != link.train_performance_id
        or oos.performance_id != link.oos_performance_id
    ):
        return _decision("MISMATCH", ["PERFORMANCE_OWNER_MISMATCH"], link)
    return _decision("VERIFIED", [], link)


class ExperimentLineageResolver:
    """Resolve only persisted M15 lineage; model-provided relationship fields are ignored."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_train_oos(
        self,
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> LineageDecision:
        if any(
            fact.sample_role == "OOS" and fact.tool_name == "walk_forward.summary"
            for fact in facts
        ):
            return _decision("MISMATCH", ["OOS_SCOPE_STUDY_AGGREGATE"])
        train = self._endpoint(facts, "TRAIN")
        oos = self._endpoint(facts, "OOS")
        if isinstance(train, LineageDecision):
            return train
        if isinstance(oos, LineageDecision):
            return oos
        validation_ids = {
            _uuid_or_none(item.identity.get("validation_id"))
            for item in evidence
            if item.tool_name
            in {"walk_forward.summary", "walk_forward.window_lineage"}
        }
        validation_ids.discard(None)
        if len(validation_ids) > 1:
            return _decision("MISMATCH", ["MULTIPLE_VALIDATION_IDENTITIES"])
        validation_id = next(iter(validation_ids), None)

        rows = list(
            self.db.scalars(
                select(PortfolioWalkForwardWindowValidation).where(
                    or_(
                        PortfolioWalkForwardWindowValidation.selected_train_run_id
                        == train.run_id,
                        PortfolioWalkForwardWindowValidation.oos_run_id == oos.run_id,
                    )
                )
            ).all()
        )
        links = [_link(row) for row in rows]
        decision = decide_lineage_link(
            train=train,
            oos=oos,
            links=links,
            validation_id=validation_id,
        )
        if decision.status != "VERIFIED":
            return decision
        selected = next(
            row
            for row in rows
            if str(row.validation_id) == decision.validation_id
            and row.window_no == decision.window_no
        )
        integrity_codes = self._integrity_codes(selected, train, oos)
        if integrity_codes:
            return _decision("MISMATCH", integrity_codes, _link(selected))
        return decision

    @staticmethod
    def _endpoint(
        facts: list[ComparisonFactContext],
        role: str,
    ) -> LineageEndpoint | LineageDecision:
        selected = [fact for fact in facts if fact.sample_role == role]
        if not selected:
            return _decision("MISMATCH", [f"{role}_FACT_MISSING"])
        if any(fact.tool_name != "performance.summary" for fact in selected):
            return _decision("MISMATCH", [f"{role}_PERFORMANCE_EVIDENCE_REQUIRED"])
        run_ids = {_uuid_or_none(fact.evidence.get("calc_run_id")) for fact in selected}
        performance_ids = {
            _uuid_or_none(fact.identity.get("performance_id")) for fact in selected
        }
        if None in run_ids or None in performance_ids:
            return _decision("UNVERIFIABLE", [f"{role}_IDENTITY_MISSING"])
        if len(run_ids) != 1 or len(performance_ids) != 1:
            return _decision("MISMATCH", [f"{role}_MIXED_RUNS"])
        return LineageEndpoint(
            run_id=next(iter(run_ids)),
            performance_id=next(iter(performance_ids)),
            sample_role=role,
            tool_name="performance.summary",
        )

    def _integrity_codes(
        self,
        link: PortfolioWalkForwardWindowValidation,
        train: LineageEndpoint,
        oos: LineageEndpoint,
    ) -> list[str]:
        codes: list[str] = []
        report = self.db.get(PortfolioWalkForwardValidationReport, link.validation_id)
        window = self.db.get(
            PortfolioWalkForwardWindow,
            {"study_id": link.study_id, "window_no": link.window_no},
        )
        trial = self.db.get(PortfolioExperimentTrial, link.selected_trial_id)
        evaluation = self.db.get(
            PortfolioExperimentEvaluationReport,
            link.train_evaluation_id,
        )
        trial_evaluation = self.db.get(
            PortfolioExperimentTrialEvaluation,
            {
                "evaluation_id": link.train_evaluation_id,
                "trial_id": link.selected_trial_id,
            },
        )
        if report is None or report.study_id != link.study_id:
            codes.append("VALIDATION_STUDY_OWNER_MISMATCH")
        if window is None:
            codes.append("WINDOW_OWNER_MISSING")
        elif any(
            (
                window.train_experiment_id != link.train_experiment_id,
                window.train_evaluation_id != link.train_evaluation_id,
                window.selected_trial_id != link.selected_trial_id,
                window.oos_run_id != link.oos_run_id,
            )
        ):
            codes.append("WINDOW_LINEAGE_MISMATCH")
        if (
            trial is None
            or trial.experiment_id != link.train_experiment_id
            or trial.run_id != train.run_id
        ):
            codes.append("TRAIN_TRIAL_NOT_SELECTED")
        if (
            evaluation is None
            or evaluation.experiment_id != link.train_experiment_id
            or evaluation.selected_trial_id != link.selected_trial_id
            or evaluation.selected_run_id != train.run_id
        ):
            codes.append("TRAIN_EVALUATION_SELECTION_MISMATCH")
        if (
            trial_evaluation is None
            or trial_evaluation.selection_rank != 1
            or trial_evaluation.run_id != train.run_id
            or trial_evaluation.performance_id != train.performance_id
        ):
            codes.append("TRAIN_SELECTED_RANK_MISMATCH")
        if window is not None:
            train_dates = self._performance_dates(train.performance_id)
            oos_dates = self._performance_dates(oos.performance_id)
            if train_dates != list(window.train_trade_dates):
                codes.append("TRAIN_DATE_SET_MISMATCH")
            if oos_dates != list(window.test_trade_dates):
                codes.append("OOS_DATE_SET_MISMATCH")
            train_report = self.db.get(PortfolioPerformanceReport, train.performance_id)
            oos_report = self.db.get(PortfolioPerformanceReport, oos.performance_id)
            if (
                train_report is None
                or train_report.start_date != window.train_start_date
                or train_report.end_date != window.train_end_date
            ):
                codes.append("TRAIN_PERIOD_MISMATCH")
            if (
                oos_report is None
                or oos_report.start_date != window.test_start_date
                or oos_report.end_date != window.test_end_date
            ):
                codes.append("OOS_PERIOD_MISMATCH")
        return list(dict.fromkeys(codes))

    def _performance_dates(self, performance_id: uuid.UUID) -> list[str]:
        return [
            value.isoformat()
            for value in self.db.scalars(
                select(PortfolioPerformanceDaily.trade_date)
                .where(PortfolioPerformanceDaily.performance_id == performance_id)
                .order_by(PortfolioPerformanceDaily.trade_date)
            ).all()
        ]


def _link(row: PortfolioWalkForwardWindowValidation) -> LineageLink:
    return LineageLink(
        validation_id=row.validation_id,
        study_id=row.study_id,
        window_no=row.window_no,
        train_experiment_id=row.train_experiment_id,
        train_evaluation_id=row.train_evaluation_id,
        selected_trial_id=row.selected_trial_id,
        train_run_id=row.selected_train_run_id,
        train_performance_id=row.train_performance_id,
        oos_run_id=row.oos_run_id,
        oos_performance_id=row.oos_performance_id,
    )


def _decision(
    status: str,
    reason_codes: list[str],
    link: LineageLink | None = None,
) -> LineageDecision:
    return LineageDecision(
        status=status,
        study_id=str(link.study_id) if link else None,
        window_no=link.window_no if link else None,
        train_run_id=str(link.train_run_id) if link else None,
        oos_run_id=str(link.oos_run_id) if link else None,
        validation_id=str(link.validation_id) if link else None,
        reason_codes=reason_codes,
        policy_version=LINEAGE_POLICY_VERSION,
    )


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None
