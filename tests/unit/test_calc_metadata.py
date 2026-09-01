import uuid

from app.services.calc_metadata import calculation_metadata, config_hash


def test_config_hash_is_stable_for_equivalent_config() -> None:
    assert config_hash({"b": 2, "a": 1}) == config_hash({"a": 1, "b": 2})


def test_calculation_metadata_contains_trace_fields() -> None:
    run_id = uuid.uuid4()

    metadata = calculation_metadata(
        config={"factor": {"ma_windows": [5, 20]}},
        calc_version="factor_v1",
        calc_run_id=run_id,
    )

    assert metadata["calc_version"] == "factor_v1"
    assert len(metadata["config_hash"]) == 64
    assert metadata["calc_run_id"] == run_id
    assert metadata["calculated_at"] is not None
