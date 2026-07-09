from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import math

import numpy as np
import polars as pl

from bybit_grid.research.range_actionable_events import add_range_quality_score
from bybit_grid.research.range_core.models import RangeInputArrays, empty_funnel
from bybit_grid.research.range_features import ONE_MINUTE_MS, stable_candidate_id
from bybit_grid.research.range_profiles import RangeProfile


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    out = np.full(x.size, np.nan, dtype=np.float64)
    if x.size >= window:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[window - 1 :] = (cs[window:] - cs[:-window]) / window
    return out


def _rolling_extreme(x: np.ndarray, window: int, *, want_max: bool) -> np.ndarray:
    out = np.full(x.size, np.nan, dtype=np.float64)
    q: deque[int] = deque()
    for i, val in enumerate(x):
        while q and q[0] <= i - window:
            q.popleft()
        if want_max:
            while q and x[q[-1]] <= val:
                q.pop()
        else:
            while q and x[q[-1]] >= val:
                q.pop()
        q.append(i)
        if i >= window - 1:
            out[i] = x[q[0]]
    return out


def _prefix_counts(mask: np.ndarray) -> np.ndarray:
    return np.insert(np.cumsum(mask.astype(np.int64)), 0, 0)


def _window_count(prefix: np.ndarray, s: int, i: int) -> int:
    return int(prefix[i + 1] - prefix[s])


def detect_ranges(arrays: RangeInputArrays, symbol: str, profile: RangeProfile, lookbacks: tuple[int, ...]) -> tuple[pl.DataFrame, dict[str, int]]:
    a = arrays.contiguous()
    order = np.argsort(a.open_time_ms, kind="mergesort")
    t, o, h, low, c, v = (x[order] for x in (a.open_time_ms, a.open, a.high, a.low, a.close, a.volume))
    turn = np.zeros_like(c) if a.turnover is None else a.turnover[order]
    n = int(t.size)
    funnel = empty_funnel()
    if n == 0:
        return pl.DataFrame(), funnel
    prev_close = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([h - low, np.abs(h - prev_close), np.abs(low - prev_close)])
    atr14 = _rolling_mean(tr, 14)
    atr60 = _rolling_mean(tr, 60)
    bad = (~np.isfinite(o)) | (~np.isfinite(h)) | (~np.isfinite(low)) | (~np.isfinite(c)) | (h < low) | (np.minimum.reduce([o, h, low, c]) <= 0)
    zero = v <= 0
    duplicate_step = np.r_[False, np.diff(t) == 0]
    bad_prefix = _prefix_counts(bad)
    zero_prefix = _prefix_counts(zero)
    dup_prefix = _prefix_counts(duplicate_step)
    turnover_prefix = np.insert(np.cumsum(turn), 0, 0.0)
    volume_prefix = np.insert(np.cumsum(v), 0, 0.0)
    rows: list[dict[str, object]] = []
    mid_low = 0.5 - 0.30 / 2
    mid_high = 0.5 + 0.30 / 2
    for lb in lookbacks:
        funnel["total_window_positions"] += max(0, n - lb + 1)
        if n < lb:
            funnel["insufficient_history_rejection_count"] += lb - n
            continue
        roll_hi = _rolling_extreme(h, lb, want_max=True)
        roll_lo = _rolling_extreme(low, lb, want_max=False)
        for i in range(lb - 1, n):
            s = i - lb + 1
            if int(t[i] - t[s]) != (lb - 1) * ONE_MINUTE_MS:
                funnel["missing_window_rejection_count"] += 1
                continue
            if _window_count(dup_prefix, s, i):
                funnel["duplicate_timestamp_rejection_count"] += 1
                continue
            bad_count = _window_count(bad_prefix, s, i)
            if bad_count:
                funnel["bad_ohlc_window_rejection_count"] += 1
                continue
            zero_count = _window_count(zero_prefix, s, i)
            if zero_count > int(lb * profile.max_zero_volume_window_pct):
                funnel["zero_volume_window_rejection_count"] += 1
                continue
            lo = float(roll_lo[i])
            hi = float(roll_hi[i])
            height = hi - lo
            height_pct = height / float(c[i]) if c[i] else math.inf
            if height <= 0 or height_pct < profile.range_height_pct_min or height_pct > profile.range_height_pct_max:
                funnel["range_height_rejection_count"] += 1
                continue
            pos = (float(c[i]) - lo) / height
            if profile.require_current_middle_zone and not (mid_low <= pos <= mid_high):
                funnel["middle_zone_rejection_count"] += 1
                continue
            lower_edge = lo + 0.20 * height
            upper_edge = hi - 0.20 * height
            lows_w = low[s : i + 1]
            highs_w = h[s : i + 1]
            lower_mask = lows_w <= lower_edge
            upper_mask = highs_w >= upper_edge
            if profile.require_lower_upper_entries and not (bool(np.any(lower_mask)) and bool(np.any(upper_mask))):
                funnel["lower_upper_entry_rejection_count"] += 1
                continue
            closes = c[s : i + 1]
            mid = lo + 0.5 * height
            crosses = int(np.count_nonzero(((closes[:-1] - mid) * (closes[1:] - mid)) < 0))
            if crosses < profile.min_midline_cross_count:
                funnel["midline_cross_rejection_count"] += 1
                continue
            lower_touches = int(np.count_nonzero(lower_mask))
            upper_touches = int(np.count_nonzero(upper_mask))
            if lower_touches < profile.min_touches_lower_zone or upper_touches < profile.min_touches_upper_zone:
                funnel["touch_count_rejection_count"] += 1
                continue
            slope_pct = abs((float(closes[-1]) - float(closes[0])) / float(closes[0])) if closes[0] else 0.0
            if slope_pct > profile.max_abs_slope_pct_per_window:
                funnel["slope_rejection_count"] += 1
                continue
            a14 = None if np.isnan(atr14[i]) else float(atr14[i])
            a60 = None if np.isnan(atr60[i]) else float(atr60[i])
            range_atr = (height / a14) if a14 else None
            if range_atr is not None and not (profile.range_height_atr_min <= range_atr <= profile.range_height_atr_max):
                funnel["range_atr_rejection_count"] += 1
                continue
            if range_atr is not None and range_atr < profile.min_path_length_over_range:
                funnel["range_atr_rejection_count"] += 1
                continue
            last_lower = int(np.flatnonzero(lower_mask)[-1])
            last_upper = int(np.flatnonzero(upper_mask)[-1])
            rets = np.diff(np.log(closes[closes > 0])) if np.all(closes > 0) else np.array([], dtype=np.float64)
            rows.append({"candidate_id": stable_candidate_id(f"{symbol}:{profile.name}", int(t[i]), lb), "profile_name": profile.name, "symbol": symbol, "signal_time_ms": int(t[i]), "signal_time_utc": datetime.fromtimestamp(int(t[i]) / 1000, tz=timezone.utc).isoformat(), "lookback_minutes": lb, "range_low": lo, "range_high": hi, "range_mid": mid, "range_height_abs": height, "range_height_pct": height_pct, "current_close": float(c[i]), "current_position_in_range": pos, "touches_lower_zone": lower_touches, "touches_upper_zone": upper_touches, "entered_lower_zone": True, "entered_upper_zone": True, "midline_crosses": crosses, "time_since_last_lower_touch_minutes": lb - 1 - last_lower, "time_since_last_upper_touch_minutes": lb - 1 - last_upper, "atr_14": a14, "atr_60": a60, "atr_rel_14": (a14 / float(c[i])) if a14 else None, "atr_rel_60": (a60 / float(c[i])) if a60 else None, "range_height_atr_14": range_atr, "range_height_atr_60": (height / a60) if a60 else None, "amplitude_score": height_pct, "mean_abs_return_inside_range": float(np.mean(np.abs(rets))) if rets.size else 0.0, "realized_volatility": float(np.std(rets)) if rets.size else 0.0, "valid_candles_in_window": lb, "expected_candles_in_window": lb, "missing_candles_in_window": 0, "zero_volume_candles_in_window": zero_count, "bad_ohlc_in_window": bad_count, "data_quality_ok": True, "candidate_passed_baseline_filters": True, "turnover_sum_window": float(turnover_prefix[i + 1] - turnover_prefix[s]), "volume_sum_window": float(volume_prefix[i + 1] - volume_prefix[s]), "symbol_rank_by_turnover": None, "launch_age_days_at_signal": None})
    out = pl.DataFrame(rows)
    if not out.is_empty():
        out = add_range_quality_score(out)
        before = out.height
        if profile.min_range_quality_score:
            out = out.filter(pl.col("range_quality_score") >= profile.min_range_quality_score)
        funnel["quality_score_rejection_count"] += before - out.height
    funnel["raw_candidate_pass_count"] += out.height
    return out, funnel
