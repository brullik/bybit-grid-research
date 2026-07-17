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
    ACTIONABLE_EVENT_SEMANTICS_VERSION,
    GRID_GEOMETRY_SEMANTICS_VERSION,
    MINUTE_MS,
    NON_AUTHORITATIVE_OUTCOME_SEMANTICS_VERSION,
    OUTCOME_SEMANTICS_VERSION,
    OUTCOME_WINDOW_SEMANTICS_VERSION,
    _col,
    deterministic_outcome_id,
    outcome_match_key,
    validate_event_identity,
    validate_kline_schema,
    validate_outcome_parameters,
)
from bybit_grid.research.outcome_core.sl_proxy import compute_sl_proxy


OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)


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
    raw_time_ms: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int64))
    raw_bad_ohlc_prefix: np.ndarray = field(
        default_factory=lambda: np.array([0], dtype=np.int64)
    )
    raw_zero_volume_prefix: np.ndarray = field(
        default_factory=lambda: np.array([0], dtype=np.int64)
    )


def _event_profile(event: dict, outcome_profile_name: str) -> tuple[str, str | None]:
    value = event.get("profile_name")
    if value is None:
        if event.get("actionable_event_semantics_version") == ACTIONABLE_EVENT_SEMANTICS_VERSION:
            raise ValueError("versioned actionable event requires profile_name")
        return outcome_profile_name, None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event profile_name must be a nonblank string when present")
    return value, value


def _causal_times(event: dict) -> tuple[int, int, int, str, bool, str | None]:
    signal = event.get("signal_time_ms")
    has_decision = "decision_time_ms" in event and event["decision_time_ms"] is not None
    decision = event.get("decision_time_ms", signal)
    upstream_version = event.get("actionable_event_semantics_version")
    if type(signal) is not int or type(decision) is not int:
        raise ValueError("signal_time_ms and decision_time_ms must be exact integers")
    if signal < 0 or decision < 0:
        raise ValueError("signal_time_ms and decision_time_ms must be nonnegative")
    if decision != signal:
        raise ValueError("decision_time_ms must equal canonical signal_time_ms")
    if upstream_version is not None and upstream_version != ACTIONABLE_EVENT_SEMANTICS_VERSION:
        raise ValueError("actionable_event_semantics_version is unsupported")
    if upstream_version == ACTIONABLE_EVENT_SEMANTICS_VERSION and not has_decision:
        raise ValueError("versioned actionable event requires explicit decision_time_ms")
    entry = ((decision // MINUTE_MS) + 1) * MINUTE_MS
    source = "event_decision_time" if has_decision else "legacy_signal_fallback"
    complete = upstream_version == ACTIONABLE_EVENT_SEMANTICS_VERSION and has_decision
    return decision, signal, entry, source, complete, upstream_version


def _window_diagnostics(
    times: np.ndarray,
    bad_count: int,
    entry: int,
    horizon: int,
) -> dict[str, object]:
    integer_dtype = np.issubdtype(times.dtype, np.integer)
    valid_times = times if integer_dtype else np.array([], dtype=np.int64)
    invalid_timestamp_count = 0 if integer_dtype else int(times.size)
    offsets = valid_times - entry
    on_grid = (
        (offsets >= 0)
        & (offsets < horizon * MINUTE_MS)
        & (offsets % MINUTE_MS == 0)
    )
    observed_unique = int(np.unique(offsets[on_grid] // MINUTE_MS).size)
    on_grid_count = int(np.sum(on_grid))
    duplicate_count = on_grid_count - observed_unique
    off_grid_count = int(valid_times.size - on_grid_count)
    missing_count = max(0, horizon - observed_unique)
    reasons: list[str] = []
    if missing_count:
        reasons.append("missing_minutes")
    if off_grid_count:
        reasons.append("off_grid_rows")
    if duplicate_count:
        reasons.append("duplicate_timestamps")
    if invalid_timestamp_count:
        reasons.append("invalid_timestamps")
    if bad_count:
        reasons.append("invalid_ohlc")
    complete = not reasons and times.size == horizon
    return {
        "future_expected_minutes_count": horizon,
        "future_observed_expected_minutes_count": observed_unique,
        "future_coverage_minutes": observed_unique,
        "future_missing_minutes_count": missing_count,
        "future_off_grid_rows_count": off_grid_count,
        "future_duplicate_timestamp_count": duplicate_count,
        "future_invalid_timestamp_rows_count": invalid_timestamp_count,
        "future_bad_ohlc_count": bad_count,
        "future_data_complete_bool": complete,
        "future_outcome_eligible_bool": complete,
        "future_outcome_ineligible_reason": "|".join(reasons) if reasons else None,
    }


def _time_col(df: pl.DataFrame) -> str:
    return "open_time_ms" if "open_time_ms" in df.columns else "start_time_ms"


def _bad_ohlc_mask(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> np.ndarray:
    if not highs.size:
        return np.array([], dtype=np.int64)
    return (
        (~np.isfinite(opens))
        | (~np.isfinite(highs))
        | (~np.isfinite(lows))
        | (~np.isfinite(closes))
        | (opens <= 0)
        | (highs <= 0)
        | (lows <= 0)
        | (closes <= 0)
        | (highs < lows)
        | (highs < np.maximum(opens, closes))
        | (lows > np.minimum(opens, closes))
    ).astype(np.int64)


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
    tc = _time_col(klines)
    validate_kline_schema(klines, tc)
    raw_kl = klines.sort(tc) if not klines.is_empty() and tc in klines.columns else klines
    raw_times = (
        raw_kl[tc].to_numpy()
        if tc in raw_kl.columns
        else np.array([], dtype=np.int64)
    )
    raw_opens = (
        raw_kl["open"].cast(pl.Float64).to_numpy()
        if "open" in raw_kl.columns
        else np.array([], dtype=float)
    )
    raw_highs = (
        raw_kl["high"].cast(pl.Float64).to_numpy()
        if "high" in raw_kl.columns
        else np.array([], dtype=float)
    )
    raw_lows = (
        raw_kl["low"].cast(pl.Float64).to_numpy()
        if "low" in raw_kl.columns
        else np.array([], dtype=float)
    )
    raw_closes = (
        raw_kl["close"].cast(pl.Float64).to_numpy()
        if "close" in raw_kl.columns
        else np.array([], dtype=float)
    )
    raw_volumes = (
        raw_kl["volume"].cast(pl.Float64).to_numpy()
        if "volume" in raw_kl.columns
        else np.array([], dtype=float)
    )
    raw_bad = _bad_ohlc_mask(raw_opens, raw_highs, raw_lows, raw_closes)
    raw_zero = (
        (raw_volumes <= 0).astype(np.int64)
        if raw_volumes.size
        else np.array([], dtype=np.int64)
    )
    kl, kd = _sorted_unique(klines, tc)
    times = kl[tc].to_numpy() if tc in kl.columns else np.array([], dtype=np.int64)
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
    bad = _bad_ohlc_mask(opens, highs, lows, closes)
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
        time_ms=np.ascontiguousarray(times),
        open=np.ascontiguousarray(opens),
        high=np.ascontiguousarray(highs),
        low=np.ascontiguousarray(lows),
        close=np.ascontiguousarray(closes),
        volume=np.ascontiguousarray(vols),
        mark_time_ms=np.ascontiguousarray(mk[mt].to_numpy().astype(np.int64))
        if mt in mk.columns
        else np.array([], dtype=np.int64),
        mark_close=np.ascontiguousarray(mk["close"].cast(pl.Float64).to_numpy())
        if "close" in mk.columns
        else np.array([], dtype=float),
        funding_time_ms=np.ascontiguousarray(fu[ft_col].to_numpy().astype(np.int64))
        if ft_col and ft_col in fu.columns
        else np.array([], dtype=np.int64),
        funding_rate=np.ascontiguousarray(rates),
        bad_ohlc_prefix=np.r_[0, np.cumsum(bad)],
        zero_volume_prefix=np.r_[0, np.cumsum(zero)],
        funding_rate_prefix=np.r_[0.0, np.cumsum(rates)],
        funding_abs_rate_prefix=np.r_[0.0, np.cumsum(np.abs(rates))],
        diagnostics={"klines_" + k: v for k, v in kd.items()}
        | {"mark_" + k: v for k, v in md.items()}
        | {"funding_" + k: v for k, v in fd.items()},
        raw_time_ms=np.ascontiguousarray(raw_times),
        raw_bad_ohlc_prefix=np.r_[0, np.cumsum(raw_bad)],
        raw_zero_volume_prefix=np.r_[0, np.cumsum(raw_zero)],
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
    validate_outcome_parameters(
        config.horizons_minutes,
        config.grid_cell_numbers,
        config.sl_atr_buffers,
        config.profile_name,
    )
    rows: list[dict] = []
    horizons = sorted(config.horizons_minutes)
    for event in events.to_dicts():
        validate_event_identity(event)
        decision, signal, entry, decision_source, causal_complete, upstream_version = (
            _causal_times(event)
        )
        output_profile_name, range_profile_name = _event_profile(
            event, config.profile_name
        )
        row_semantics_version = (
            OUTCOME_SEMANTICS_VERSION
            if causal_complete and range_profile_name is not None
            else NON_AUTHORITATIVE_OUTCOME_SEMANTICS_VERSION
        )
        end_max = entry + max(horizons) * MINUTE_MS
        start = int(np.searchsorted(arrays.time_ms, entry, side="left"))
        stop = int(np.searchsorted(arrays.time_ms, end_max, side="left"))
        raw_start = int(np.searchsorted(arrays.raw_time_ms, entry, side="left"))
        raw_stop = int(np.searchsorted(arrays.raw_time_ms, end_max, side="left"))
        slc = slice(start, stop)
        raw_times = arrays.raw_time_ms[raw_start:raw_stop]
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
            raw_n = int(np.searchsorted(raw_times, end, side="left"))
            ht = times[:n]
            raw_ht = raw_times[:raw_n]
            hh = highs[:n]
            hl = lows[:n]
            hc = closes[:n]
            up = np.where(hh > range_high)[0] if n else np.array([], dtype=int)
            dn = np.where(hl < range_low)[0] if n else np.array([], dtype=int)
            first_exit_side, first_exit_time, first_exit_amb = _first(
                np.array([up, dn], dtype=object), ht, "up", "down"
            )
            bad_count = int(
                arrays.raw_bad_ohlc_prefix[raw_start + raw_n]
                - arrays.raw_bad_ohlc_prefix[raw_start]
            )
            diagnostics = _window_diagnostics(
                raw_ht,
                bad_count,
                entry,
                horizon,
            )
            complete = bool(diagnostics["future_data_complete_bool"])
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
                "future_rows_available": raw_n,
                **diagnostics,
                "future_zero_volume_count": int(
                    arrays.raw_zero_volume_prefix[raw_start + raw_n]
                    - arrays.raw_zero_volume_prefix[raw_start]
                ),
                "first_exit_side": first_exit_side if complete else None,
                "first_exit_ambiguous_bool": first_exit_amb if complete else None,
                "first_exit_time_ms": first_exit_time if complete else None,
                "minutes_to_first_exit": None
                if not complete or first_exit_time is None
                else int((first_exit_time - entry) // MINUTE_MS),
                "time_inside_range_minutes": int(inside_cum[n]) if complete else None,
                "inside_range_candle_count": int(inside_cum[n]) if complete else None,
                "inside_range_ratio": (
                    int(inside_cum[n]) / horizon if complete and horizon else None
                ),
                "max_high_above_range_pct": float(
                    max(0, (np.max(hh) - range_high) / range_high * 100)
                )
                if complete and n and range_high
                else None,
                "max_low_below_range_pct": float(max(0, (range_low - np.min(hl)) / range_low * 100))
                if complete and n and range_low
                else None,
                "max_close_distance_from_mid_pct": float(
                    np.max(np.abs(hc - range_mid)) / range_mid * 100
                )
                if complete and n and range_mid
                else None,
                "future_midline_cross_count": int(mid_cum[n]) if complete else None,
                "future_upper_zone_touch_count": int(upper_touch_cum[n]) if complete else None,
                "future_lower_zone_touch_count": int(lower_touch_cum[n]) if complete else None,
                **fund,
                "mark_price_future_rows_available": int(mc.size),
                "mark_price_max_deviation_from_last_pct": mark_dev if complete else None,
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
                                eid, horizon, int(gc), float(sl_buf), row_semantics_version
                            ),
                            "outcome_match_key": outcome_match_key(
                                eid, horizon, int(gc), float(sl_buf)
                            ),
                            "range_action_event_id": eid,
                            "range_regime_id": str(_col(event, "range_regime_id", "")),
                            "symbol": sym,
                            "profile_name": output_profile_name,
                            "range_profile_name": range_profile_name,
                            "outcome_profile_name": config.profile_name,
                            "outcome_semantics_version": row_semantics_version,
                            "outcome_window_semantics_version": OUTCOME_WINDOW_SEMANTICS_VERSION,
                            "range_run_id": config.range_run_id,
                            "outcome_run_id": config.outcome_run_id,
                            "actionable_event_semantics_version": upstream_version,
                            "decision_time_source": decision_source,
                            "causal_provenance_complete_bool": causal_complete,
                            "decision_time_ms": decision,
                            "signal_time_ms": signal,
                            "entry_time_ms": entry,
                            "outcome_end_exclusive_ms": end,
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
                            "first_sl_side": fs if complete else None,
                            "first_sl_ambiguous_bool": fa if complete else None,
                            "first_sl_time_ms": ft if complete else None,
                            "minutes_to_first_sl": None
                            if not complete or ft is None
                            else int((ft - entry) // MINUTE_MS),
                            "sl_hit_bool": (fs != "none") if complete else None,
                            "geometric_grid_levels_json": levels_json(levels),
                            "grid_levels_serialization_version": GRID_LEVELS_SERIALIZATION_VERSION,
                            "future_close_level_cross_count": grid_cross if complete else None,
                            "future_intrabar_level_touch_count": intrabar if complete else None,
                            "future_unique_grid_levels_touched_count": unique_touched if complete else None,
                            "future_internal_level_close_cross_count": int(icross[n]) if complete else None,
                            "future_internal_level_intrabar_touch_count": int(itouch[n]) if complete else None,
                            "fill_activity_lower_bound_proxy": grid_cross if complete else None,
                            "fill_activity_upper_bound_proxy": intrabar if complete else None,
                            "future_grid_level_cross_count": grid_cross if complete else None,
                            "grid_crossings_per_hour": grid_cross / (horizon / 60) if complete else None,
                            "grid_step_pct_mean": step_pct,
                            "grid_step_bps_mean": step_pct * 100,
                            "grid_step_fee_multiple_proxy": None,
                            "grid_step_fee_multiple_proxy_deprecated_bool": True,
                            "label_stayed_in_range_until_horizon": (first_exit_side == "none") if complete else None,
                            "label_sl_hit_before_horizon": (fs != "none") if complete else None,
                            "label_good_chop_proxy": (base["inside_range_ratio"] >= 0.70 and grid_cross >= min_cross) if complete else None,
                            "label_low_activity_proxy": (grid_cross < min_cross) if complete else None,
                            "label_high_breakout_risk_proxy": (fs != "none" or base["inside_range_ratio"] < 0.40) if complete else None,
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
