from __future__ import annotations

from datetime import datetime, timezone
import math

import polars as pl

from bybit_grid.research.range_actionable_events import add_range_quality_score
from bybit_grid.research.range_core.models import empty_funnel
from bybit_grid.research.range_detector import DetectionConfig, _col, _mean, _rolling_mean, _std
from bybit_grid.research.range_features import ONE_MINUTE_MS, stable_candidate_id
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile


RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"


def _float_or_nan(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return math.nan


def _normalized_volume(value: object) -> float:
    converted = _float_or_nan(value)
    return converted if math.isfinite(converted) and converted > 0.0 else 0.0


def _normalized_turnover(value: object) -> float:
    converted = _float_or_nan(value)
    return converted if math.isfinite(converted) and converted >= 0.0 else 0.0


def _selected_profile(
    config: DetectionConfig,
    profile: RangeProfile | None,
) -> RangeProfile:
    if profile is not None:
        return profile
    try:
        return RANGE_PROFILES[config.profile_name]
    except KeyError:
        raise ValueError(
            "profile_name must name a registered profile when no explicit profile is supplied"
        ) from None


def _true_ranges(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> list[float]:
    ranges: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        envelope_is_valid = (
            math.isfinite(high)
            and math.isfinite(low)
            and high > 0.0
            and low > 0.0
            and high >= low
        )
        if not envelope_is_valid:
            ranges.append(math.nan)
            continue

        previous_close = closes[index - 1] if index else math.nan
        if not math.isfinite(previous_close) or previous_close <= 0.0:
            ranges.append(high - low)
            continue
        ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
    return ranges


def _detect_reference(
    df: pl.DataFrame,
    symbol: str,
    config: DetectionConfig | None,
    profile: RangeProfile | None,
) -> tuple[pl.DataFrame, dict[str, int]]:
    cfg = DetectionConfig() if config is None else config
    selected_profile = _selected_profile(cfg, profile)
    funnel = empty_funnel()
    if df.is_empty():
        return pl.DataFrame(), funnel

    timestamp_column = _col(df, "open_time_ms", "start_time_ms", "timestamp_ms")
    open_column = _col(df, "open", "open_price")
    high_column = _col(df, "high", "high_price")
    low_column = _col(df, "low", "low_price")
    close_column = _col(df, "close", "close_price")
    volume_column = "volume" if "volume" in df.columns else None
    turnover_column = (
        "turnover"
        if "turnover" in df.columns
        else ("turnover_usdt" if "turnover_usdt" in df.columns else None)
    )

    records = df.sort(timestamp_column, maintain_order=True).to_dicts()
    timestamps = [int(record[timestamp_column]) for record in records]
    opens = [_float_or_nan(record[open_column]) for record in records]
    highs = [_float_or_nan(record[high_column]) for record in records]
    lows = [_float_or_nan(record[low_column]) for record in records]
    closes = [_float_or_nan(record[close_column]) for record in records]
    volumes = (
        [_normalized_volume(record.get(volume_column)) for record in records]
        if volume_column is not None
        else [1.0] * len(records)
    )
    turnovers = (
        [_normalized_turnover(record.get(turnover_column)) for record in records]
        if turnover_column is not None
        else [0.0] * len(records)
    )

    count = len(timestamps)
    true_ranges = _true_ranges(highs, lows, closes)
    atr14 = _rolling_mean(true_ranges, 14)
    atr60 = _rolling_mean(true_ranges, 60)
    bad_ohlc = [
        not all(
            math.isfinite(value)
            for value in (opens[index], highs[index], lows[index], closes[index])
        )
        or highs[index] < lows[index]
        or min(opens[index], highs[index], lows[index], closes[index]) <= 0.0
        for index in range(count)
    ]
    zero_volume = [volume == 0.0 for volume in volumes]
    effective_zero_volume_pct = min(
        float(cfg.max_zero_volume_window_pct),
        float(selected_profile.max_zero_volume_window_pct),
    )
    effective_minimum_height_pct = max(
        float(cfg.min_range_height_pct),
        float(selected_profile.range_height_pct_min),
    )
    middle_low = 0.5 - cfg.mid_zone_pct / 2.0
    middle_high = 0.5 + cfg.mid_zone_pct / 2.0
    rows: list[dict[str, object]] = []

    for lookback in cfg.lookbacks:
        funnel["total_window_positions"] += max(0, count - lookback + 1)
        if count < lookback:
            funnel["insufficient_history_rejection_count"] += lookback - count
            continue

        for end in range(lookback - 1, count):
            start = end - lookback + 1
            window_timestamps = timestamps[start : end + 1]
            if timestamps[end] - timestamps[start] != (lookback - 1) * ONE_MINUTE_MS:
                funnel["missing_window_rejection_count"] += 1
                continue
            if len(set(window_timestamps)) != lookback:
                funnel["duplicate_timestamp_rejection_count"] += 1
                continue
            if any(
                current - previous != ONE_MINUTE_MS
                for previous, current in zip(
                    window_timestamps,
                    window_timestamps[1:],
                )
            ):
                funnel["missing_window_rejection_count"] += 1
                continue

            bad_count = sum(bad_ohlc[start : end + 1])
            if bad_count:
                funnel["bad_ohlc_window_rejection_count"] += 1
                continue
            zero_count = sum(zero_volume[start : end + 1])
            if zero_count > int(lookback * effective_zero_volume_pct):
                funnel["zero_volume_window_rejection_count"] += 1
                continue

            low = min(lows[start : end + 1])
            high = max(highs[start : end + 1])
            height = high - low
            height_pct = height / closes[end]
            if (
                height <= 0.0
                or height_pct < effective_minimum_height_pct
                or height_pct > selected_profile.range_height_pct_max
            ):
                funnel["range_height_rejection_count"] += 1
                continue

            current_position = (closes[end] - low) / height
            if selected_profile.require_current_middle_zone and not (
                middle_low <= current_position <= middle_high
            ):
                funnel["middle_zone_rejection_count"] += 1
                continue

            lower_edge = low + cfg.lower_zone_pct * height
            upper_edge = high - cfg.upper_zone_pct * height
            lower_mask = [value <= lower_edge for value in lows[start : end + 1]]
            upper_mask = [value >= upper_edge for value in highs[start : end + 1]]
            if selected_profile.require_lower_upper_entries and not (
                any(lower_mask) and any(upper_mask)
            ):
                funnel["lower_upper_entry_rejection_count"] += 1
                continue

            middle = low + 0.5 * height
            window_closes = closes[start : end + 1]
            crossings = sum(
                1
                for left, right in zip(window_closes, window_closes[1:])
                if (left < middle and right > middle)
                or (left > middle and right < middle)
            )
            if crossings < selected_profile.min_midline_cross_count:
                funnel["midline_cross_rejection_count"] += 1
                continue

            lower_touches = sum(lower_mask)
            upper_touches = sum(upper_mask)
            if (
                lower_touches < selected_profile.min_touches_lower_zone
                or upper_touches < selected_profile.min_touches_upper_zone
            ):
                funnel["touch_count_rejection_count"] += 1
                continue

            slope_pct = abs(
                (window_closes[-1] - window_closes[0]) / window_closes[0]
            )
            if slope_pct > selected_profile.max_abs_slope_pct_per_window:
                funnel["slope_rejection_count"] += 1
                continue

            current_atr14 = atr14[end]
            current_atr60 = atr60[end]
            range_atr14 = (
                height / current_atr14
                if current_atr14 is not None and current_atr14 > 0.0
                else None
            )
            if range_atr14 is not None and not (
                selected_profile.range_height_atr_min
                <= range_atr14
                <= selected_profile.range_height_atr_max
            ):
                funnel["range_atr_rejection_count"] += 1
                continue
            if (
                range_atr14 is not None
                and range_atr14 < selected_profile.min_path_length_over_range
            ):
                funnel["range_atr_rejection_count"] += 1
                continue

            last_lower = max(index for index, touched in enumerate(lower_mask) if touched)
            last_upper = max(index for index, touched in enumerate(upper_mask) if touched)
            returns = [
                math.log(window_closes[index]) - math.log(window_closes[index - 1])
                for index in range(1, len(window_closes))
                if window_closes[index] > 0.0 and window_closes[index - 1] > 0.0
            ]
            range_atr60 = (
                height / current_atr60
                if current_atr60 is not None and current_atr60 > 0.0
                else None
            )
            rows.append(
                {
                    "candidate_id": stable_candidate_id(
                        f"{symbol}:{selected_profile.name}",
                        int(timestamps[end]),
                        lookback,
                    ),
                    "profile_name": selected_profile.name,
                    "symbol": symbol,
                    "signal_time_ms": int(timestamps[end]),
                    "signal_time_utc": datetime.fromtimestamp(
                        int(timestamps[end]) / 1000,
                        tz=timezone.utc,
                    ).isoformat(),
                    "lookback_minutes": lookback,
                    "range_low": low,
                    "range_high": high,
                    "range_mid": middle,
                    "range_height_abs": height,
                    "range_height_pct": height_pct,
                    "current_close": closes[end],
                    "current_position_in_range": current_position,
                    "touches_lower_zone": lower_touches,
                    "touches_upper_zone": upper_touches,
                    "entered_lower_zone": True,
                    "entered_upper_zone": True,
                    "midline_crosses": crossings,
                    "time_since_last_lower_touch_minutes": lookback - 1 - last_lower,
                    "time_since_last_upper_touch_minutes": lookback - 1 - last_upper,
                    "atr_14": current_atr14,
                    "atr_60": current_atr60,
                    "atr_rel_14": (
                        current_atr14 / closes[end]
                        if current_atr14 is not None and current_atr14 > 0.0
                        else None
                    ),
                    "atr_rel_60": (
                        current_atr60 / closes[end]
                        if current_atr60 is not None and current_atr60 > 0.0
                        else None
                    ),
                    "range_height_atr_14": range_atr14,
                    "range_height_atr_60": range_atr60,
                    "amplitude_score": height_pct,
                    "mean_abs_return_inside_range": _mean(
                        [abs(value) for value in returns]
                    ),
                    "realized_volatility": _std(returns),
                    "valid_candles_in_window": lookback,
                    "expected_candles_in_window": lookback,
                    "missing_candles_in_window": 0,
                    "zero_volume_candles_in_window": zero_count,
                    "bad_ohlc_in_window": bad_count,
                    "data_quality_ok": True,
                    "candidate_passed_baseline_filters": True,
                    "turnover_sum_window": math.fsum(turnovers[start : end + 1]),
                    "volume_sum_window": math.fsum(volumes[start : end + 1]),
                    "symbol_rank_by_turnover": None,
                    "launch_age_days_at_signal": None,
                }
            )

    output = pl.DataFrame(rows)
    if not output.is_empty():
        output = add_range_quality_score(output)
        before_quality = output.height
        if selected_profile.min_range_quality_score:
            output = output.filter(
                pl.col("range_quality_score")
                >= selected_profile.min_range_quality_score
            )
        funnel["quality_score_rejection_count"] += before_quality - output.height
    funnel["raw_candidate_pass_count"] += output.height
    return output, funnel


def detect_from_frame(
    df: pl.DataFrame,
    symbol: str,
    config: DetectionConfig,
    profile: RangeProfile,
) -> pl.DataFrame:
    return _detect_reference(df, symbol, config, profile)[0]


def detect_from_frame_with_funnel(
    df: pl.DataFrame,
    symbol: str,
    config: DetectionConfig,
    profile: RangeProfile,
) -> tuple[pl.DataFrame, dict[str, int]]:
    return _detect_reference(df, symbol, config, profile)
