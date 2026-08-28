from app.repositories.upsert import _chunk_size


def test_chunk_size_respects_parameter_limit() -> None:
    payload = [{"a": idx, "b": idx, "c": idx} for idx in range(10)]

    assert _chunk_size(payload, max_parameters=7) == 2


def test_chunk_size_is_at_least_one_row() -> None:
    payload = [{"a": 1, "b": 2, "c": 3}]

    assert _chunk_size(payload, max_parameters=1) == 1
