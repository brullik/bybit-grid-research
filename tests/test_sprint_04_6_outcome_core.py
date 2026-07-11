from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.outcome_fast import (
    _cross_counts,
    _funding,
    build_outcome_symbol_arrays,
)


def test_fast_core_does_not_import_reference_compute_event_outcomes() -> None:
    tree = ast.parse(Path("src/bybit_grid/research/outcome_core/outcome_fast.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").endswith("outcome_reference")
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("outcome_numpy"):
            assert all(alias.name != "compute_event_outcomes" for alias in node.names)


def test_searchsorted_crossing_endpoint_formula() -> None:
    closes = np.array([100.0, 110.0, 100.0, 100.0])
    levels = np.array([100.0, 105.0, 110.0])
    assert _cross_counts(closes, levels).sum() == 4


def test_funding_prefix_aggregation() -> None:
    arr = build_outcome_symbol_arrays(
        pl.DataFrame(
            {
                "open_time_ms": [0],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
            }
        ),
        pl.DataFrame(),
        pl.DataFrame(
            {"funding_time_ms": [60_000, 120_000, 180_000], "funding_rate": [0.1, -0.2, 0.3]}
        ),
    )
    got = _funding(arr, 60_000, 180_000)
    assert got["funding_rows_in_horizon"] == 2
    assert abs(got["funding_rate_sum"] - 0.1) < 1e-12
    assert abs(got["funding_rate_abs_sum"] - 0.5) < 1e-12
