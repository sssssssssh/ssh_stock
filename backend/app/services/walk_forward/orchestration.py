from dataclasses import dataclass

from app.models.experiment import PortfolioExperiment
from app.models.job import JobRun
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import PortfolioWalkForwardWindow


@dataclass(frozen=True)
class WindowProjection:
    state: str
    blocked: bool = False
    error_code: str | None = None


def project_window_state(
    window: PortfolioWalkForwardWindow,
    *,
    experiment: PortfolioExperiment | None,
    train_active: bool,
    evaluation_job: JobRun | None,
    oos_run: PortfolioBacktestRun | None,
) -> WindowProjection:
    if window.train_experiment_id is None:
        return WindowProjection("TRAIN_PLANNED")
    if experiment is None:
        return WindowProjection(
            "TRAIN_FAILED", True, "WALK_FORWARD_TRAIN_EXPERIMENT_MISMATCH"
        )
    if experiment.started_at is None:
        return WindowProjection("TRAIN_CREATED")
    if train_active:
        return WindowProjection("TRAIN_RUNNING")
    if evaluation_job is not None:
        state = (
            "TRAIN_EVALUATION_RUNNING"
            if evaluation_job.status == "RUNNING"
            else "TRAIN_EVALUATION_QUEUED"
        )
        return WindowProjection(state)
    if window.train_evaluation_id is None:
        return WindowProjection("TRAIN_TERMINAL")
    if window.selected_trial_id is None:
        return WindowProjection(
            "TRAIN_NO_FEASIBLE_CANDIDATE",
            True,
            "WALK_FORWARD_TRAIN_NO_FEASIBLE_CANDIDATE",
        )
    if window.oos_run_id is None:
        return WindowProjection("SELECTION_FROZEN")
    if oos_run is None:
        return WindowProjection(
            "OOS_FAILED", True, "WALK_FORWARD_OOS_IDENTITY_MISMATCH"
        )
    if oos_run.status == "CREATED":
        return WindowProjection("OOS_CREATED")
    if oos_run.status == "RUNNING":
        return WindowProjection("OOS_RUNNING")
    if oos_run.status == "FAILED":
        return WindowProjection("OOS_FAILED", True, "WALK_FORWARD_OOS_RUN_FAILED")
    if oos_run.status == "CANCELLED":
        return WindowProjection(
            "OOS_CANCELLED", True, "WALK_FORWARD_OOS_RUN_CANCELLED"
        )
    if window.oos_bound_at is None:
        return WindowProjection("OOS_ANALYTICS_REQUIRED")
    return WindowProjection("OOS_READY")
