from __future__ import annotations

import hashlib
import math

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.funding_join import aggregate_funding
from bybit_grid.research.outcome_core.grid_crossings import (
    count_level_crossings,
    count_midline_crossings,
    geometric_grid_levels,
    levels_json,
)

MINUTE_MS = 60_000


def deterministic_outcome_id(event_id: str, horizon: int, grid_count: int, sl_atr_buffer: float) -> str:
    key = f"{event_id}|{horizon}|{grid_count}|{sl_atr_buffer:g}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _col(row: dict, name: str, default=0):
    return row[name] if name in row and row[name] is not None else default


def compute_event_outcomes(
    event: dict,
    klines: pl.DataFrame,
    mark_klines: pl.DataFrame,
    funding: pl.DataFrame,
    horizons: list[int],
    grid_counts: list[int],
    sl_atr_buffers: list[float],
    profile_name: str = "candidate_outcomes_v1",
) -> list[dict]:
    signal = int(_col(event, "signal_time_ms"))
    entry = ((signal // MINUTE_MS) + 1) * MINUTE_MS
    symbol = str(_col(event, "symbol", ""))
    time_col = "open_time_ms" if "open_time_ms" in klines.columns else "start_time_ms"
    rows: list[dict] = []
    for horizon in horizons:
        end = entry + horizon * MINUTE_MS
        fut = klines.filter((pl.col(time_col) >= entry) & (pl.col(time_col) < end)).sort(time_col)
        times = fut[time_col].to_numpy() if not fut.is_empty() else np.array([], dtype=np.int64)
        opens = fut["open"].cast(pl.Float64).to_numpy() if "open" in fut.columns else np.array([])
        highs = fut["high"].cast(pl.Float64).to_numpy() if "high" in fut.columns else np.array([])
        lows = fut["low"].cast(pl.Float64).to_numpy() if "low" in fut.columns else np.array([])
        closes = fut["close"].cast(pl.Float64).to_numpy() if "close" in fut.columns else np.array([])
        vols = fut["volume"].cast(pl.Float64).to_numpy() if "volume" in fut.columns else np.array([])
        range_low = float(_col(event, "range_low"))
        range_high = float(_col(event, "range_high"))
        range_mid = float(_col(event, "range_mid", (range_low + range_high) / 2))
        bad = int(np.sum((highs < lows) | (opens <= 0) | (closes <= 0))) if highs.size else 0
        zero_vol = int(np.sum(vols <= 0)) if vols.size else 0
        missing = max(0, horizon - int(len(times)))
        up_idx = np.where(highs > range_high)[0] if highs.size else np.array([], dtype=int)
        dn_idx = np.where(lows < range_low)[0] if lows.size else np.array([], dtype=int)
        first_exit_side = "none"
        first_exit_time = None
        if up_idx.size or dn_idx.size:
            u = int(up_idx[0]) if up_idx.size else math.inf
            d = int(dn_idx[0]) if dn_idx.size else math.inf
            if u <= d:
                first_exit_side, first_exit_time = "up", int(times[u])
            else:
                first_exit_side, first_exit_time = "down", int(times[d])
        inside = int(np.sum((highs <= range_high) & (lows >= range_low))) if highs.size else 0
        inside_ratio = inside / horizon if horizon else 0.0
        fund = aggregate_funding(funding, entry, end)
        mark_rows = mark_klines.filter((pl.col(time_col) >= entry) & (pl.col(time_col) < end)) if not mark_klines.is_empty() and time_col in mark_klines.columns else pl.DataFrame()
        mark_dev = 0.0
        if not mark_rows.is_empty() and closes.size and "close" in mark_rows.columns:
            mc = mark_rows["close"].cast(pl.Float64).to_numpy()
            last = closes[0]
            mark_dev = float(np.max(np.abs(mc - last) / last * 100)) if last else 0.0
        for grid_count in grid_counts:
            levels = geometric_grid_levels(range_low, range_high, grid_count)
            grid_cross = count_level_crossings(closes, levels)
            mid_cross = count_midline_crossings(closes, range_mid)
            step_pct = float(np.mean(np.diff(levels) / levels[:-1] * 100)) if len(levels) > 1 and np.all(levels[:-1] != 0) else 0.0
            for sl_buf in sl_atr_buffers:
                atr_pct = float(_col(event, "range_height_atr_14", 0.0)) * float(sl_buf)
                lower_sl = range_low * (1 - atr_pct / 100)
                upper_sl = range_high * (1 + atr_pct / 100)
                upper_idx = np.where(highs >= upper_sl)[0] if highs.size else np.array([], dtype=int)
                lower_idx = np.where(lows <= lower_sl)[0] if lows.size else np.array([], dtype=int)
                first_sl_side = "none"
                first_sl_time = None
                if upper_idx.size or lower_idx.size:
                    u = int(upper_idx[0]) if upper_idx.size else math.inf
                    d = int(lower_idx[0]) if lower_idx.size else math.inf
                    first_sl_side, first_sl_time = ("upper", int(times[u])) if u <= d else ("lower", int(times[d]))
                min_cross = max(1, horizon // 240)
                rows.append({
                    "outcome_id": deterministic_outcome_id(str(_col(event,"range_action_event_id", _col(event,"range_event_id",""))), horizon, grid_count, float(sl_buf)),
                    "range_action_event_id": str(_col(event,"range_action_event_id", _col(event,"range_event_id",""))), "range_regime_id": str(_col(event,"range_regime_id", "")), "symbol": symbol, "profile_name": profile_name,
                    "signal_time_ms": signal, "entry_time_ms": entry, "future_horizon_minutes": horizon, "grid_count": grid_count, "sl_atr_buffer": float(sl_buf),
                    **{k: _col(event,k,None) for k in ["best_lookback_minutes","lookbacks_observed","range_low","range_high","range_mid","range_height_pct","range_height_atr_14","range_quality_score","path_length_over_range","midline_crosses","min_touches_lower_zone","min_touches_upper_zone","fgrid_investment_min","min_investment_feasible_at_5usdt"]},
                    "future_rows_available": int(len(times)), "future_coverage_minutes": int(len(times)), "future_data_complete_bool": len(times) >= horizon, "future_missing_minutes_count": missing, "future_bad_ohlc_count": bad, "future_zero_volume_count": zero_vol,
                    "first_exit_side": first_exit_side, "first_exit_time_ms": first_exit_time, "minutes_to_first_exit": None if first_exit_time is None else int((first_exit_time-entry)//MINUTE_MS), "time_inside_range_minutes": inside, "inside_range_ratio": inside_ratio,
                    "max_high_above_range_pct": float(max(0, (np.max(highs)-range_high)/range_high*100)) if highs.size and range_high else 0.0, "max_low_below_range_pct": float(max(0, (range_low-np.min(lows))/range_low*100)) if lows.size and range_low else 0.0, "max_close_distance_from_mid_pct": float(np.max(np.abs(closes-range_mid))/range_mid*100) if closes.size and range_mid else 0.0,
                    "lower_sl_price": lower_sl, "upper_sl_price": upper_sl, "first_sl_side": first_sl_side, "first_sl_time_ms": first_sl_time, "minutes_to_first_sl": None if first_sl_time is None else int((first_sl_time-entry)//MINUTE_MS), "sl_hit_bool": first_sl_side != "none", "sl_distance_lower_pct": (range_low-lower_sl)/range_low*100 if range_low else 0.0, "sl_distance_upper_pct": (upper_sl-range_high)/range_high*100 if range_high else 0.0,
                    "geometric_grid_levels_json": levels_json(levels), "future_grid_level_cross_count": grid_cross, "future_midline_cross_count": mid_cross, "future_upper_zone_touch_count": int(np.sum(highs >= range_high)) if highs.size else 0, "future_lower_zone_touch_count": int(np.sum(lows <= range_low)) if lows.size else 0, "grid_crossings_per_hour": grid_cross / (horizon / 60), "grid_step_pct_mean": step_pct, "grid_step_fee_multiple_proxy": step_pct / 0.055 if step_pct else 0.0,
                    **fund, "mark_price_future_rows_available": mark_rows.height, "mark_price_max_deviation_from_last_pct": mark_dev,
                    "label_stayed_in_range_until_horizon": first_exit_side == "none", "label_sl_hit_before_horizon": first_sl_side != "none", "label_good_chop_proxy": inside_ratio >= 0.70 and grid_cross >= min_cross, "label_low_activity_proxy": grid_cross < min_cross, "label_high_breakout_risk_proxy": first_sl_side != "none" or inside_ratio < 0.40,
                })
    return rows
