from __future__ import annotations
import polars as pl


def _col(df: pl.DataFrame, name: str, default: object, dtype: pl.DataType | None = None) -> pl.Expr:
    expr = pl.col(name) if name in df.columns else pl.lit(default)
    return expr.cast(dtype) if dtype is not None else expr


def add_ex_post_components(df: pl.DataFrame) -> pl.DataFrame:
    h = pl.col("future_horizon_minutes").cast(pl.Float64)
    coverage = _col(df, "future_coverage_minutes", None, pl.Float64)
    rows = _col(df, "future_rows_available", 0, pl.Float64)
    exit_min = _col(df, "minutes_to_first_exit", None, pl.Float64)
    if "minutes_until_range_exit" in df.columns and "minutes_to_first_exit" not in df.columns:
        exit_min = pl.col("minutes_until_range_exit").cast(pl.Float64)
    sl_min = _col(df, "minutes_to_first_sl", None, pl.Float64)
    complete = _col(df, "future_data_complete_bool", False, pl.Boolean)
    sl_hit = _col(df, "sl_hit_bool", None, pl.Boolean)
    sl_valid = _col(df, "sl_proxy_valid_bool", False, pl.Boolean)
    funding_status = _col(df, "funding_source_status", "missing_file", pl.Utf8)
    survival_min = (
        pl.when(exit_min.is_not_null())
        .then(exit_min)
        .otherwise(pl.when(complete).then(h).otherwise(coverage.fill_null(0)))
        .clip(0, h)
    )
    sl_risk = (
        pl.when(~sl_valid)
        .then(1.0)
        .when(sl_hit.fill_null(False))
        .then((1 - (sl_min.fill_null(0) / h)).clip(0, 1))
        .otherwise(0.0)
    )
    term = pl.min_horizontal([exit_min.fill_null(h), sl_min.fill_null(h), coverage.fill_null(h), h])
    out = df.with_columns(
        [
            pl.min_horizontal(
                [
                    (coverage / h).clip(0, 1).fill_null(0),
                    (rows / h).clip(0, 1).fill_null(0),
                    pl.when(complete).then(1.0).otherwise(0.999),
                ]
            ).alias("ex_post_data_complete_score"),
            (
                _col(df, "future_bad_ohlc_count", 0, pl.Float64)
                / pl.max_horizontal([rows, pl.lit(1.0)])
            ).alias("ex_post_bad_ohlc_rate"),
            (
                _col(df, "future_zero_volume_count", 0, pl.Float64)
                / pl.max_horizontal([rows, pl.lit(1.0)])
            ).alias("ex_post_zero_volume_rate"),
            pl.max_horizontal(
                [
                    _col(df, "first_exit_ambiguous_bool", False, pl.Boolean).cast(pl.Float64),
                    _col(df, "first_sl_ambiguous_bool", False, pl.Boolean).cast(pl.Float64),
                ]
            ).alias("ex_post_ambiguity_penalty"),
            survival_min.alias("ex_post_range_survival_minutes"),
            ((survival_min >= h) & complete).alias("ex_post_stayed_in_range_bool"),
            (sl_valid & ~sl_hit.fill_null(False)).alias("ex_post_sl_survival_bool"),
            sl_min.alias("ex_post_minutes_to_sl"),
            _col(df, "sl_atr_buffer", None, pl.Float64).alias("ex_post_sl_distance_atr"),
            pl.when(sl_valid & complete)
            .then(sl_risk)
            .otherwise(None)
            .alias("ex_post_sl_risk_score"),
            _col(df, "first_sl_ambiguous_bool", False, pl.Boolean)
            .cast(pl.Float64)
            .alias("ex_post_sl_ambiguity_penalty"),
            _col(df, "future_close_level_cross_count", 0, pl.Int64).alias(
                "ex_post_close_cross_activity_lower"
            ),
            _col(df, "future_intrabar_level_touch_count", 0, pl.Int64).alias(
                "ex_post_intrabar_touch_activity_upper"
            ),
            _col(df, "future_unique_grid_levels_touched_count", 0, pl.Int64).alias(
                "ex_post_unique_levels_touched"
            ),
            pl.lit(True).alias("proxy_only_bool"),
            pl.lit(True).alias("not_actual_native_fills_bool"),
            _col(df, "funding_rate_sum", None, pl.Float64).alias(
                "ex_post_funding_rate_sum_context"
            ),
            _col(df, "funding_rate_abs_sum", None, pl.Float64).alias(
                "ex_post_funding_rate_abs_sum_context"
            ),
            _col(df, "funding_rate_mean", None, pl.Float64).alias(
                "ex_post_funding_rate_mean_context"
            ),
            (funding_status == "missing_file").alias("ex_post_funding_missing_bool"),
            (funding_status == "no_overlap").alias("ex_post_funding_no_overlap_bool"),
            pl.lit(True).alias("ex_post_funding_position_path_unknown_bool"),
            term.clip(0, h).alias("ex_post_capital_lock_minutes_proxy"),
            pl.lit(5.0).alias("risk_budget_usdt"),
            pl.lit("NOT_YET_PROVEN").alias("risk_model_status"),
            pl.lit(False).alias("risk_position_path_available_bool"),
            pl.lit(False).alias("risk_budget_proven_bool"),
            complete.alias("ex_post_event_evidence_complete_bool"),
            (sl_valid & complete).alias("ex_post_sl_evidence_complete_bool"),
            complete.alias("ex_post_grid_evidence_complete_bool"),
        ]
    )
    out = out.with_columns(
        [
            (pl.col("ex_post_range_survival_minutes") / h)
            .clip(0, 1)
            .alias("ex_post_range_survival_ratio"),
            (1 - (pl.col("ex_post_range_survival_minutes") / h).clip(0, 1)).alias(
                "ex_post_exit_risk_score"
            ),
            (pl.col("ex_post_close_cross_activity_lower") // 2).alias(
                "ex_post_completed_cycle_proxy_lower"
            ),
            (pl.col("ex_post_intrabar_touch_activity_upper") // 2).alias(
                "ex_post_completed_cycle_proxy_upper"
            ),
            (1 / (1 + pl.col("ex_post_capital_lock_minutes_proxy") / 1440)).alias(
                "ex_post_capital_turnover_score"
            ),
            pl.lit(None).cast(pl.Float64).alias("sl_distance_fraction_from_range_edge"),
            pl.lit(None).cast(pl.Float64).alias("max_single_side_notional_proxy_for_5usdt"),
            (
                pl.col("ex_post_data_complete_score")
                * (1 - pl.col("ex_post_bad_ohlc_rate")).clip(0, 1)
                * (1 - pl.col("ex_post_ambiguity_penalty")).clip(0, 1)
            )
            .clip(0, 1)
            .alias("ex_post_data_quality_score"),
            (
                pl.col("ex_post_event_evidence_complete_bool")
                & pl.col("ex_post_sl_evidence_complete_bool")
                & pl.col("ex_post_grid_evidence_complete_bool")
            ).alias("ex_post_score_eligible_bool"),
            pl.when(~pl.col("ex_post_event_evidence_complete_bool"))
            .then(pl.lit("incomplete_future_evidence"))
            .when(~pl.col("ex_post_sl_evidence_complete_bool"))
            .then(pl.lit("missing_or_incomplete_sl_evidence"))
            .otherwise(pl.lit(None))
            .alias("ex_post_score_incomplete_reason"),
        ]
    )
    return out
