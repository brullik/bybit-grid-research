from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import math
import polars as pl

from bybit_grid.research.range_features import DEFAULT_LOOKBACKS, ONE_MINUTE_MS, stable_candidate_id
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile


@dataclass(frozen=True)
class DetectionConfig:
    lookbacks: tuple[int, ...] = DEFAULT_LOOKBACKS
    lower_zone_pct: float = 0.20
    mid_zone_pct: float = 0.30
    upper_zone_pct: float = 0.20
    min_valid_candle_pct: float = 1.0
    max_zero_volume_window_pct: float = 0.05
    min_range_height_pct: float = 0.0001
    profile_name: str = "broad_diagnostic"


def _col(df: pl.DataFrame, *names: str) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"missing required column; tried {names}")


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    total = 0.0
    for i, val in enumerate(values):
        total += val
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def detect_range_candidates(
    df: pl.DataFrame, symbol: str, config: DetectionConfig | None = None, profile: RangeProfile | None = None
) -> pl.DataFrame:
    cfg = config or DetectionConfig()
    prof = profile or RANGE_PROFILES.get(cfg.profile_name, RANGE_PROFILES["broad_diagnostic"])
    if df.is_empty():
        return pl.DataFrame()
    ts_col = _col(df, "open_time_ms", "start_time_ms", "timestamp_ms")
    open_col = _col(df, "open", "open_price")
    high_col = _col(df, "high", "high_price")
    low_col = _col(df, "low", "low_price")
    close_col = _col(df, "close", "close_price")
    volume_col = "volume" if "volume" in df.columns else None
    turnover_col = (
        "turnover"
        if "turnover" in df.columns
        else ("turnover_usdt" if "turnover_usdt" in df.columns else None)
    )
    recs = df.sort(ts_col).to_dicts()
    t = [int(r[ts_col]) for r in recs]
    o = [float(r[open_col]) for r in recs]
    h = [float(r[high_col]) for r in recs]
    lows = [float(r[low_col]) for r in recs]
    c = [float(r[close_col]) for r in recs]
    v = [float(r.get(volume_col, 1.0) or 0.0) for r in recs] if volume_col else [1.0] * len(recs)
    turn = (
        [float(r.get(turnover_col, 0.0) or 0.0) for r in recs]
        if turnover_col
        else [0.0] * len(recs)
    )
    n = len(t)
    tr = []
    for i in range(n):
        pc = c[i - 1] if i else c[0]
        tr.append(max(h[i] - lows[i], abs(h[i] - pc), abs(lows[i] - pc)))
    atr14 = _rolling_mean(tr, 14)
    atr60 = _rolling_mean(tr, 60)
    bad = [
        (not all(math.isfinite(x) for x in (o[i], h[i], lows[i], c[i])))
        or h[i] < lows[i]
        or min(o[i], h[i], lows[i], c[i]) <= 0
        for i in range(n)
    ]
    zero = [vol <= 0 for vol in v]
    rows: list[dict[str, object]] = []
    for lb in cfg.lookbacks:
        if n < lb:
            continue
        for i in range(lb - 1, n):
            s = i - lb + 1
            missing = (
                0
                if int(t[i] - t[s]) == (lb - 1) * ONE_MINUTE_MS and len(set(t[s : i + 1])) == lb
                else 1
            )
            bad_count = sum(bad[s : i + 1])
            zero_count = sum(zero[s : i + 1])
            if missing or bad_count or zero_count > int(lb * prof.max_zero_volume_window_pct):
                continue
            lo = min(lows[s : i + 1])
            hi = max(h[s : i + 1])
            height = hi - lo
            height_pct = height / c[i]
            if height <= 0 or height_pct < max(cfg.min_range_height_pct, prof.range_height_pct_min) or height_pct > prof.range_height_pct_max:
                continue
            pos = (c[i] - lo) / height
            mid_low = 0.5 - cfg.mid_zone_pct / 2
            mid_high = 0.5 + cfg.mid_zone_pct / 2
            if prof.require_current_middle_zone and not (mid_low <= pos <= mid_high):
                continue
            lower_edge = lo + cfg.lower_zone_pct * height
            upper_edge = hi - cfg.upper_zone_pct * height
            lower_mask = [x <= lower_edge for x in lows[s : i + 1]]
            upper_mask = [x >= upper_edge for x in h[s : i + 1]]
            if prof.require_lower_upper_entries and not (any(lower_mask) and any(upper_mask)):
                continue
            mid = lo + 0.5 * height
            closes = c[s : i + 1]
            crosses = sum(1 for a, b in zip(closes, closes[1:]) if (a - mid) * (b - mid) < 0)
            rets = [
                math.log(closes[j] / closes[j - 1])
                for j in range(1, len(closes))
                if closes[j] > 0 and closes[j - 1] > 0
            ]
            last_lower = max(j for j, ok in enumerate(lower_mask) if ok)
            last_upper = max(j for j, ok in enumerate(upper_mask) if ok)
            a14 = atr14[i]
            a60 = atr60[i]
            lower_touches = sum(lower_mask)
            upper_touches = sum(upper_mask)
            slope_pct = abs((closes[-1] - closes[0]) / closes[0]) if closes[0] else 0.0
            a14 = atr14[i]
            range_atr = (height / a14) if a14 else None
            if crosses < prof.min_midline_cross_count:
                continue
            if lower_touches < prof.min_touches_lower_zone or upper_touches < prof.min_touches_upper_zone:
                continue
            if slope_pct > prof.max_abs_slope_pct_per_window:
                continue
            if range_atr is not None and not (prof.range_height_atr_min <= range_atr <= prof.range_height_atr_max):
                continue
            rows.append(
                {
                    "candidate_id": stable_candidate_id(f"{symbol}:{prof.name}", int(t[i]), lb),
                    "profile_name": prof.name,
                    "symbol": symbol,
                    "signal_time_ms": int(t[i]),
                    "signal_time_utc": datetime.fromtimestamp(
                        int(t[i]) / 1000, tz=timezone.utc
                    ).isoformat(),
                    "lookback_minutes": lb,
                    "range_low": lo,
                    "range_high": hi,
                    "range_mid": mid,
                    "range_height_abs": height,
                    "range_height_pct": height_pct,
                    "current_close": c[i],
                    "current_position_in_range": pos,
                    "touches_lower_zone": lower_touches,
                    "touches_upper_zone": upper_touches,
                    "entered_lower_zone": True,
                    "entered_upper_zone": True,
                    "midline_crosses": crosses,
                    "time_since_last_lower_touch_minutes": lb - 1 - last_lower,
                    "time_since_last_upper_touch_minutes": lb - 1 - last_upper,
                    "atr_14": a14,
                    "atr_60": a60,
                    "atr_rel_14": (a14 / c[i]) if a14 else None,
                    "atr_rel_60": (a60 / c[i]) if a60 else None,
                    "range_height_atr_14": range_atr,
                    "range_height_atr_60": (height / a60) if a60 else None,
                    "amplitude_score": height / c[i],
                    "mean_abs_return_inside_range": _mean([abs(x) for x in rets]),
                    "realized_volatility": _std(rets),
                    "valid_candles_in_window": lb,
                    "expected_candles_in_window": lb,
                    "missing_candles_in_window": missing,
                    "zero_volume_candles_in_window": zero_count,
                    "bad_ohlc_in_window": bad_count,
                    "data_quality_ok": True,
                    "candidate_passed_baseline_filters": True,
                    "turnover_sum_window": sum(turn[s : i + 1]),
                    "volume_sum_window": sum(v[s : i + 1]),
                    "symbol_rank_by_turnover": None,
                    "launch_age_days_at_signal": None,
                }
            )
    return pl.DataFrame(rows)
