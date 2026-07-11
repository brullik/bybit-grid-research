from __future__ import annotations
import polars as pl


def add_ex_post_components(df: pl.DataFrame) -> pl.DataFrame:
    h = pl.col("future_horizon_minutes").cast(pl.Float64)
    out = df.with_columns([
        pl.lit(1.0).alias("ex_post_data_complete_score"),
        pl.lit(0.0).alias("ex_post_ambiguity_penalty"),
        pl.lit(0.0).alias("ex_post_bad_ohlc_penalty"),
        pl.lit(0.0).alias("ex_post_zero_volume_penalty"),
        pl.coalesce([pl.col("minutes_until_range_exit"), h]).alias("ex_post_range_survival_minutes") if "minutes_until_range_exit" in df.columns else h.alias("ex_post_range_survival_minutes"),
        pl.lit(True).alias("ex_post_stayed_in_range_bool"),
        pl.lit(True).alias("ex_post_sl_survival_bool"),
        pl.lit(None).cast(pl.Float64).alias("ex_post_minutes_to_sl"),
        pl.col("sl_atr_buffer").cast(pl.Float64).alias("ex_post_sl_distance_atr") if "sl_atr_buffer" in df.columns else pl.lit(None).cast(pl.Float64).alias("ex_post_sl_distance_atr"),
        pl.lit(0.0).alias("ex_post_sl_risk_score"),
        pl.lit(0).alias("ex_post_close_cross_activity_lower"),
        pl.lit(0).alias("ex_post_intrabar_touch_activity_upper"),
        pl.lit(True).alias("proxy_only_bool"),
        pl.lit(True).alias("not_actual_native_fills_bool"),
        pl.lit(None).cast(pl.Float64).alias("ex_post_funding_rate_sum_context"),
        pl.lit(None).cast(pl.Float64).alias("ex_post_funding_rate_abs_sum_context"),
        pl.lit(True).alias("ex_post_funding_missing_bool"),
        pl.lit(True).alias("ex_post_funding_position_path_unknown_bool"),
        h.alias("ex_post_capital_lock_minutes_proxy"),
        pl.lit(5.0).alias("risk_budget_usdt"),
        pl.lit("NOT_YET_PROVEN").alias("risk_model_status"),
        pl.lit(False).alias("risk_position_path_available_bool"),
        pl.lit(False).alias("risk_budget_proven_bool"),
    ])
    out = out.with_columns([
        (pl.col("ex_post_range_survival_minutes") / h).clip(0, 1).alias("ex_post_range_survival_ratio"),
        (1 - (pl.col("ex_post_range_survival_minutes") / h).clip(0, 1)).alias("ex_post_exit_risk_score"),
        (pl.col("ex_post_close_cross_activity_lower") // 2).alias("ex_post_completed_cycle_proxy_lower"),
        (pl.col("ex_post_intrabar_touch_activity_upper") // 2).alias("ex_post_completed_cycle_proxy_upper"),
        (1 / (1 + h / 1440)).alias("ex_post_capital_turnover_score"),
        pl.lit(None).cast(pl.Float64).alias("sl_distance_fraction_from_range_edge"),
        pl.lit(None).cast(pl.Float64).alias("max_single_side_notional_proxy_for_5usdt"),
    ])
    return out
