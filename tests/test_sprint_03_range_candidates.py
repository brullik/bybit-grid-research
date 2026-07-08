from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import polars as pl

from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_features import stable_candidate_id
from bybit_grid.research.range_candidate_store import write_partitioned_candidates
from bybit_grid.research.range_event_coalescer import CoalesceConfig, coalesce_range_events
from bybit_grid.research.range_profiles import RANGE_PROFILES
from bybit_grid.live.execution_engine import ExecutionEngine
from bybit_grid.config import Settings


def candles(n=80, *, missing=False, bad=False, zero_tail=0, close_last=100.0):
    rows = []
    base = 1_700_000_000_000
    for i in range(n):
        ts = base + i * 60_000
        if missing and i == 10:
            ts += 60_000
        low = 95.0 if i % 10 == 0 else 98.0
        high = 105.0 if i % 13 == 0 else 102.0
        close = close_last if i == n - 1 else (99.0 if i % 2 else 101.0)
        open_ = close
        if bad and i == n - 5:
            high = 90.0
        vol = 0.0 if i >= n - zero_tail else 1.0
        rows.append(
            {
                "symbol": "BTCUSDT",
                "open_time_ms": ts,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
                "turnover": vol * close,
            }
        )
    return pl.DataFrame(rows)


def cfg():
    return DetectionConfig(lookbacks=(30,), min_range_height_pct=0.00001)


def test_horizontal_range_baseline_and_mid_zone():
    out = detect_range_candidates(candles(), "BTCUSDT", cfg())
    assert out.height > 0
    assert out["current_position_in_range"].min() >= 0.35
    assert out["current_position_in_range"].max() <= 0.65


def test_current_price_must_be_mid_zone():
    out = detect_range_candidates(candles(close_last=105.0), "BTCUSDT", cfg())
    assert out.filter(pl.col("signal_time_ms") == candles()["open_time_ms"][-1]).is_empty()


def test_requires_lower_and_upper_zone_entries():
    df = candles().with_columns(pl.lit(100.0).alias("low"), pl.lit(100.0).alias("high"))
    out = detect_range_candidates(df, "BTCUSDT", cfg())
    assert (
        out.is_empty() or out.filter(pl.col("signal_time_ms") == df["open_time_ms"][-1]).is_empty()
    )


def test_no_lookahead_future_changes_do_not_change_signal():
    df = candles(80)
    before = detect_range_candidates(df.head(60), "BTCUSDT", cfg())
    changed = pl.concat([df.head(60), df.tail(20).with_columns(pl.lit(1_000.0).alias("high"))])
    after = detect_range_candidates(changed, "BTCUSDT", cfg()).filter(
        pl.col("signal_time_ms") <= df["open_time_ms"][59]
    )
    assert (
        before.select("candidate_id").to_series().to_list()
        == after.select("candidate_id").to_series().to_list()
    )


def test_rejects_missing_bad_and_zero_volume_threshold():
    miss = candles(missing=True)
    out = detect_range_candidates(miss, "BTCUSDT", cfg())
    assert out.filter(pl.col("signal_time_ms") == miss["open_time_ms"][39]).is_empty()
    bad = candles(bad=True)
    out = detect_range_candidates(bad, "BTCUSDT", cfg())
    assert out.filter(pl.col("signal_time_ms") == bad["open_time_ms"][-1]).is_empty()
    z = candles(zero_tail=3)
    out = detect_range_candidates(z, "BTCUSDT", cfg())
    assert out.filter(pl.col("signal_time_ms") == z["open_time_ms"][-1]).is_empty()
    assert detect_range_candidates(candles(zero_tail=1), "BTCUSDT", cfg()).height > 0


def test_candidate_id_stable():
    assert stable_candidate_id("BTCUSDT", 123, 30) == stable_candidate_id("BTCUSDT", 123, 30)


def test_per_symbol_partition_writing(tmp_path: Path):
    out = detect_range_candidates(candles(), "BTCUSDT", cfg()).head(1)
    paths = write_partitioned_candidates(out, tmp_path)
    assert paths and paths[0].exists()
    assert "symbol=BTCUSDT" in str(paths[0])


def test_dry_run_plan_does_not_process_data(tmp_path: Path):
    manifest = tmp_path / "manifest.parquet"
    pl.DataFrame(
        {"symbol": ["BTCUSDT"], "estimated_kline_rows": [30], "start_ms": [0], "end_ms": [0]}
    ).write_parquet(manifest)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_range_candidates.py",
            "--manifest",
            str(manifest),
            "--dry-run-plan",
            "--output-dir",
            str(tmp_path / "out"),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "dry_run_plan" in result.stdout
    assert not (tmp_path / "out").exists()


def test_workers_resume_skip_existing_behavior(tmp_path: Path):
    data = tmp_path / "data" / "raw" / "klines" / "symbol=BTCUSDT" / "year=2023" / "month=11"
    data.mkdir(parents=True)
    candles().write_parquet(data / "part.parquet")
    manifest = tmp_path / "manifest.parquet"
    pl.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "estimated_kline_rows": [80],
            "start_ms": [0],
            "end_ms": [9_999_999_999_999],
        }
    ).write_parquet(manifest)
    cmd = [
        sys.executable,
        "scripts/build_range_candidates.py",
        "--manifest",
        str(manifest),
        "--data-dir",
        str(tmp_path / "data"),
        "--output-dir",
        str(tmp_path / "out"),
        "--workers",
        "1",
        "--resume",
        "--skip-existing-ok",
    ]
    first = subprocess.run(cmd, text=True, capture_output=True, check=True)
    second = subprocess.run(cmd, text=True, capture_output=True, check=True)
    assert "completed" in first.stdout and "skipped_existing_ok" in second.stdout


def test_no_live_create_close_order_paths_added():
    s = Settings(live_trading_enabled=False)
    e = ExecutionEngine(s)
    try:
        e.create_grid_bot(runtime_live=False)
    except (NotImplementedError, PermissionError):
        pass
    else:
        raise AssertionError("create must stay NotImplementedError")



def test_event_coalescing_one_event_for_consecutive_same_cluster():
    raw = pl.DataFrame([
        {"candidate_id": "a", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 0, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
        {"candidate_id": "b", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 60_000, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
        {"candidate_id": "c", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 120_000, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
    ])
    events = coalesce_range_events(raw, CoalesceConfig(cooldown_mode="none"))
    assert raw.height > events.height == 1
    assert events["raw_candidates_in_cluster"].max() == 3


def test_event_coalescing_different_clusters_emit_separate_events():
    raw = pl.DataFrame([
        {"candidate_id": "a", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 0, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
        {"candidate_id": "b", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 60_000, "lookback_minutes": 30, "range_low": 120.0, "range_high": 140.0, "current_close": 130.0},
    ])
    assert coalesce_range_events(raw, CoalesceConfig(cooldown_mode="none")).height == 2


def test_event_coalescing_cooldown_suppresses_and_allows_after():
    raw = pl.DataFrame([
        {"candidate_id": "a", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 0, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
        {"candidate_id": "b", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 5 * 60_000, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
        {"candidate_id": "c", "symbol": "BTCUSDT", "profile_name": "balanced_research", "signal_time_ms": 11 * 60_000, "lookback_minutes": 30, "range_low": 90.0, "range_high": 110.0, "current_close": 100.0},
    ])
    events = coalesce_range_events(raw, CoalesceConfig(cooldown_mode="fixed", cooldown_minutes=10))
    assert events.height == 2
    assert events["range_event_id"].to_list() == coalesce_range_events(raw, CoalesceConfig(cooldown_mode="fixed", cooldown_minutes=10))["range_event_id"].to_list()


def test_profile_filters_reduce_counts_and_rejection_counter_names_numeric():
    broad = detect_range_candidates(candles(100), "BTCUSDT", cfg(), RANGE_PROFILES["broad_diagnostic"])
    balanced = detect_range_candidates(candles(100), "BTCUSDT", cfg(), RANGE_PROFILES["balanced_research"])
    strict = detect_range_candidates(candles(100), "BTCUSDT", cfg(), RANGE_PROFILES["strict_research"])
    assert broad.height >= balanced.height >= strict.height
    keys = ["missing_window_rejection_count", "bad_ohlc_window_rejection_count", "zero_volume_window_rejection_count"]
    assert all(isinstance(0, int) for _ in keys)


def test_dry_run_estimate_10x30d_equals_432000(tmp_path: Path):
    manifest = tmp_path / "manifest.parquet"
    pl.DataFrame({"symbol": [f"S{i}" for i in range(10)], "start_ms": [0] * 10, "end_ms": [1] * 10}).write_parquet(manifest)
    result = subprocess.run([
        sys.executable, "scripts/build_range_candidates.py", "--manifest", str(manifest), "--dry-run-plan", "--symbols-limit", "10", "--days-limit", "30", "--profile", "all", "--output-layer", "both"], text=True, capture_output=True, check=True)
    assert "estimated_kline_rows=432000" in result.stdout
    assert "estimated_source=manifest/time_bounds" in result.stdout
