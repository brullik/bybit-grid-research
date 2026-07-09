from __future__ import annotations


import polars as pl

from bybit_grid.research.range_candidate_summary import build_summary
from bybit_grid.research.range_core import arrays_from_frame, detect_ranges_core_with_funnel
from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_profiles import RANGE_PROFILES
from scripts.make_pm_review_pack import allowed


def _candles(n: int = 80) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "open_time_ms": [i * 60_000 for i in range(n)],
            "open": [100.0] * n,
            "high": [101.0 if i % 2 else 100.5 for i in range(n)],
            "low": [99.0 if i % 2 else 99.5 for i in range(n)],
            "close": [100.0] * n,
            "volume": [1.0] * n,
        }
    )


def test_summary_accepts_actionable_and_regime_lookback_schemas() -> None:
    actionable = pl.DataFrame(
        {"symbol": ["BTCUSDT"], "best_lookback_minutes": [30], "range_height_pct": [0.01]}
    )
    regimes = pl.DataFrame(
        {"symbol": ["BTCUSDT"], "lookback_min": [30], "lookback_max": [60], "lookbacks_observed": ["30,60"]}
    )
    assert build_summary(actionable)["candidate_rows_written"] == 1
    assert build_summary(regimes)["candidate_rows_written"] == 1


def test_numpy_fast_matches_reference_fallback_and_funnel_numeric() -> None:
    df = _candles()
    profile = RANGE_PROFILES["broad_diagnostic"]
    lookbacks = (30,)
    fast, funnel = detect_ranges_core_with_funnel(arrays_from_frame(df), "BTCUSDT", profile, lookbacks, core="numpy_fast")
    ref = detect_range_candidates(df, "BTCUSDT", DetectionConfig(lookbacks=lookbacks), profile)
    assert fast.select(["candidate_id", "signal_time_ms", "lookback_minutes"]).to_dicts() == ref.select(
        ["candidate_id", "signal_time_ms", "lookback_minutes"]
    ).to_dicts()
    assert all(isinstance(v, int) for v in funnel.values())
    assert funnel["total_window_positions"] >= funnel["raw_candidate_pass_count"]


def test_pm_pack_allowlist_excludes_raw_and_secrets(tmp_path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("SECRET=1", encoding="utf-8")
    assert not allowed(secret, "run1")
    assert not allowed(tmp_path / "data/raw/x.parquet", "run1")
    assert not allowed(tmp_path / "data/processed/range_runs/run1/actionable_events/x.parquet", "run1")
