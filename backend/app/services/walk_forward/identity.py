import hashlib
import uuid
from typing import Any

from app.core.walk_forward_config import (
    WalkForwardConfig,
    WalkForwardValidationPolicyConfig,
)
from app.services.experiment_evaluation.identity import canonical_value, stable_hash


def walk_forward_config_hash(config: WalkForwardConfig) -> str:
    """Return the complete runtime configuration identity for audit metadata."""
    return stable_hash(config.model_dump(mode="python"))


def validation_policy_snapshot(
    policy: WalkForwardValidationPolicyConfig,
) -> dict[str, Any]:
    snapshot = canonical_value(policy.model_dump(mode="python"))
    assert isinstance(snapshot, dict)
    return snapshot


def validation_policy_hash(policy: WalkForwardValidationPolicyConfig) -> str:
    return stable_hash(validation_policy_snapshot(policy))


def study_lock_key(study_id: uuid.UUID) -> int:
    return _lock_key(f"portfolio_walk_forward:{study_id}")


def validation_lock_key(
    study_id: uuid.UUID,
    policy_identity_version: str,
    policy_hash: str,
    source_hash: str,
) -> int:
    return _lock_key(
        "portfolio_walk_forward_validation:"
        f"{study_id}:{policy_identity_version}:{policy_hash}:{source_hash}"
    )


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
