import pytest
from app.api.v1.experiments import ExperimentDefinitionRequest
from pydantic import ValidationError


def _request() -> dict[str, object]:
    return {
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "grid": {
            "candidate": {"min_score": ["65", "70"], "top_n": [10]},
            "construction": {"max_positions": [10]},
        },
    }


def test_typed_grid_rejects_non_portfolio_search_fields() -> None:
    payload = _request()
    grid = payload["grid"]
    assert isinstance(grid, dict)
    grid["execution"] = {"slippage_bps": [0, 5]}

    with pytest.raises(ValidationError, match="execution"):
        ExperimentDefinitionRequest.model_validate(payload)


def test_typed_grid_rejects_coerced_integer_and_nonfinite_decimal() -> None:
    payload = _request()
    grid = payload["grid"]
    assert isinstance(grid, dict)
    candidate = grid["candidate"]
    assert isinstance(candidate, dict)
    candidate["top_n"] = ["10"]
    with pytest.raises(ValidationError, match="top_n"):
        ExperimentDefinitionRequest.model_validate(payload)

    payload = _request()
    grid = payload["grid"]
    assert isinstance(grid, dict)
    candidate = grid["candidate"]
    assert isinstance(candidate, dict)
    candidate["min_score"] = ["NaN"]
    with pytest.raises(ValidationError, match="finite"):
        ExperimentDefinitionRequest.model_validate(payload)
