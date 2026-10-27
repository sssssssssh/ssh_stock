"""Compact immutable input blocks; reconstruct raw scalars before dtype inference.

SQL NULL has its own mask: an all-NULL float window must not be confused with
an all-NaN window. FETCH boundaries never become calculation boundaries.
"""

import sys
from decimal import Decimal

import numpy as np
import pandas as pd


class InputBlock:
    def __init__(self, columns, nulls, specials=None):
        self.columns, self.nulls = columns, nulls
        self.specials = specials or {}
        self.nbytes = int(
            sys.getsizeof(columns)
            + sys.getsizeof(nulls)
            + sum(
                value.nbytes if isinstance(value, np.ndarray) else value.memory_usage(deep=True)
                for value in columns.values()
            )
            + sum(value.nbytes for value in nulls.values())
            + sys.getsizeof(self.specials)
            + sum(
                sys.getsizeof(values)
                + sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in values.items())
                for values in self.specials.values()
            )
        )

    @classmethod
    def from_records(cls, records, float_columns):
        if not records:
            raise ValueError("FACTOR_INPUT_EMPTY_BLOCK")
        columns, nulls, specials = {}, {}, {}
        for name in records[0].keys():
            values = [row[name] for row in records]
            nulls[name] = np.fromiter((value is None for value in values), dtype=bool)
            # Categoricals collapse every missing sentinel to NaN. Preserve the
            # actual scalar separately; SQL NULL keeps its original dedicated mask.
            marked = {
                i: value
                for i, value in enumerate(values)
                if value is pd.NA
                or value is pd.NaT
                or isinstance(value, Decimal)
                and value.is_nan()
            }
            if marked:
                specials[name] = marked
                values = [None if i in marked else value for i, value in enumerate(values)]
            columns[name] = (
                np.asarray(values, dtype=float) if name in float_columns else pd.Categorical(values)
            )
        return cls(columns, nulls, specials)

    def since(self, start):
        dates = np.asarray(self.columns["trade_date"], dtype=object)
        keep = dates >= start
        if keep.all():
            return self
        if not keep.any():
            return None
        columns = {}
        for name, values in self.columns.items():
            cropped = values[keep]
            columns[name] = (
                cropped if isinstance(cropped, np.ndarray) else cropped.remove_unused_categories()
            )
        positions = {int(old): new for new, old in enumerate(np.flatnonzero(keep))}
        specials = {
            name: {positions[i]: value for i, value in values.items() if i in positions}
            for name, values in self.specials.items()
        }
        return InputBlock(
            columns, {name: values[keep] for name, values in self.nulls.items()}, specials
        )


def blocks_to_frame(blocks):
    if not blocks:
        return pd.DataFrame()
    frame = pd.DataFrame()
    for name in blocks[0].columns:
        values = np.concatenate([np.asarray(block.columns[name], dtype=object) for block in blocks])
        nulls = np.concatenate([block.nulls[name] for block in blocks])
        values[nulls] = None
        offset = 0
        for block in blocks:
            for index, value in block.specials.get(name, {}).items():
                values[offset + index] = value
            offset += len(block.columns[name])
        # Infer once per WHOLE column, not per FETCH. Release temporary Python
        # scalars each column, rather than retaining millions of row dictionaries.
        frame[name] = pd.Series(values.tolist())
        del values, nulls
    return frame
