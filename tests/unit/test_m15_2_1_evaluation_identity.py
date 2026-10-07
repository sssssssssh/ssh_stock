import hashlib
import json

from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER
from app.services.experiment_evaluation.identity import experiment_parameter_hash


def test_evaluation_parameter_hash_matches_m15_1_canonical_hash() -> None:
    parameters = {
        "candidate.min_score": "70",
        "candidate.top_n": 50,
        "construction.max_positions": 10,
        "construction.max_single_position_weight": "0.1",
        "construction.min_cash_ratio": "0.05",
        "construction.max_new_positions_per_day": 3,
    }
    assert tuple(parameters) == EXPERIMENT_PARAMETER_ORDER
    payload = json.dumps(
        parameters,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    m15_1_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert experiment_parameter_hash(parameters) == m15_1_hash
