from __future__ import annotations

import polars as pl


def aggregate_funding(funding: pl.DataFrame, start_ms: int, end_ms: int) -> dict[str, float | int]:
    if funding.is_empty():
        return {"funding_rows_in_horizon": 0, "funding_rate_sum": 0.0, "funding_rate_abs_sum": 0.0}
    time_col = "funding_time_ms" if "funding_time_ms" in funding.columns else "start_time_ms"
    rate_col = "funding_rate" if "funding_rate" in funding.columns else "rate"
    if time_col not in funding.columns or rate_col not in funding.columns:
        return {"funding_rows_in_horizon": 0, "funding_rate_sum": 0.0, "funding_rate_abs_sum": 0.0}
    rows = funding.filter((pl.col(time_col) > start_ms) & (pl.col(time_col) <= end_ms))
    if rows.is_empty():
        return {"funding_rows_in_horizon": 0, "funding_rate_sum": 0.0, "funding_rate_abs_sum": 0.0}
    rates = rows[rate_col].cast(pl.Float64)
    return {
        "funding_rows_in_horizon": rows.height,
        "funding_rate_sum": float(rates.sum()),
        "funding_rate_abs_sum": float(rates.abs().sum()),
    }
