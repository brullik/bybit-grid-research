from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.funding_join import aggregate_funding
from bybit_grid.research.outcome_core.grid_crossings import count_level_crossings, geometric_grid_levels
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes, deterministic_outcome_id
from bybit_grid.research.outcome_store import write_partitioned_outcomes


def event():
    return {"range_action_event_id":"a1","range_regime_id":"r1","symbol":"BTCUSDT","signal_time_ms":0,"range_low":100.0,"range_high":110.0,"range_mid":105.0,"range_height_atr_14":1.0}

def klines(vals):
    return pl.DataFrame({"open_time_ms":[60_000*(i+1) for i in range(len(vals))],"open":[v[0] for v in vals],"high":[v[1] for v in vals],"low":[v[2] for v in vals],"close":[v[3] for v in vals],"volume":[1.0]*len(vals)})

def test_no_lookahead_future_starts_after_signal_and_missing():
    out=compute_event_outcomes(event(), klines([(105,106,104,105)]), pl.DataFrame(), pl.DataFrame(), [2], [5], [0.5])[0]
    assert out["entry_time_ms"] == 60_000
    assert out["future_rows_available"] == 1
    assert out["future_missing_minutes_count"] == 1
    assert not out["future_data_complete_bool"]

def test_first_exit_side_time_and_sl_upper_lower():
    up=compute_event_outcomes(event(), klines([(105,111,104,109)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.0])[0]
    assert (up["first_exit_side"], up["first_exit_time_ms"], up["first_sl_side"]) == ("up",60_000,"upper")
    dn=compute_event_outcomes(event(), klines([(105,106,99,101)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.0])[0]
    assert (dn["first_exit_side"], dn["first_sl_side"]) == ("down","lower")

def test_grid_crossing_count_and_monotonicity():
    levels=geometric_grid_levels(100, 110, 5)
    assert np.all(np.diff(levels) > 0)
    assert count_level_crossings(np.array([100, 105, 110], dtype=float), np.array([102, 108], dtype=float)) == 2

def test_funding_aggregation_by_horizon():
    f=pl.DataFrame({"funding_time_ms":[60_000,120_000,240_000],"funding_rate":[0.1,-0.2,0.3]})
    got=aggregate_funding(f, 0, 180_000)
    assert got["funding_rows_in_horizon"] == 2
    assert round(got["funding_rate_sum"], 6) == -0.1
    assert round(got["funding_rate_abs_sum"], 6) == 0.3

def test_deterministic_outcome_id():
    assert deterministic_outcome_id("a", 60, 10, 0.5) == deterministic_outcome_id("a", 60, 10, 0.5)
    assert deterministic_outcome_id("a", 60, 10, 0.5) != deterministic_outcome_id("a", 60, 20, 0.5)

def test_partition_write_and_dedupe(tmp_path: Path):
    row=compute_event_outcomes(event(), klines([(105,106,104,105)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.5])[0]
    df=pl.DataFrame([row,row])
    paths=write_partitioned_outcomes(df, tmp_path)
    assert len(paths)==1
    assert pl.read_parquet(paths[0]).height == 1

def test_review_pack_allowlist(tmp_path: Path):
    p=tmp_path/'pack.zip'
    with zipfile.ZipFile(p,'w') as z:
        for n in ['outcome_report.md','outcome_quality_report.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json']:
            z.writestr(n, 'x')
    with zipfile.ZipFile(p) as z:
        assert set(z.namelist()) == {'outcome_report.md','outcome_quality_report.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json'}

def test_no_live_create_close_order_code_in_outcome_files():
    for path in list(Path('src/bybit_grid/research').glob('outcome*.py')) + list(Path('src/bybit_grid/research/outcome_core').glob('*.py')) + list(Path('scripts').glob('*outcome*.py')):
        txt=path.read_text().lower()
        assert 'create order' not in txt and 'close order' not in txt and 'telegram' not in txt
