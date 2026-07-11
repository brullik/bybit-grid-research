from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.funding_join import _empty
from bybit_grid.research.outcome_core.grid_crossings import (
    GRID_LEVELS_SERIALIZATION_VERSION,
    geometric_grid_levels,
    levels_json,
)
from bybit_grid.research.outcome_core.outcome_numpy import (
    GRID_GEOMETRY_SEMANTICS_VERSION,
    MINUTE_MS,
    OUTCOME_SEMANTICS_VERSION,
    _col,
    deterministic_outcome_id,
    outcome_match_key,
)
from bybit_grid.research.outcome_core.sl_proxy import compute_sl_proxy


@dataclass(frozen=True)
class OutcomeCoreConfig:
    horizons_minutes: tuple[int, ...]
    grid_cell_numbers: tuple[int, ...]
    sl_atr_buffers: tuple[float, ...]
    range_run_id: str
    outcome_run_id: str
    profile_name: str = "candidate_outcomes_v1"


@dataclass
class OutcomeSymbolArrays:
    time_ms: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    mark_time_ms: np.ndarray
    mark_close: np.ndarray
    funding_time_ms: np.ndarray
    funding_rate: np.ndarray
    bad_ohlc_prefix: np.ndarray
    zero_volume_prefix: np.ndarray
    funding_rate_prefix: np.ndarray
    funding_abs_rate_prefix: np.ndarray
    diagnostics: dict[str, int] = field(default_factory=dict)


def _time_col(df: pl.DataFrame) -> str:
    return "open_time_ms" if "open_time_ms" in df.columns else "start_time_ms"


def _sorted_unique(df: pl.DataFrame, time_col: str) -> tuple[pl.DataFrame, dict[str, int]]:
    if df.is_empty() or time_col not in df.columns:
        return df, {"rows": 0, "duplicate_timestamps": 0, "non_ascending_timestamps": 0}
    sorted_df = df.sort(time_col)
    ts = sorted_df[time_col].to_numpy()
    dup = int(ts.size - np.unique(ts).size)
    non_asc = int(np.sum(np.diff(ts) <= 0)) if ts.size > 1 else 0
    return sorted_df.unique(subset=[time_col], keep="first", maintain_order=True), {
        "rows": int(ts.size),
        "duplicate_timestamps": dup,
        "non_ascending_timestamps": non_asc,
    }


def build_outcome_symbol_arrays(
    klines: pl.DataFrame, mark_klines: pl.DataFrame, funding: pl.DataFrame
) -> OutcomeSymbolArrays:
    tc = _time_col(klines) if not klines.is_empty() else "open_time_ms"
    kl, kd = _sorted_unique(klines, tc)
    times = kl[tc].to_numpy().astype(np.int64) if tc in kl.columns else np.array([], dtype=np.int64)
    opens = (
        kl["open"].cast(pl.Float64).to_numpy()
        if "open" in kl.columns
        else np.array([], dtype=float)
    )
    highs = (
        kl["high"].cast(pl.Float64).to_numpy()
        if "high" in kl.columns
        else np.array([], dtype=float)
    )
    lows = (
        kl["low"].cast(pl.Float64).to_numpy() if "low" in kl.columns else np.array([], dtype=float)
    )
    closes = (
        kl["close"].cast(pl.Float64).to_numpy()
        if "close" in kl.columns
        else np.array([], dtype=float)
    )
    vols = (
        kl["volume"].cast(pl.Float64).to_numpy()
        if "volume" in kl.columns
        else np.array([], dtype=float)
    )
    bad = (
        ((highs < lows) | (opens <= 0) | (closes <= 0)).astype(np.int64)
        if highs.size
        else np.array([], dtype=np.int64)
    )
    zero = (vols <= 0).astype(np.int64) if vols.size else np.array([], dtype=np.int64)
    mt = _time_col(mark_klines) if not mark_klines.is_empty() else "open_time_ms"
    mk, md = _sorted_unique(mark_klines, mt)
    ft_col = next(
        (
            c
            for c in ["funding_rate_timestamp_ms", "funding_time_ms", "start_time_ms"]
            if c in funding.columns
        ),
        "",
    )
    rate_col = "funding_rate" if "funding_rate" in funding.columns else "rate"
    fu, fd = (
        _sorted_unique(funding, ft_col)
        if ft_col
        else (pl.DataFrame(), {"rows": 0, "duplicate_timestamps": 0, "non_ascending_timestamps": 0})
    )
    rates = (
        fu[rate_col].cast(pl.Float64).to_numpy()
        if rate_col in fu.columns
        else np.array([], dtype=float)
    )
    return OutcomeSymbolArrays(
        np.ascontiguousarray(times),
        np.ascontiguousarray(opens),
        np.ascontiguousarray(highs),
        np.ascontiguousarray(lows),
        np.ascontiguousarray(closes),
        np.ascontiguousarray(vols),
        np.ascontiguousarray(mk[mt].to_numpy().astype(np.int64))
        if mt in mk.columns
        else np.array([], dtype=np.int64),
        np.ascontiguousarray(mk["close"].cast(pl.Float64).to_numpy())
        if "close" in mk.columns
        else np.array([], dtype=float),
        np.ascontiguousarray(fu[ft_col].to_numpy().astype(np.int64))
        if ft_col and ft_col in fu.columns
        else np.array([], dtype=np.int64),
        np.ascontiguousarray(rates),
        np.r_[0, np.cumsum(bad)],
        np.r_[0, np.cumsum(zero)],
        np.r_[0.0, np.cumsum(rates)],
        np.r_[0.0, np.cumsum(np.abs(rates))],
        {"klines_" + k: v for k, v in kd.items()}
        | {"mark_" + k: v for k, v in md.items()}
        | {"funding_" + k: v for k, v in fd.items()},
    )


def _first(
    indices: np.ndarray, times: np.ndarray, label_a: str, label_b: str
) -> tuple[str, int | None, bool]:
    a, b = indices
    if a.size or b.size:
        ia = int(a[0]) if a.size else math.inf
        ib = int(b[0]) if b.size else math.inf
        if ia == ib:
            return "ambiguous_both", int(times[ia]), True
        if ia < ib:
            return label_a, int(times[ia]), False
        return label_b, int(times[ib]), False
    return "none", None, False


def _funding(arr: OutcomeSymbolArrays, entry: int, end: int) -> dict:
    if arr.funding_time_ms.size == 0:
        return _empty("missing_file")
    left = int(np.searchsorted(arr.funding_time_ms, entry, side="right"))
    right = int(np.searchsorted(arr.funding_time_ms, end, side="right"))
    count = right - left
    if count <= 0:
        return _empty("no_overlap")
    s = float(arr.funding_rate_prefix[right] - arr.funding_rate_prefix[left])
    return {
        "funding_rows_in_horizon": count,
        "funding_rate_sum": s,
        "funding_rate_abs_sum": float(
            arr.funding_abs_rate_prefix[right] - arr.funding_abs_rate_prefix[left]
        ),
        "funding_rate_mean": s / count,
        "funding_source_status": "ok",
    }


def _cross_counts(closes: np.ndarray, levels: np.ndarray) -> np.ndarray:
    if closes.size < 2 or levels.size == 0:
        return np.zeros(closes.size, dtype=np.int64)
    lo = np.minimum(closes[:-1], closes[1:])
    hi = np.maximum(closes[:-1], closes[1:])
    moved = closes[1:] != closes[:-1]
    c = (
        np.searchsorted(levels, hi, side="right") - np.searchsorted(levels, lo, side="right")
    ) * moved
    return np.r_[0, c].astype(np.int64)


def _touch_counts(lows: np.ndarray, highs: np.ndarray, levels: np.ndarray) -> np.ndarray:
    if lows.size == 0 or levels.size == 0:
        return np.zeros(lows.size, dtype=np.int64)
    return (
        np.searchsorted(levels, highs, side="right") - np.searchsorted(levels, lows, side="left")
    ).astype(np.int64)


def compute_symbol_outcomes_fast(
    events: pl.DataFrame, arrays: OutcomeSymbolArrays, config: OutcomeCoreConfig
) -> pl.DataFrame:
    rows: list[dict] = []
    horizons = sorted(config.horizons_minutes)
    for event in events.to_dicts():
        signal = int(_col(event, "signal_time_ms"))
        entry = ((signal // MINUTE_MS) + 1) * MINUTE_MS
        end_max = entry + max(horizons) * MINUTE_MS
        start = int(np.searchsorted(arrays.time_ms, entry, side="left"))
        stop = int(np.searchsorted(arrays.time_ms, end_max, side="left"))
        slc = slice(start, stop)
        times = arrays.time_ms[slc]
        highs = arrays.high[slc]
        lows = arrays.low[slc]
        closes = arrays.close[slc]
        range_low = float(_col(event, "range_low"))
        range_high = float(_col(event, "range_high"))
        range_mid = float(_col(event, "range_mid", (range_low + range_high) / 2))
        inside_cum = np.r_[0, np.cumsum((highs <= range_high) & (lows >= range_low))]
        upper_touch_cum = np.r_[0, np.cumsum(highs >= range_high)]
        lower_touch_cum = np.r_[0, np.cumsum(lows <= range_low)]
        mid_cum = np.r_[0, np.cumsum(_cross_counts(closes, np.array([range_mid], dtype=float)))]
        sym = str(_col(event, "symbol", ""))
        eid = str(_col(event, "range_action_event_id", _col(event, "range_event_id", "")))
        sl_by_h = {}
        for sl_buf in config.sl_atr_buffers:
            sl = compute_sl_proxy(event, range_low, range_high, float(sl_buf))
            lower = sl.lower_sl_price if sl.lower_sl_price is not None else -math.inf
            upper = sl.upper_sl_price if sl.upper_sl_price is not None else math.inf
            up_all = (
                np.where(highs >= upper)[0]
                if highs.size and sl.sl_proxy_valid_bool
                else np.array([], dtype=int)
            )
            dn_all = (
                np.where(lows <= lower)[0]
                if lows.size and sl.sl_proxy_valid_bool
                else np.array([], dtype=int)
            )
            sl_by_h[sl_buf] = (sl, up_all, dn_all)
        grid_by_count = {}
        for gc in config.grid_cell_numbers:
            levels = geometric_grid_levels(range_low, range_high, int(gc))
            internal = levels[1:-1]
            grid_by_count[gc] = (
                levels,
                np.r_[0, np.cumsum(_cross_counts(closes, levels))],
                np.r_[0, np.cumsum(_touch_counts(lows, highs, levels))],
                np.r_[0, np.cumsum(_cross_counts(closes, internal))],
                np.r_[0, np.cumsum(_touch_counts(lows, highs, internal))],
            )
        for horizon in config.horizons_minutes:
            end = entry + horizon * MINUTE_MS
            n = int(np.searchsorted(times, end, side="left"))
            ht = times[:n]
            hh = highs[:n]
            hl = lows[:n]
            hc = closes[:n]
            up = np.where(hh > range_high)[0] if n else np.array([], dtype=int)
            dn = np.where(hl < range_low)[0] if n else np.array([], dtype=int)
            first_exit_side, first_exit_time, first_exit_amb = _first(
                np.array([up, dn], dtype=object), ht, "up", "down"
            )
            fund = _funding(arrays, entry, end)
            ml = int(np.searchsorted(arrays.mark_time_ms, entry, side="left"))
            mr = int(np.searchsorted(arrays.mark_time_ms, end, side="left"))
            mc = arrays.mark_close[ml:mr]
            mark_dev = (
                float(np.max(np.abs(mc - hc[0]) / hc[0] * 100))
                if mc.size and hc.size and hc[0]
                else 0.0
            )
            base = {
                "future_rows_available": n,
                "future_coverage_minutes": n,
                "future_data_complete_bool": n >= horizon,
                "future_missing_minutes_count": max(0, horizon - n),
                "future_bad_ohlc_count": int(
                    arrays.bad_ohlc_prefix[start + n] - arrays.bad_ohlc_prefix[start]
                ),
                "future_zero_volume_count": int(
                    arrays.zero_volume_prefix[start + n] - arrays.zero_volume_prefix[start]
                ),
                "first_exit_side": first_exit_side,
                "first_exit_ambiguous_bool": first_exit_amb,
                "first_exit_time_ms": first_exit_time,
                "minutes_to_first_exit": None
                if first_exit_time is None
                else int((first_exit_time - entry) // MINUTE_MS),
                "time_inside_range_minutes": int(inside_cum[n]),
                "inside_range_candle_count": int(inside_cum[n]),
                "inside_range_ratio": int(inside_cum[n]) / horizon if horizon else 0.0,
                "max_high_above_range_pct": float(
                    max(0, (np.max(hh) - range_high) / range_high * 100)
                )
                if n and range_high
                else 0.0,
                "max_low_below_range_pct": float(max(0, (range_low - np.min(hl)) / range_low * 100))
                if n and range_low
                else 0.0,
                "max_close_distance_from_mid_pct": float(
                    np.max(np.abs(hc - range_mid)) / range_mid * 100
                )
                if n and range_mid
                else 0.0,
                "future_midline_cross_count": int(mid_cum[n]),
                "future_upper_zone_touch_count": int(upper_touch_cum[n]),
                "future_lower_zone_touch_count": int(lower_touch_cum[n]),
                **fund,
                "mark_price_future_rows_available": int(mc.size),
                "mark_price_max_deviation_from_last_pct": mark_dev,
            }
            for gc in config.grid_cell_numbers:
                levels, gcross, gtouch, icross, itouch = grid_by_count[gc]
                interval_ratio = (range_high / range_low) ** (1.0 / int(gc))
                step_pct = float((interval_ratio - 1.0) * 100.0)
                unique_touched = (
                    int(((levels[:, None] >= hl) & (levels[:, None] <= hh)).any(axis=1).sum())
                    if n
                    else 0
                )
                for sl_buf in config.sl_atr_buffers:
                    sl, up_all, dn_all = sl_by_h[sl_buf]
                    fs, ft, fa = _first(
                        np.array([up_all[up_all < n], dn_all[dn_all < n]], dtype=object),
                        ht,
                        "upper",
                        "lower",
                    )
                    min_cross = max(1, horizon // 240)
                    grid_cross = int(gcross[n])
                    intrabar = int(gtouch[n])
                    rows.append(
                        {
                            "outcome_id": deterministic_outcome_id(
                                eid, horizon, int(gc), float(sl_buf), OUTCOME_SEMANTICS_VERSION
                            ),
                            "outcome_match_key": outcome_match_key(
                                eid, horizon, int(gc), float(sl_buf)
                            ),
                            "range_action_event_id": eid,
                            "range_regime_id": str(_col(event, "range_regime_id", "")),
                            "symbol": sym,
                            "profile_name": config.profile_name,
                            "outcome_semantics_version": OUTCOME_SEMANTICS_VERSION,
                            "range_run_id": config.range_run_id,
                            "outcome_run_id": config.outcome_run_id,
                            "signal_time_ms": signal,
                            "entry_time_ms": entry,
                            "future_horizon_minutes": horizon,
                            "grid_count": int(gc),
                            "grid_cell_number": int(gc),
                            "grid_price_level_count": int(gc) + 1,
                            "grid_interval_count": int(gc),
                            "grid_interval_ratio": interval_ratio,
                            "grid_interval_pct": step_pct,
                            "grid_interval_bps": step_pct * 100,
                            "grid_count_semantics": "native_bybit_cell_number",
                            "grid_geometry_semantics_version": GRID_GEOMETRY_SEMANTICS_VERSION,
                            "sl_atr_buffer": float(sl_buf),
                            **{
                                k: _col(event, k, None)
                                for k in [
                                    "best_lookback_minutes",
                                    "lookbacks_observed",
                                    "range_low",
                                    "range_high",
                                    "range_mid",
                                    "range_height_pct",
                                    "range_height_atr_14",
                                    "range_quality_score",
                                    "path_length_over_range",
                                    "midline_crosses",
                                    "min_touches_lower_zone",
                                    "min_touches_upper_zone",
                                    "fgrid_investment_min",
                                    "min_investment_feasible_at_5usdt",
                                ]
                            },
                            **base,
                            **sl.as_dict(),
                            "first_sl_side": fs,
                            "first_sl_ambiguous_bool": fa,
                            "first_sl_time_ms": ft,
                            "minutes_to_first_sl": None
                            if ft is None
                            else int((ft - entry) // MINUTE_MS),
                            "sl_hit_bool": fs != "none",
                            "geometric_grid_levels_json": levels_json(levels),
                            "grid_levels_serialization_version": GRID_LEVELS_SERIALIZATION_VERSION,
                            "future_close_level_cross_count": grid_cross,
                            "future_intrabar_level_touch_count": intrabar,
                            "future_unique_grid_levels_touched_count": unique_touched,
                            "future_internal_level_close_cross_count": int(icross[n]),
                            "future_internal_level_intrabar_touch_count": int(itouch[n]),
                            "fill_activity_lower_bound_proxy": grid_cross,
                            "fill_activity_upper_bound_proxy": intrabar,
                            "future_grid_level_cross_count": grid_cross,
                            "grid_crossings_per_hour": grid_cross / (horizon / 60),
                            "grid_step_pct_mean": step_pct,
                            "grid_step_bps_mean": step_pct * 100,
                            "grid_step_fee_multiple_proxy": None,
                            "grid_step_fee_multiple_proxy_deprecated_bool": True,
                            "label_stayed_in_range_until_horizon": first_exit_side == "none",
                            "label_sl_hit_before_horizon": fs != "none",
                            "label_good_chop_proxy": base["inside_range_ratio"] >= 0.70
                            and grid_cross >= min_cross,
                            "label_low_activity_proxy": grid_cross < min_cross,
                            "label_high_breakout_risk_proxy": fs != "none"
                            or base["inside_range_ratio"] < 0.40,
                        }
                    )
    return pl.DataFrame(rows)


def compute_symbol_outcomes_reference(*args, **kwargs):
    raise NotImplementedError("reference symbol path is intentionally not implemented in fast core")


def compute_event_outcomes(
    event: dict,
    klines: pl.DataFrame,
    mark_klines: pl.DataFrame,
    funding: pl.DataFrame,
    horizons: list[int],
    grid_counts: list[int],
    sl_atr_buffers: list[float],
    profile_name: str = "candidate_outcomes_v1",
    range_run_id: str = "",
    outcome_run_id: str = "",
) -> list[dict]:
    arrays = build_outcome_symbol_arrays(klines, mark_klines, funding)
    cfg = OutcomeCoreConfig(
        tuple(horizons),
        tuple(grid_counts),
        tuple(sl_atr_buffers),
        range_run_id,
        outcome_run_id,
        profile_name,
    )
    return compute_symbol_outcomes_fast(pl.DataFrame([event]), arrays, cfg).to_dicts()
