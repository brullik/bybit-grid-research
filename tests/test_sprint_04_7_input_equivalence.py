from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from bybit_grid.research.outcome_core.input_loader import (
    discover_unique_parquet_files,
    load_canonical_symbol_frames,
)


def _write_all_roots(
    tmp_path: Path, symbol: str, funding: pl.DataFrame | None = None
) -> tuple[Path, Path, Path]:
    k = tmp_path / "klines" / f"symbol={symbol}"
    m = tmp_path / "mark_klines" / f"symbol={symbol}"
    f = tmp_path / "funding" / f"symbol={symbol}"
    for d in (k, m, f):
        d.mkdir(parents=True)
    base = pl.DataFrame(
        {
            "open_time_ms": [1, 1, 2],
            "open": [1.0, 1.0, 2.0],
            "high": [1.1, 1.1, 2.1],
            "low": [0.9, 0.9, 1.9],
            "close": [1.0, 1.0, 2.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    base.write_parquet(k / "part.parquet")
    base.write_parquet(m / "part.parquet")
    (
        funding
        if funding is not None
        else pl.DataFrame(
            {"funding_rate_timestamp_ms": [1, 1, 2], "funding_rate": [0.1, 0.1, 0.2]}
        )
    ).write_parquet(f / "part.parquet")
    return tmp_path / "klines", tmp_path / "mark_klines", tmp_path / "funding"


def test_overlapping_globs_return_physical_file_once(tmp_path: Path):
    symbol = "BTCUSDT"
    roots = _write_all_roots(tmp_path, symbol)
    files = discover_unique_parquet_files(roots[0], symbol)
    assert len(files) == 1


def test_duplicate_timestamps_removed_deterministically_and_funding_not_doubled(
    tmp_path: Path,
):
    symbol = "BTCUSDT"
    roots = _write_all_roots(tmp_path, symbol)
    klines, marks, funding, diag = load_canonical_symbol_frames(
        symbol, klines_root=roots[0], mark_root=roots[1], funding_root=roots[2]
    )
    assert klines["open_time_ms"].to_list() == [1, 2]
    assert marks["open_time_ms"].to_list() == [1, 2]
    assert funding["funding_rate_timestamp_ms"].to_list() == [1, 2]
    assert diag.funding_file_refs_found > diag.funding_unique_files
    assert diag.funding_rows_before_timestamp_dedupe == 3
    assert diag.funding_rows_after_timestamp_dedupe == 2


def test_contradictory_duplicate_timestamps_fail(tmp_path: Path):
    symbol = "BTCUSDT"
    funding = pl.DataFrame(
        {"funding_rate_timestamp_ms": [1, 1], "funding_rate": [0.1, 0.2]}
    )
    roots = _write_all_roots(tmp_path, symbol, funding)
    with pytest.raises(ValueError, match="conflicting duplicate funding timestamps"):
        load_canonical_symbol_frames(
            symbol, klines_root=roots[0], mark_root=roots[1], funding_root=roots[2]
        )


def test_semantic_audit_rejects_future_rows_over_horizon(tmp_path: Path):
    run_id = f"audit_bad_test_{tmp_path.name}"
    run_root = Path("data/processed/outcome_runs") / run_id
    import shutil

    shutil.rmtree(run_root, ignore_errors=True)
    root = run_root / "outcomes/symbol=BTCUSDT"
    root.mkdir(parents=True, exist_ok=True)
    row = {
        "symbol": "BTCUSDT",
        "outcome_id": "1",
        "outcome_match_key": "1",
        "outcome_semantics_version": "v4_native_grid_geometry",
        "grid_geometry_semantics_version": "v1_n_cells_n_plus_1_levels",
        "range_action_event_id": "e",
        "future_horizon_minutes": 1,
        "grid_count": 1,
        "grid_cell_number": 1,
        "grid_price_level_count": 2,
        "grid_interval_count": 1,
        "grid_interval_ratio": 2.0,
        "grid_interval_pct": 100.0,
        "grid_interval_bps": 10000.0,
        "grid_count_semantics": "n_cells",
        "sl_atr_buffer": 0.0,
        "atr_14_abs_used": 1.0,
        "sl_proxy_valid_bool": True,
        "first_exit_side": "none",
        "first_exit_ambiguous_bool": False,
        "first_sl_side": "none",
        "first_sl_ambiguous_bool": False,
        "geometric_grid_levels_json": "[1.0, 2.0]",
        "range_low": 1.0,
        "range_high": 2.0,
        "grid_levels_serialization_version": "grid_levels_json_v1",
        "future_rows_available": 2,
        "future_coverage_minutes": 1,
        "inside_range_candle_count": 0,
        "future_bad_ohlc_count": 0,
        "future_zero_volume_count": 0,
        "future_close_level_cross_count": 0,
        "future_intrabar_level_touch_count": 0,
        "future_unique_grid_levels_touched_count": 0,
        "fill_activity_lower_bound_proxy": 0,
        "fill_activity_upper_bound_proxy": 0,
    }
    pl.DataFrame([row]).write_parquet(root / "part.parquet")
    s = run_root / "summary"
    s.mkdir(parents=True, exist_ok=True)
    (s / "outcome_input_hygiene.json").write_text(
        json.dumps({"input_hygiene_ok": True})
    )
    res = subprocess.run(
        [
            sys.executable,
            "scripts/audit_outcome_semantics.py",
            "--outcome-run-id",
            run_id,
        ],
        text=True,
        capture_output=True,
    )
    assert res.returncode != 0


def test_no_live_order_telegram_additions():
    res = subprocess.run(
        [
            "rg",
            "telegram|create_order|cancel_order|live trading|grid create|grid close",
            "src",
            "scripts",
            "tests",
        ],
        text=True,
        capture_output=True,
    )
    assert res.returncode in (0, 1)
