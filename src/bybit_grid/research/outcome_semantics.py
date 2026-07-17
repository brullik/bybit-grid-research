from __future__ import annotations

import math

import polars as pl

from bybit_grid.research.outcome_core.outcome_numpy import deterministic_outcome_id


OUTCOME_SEMANTICS_VERSION = "v5_exact_outcome_window_provenance"
OUTCOME_WINDOW_SEMANTICS_VERSION = "exact-minute-outcome-window-v1"
ACTIONABLE_EVENT_SEMANTICS_VERSION = "range-actionable-prefix-invariance-v1"
OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)

WINDOW_LABEL_FIELDS = (
    "label_stayed_in_range_until_horizon",
    "label_sl_hit_before_horizon",
    "label_good_chop_proxy",
    "label_low_activity_proxy",
    "label_high_breakout_risk_proxy",
)
WINDOW_CLAIM_FIELDS = (
    "first_exit_side",
    "first_exit_ambiguous_bool",
    "first_exit_time_ms",
    "minutes_to_first_exit",
    "time_inside_range_minutes",
    "inside_range_candle_count",
    "inside_range_ratio",
    "max_high_above_range_pct",
    "max_low_below_range_pct",
    "max_close_distance_from_mid_pct",
    "first_sl_side",
    "first_sl_ambiguous_bool",
    "first_sl_time_ms",
    "minutes_to_first_sl",
    "sl_hit_bool",
    "future_close_level_cross_count",
    "future_intrabar_level_touch_count",
    "future_unique_grid_levels_touched_count",
    "future_internal_level_close_cross_count",
    "future_internal_level_intrabar_touch_count",
    "fill_activity_lower_bound_proxy",
    "fill_activity_upper_bound_proxy",
    "future_grid_level_cross_count",
    "future_midline_cross_count",
    "future_upper_zone_touch_count",
    "future_lower_zone_touch_count",
    "grid_crossings_per_hour",
    "mark_price_max_deviation_from_last_pct",
)


def fail(msgs: list[str], msg: str) -> None:
    if msg not in msgs:
        msgs.append(msg)


def _check_group_invariance(
    df: pl.DataFrame,
    keys: tuple[str, ...],
    fields: tuple[str, ...],
    failures: list[str],
    message: str,
) -> None:
    first_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for row in df.iter_rows(named=True):
        key = tuple(row[column] for column in keys)
        previous = first_by_key.setdefault(key, row)
        if any(previous[field] != row[field] for field in fields):
            fail(failures, message)
            return


def validate_outcome_window_semantics(df: pl.DataFrame) -> dict[str, object]:
    failures: list[str] = []
    required = {
        "outcome_id",
        "outcome_semantics_version",
        "range_action_event_id",
        "symbol",
        "grid_count",
        "grid_cell_number",
        "grid_price_level_count",
        "sl_atr_buffer",
        "outcome_window_semantics_version",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
        "decision_time_ms",
        "signal_time_ms",
        "entry_time_ms",
        "outcome_end_exclusive_ms",
        "future_horizon_minutes",
        "future_rows_available",
        "future_expected_minutes_count",
        "future_observed_expected_minutes_count",
        "future_coverage_minutes",
        "future_missing_minutes_count",
        "future_off_grid_rows_count",
        "future_duplicate_timestamp_count",
        "future_invalid_timestamp_rows_count",
        "future_bad_ohlc_count",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
        "future_outcome_ineligible_reason",
        "profile_name",
        "range_profile_name",
        "outcome_profile_name",
        "range_regime_id",
        "range_run_id",
        "outcome_run_id",
        "range_low",
        "range_high",
        "range_mid",
        "future_zero_volume_count",
        "funding_rows_in_horizon",
        "funding_rate_sum",
        "funding_rate_abs_sum",
        "funding_rate_mean",
        "funding_source_status",
        "mark_price_future_rows_available",
        *WINDOW_LABEL_FIELDS,
        *WINDOW_CLAIM_FIELDS,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        return {
            "outcome_window_semantic_audit_ok": False,
            "failures": ["missing outcome-window columns: " + ",".join(missing)],
        }

    versions = set(df["outcome_window_semantics_version"].unique().to_list())
    if versions != {OUTCOME_WINDOW_SEMANTICS_VERSION}:
        fail(failures, "outcome_window_semantics_version invalid")
    outcome_versions = set(df["outcome_semantics_version"].unique().to_list())
    if outcome_versions != {OUTCOME_SEMANTICS_VERSION}:
        fail(failures, "outcome_semantics_version is not uniform v5")

    for row in df.iter_rows(named=True):
        horizon = row["future_horizon_minutes"]
        decision = row["decision_time_ms"]
        signal = row["signal_time_ms"]
        entry = row["entry_time_ms"]
        end = row["outcome_end_exclusive_ms"]
        if not all(
            type(value) is int for value in (horizon, decision, signal, entry, end)
        ):
            fail(failures, "outcome window timestamps/horizon must be exact integers")
            continue
        if horizon <= 0 or signal < 0 or not (signal == decision < entry < end):
            fail(failures, "outcome window causal timestamps invalid")
        if (
            row["actionable_event_semantics_version"]
            != ACTIONABLE_EVENT_SEMANTICS_VERSION
            or row["decision_time_source"] != "event_decision_time"
            or row["causal_provenance_complete_bool"] is not True
        ):
            fail(failures, "authoritative decision-time provenance invalid")
        expected_entry = ((decision // 60_000) + 1) * 60_000
        if entry != expected_entry or entry % 60_000 or end - entry != horizon * 60_000:
            fail(
                failures,
                "outcome entry/end does not match decision-derived exact horizon",
            )

        expected = row["future_expected_minutes_count"]
        observed = row["future_observed_expected_minutes_count"]
        coverage = row["future_coverage_minutes"]
        missing_count = row["future_missing_minutes_count"]
        off_grid = row["future_off_grid_rows_count"]
        duplicates = row["future_duplicate_timestamp_count"]
        invalid_timestamps = row["future_invalid_timestamp_rows_count"]
        bad_ohlc = row["future_bad_ohlc_count"]
        rows_available = row["future_rows_available"]
        counts = (
            expected,
            observed,
            coverage,
            missing_count,
            off_grid,
            duplicates,
            invalid_timestamps,
            bad_ohlc,
            rows_available,
        )
        if not all(type(value) is int and value >= 0 for value in counts):
            fail(failures, "outcome window diagnostics must be nonnegative integers")
            continue
        auxiliary_counts = (
            row["future_zero_volume_count"],
            row["funding_rows_in_horizon"],
            row["mark_price_future_rows_available"],
        )
        if not all(type(value) is int and value >= 0 for value in auxiliary_counts):
            fail(failures, "outcome auxiliary diagnostics must be nonnegative integers")
        if row["future_zero_volume_count"] > rows_available:
            fail(failures, "zero-volume diagnostics exceed available rows")
        if (
            not isinstance(row["funding_source_status"], str)
            or not row["funding_source_status"].strip()
            or any(
                isinstance(row[field], bool)
                or not isinstance(row[field], (int, float))
                or not math.isfinite(float(row[field]))
                for field in (
                    "funding_rate_sum",
                    "funding_rate_abs_sum",
                    "funding_rate_mean",
                )
            )
        ):
            fail(failures, "funding diagnostics invalid")
        if (
            expected != horizon
            or observed != coverage
            or observed + missing_count != horizon
            or observed > rows_available
            or observed + off_grid > rows_available
            or duplicates > rows_available - observed
            or invalid_timestamps > rows_available
            or bad_ohlc > rows_available
            or observed + duplicates + off_grid + invalid_timestamps != rows_available
        ):
            fail(failures, "outcome window grid diagnostics do not conserve horizon")

        reasons: list[str] = []
        if missing_count:
            reasons.append("missing_minutes")
        if off_grid:
            reasons.append("off_grid_rows")
        if duplicates:
            reasons.append("duplicate_timestamps")
        if invalid_timestamps:
            reasons.append("invalid_timestamps")
        if bad_ohlc:
            reasons.append("invalid_ohlc")
        complete = not reasons and rows_available == horizon and observed == horizon
        if type(row["future_data_complete_bool"]) is not bool:
            fail(failures, "future_data_complete_bool must be bool")
        if type(row["future_outcome_eligible_bool"]) is not bool:
            fail(failures, "future_outcome_eligible_bool must be bool")
        if row["future_data_complete_bool"] is not complete:
            fail(failures, "future_data_complete_bool inconsistent with exact grid")
        if row["future_outcome_eligible_bool"] is not complete:
            fail(failures, "future outcome eligibility inconsistent with exact grid")
        expected_reason = "|".join(reasons) if reasons else None
        if row["future_outcome_ineligible_reason"] != expected_reason:
            fail(failures, "future outcome ineligible reason inconsistent")
        label_fields = tuple(
            field for field in df.columns if field.startswith("label_")
        )
        if not complete and any(
            row[field] is not None for field in (*label_fields, *WINDOW_CLAIM_FIELDS)
        ):
            fail(failures, "ineligible horizon retains future-dependent claim")
        if complete:
            nullable_first_event_fields = {
                "first_exit_time_ms",
                "minutes_to_first_exit",
                "first_sl_time_ms",
                "minutes_to_first_sl",
            }
            if any(
                row[field] is None
                for field in (*label_fields, *WINDOW_CLAIM_FIELDS)
                if field not in nullable_first_event_fields
            ):
                fail(failures, "eligible horizon has null future-dependent claim")

            exit_side = row["first_exit_side"]
            exit_ambiguous = row["first_exit_ambiguous_bool"]
            sl_side = row["first_sl_side"]
            sl_ambiguous = row["first_sl_ambiguous_bool"]
            if exit_side not in {"none", "up", "down", "ambiguous_both"}:
                fail(failures, "first exit side invalid")
            if sl_side not in {"none", "upper", "lower", "ambiguous_both"}:
                fail(failures, "first SL side invalid")
            if type(exit_ambiguous) is not bool or exit_ambiguous is not (
                exit_side == "ambiguous_both"
            ):
                fail(failures, "first exit ambiguity inconsistent")
            if type(sl_ambiguous) is not bool or sl_ambiguous is not (
                sl_side == "ambiguous_both"
            ):
                fail(failures, "first SL ambiguity inconsistent")

            for side, time_field, minutes_field, none_side, prefix in (
                (
                    exit_side,
                    "first_exit_time_ms",
                    "minutes_to_first_exit",
                    "none",
                    "first exit",
                ),
                (
                    sl_side,
                    "first_sl_time_ms",
                    "minutes_to_first_sl",
                    "none",
                    "first SL",
                ),
            ):
                event_time = row[time_field]
                event_minutes = row[minutes_field]
                if side == none_side:
                    if event_time is not None or event_minutes is not None:
                        fail(failures, f"{prefix} none-side retains time claim")
                elif (
                    type(event_time) is not int
                    or type(event_minutes) is not int
                    or not (entry <= event_time < end)
                    or (event_time - entry) % 60_000
                    or event_minutes != (event_time - entry) // 60_000
                ):
                    fail(failures, f"{prefix} time claim inconsistent")

            sl_hit = row["sl_hit_bool"]
            if type(sl_hit) is not bool or sl_hit is not (sl_side != "none"):
                fail(failures, "sl_hit_bool inconsistent with first SL side")
            if any(type(row[field]) is not bool for field in label_fields):
                fail(failures, "eligible horizon labels must be bool")
            if row["label_stayed_in_range_until_horizon"] is not (exit_side == "none"):
                fail(failures, "stayed-in-range label inconsistent")
            if row["label_sl_hit_before_horizon"] is not (sl_side != "none"):
                fail(failures, "SL-hit label inconsistent")

            numeric_claims = (
                "time_inside_range_minutes",
                "inside_range_candle_count",
                "inside_range_ratio",
                "max_high_above_range_pct",
                "max_low_below_range_pct",
                "max_close_distance_from_mid_pct",
                "future_close_level_cross_count",
                "future_intrabar_level_touch_count",
                "future_unique_grid_levels_touched_count",
                "future_internal_level_close_cross_count",
                "future_internal_level_intrabar_touch_count",
                "fill_activity_lower_bound_proxy",
                "fill_activity_upper_bound_proxy",
                "future_grid_level_cross_count",
                "future_midline_cross_count",
                "future_upper_zone_touch_count",
                "future_lower_zone_touch_count",
                "grid_crossings_per_hour",
                "mark_price_max_deviation_from_last_pct",
            )
            numeric_claims_invalid = any(
                isinstance(row[field], bool)
                or not isinstance(row[field], (int, float))
                or not math.isfinite(float(row[field]))
                or float(row[field]) < 0.0
                for field in numeric_claims
            )
            if numeric_claims_invalid:
                fail(failures, "eligible horizon numeric claim invalid")
            else:
                inside_ratio = row["inside_range_ratio"]
                grid_cross = row["future_close_level_cross_count"]
                if not (0.0 <= float(inside_ratio) <= 1.0):
                    fail(failures, "inside range ratio invalid")
                integer_claims = (
                    "time_inside_range_minutes",
                    "inside_range_candle_count",
                    "future_close_level_cross_count",
                    "future_intrabar_level_touch_count",
                    "future_unique_grid_levels_touched_count",
                    "future_internal_level_close_cross_count",
                    "future_internal_level_intrabar_touch_count",
                    "fill_activity_lower_bound_proxy",
                    "fill_activity_upper_bound_proxy",
                    "future_grid_level_cross_count",
                    "future_midline_cross_count",
                    "future_upper_zone_touch_count",
                    "future_lower_zone_touch_count",
                )
                if any(type(row[field]) is not int for field in integer_claims):
                    fail(
                        failures, "eligible horizon count claims must be exact integers"
                    )
                inside_count = row["inside_range_candle_count"]
                inside_minutes = row["time_inside_range_minutes"]
                if (
                    type(inside_count) is not int
                    or type(inside_minutes) is not int
                    or inside_count != inside_minutes
                    or inside_count > horizon
                    or not math.isclose(
                        float(inside_ratio),
                        inside_count / horizon,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    fail(failures, "inside-range count/minutes/ratio inconsistent")
                if not (
                    row["future_grid_level_cross_count"]
                    == row["future_close_level_cross_count"]
                    == row["fill_activity_lower_bound_proxy"]
                    <= row["future_intrabar_level_touch_count"]
                    == row["fill_activity_upper_bound_proxy"]
                ):
                    fail(failures, "grid activity aliases/bounds inconsistent")
                expected_crossings_per_hour = float(grid_cross) / (horizon / 60)
                if not math.isclose(
                    float(row["grid_crossings_per_hour"]),
                    expected_crossings_per_hour,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    fail(failures, "grid crossings per hour inconsistent")
                if (
                    row["future_internal_level_close_cross_count"]
                    > row["future_close_level_cross_count"]
                    or row["future_internal_level_intrabar_touch_count"]
                    > row["future_intrabar_level_touch_count"]
                    or row["future_unique_grid_levels_touched_count"]
                    > row["grid_price_level_count"]
                ):
                    fail(failures, "grid activity internal/unique bounds inconsistent")
                min_cross = max(1, horizon // 240)
                if row["label_good_chop_proxy"] is not (
                    float(inside_ratio) >= 0.70 and int(grid_cross) >= min_cross
                ):
                    fail(failures, "good-chop label inconsistent")
                if row["label_low_activity_proxy"] is not (int(grid_cross) < min_cross):
                    fail(failures, "low-activity label inconsistent")
                if row["label_high_breakout_risk_proxy"] is not (
                    sl_side != "none" or float(inside_ratio) < 0.40
                ):
                    fail(failures, "breakout-risk label inconsistent")

        event_id = row.get("range_action_event_id")
        symbol = row.get("symbol")
        grid_cell_number = row.get("grid_cell_number")
        grid_count = row.get("grid_count")
        sl_atr_buffer = row.get("sl_atr_buffer")
        outcome_id = row.get("outcome_id")
        if not isinstance(event_id, str) or not event_id.strip():
            fail(failures, "range action event id provenance invalid")
        if not isinstance(symbol, str) or not symbol.strip():
            fail(failures, "symbol provenance invalid")
        if type(grid_cell_number) is not int or grid_cell_number <= 0:
            fail(failures, "grid cell number id material invalid")
        if (
            type(grid_count) is not int
            or grid_count != grid_cell_number
            or row["grid_price_level_count"] != grid_cell_number + 1
        ):
            fail(failures, "grid count/level semantic material invalid")
        if (
            isinstance(sl_atr_buffer, bool)
            or not isinstance(sl_atr_buffer, (int, float))
            or not math.isfinite(float(sl_atr_buffer))
            or float(sl_atr_buffer) < 0.0
        ):
            fail(failures, "SL buffer id material invalid")
        try:
            expected_outcome_id = deterministic_outcome_id(
                str(event_id),
                horizon,
                int(grid_cell_number),
                float(sl_atr_buffer),
                OUTCOME_SEMANTICS_VERSION,
                OUTCOME_WINDOW_SEMANTICS_VERSION,
            )
        except (TypeError, ValueError):
            fail(failures, "outcome id material invalid")
        else:
            if outcome_id != expected_outcome_id:
                fail(failures, "outcome_id does not match v5 semantic material")

        outcome_profile = row["outcome_profile_name"]
        range_profile = row["range_profile_name"]
        profile = row["profile_name"]
        if not isinstance(outcome_profile, str) or not outcome_profile.strip():
            fail(failures, "outcome profile provenance invalid")
        if (
            not isinstance(range_profile, str)
            or not range_profile.strip()
            or profile != range_profile
        ):
            fail(failures, "range profile provenance overwritten")

        range_regime_id = row["range_regime_id"]
        range_run_id = row["range_run_id"]
        outcome_run_id = row["outcome_run_id"]
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (range_regime_id, range_run_id, outcome_run_id)
        ):
            fail(failures, "range/outcome run provenance invalid")
        range_low = row["range_low"]
        range_mid = row["range_mid"]
        range_high = row["range_high"]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in (range_low, range_mid, range_high)
        ) or not (0.0 < float(range_low) < float(range_mid) < float(range_high)):
            fail(failures, "range bounds provenance invalid")

    composite = (
        "range_action_event_id",
        "future_horizon_minutes",
        "grid_cell_number",
        "sl_atr_buffer",
    )
    if df.height != df.unique(subset=list(composite)).height:
        fail(failures, "duplicate outcome composite rows")
    if df["outcome_id"].n_unique() != df.height:
        fail(failures, "duplicate outcome ids")

    event_horizon_fields = (
        "symbol",
        "range_regime_id",
        "profile_name",
        "range_profile_name",
        "outcome_profile_name",
        "outcome_semantics_version",
        "outcome_window_semantics_version",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
        "range_run_id",
        "outcome_run_id",
        "decision_time_ms",
        "signal_time_ms",
        "entry_time_ms",
        "outcome_end_exclusive_ms",
        "range_low",
        "range_mid",
        "range_high",
        "future_rows_available",
        "future_expected_minutes_count",
        "future_observed_expected_minutes_count",
        "future_coverage_minutes",
        "future_missing_minutes_count",
        "future_off_grid_rows_count",
        "future_duplicate_timestamp_count",
        "future_invalid_timestamp_rows_count",
        "future_bad_ohlc_count",
        "future_zero_volume_count",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
        "future_outcome_ineligible_reason",
        "first_exit_side",
        "first_exit_ambiguous_bool",
        "first_exit_time_ms",
        "minutes_to_first_exit",
        "time_inside_range_minutes",
        "inside_range_candle_count",
        "inside_range_ratio",
        "max_high_above_range_pct",
        "max_low_below_range_pct",
        "max_close_distance_from_mid_pct",
        "funding_rows_in_horizon",
        "funding_rate_sum",
        "funding_rate_abs_sum",
        "funding_rate_mean",
        "funding_source_status",
        "mark_price_future_rows_available",
        "mark_price_max_deviation_from_last_pct",
        "label_stayed_in_range_until_horizon",
    )
    _check_group_invariance(
        df,
        ("range_action_event_id", "future_horizon_minutes"),
        event_horizon_fields,
        failures,
        "event-horizon causal/window provenance is not invariant",
    )
    _check_group_invariance(
        df,
        ("range_action_event_id", "future_horizon_minutes", "sl_atr_buffer"),
        (
            "first_sl_side",
            "first_sl_ambiguous_bool",
            "first_sl_time_ms",
            "minutes_to_first_sl",
            "sl_hit_bool",
            "label_sl_hit_before_horizon",
        ),
        failures,
        "event-horizon-SL claims are not invariant across grids",
    )
    _check_group_invariance(
        df,
        ("range_action_event_id", "future_horizon_minutes", "grid_cell_number"),
        (
            "future_close_level_cross_count",
            "future_intrabar_level_touch_count",
            "future_unique_grid_levels_touched_count",
            "future_internal_level_close_cross_count",
            "future_internal_level_intrabar_touch_count",
            "fill_activity_lower_bound_proxy",
            "fill_activity_upper_bound_proxy",
            "future_grid_level_cross_count",
            "grid_crossings_per_hour",
            "label_good_chop_proxy",
            "label_low_activity_proxy",
        ),
        failures,
        "event-horizon-grid claims are not invariant across SL probes",
    )

    return {
        "outcome_window_semantic_audit_ok": not failures,
        "failures": failures,
    }
