import hashlib
import uuid
from typing import Any

from app.core.walk_forward_config import (
    WalkForwardConfig,
    WalkForwardValidationPolicyConfig,
)
from app.services.experiment_evaluation.identity import stable_hash


def walk_forward_config_hash(config: WalkForwardConfig) -> str:
    """Compatibility name for the validation-policy identity stored by M15.3."""
    return validation_policy_hash(config.validation_policy)


def validation_policy_snapshot(
    policy: WalkForwardValidationPolicyConfig,
) -> dict[str, Any]:
    return policy.model_dump(mode="json")


def validation_policy_hash(policy: WalkForwardValidationPolicyConfig) -> str:
    return stable_hash(validation_policy_snapshot(policy))


def study_lock_key(study_id: uuid.UUID) -> int:
    return _lock_key(f"portfolio_walk_forward:{study_id}")


def validation_lock_key(study_id: uuid.UUID, source_hash: str) -> int:
    return _lock_key(f"portfolio_walk_forward_validation:{study_id}:{source_hash}")


def definition_hash(payload: dict[str, Any]) -> str:
    return stable_hash(payload)


def calendar_hash(open_dates: tuple[object, ...]) -> str:
    return stable_hash(
        [value.isoformat() if hasattr(value, "isoformat") else str(value) for value in open_dates]
    )


def _lock_key(identity: str) -> int:
    return int.from_bytes(
        hashlib.sha256(identity.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
