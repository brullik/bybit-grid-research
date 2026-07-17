from __future__ import annotations

import hashlib
import math

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.funding_join import aggregate_funding
from bybit_grid.research.outcome_core.grid_crossings import (
    count_intrabar_level_touches,
    count_level_crossings,
    count_midline_crossings,
    count_unique_intrabar_levels_touched,
    geometric_grid_levels,
    levels_json,
    GRID_LEVELS_SERIALIZATION_VERSION,
)
from bybit_grid.research.outcome_core.sl_proxy import compute_sl_proxy

MINUTE_MS = 60_000


OUTCOME_SEMANTICS_VERSION = "v5_exact_outcome_window_provenance"
NON_AUTHORITATIVE_OUTCOME_SEMANTICS_VERSION = "v4_native_grid_geometry"
GRID_GEOMETRY_SEMANTICS_VERSION = "v1_n_cells_n_plus_1_levels"
OUTCOME_WINDOW_SEMANTICS_VERSION = "exact-minute-outcome-window-v1"
ACTIONABLE_EVENT_SEMANTICS_VERSION = "range-actionable-prefix-invariance-v1"
OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
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
    bad_ohlc: np.ndarray,
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
    observed_offsets = offsets[on_grid] // MINUTE_MS
    observed_unique = int(np.unique(observed_offsets).size)
    on_grid_count = int(np.sum(on_grid))
    duplicate_count = on_grid_count - observed_unique
    off_grid_count = int(valid_times.size - on_grid_count)
    missing_count = max(0, horizon - observed_unique)
    bad_count = int(np.sum(bad_ohlc))
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


def outcome_match_key(event_id: str, horizon: int, grid_cell_number: int, sl_atr_buffer: float) -> str:
    key = f"{event_id}|{horizon}|{grid_cell_number}|{sl_atr_buffer:g}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def deterministic_outcome_id(
    event_id: str,
    horizon: int,
    grid_cell_number: int,
    sl_atr_buffer: float,
    semantics_version: str = OUTCOME_SEMANTICS_VERSION,
    window_semantics_version: str = OUTCOME_WINDOW_SEMANTICS_VERSION,
) -> str:
    key = (
        f"{semantics_version}|{window_semantics_version}|{event_id}|"
        f"{horizon}|{grid_cell_number}|{sl_atr_buffer:g}"
    )
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _col(row: dict, name: str, default=0):
    return row[name] if name in row and row[name] is not None else default


def validate_outcome_parameters(
    horizons: list[int] | tuple[int, ...],
    grid_counts: list[int] | tuple[int, ...],
    sl_atr_buffers: list[float] | tuple[float, ...],
    profile_name: str,
) -> None:
    if not horizons or any(type(value) is not int or value <= 0 for value in horizons):
        raise ValueError("outcome horizons must be nonempty exact positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("outcome horizons must be unique")
    if not grid_counts or any(type(value) is not int or value < 2 for value in grid_counts):
        raise ValueError("grid cell numbers must be nonempty exact integers >= 2")
    if len(set(grid_counts)) != len(grid_counts):
        raise ValueError("grid cell numbers must be unique")
    if not sl_atr_buffers or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
        for value in sl_atr_buffers
    ):
        raise ValueError("SL ATR buffers must be nonempty finite nonnegative numbers")
    if len({float(value) for value in sl_atr_buffers}) != len(sl_atr_buffers):
        raise ValueError("SL ATR buffers must be unique")
    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ValueError("outcome profile_name must be a nonblank string")


def validate_event_identity(event: dict) -> None:
    event_id = event.get("range_action_event_id", event.get("range_event_id"))
    symbol = event.get("symbol")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("range action event id must be a nonblank string")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("event symbol must be a nonblank string")


def validate_kline_schema(klines: pl.DataFrame, time_col: str) -> None:
    if klines.is_empty() and not klines.columns:
        return
    missing = {time_col, "open", "high", "low", "close"} - set(klines.columns)
    if missing:
        raise ValueError("kline timestamp/OHLC columns are missing: " + ",".join(sorted(missing)))
    if klines[time_col].null_count():
        raise ValueError("kline timestamps must be non-null")


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
    validate_outcome_parameters(horizons, grid_counts, sl_atr_buffers, profile_name)
    validate_event_identity(event)
    decision, signal, entry, decision_source, causal_complete, upstream_version = (
        _causal_times(event)
    )
    output_profile_name, range_profile_name = _event_profile(event, profile_name)
    row_semantics_version = (
        OUTCOME_SEMANTICS_VERSION
        if causal_complete and range_profile_name is not None
        else NON_AUTHORITATIVE_OUTCOME_SEMANTICS_VERSION
    )
    symbol = str(_col(event, "symbol", ""))
    time_col = "open_time_ms" if "open_time_ms" in klines.columns else "start_time_ms"
    validate_kline_schema(klines, time_col)
    rows: list[dict] = []
    for horizon in horizons:
        end = entry + horizon * MINUTE_MS
        fut = (
            pl.DataFrame()
            if klines.is_empty() and not klines.columns
            else klines.filter(
                (pl.col(time_col) >= entry) & (pl.col(time_col) < end)
            ).sort(time_col)
        )
        times = fut[time_col].to_numpy() if not fut.is_empty() else np.array([], dtype=np.int64)
        opens = fut["open"].cast(pl.Float64).to_numpy() if "open" in fut.columns else np.array([])
        highs = fut["high"].cast(pl.Float64).to_numpy() if "high" in fut.columns else np.array([])
        lows = fut["low"].cast(pl.Float64).to_numpy() if "low" in fut.columns else np.array([])
        closes = fut["close"].cast(pl.Float64).to_numpy() if "close" in fut.columns else np.array([])
        vols = fut["volume"].cast(pl.Float64).to_numpy() if "volume" in fut.columns else np.array([])
        range_low = float(_col(event, "range_low"))
        range_high = float(_col(event, "range_high"))
        range_mid = float(_col(event, "range_mid", (range_low + range_high) / 2))
        bad_mask = (
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
        ) if highs.size else np.array([], dtype=bool)
        diagnostics = _window_diagnostics(times, bad_mask, entry, horizon)
        complete = bool(diagnostics["future_data_complete_bool"])
        zero_vol = int(np.sum(vols <= 0)) if vols.size else 0
        up_idx = np.where(highs > range_high)[0] if highs.size else np.array([], dtype=int)
        dn_idx = np.where(lows < range_low)[0] if lows.size else np.array([], dtype=int)
        first_exit_side = "none"
        first_exit_time = None
        first_exit_ambiguous = False
        if up_idx.size or dn_idx.size:
            u = int(up_idx[0]) if up_idx.size else math.inf
            d = int(dn_idx[0]) if dn_idx.size else math.inf
            if u == d:
                first_exit_side, first_exit_time, first_exit_ambiguous = "ambiguous_both", int(times[u]), True
            elif u < d:
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
            grid_cell_number = int(grid_count)
            levels = geometric_grid_levels(range_low, range_high, grid_cell_number)
            internal_levels = levels[1:-1]
            grid_cross = count_level_crossings(closes, levels)
            intrabar_touches = count_intrabar_level_touches(lows, highs, levels)
            unique_touched = count_unique_intrabar_levels_touched(lows, highs, levels)
            internal_grid_cross = count_level_crossings(closes, internal_levels)
            internal_intrabar_touches = count_intrabar_level_touches(lows, highs, internal_levels)
            mid_cross = count_midline_crossings(closes, range_mid)
            interval_ratio = (range_high / range_low) ** (1.0 / grid_cell_number)
            step_pct = float((interval_ratio - 1.0) * 100.0)
            for sl_buf in sl_atr_buffers:
                sl = compute_sl_proxy(event, range_low, range_high, float(sl_buf))
                lower_sl = sl.lower_sl_price if sl.lower_sl_price is not None else -math.inf
                upper_sl = sl.upper_sl_price if sl.upper_sl_price is not None else math.inf
                upper_idx = np.where(highs >= upper_sl)[0] if highs.size and sl.sl_proxy_valid_bool else np.array([], dtype=int)
                lower_idx = np.where(lows <= lower_sl)[0] if lows.size and sl.sl_proxy_valid_bool else np.array([], dtype=int)
                first_sl_side = "none"
                first_sl_time = None
                first_sl_ambiguous = False
                if upper_idx.size or lower_idx.size:
                    u = int(upper_idx[0]) if upper_idx.size else math.inf
                    d = int(lower_idx[0]) if lower_idx.size else math.inf
                    if u == d:
                        first_sl_side, first_sl_time, first_sl_ambiguous = "ambiguous_both", int(times[u]), True
                    elif u < d:
                        first_sl_side, first_sl_time = "upper", int(times[u])
                    else:
                        first_sl_side, first_sl_time = "lower", int(times[d])
                min_cross = max(1, horizon // 240)
                rows.append({
                    "outcome_id": deterministic_outcome_id(str(_col(event,"range_action_event_id", _col(event,"range_event_id",""))), horizon, grid_cell_number, float(sl_buf), row_semantics_version),
                    "outcome_match_key": outcome_match_key(str(_col(event,"range_action_event_id", _col(event,"range_event_id",""))), horizon, grid_cell_number, float(sl_buf)),
                    "range_action_event_id": str(_col(event,"range_action_event_id", _col(event,"range_event_id",""))), "range_regime_id": str(_col(event,"range_regime_id", "")), "symbol": symbol, "profile_name": output_profile_name, "range_profile_name": range_profile_name, "outcome_profile_name": profile_name, "outcome_semantics_version": row_semantics_version, "outcome_window_semantics_version": OUTCOME_WINDOW_SEMANTICS_VERSION, "range_run_id": range_run_id, "outcome_run_id": outcome_run_id,
                    "actionable_event_semantics_version": upstream_version, "decision_time_source": decision_source, "causal_provenance_complete_bool": causal_complete, "decision_time_ms": decision, "signal_time_ms": signal, "entry_time_ms": entry, "outcome_end_exclusive_ms": end, "future_horizon_minutes": horizon, "grid_count": grid_cell_number, "grid_cell_number": grid_cell_number, "grid_price_level_count": grid_cell_number + 1, "grid_interval_count": grid_cell_number, "grid_interval_ratio": interval_ratio, "grid_interval_pct": step_pct, "grid_interval_bps": step_pct * 100, "grid_count_semantics": "native_bybit_cell_number", "grid_geometry_semantics_version": GRID_GEOMETRY_SEMANTICS_VERSION, "sl_atr_buffer": float(sl_buf),
                    **{k: _col(event,k,None) for k in ["best_lookback_minutes","lookbacks_observed","range_low","range_high","range_mid","range_height_pct","range_height_atr_14","range_quality_score","path_length_over_range","midline_crosses","min_touches_lower_zone","min_touches_upper_zone","fgrid_investment_min","min_investment_feasible_at_5usdt"]},
                    "future_rows_available": int(len(times)), **diagnostics, "future_zero_volume_count": zero_vol,
                    "first_exit_side": first_exit_side if complete else None, "first_exit_ambiguous_bool": first_exit_ambiguous if complete else None, "first_exit_time_ms": first_exit_time if complete else None, "minutes_to_first_exit": None if not complete or first_exit_time is None else int((first_exit_time-entry)//MINUTE_MS), "time_inside_range_minutes": inside if complete else None, "inside_range_candle_count": inside if complete else None, "inside_range_ratio": inside_ratio if complete else None,
                    "max_high_above_range_pct": float(max(0, (np.max(highs)-range_high)/range_high*100)) if complete and highs.size and range_high else None, "max_low_below_range_pct": float(max(0, (range_low-np.min(lows))/range_low*100)) if complete and lows.size and range_low else None, "max_close_distance_from_mid_pct": float(np.max(np.abs(closes-range_mid))/range_mid*100) if complete and closes.size and range_mid else None,
                    **sl.as_dict(), "first_sl_side": first_sl_side if complete else None, "first_sl_ambiguous_bool": first_sl_ambiguous if complete else None, "first_sl_time_ms": first_sl_time if complete else None, "minutes_to_first_sl": None if not complete or first_sl_time is None else int((first_sl_time-entry)//MINUTE_MS), "sl_hit_bool": (first_sl_side != "none") if complete else None,
                    "geometric_grid_levels_json": levels_json(levels), "grid_levels_serialization_version": GRID_LEVELS_SERIALIZATION_VERSION, "future_close_level_cross_count": grid_cross if complete else None, "future_intrabar_level_touch_count": intrabar_touches if complete else None, "future_unique_grid_levels_touched_count": unique_touched if complete else None, "future_internal_level_close_cross_count": internal_grid_cross if complete else None, "future_internal_level_intrabar_touch_count": internal_intrabar_touches if complete else None, "fill_activity_lower_bound_proxy": grid_cross if complete else None, "fill_activity_upper_bound_proxy": intrabar_touches if complete else None, "future_grid_level_cross_count": grid_cross if complete else None, "future_midline_cross_count": mid_cross if complete else None, "future_upper_zone_touch_count": int(np.sum(highs >= range_high)) if complete and highs.size else None, "future_lower_zone_touch_count": int(np.sum(lows <= range_low)) if complete and lows.size else None, "grid_crossings_per_hour": grid_cross / (horizon / 60) if complete else None, "grid_step_pct_mean": step_pct, "grid_step_bps_mean": step_pct * 100, "grid_step_fee_multiple_proxy": None, "grid_step_fee_multiple_proxy_deprecated_bool": True,
                    **fund, "mark_price_future_rows_available": mark_rows.height, "mark_price_max_deviation_from_last_pct": mark_dev if complete else None,
                    "label_stayed_in_range_until_horizon": (first_exit_side == "none") if complete else None, "label_sl_hit_before_horizon": (first_sl_side != "none") if complete else None, "label_good_chop_proxy": (inside_ratio >= 0.70 and grid_cross >= min_cross) if complete else None, "label_low_activity_proxy": (grid_cross < min_cross) if complete else None, "label_high_breakout_risk_proxy": (first_sl_side != "none" or inside_ratio < 0.40) if complete else None,
                })
    return rows
