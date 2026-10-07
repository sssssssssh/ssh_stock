import hashlib
import json
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.core.experiment_evaluation_config import (
    EvaluationPolicyConfig,
    ExperimentEvaluationConfig,
)
from app.domain.experiment_evaluation.contracts import EvaluationPolicy
from app.domain.experiment_evaluation.metrics import validate_policy_metrics


def canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def experiment_parameter_hash(parameter_values: Mapping[str, Any]) -> str:
    """Reproduce the canonical M15.1 Trial parameter identity."""
    return stable_hash(dict(parameter_values))


def effective_policy(
    policy: EvaluationPolicyConfig, config: ExperimentEvaluationConfig
) -> tuple[EvaluationPolicy, dict[str, Any], str]:
    validate_policy_metrics(
        policy.primary_objective, policy.pareto_metrics, policy.tie_breakers
    )
    if policy.shortlist_size > config.max_shortlist_size:
        raise ValueError("shortlist_size exceeds configured maximum")
    if not 2 <= len(policy.pareto_metrics) <= config.max_pareto_metrics:
        raise ValueError("pareto metric count is outside configured bounds")
    constraints = policy.constraints.model_dump(mode="python")
    snapshot = {
        "primary_objective": policy.primary_objective,
        "shortlist_size": policy.shortlist_size,
        "constraints": constraints,
        "pareto_metrics": list(policy.pareto_metrics),
        "tie_breakers": list(policy.tie_breakers),
    }
    domain = EvaluationPolicy(
        primary_objective=policy.primary_objective,
        shortlist_size=policy.shortlist_size,
        constraints=constraints,
        pareto_metrics=policy.pareto_metrics,
        tie_breakers=policy.tie_breakers,
    )
    canonical = canonical_value(snapshot)
    return domain, canonical, stable_hash(canonical)


def evaluation_config_hash(config: ExperimentEvaluationConfig) -> str:
    return stable_hash(config.model_dump(mode="python"))


def evaluation_lock_key(experiment_id: uuid.UUID, policy_hash: str) -> int:
    identity = f"portfolio_experiment_evaluation:{experiment_id}:{policy_hash}"
    return int.from_bytes(
        hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big", signed=True
    )
