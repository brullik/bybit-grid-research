from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import math

import numpy as np
import polars as pl

from bybit_grid.research.range_actionable_events import add_range_quality_score
from bybit_grid.research.range_core.models import RangeInputArrays, empty_funnel
from bybit_grid.research.range_detector import DetectionConfig
from bybit_grid.research.range_features import ONE_MINUTE_MS, stable_candidate_id
from bybit_grid.research.range_profiles import RangeProfile


RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"


def _stable_sum(values: np.ndarray) -> float:
    return float(math.fsum(float(value) for value in values))


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(
        math.fsum((value - mean) ** 2 for value in values) / len(values)
    )


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    out = np.full(x.size, np.nan, dtype=np.float64)
    for end in range(window - 1, x.size):
        values = x[end - window + 1 : end + 1]
        if bool(np.all(np.isfinite(values))):
            out[end] = _stable_sum(values) / window
    return out


def _rolling_extreme(x: np.ndarray, window: int, *, want_max: bool) -> np.ndarray:
    out = np.full(x.size, np.nan, dtype=np.float64)
    q: deque[int] = deque()
    for i, value in enumerate(x):
        while q and q[0] <= i - window:
            q.popleft()
        if want_max:
            while q and x[q[-1]] <= value:
                q.pop()
        else:
            while q and x[q[-1]] >= value:
                q.pop()
        q.append(i)
        if i >= window - 1:
            out[i] = x[q[0]]
    return out


def _prefix_counts(mask: np.ndarray) -> np.ndarray:
    return np.insert(np.cumsum(mask.astype(np.int64)), 0, 0)


def _window_count(prefix: np.ndarray, start: int, end: int) -> int:
    return int(prefix[end + 1] - prefix[start])


def _step_count(prefix: np.ndarray, start: int, end: int) -> int:
    return int(prefix[end] - prefix[start])


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    out = np.full(high.size, np.nan, dtype=np.float64)
    for i in range(high.size):
        current_high = float(high[i])
        current_low = float(low[i])
        if (
            not math.isfinite(current_high)
            or not math.isfinite(current_low)
            or current_high <= 0.0
            or current_low <= 0.0
            or current_high < current_low
        ):
            continue
        previous_close = float(close[i - 1]) if i else math.nan
        high_low = current_high - current_low
        if not math.isfinite(previous_close) or previous_close <= 0.0:
            out[i] = high_low
            continue
        out[i] = max(
            high_low,
            abs(current_high - previous_close),
            abs(current_low - previous_close),
        )
    return out


def _resolve_config(
    lookbacks: tuple[int, ...],
    config: DetectionConfig | None,
) -> DetectionConfig:
    if config is None:
        return DetectionConfig(lookbacks=lookbacks)
    if config.lookbacks != lookbacks:
        raise ValueError("config.lookbacks must exactly match positional lookbacks")
    return config


def detect_ranges(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    config: DetectionConfig | None = None,
) -> tuple[pl.DataFrame, dict[str, int]]:
    cfg = _resolve_config(lookbacks, config)
    source = arrays.contiguous()
    order = np.argsort(source.open_time_ms, kind="mergesort")
    timestamps = np.asarray(source.open_time_ms)[order]
    opens = np.asarray(source.open, dtype=np.float64)[order]
    highs = np.asarray(source.high, dtype=np.float64)[order]
    lows = np.asarray(source.low, dtype=np.float64)[order]
    closes = np.asarray(source.close, dtype=np.float64)[order]
    raw_volume = np.asarray(source.volume, dtype=np.float64)[order]
    volume = np.where(
        np.isfinite(raw_volume) & (raw_volume > 0.0),
        raw_volume,
        0.0,
    )
    if source.turnover is None:
        turnover = np.zeros(closes.size, dtype=np.float64)
    else:
        raw_turnover = np.asarray(source.turnover, dtype=np.float64)[order]
        turnover = np.where(
            np.isfinite(raw_turnover) & (raw_turnover >= 0.0),
            raw_turnover,
            0.0,
        )

    size = int(timestamps.size)
    funnel = empty_funnel()
    if size == 0:
        return pl.DataFrame(), funnel

    true_range = _true_range(highs, lows, closes)
    atr14 = _rolling_mean(true_range, 14)
    atr60 = _rolling_mean(true_range, 60)
    bad_ohlc = (
        (~np.isfinite(opens))
        | (~np.isfinite(highs))
        | (~np.isfinite(lows))
        | (~np.isfinite(closes))
        | (highs < lows)
        | (np.minimum.reduce([opens, highs, lows, closes]) <= 0.0)
    )
    zero_volume = volume <= 0.0
    steps = np.diff(timestamps)
    duplicate_step_prefix = _prefix_counts(steps == 0)
    irregular_step_prefix = _prefix_counts(steps != ONE_MINUTE_MS)
    bad_prefix = _prefix_counts(bad_ohlc)
    zero_prefix = _prefix_counts(zero_volume)

    effective_zero_pct = min(
        float(cfg.max_zero_volume_window_pct),
        float(profile.max_zero_volume_window_pct),
    )
    effective_min_height_pct = max(
        float(cfg.min_range_height_pct),
        float(profile.range_height_pct_min),
    )
    middle_low = 0.5 - float(cfg.mid_zone_pct) / 2.0
    middle_high = 0.5 + float(cfg.mid_zone_pct) / 2.0
    rows: list[dict[str, object]] = []

    for lookback in lookbacks:
        funnel["total_window_positions"] += max(0, size - lookback + 1)
        if size < lookback:
            funnel["insufficient_history_rejection_count"] += lookback - size
            continue

        rolling_high = _rolling_extreme(highs, lookback, want_max=True)
        rolling_low = _rolling_extreme(lows, lookback, want_max=False)
        for end in range(lookback - 1, size):
            start = end - lookback + 1
            expected_span = (lookback - 1) * ONE_MINUTE_MS
            actual_span = int(timestamps[end]) - int(timestamps[start])
            if actual_span != expected_span:
                funnel["missing_window_rejection_count"] += 1
                continue
            if _step_count(duplicate_step_prefix, start, end):
                funnel["duplicate_timestamp_rejection_count"] += 1
                continue
            if _step_count(irregular_step_prefix, start, end):
                funnel["missing_window_rejection_count"] += 1
                continue

            bad_count = _window_count(bad_prefix, start, end)
            if bad_count:
                funnel["bad_ohlc_window_rejection_count"] += 1
                continue
            zero_count = _window_count(zero_prefix, start, end)
            if zero_count > int(lookback * effective_zero_pct):
                funnel["zero_volume_window_rejection_count"] += 1
                continue

            range_low = float(rolling_low[end])
            range_high = float(rolling_high[end])
            range_height = range_high - range_low
            current_close = float(closes[end])
            range_height_pct = range_height / current_close
            if (
                range_height <= 0.0
                or range_height_pct < effective_min_height_pct
                or range_height_pct > float(profile.range_height_pct_max)
            ):
                funnel["range_height_rejection_count"] += 1
                continue

            position = (current_close - range_low) / range_height
            if profile.require_current_middle_zone and not (
                middle_low <= position <= middle_high
            ):
                funnel["middle_zone_rejection_count"] += 1
                continue

            lower_edge = range_low + float(cfg.lower_zone_pct) * range_height
            upper_edge = range_high - float(cfg.upper_zone_pct) * range_height
            lows_window = lows[start : end + 1]
            highs_window = highs[start : end + 1]
            lower_mask = lows_window <= lower_edge
            upper_mask = highs_window >= upper_edge
            entered_lower = bool(np.any(lower_mask))
            entered_upper = bool(np.any(upper_mask))
            if profile.require_lower_upper_entries and not (
                entered_lower and entered_upper
            ):
                funnel["lower_upper_entry_rejection_count"] += 1
                continue

            closes_window = closes[start : end + 1]
            range_mid = range_low + 0.5 * range_height
            left_below = closes_window[:-1] < range_mid
            left_above = closes_window[:-1] > range_mid
            right_below = closes_window[1:] < range_mid
            right_above = closes_window[1:] > range_mid
            crosses = int(
                np.count_nonzero(
                    (left_below & right_above) | (left_above & right_below)
                )
            )
            if crosses < profile.min_midline_cross_count:
                funnel["midline_cross_rejection_count"] += 1
                continue

            lower_touches = int(np.count_nonzero(lower_mask))
            upper_touches = int(np.count_nonzero(upper_mask))
            if (
                lower_touches < profile.min_touches_lower_zone
                or upper_touches < profile.min_touches_upper_zone
            ):
                funnel["touch_count_rejection_count"] += 1
                continue

            first_close = float(closes_window[0])
            last_close = float(closes_window[-1])
            slope_pct = abs((last_close - first_close) / first_close)
            if slope_pct > profile.max_abs_slope_pct_per_window:
                funnel["slope_rejection_count"] += 1
                continue

            atr14_value = float(atr14[end])
            atr60_value = float(atr60[end])
            current_atr14 = atr14_value if math.isfinite(atr14_value) else None
            current_atr60 = atr60_value if math.isfinite(atr60_value) else None
            range_atr14 = (
                range_height / current_atr14 if current_atr14 else None
            )
            if range_atr14 is not None and not (
                profile.range_height_atr_min
                <= range_atr14
                <= profile.range_height_atr_max
            ):
                funnel["range_atr_rejection_count"] += 1
                continue
            if (
                range_atr14 is not None
                and range_atr14 < profile.min_path_length_over_range
            ):
                funnel["range_atr_rejection_count"] += 1
                continue

            last_lower = int(np.flatnonzero(lower_mask)[-1])
            last_upper = int(np.flatnonzero(upper_mask)[-1])
            log_returns = [
                math.log(float(closes_window[index]))
                - math.log(float(closes_window[index - 1]))
                for index in range(1, len(closes_window))
            ]
            mean_abs_return = _mean([abs(value) for value in log_returns])
            realized_volatility = _std(log_returns)
            range_atr60 = (
                range_height / current_atr60 if current_atr60 else None
            )
            rows.append(
                {
                    "candidate_id": stable_candidate_id(
                        f"{symbol}:{profile.name}",
                        int(timestamps[end]),
                        lookback,
                    ),
                    "profile_name": profile.name,
                    "symbol": symbol,
                    "signal_time_ms": int(timestamps[end]),
                    "signal_time_utc": datetime.fromtimestamp(
                        int(timestamps[end]) / 1000,
                        tz=timezone.utc,
                    ).isoformat(),
                    "lookback_minutes": lookback,
                    "range_low": range_low,
                    "range_high": range_high,
                    "range_mid": range_mid,
                    "range_height_abs": range_height,
                    "range_height_pct": range_height_pct,
                    "current_close": current_close,
                    "current_position_in_range": position,
                    "touches_lower_zone": lower_touches,
                    "touches_upper_zone": upper_touches,
                    "entered_lower_zone": entered_lower,
                    "entered_upper_zone": entered_upper,
                    "midline_crosses": crosses,
                    "time_since_last_lower_touch_minutes": (
                        lookback - 1 - last_lower
                    ),
                    "time_since_last_upper_touch_minutes": (
                        lookback - 1 - last_upper
                    ),
                    "atr_14": current_atr14,
                    "atr_60": current_atr60,
                    "atr_rel_14": (
                        current_atr14 / current_close if current_atr14 else None
                    ),
                    "atr_rel_60": (
                        current_atr60 / current_close if current_atr60 else None
                    ),
                    "range_height_atr_14": range_atr14,
                    "range_height_atr_60": range_atr60,
                    "amplitude_score": range_height_pct,
                    "mean_abs_return_inside_range": mean_abs_return,
                    "realized_volatility": realized_volatility,
                    "valid_candles_in_window": lookback,
                    "expected_candles_in_window": lookback,
                    "missing_candles_in_window": 0,
                    "zero_volume_candles_in_window": zero_count,
                    "bad_ohlc_in_window": bad_count,
                    "data_quality_ok": True,
                    "candidate_passed_baseline_filters": True,
                    "turnover_sum_window": _stable_sum(
                        turnover[start : end + 1]
                    ),
                    "volume_sum_window": _stable_sum(volume[start : end + 1]),
                    "symbol_rank_by_turnover": None,
                    "launch_age_days_at_signal": None,
                }
            )

    output = pl.DataFrame(rows)
    if not output.is_empty():
        output = add_range_quality_score(output)
        before_quality = output.height
        if profile.min_range_quality_score:
            output = output.filter(
                pl.col("range_quality_score") >= profile.min_range_quality_score
            )
        funnel["quality_score_rejection_count"] += int(
            before_quality - output.height
        )
    funnel["raw_candidate_pass_count"] += int(output.height)
    return output, funnel
