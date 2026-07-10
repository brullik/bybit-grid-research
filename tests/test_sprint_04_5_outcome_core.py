from __future__ import annotations

import json
import math

import polars as pl

from bybit_grid.research.outcome_core.grid_crossings import GRID_LEVELS_SERIALIZATION_VERSION, geometric_grid_levels, levels_json
from bybit_grid.research.outcome_core.outcome_fast import compute_event_outcomes as fast
from bybit_grid.research.outcome_core.outcome_reference import compute_event_outcomes as reference
from bybit_grid.research.outcome_core.symbol_arrays import build_symbol_arrays


def test_low_price_levels_round_trip_constant_ratio():
    levels = geometric_grid_levels(0.000008, 0.000012, 20)
    decoded = json.loads(levels_json(levels))
    assert decoded == [float(x) for x in levels]
    expected = math.log(0.000012 / 0.000008) / 20
    assert max(abs(math.log(decoded[i + 1] / decoded[i]) - expected) for i in range(20)) < 1e-12


def _frames():
    times = [60_000 * i for i in range(1, 8)]
    klines = pl.DataFrame({"open_time_ms": times, "open": [100, 101, 99, 102, 100, 98, 101], "high": [101, 112, 100, 103, 111, 99, 102], "low": [99, 90, 98, 101, 99, 89, 100], "close": [100, 99, 102, 100, 98, 101, 100], "volume": [1, 1, 0, 1, 1, 1, 1]})
    marks = pl.DataFrame({"open_time_ms": times, "close": [100.0, 100.5, 99.5, 101.0, 100.0, 99.0, 100.0]})
    funding = pl.DataFrame({"funding_time_ms": [120_000, 300_000], "funding_rate": [0.001, -0.0005]})
    return klines, marks, funding


def test_symbol_arrays_prefixes():
    klines, marks, funding = _frames()
    arrays = build_symbol_arrays(klines, marks, funding)
    assert arrays.time_ms.tolist() == klines["open_time_ms"].to_list()
    assert arrays.zero_volume_prefix[-1] == 1
    assert arrays.mark_time_ms.size == marks.height
    assert arrays.funding_rate.size == funding.height


def test_reference_fast_equivalence_synthetic_low_price_missing_ambiguity_funding_mark():
    klines, marks, funding = _frames()
    event = {"signal_time_ms": 0, "symbol": "LOWUSDT", "range_action_event_id": "e1", "range_low": 95.0, "range_high": 105.0, "range_mid": 100.0, "atr_14_abs": 5.0}
    horizons = [1, 3, 6]
    grids = [5, 10, 20]
    sls = [0.0, 0.5, 1.0]
    r = reference(event, klines, marks, funding, horizons, grids, sls, range_run_id="rr", outcome_run_id="ref")
    f = fast(event, klines, marks, funding, horizons, grids, sls, range_run_id="rr", outcome_run_id="ref")
    assert len(r) == len(f)
    for a, b in zip(r, f, strict=True):
        assert a.keys() == b.keys()
        assert a["outcome_id"] == b["outcome_id"]
        assert a["outcome_match_key"] == b["outcome_match_key"]
        assert a["grid_levels_serialization_version"] == GRID_LEVELS_SERIALIZATION_VERSION
        for k in a:
            if isinstance(a[k], float):
                assert math.isclose(a[k], b[k], rel_tol=1e-12, abs_tol=1e-12)
            else:
                assert a[k] == b[k]
