from __future__ import annotations

import polars as pl


def _empty(status: str) -> dict[str, float | int | str]:
    return {
        "funding_rows_in_horizon": 0,
        "funding_rate_sum": 0.0,
        "funding_rate_abs_sum": 0.0,
        "funding_rate_mean": 0.0,
        "funding_source_status": status,
    }


def aggregate_funding(funding: pl.DataFrame, start_ms: int, end_ms: int) -> dict[str, float | int | str]:
    if funding.is_empty():
        return _empty("missing_file")
    time_col = next((c for c in ["funding_rate_timestamp_ms", "funding_time_ms", "start_time_ms"] if c in funding.columns), "")
    rate_col = "funding_rate" if "funding_rate" in funding.columns else "rate"
    if not time_col or rate_col not in funding.columns:
        return _empty("empty_file")
    rows = funding.filter((pl.col(time_col) > start_ms) & (pl.col(time_col) <= end_ms))
    if rows.is_empty():
        return _empty("no_overlap")
    rates = rows[rate_col].cast(pl.Float64)
    return {
        "funding_rows_in_horizon": rows.height,
        "funding_rate_sum": float(rates.sum()),
        "funding_rate_abs_sum": float(rates.abs().sum()),
        "funding_rate_mean": float(rates.mean()),
        "funding_source_status": "ok",
    }
