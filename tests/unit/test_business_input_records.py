from datetime import date

import numpy as np
import pandas as pd
import pytest
from app.services.factors.input_records import InputBlock, blocks_to_frame
from pandas.testing import assert_frame_equal


@pytest.mark.parametrize("values", [
    [None, None, None], [None, 1.0, None], [np.nan, np.nan, np.nan],
    [None, np.nan, 0.0], [True, None, False], [None, None, True],
    ["A", None, "B"], [date(2025, 1, 1), None, date(2025, 1, 2)],
])
def test_compact_fetch_blocks_keep_whole_window_inference(values):
    rows = [dict(value=value) for value in values]
    numeric = {"value"} if not any(isinstance(v, (bool, str, date)) for v in values) else set()
    blocks = [InputBlock.from_records([row], numeric) for row in rows]
    assert_frame_equal(blocks_to_frame(blocks), pd.DataFrame(rows), check_exact=True)


def test_eviction_restores_all_null_dtype_instead_of_carrying_float_dtype():
    rows = [dict(trade_date=date(2025, 1, day), ts_code="A", value=value)
            for day, value in enumerate([2.0, None, None], 1)]
    block = InputBlock.from_records(rows, {"value"})
    cropped = block.since(date(2025, 1, 2))
    assert_frame_equal(blocks_to_frame([cropped]), pd.DataFrame(rows[1:]), check_exact=True)
    assert block.since(date(2025, 2, 1)) is None


def test_compaction_does_not_retain_source_record_dictionaries():
    rows = [dict(trade_date=date(2025, 1, 1), ts_code=f"T{i % 20:04d}", value=1.5)
            for i in range(5000)]
    block = InputBlock.from_records(rows, {"value"})
    assert block.nbytes < 200000
    assert_frame_equal(blocks_to_frame([block]), pd.DataFrame(rows), check_exact=True)
