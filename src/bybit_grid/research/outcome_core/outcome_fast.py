from __future__ import annotations

import polars as pl

from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes as _reference_compute
from bybit_grid.research.outcome_core.symbol_arrays import build_symbol_arrays

CORE_NAME = "numpy_fast_v2"


def compute_event_outcomes(*args, **kwargs) -> list[dict]:
    """Fast-core entry point.

    The public core is isolated behind this module so callers can select the v2
    engine.  It currently preserves the reference semantics exactly while the
    symbol-array model is rolled out under test coverage.
    """
    return _reference_compute(*args, **kwargs)


def prepare_symbol_arrays(klines: pl.DataFrame, mark_klines: pl.DataFrame, funding: pl.DataFrame):
    return build_symbol_arrays(klines, mark_klines, funding)
