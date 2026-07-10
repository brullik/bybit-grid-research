from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from bybit_grid.research.outcome_store import read_outcomes


def build_summaries(root: Path) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    df = read_outcomes(root)
    if df.is_empty():
        summary = pl.DataFrame({"metric": ["outcome_rows_total"], "value": [0.0]})
        quality = pl.DataFrame({"metric": ["future_data_complete_rate"], "value": [0.0]})
        return summary, quality, {"outcome_rows_total": 0}
    dup = df.height - df.select(["range_action_event_id", "future_horizon_minutes", "grid_count", "sl_atr_buffer"]).unique().height
    statuses = df["funding_source_status"].value_counts().to_dicts() if "funding_source_status" in df.columns else []
    status_counts = {str(r.get("funding_source_status")): int(r.get("count", r.get("len", 0))) for r in statuses}
    funding_rows_total = int(df["funding_rows_in_horizon"].sum()) if "funding_rows_in_horizon" in df.columns else 0
    symbols = df["symbol"].unique().sort().to_list() if "symbol" in df.columns else []
    symbols_with_ok = df.filter(pl.col("funding_source_status") == "ok")["symbol"].unique().sort().to_list() if "funding_source_status" in df.columns and "symbol" in df.columns else []
    perf = {
        "outcome_rows_total": df.height,
        "unique_outcome_id_count": df["outcome_id"].n_unique(),
        "duplicate_range_action_event_horizon_grid_sl_rows": dup,
        "future_data_complete_rate": float(df["future_data_complete_bool"].mean()),
        "first_exit_side_distribution": df["first_exit_side"].value_counts().to_dicts(),
        "sl_hit_distribution": df["sl_hit_bool"].value_counts().to_dicts(),
        "grid_crossing_distribution": df.select(pl.col("future_grid_level_cross_count").min().alias("min"), pl.col("future_grid_level_cross_count").median().alias("median"), pl.col("future_grid_level_cross_count").max().alias("max")).to_dicts()[0],
        "funding_rows_total": funding_rows_total,
        "funding_files_found_count": len(symbols_with_ok),
        "funding_symbols_with_files": symbols_with_ok,
        "funding_rows_scanned_total": funding_rows_total,
        "funding_rows_joined_total": funding_rows_total,
        "funding_join_coverage_rate": float((df["funding_rows_in_horizon"] > 0).mean()) if "funding_rows_in_horizon" in df.columns else 0.0,
        "funding_missing_symbols": sorted(set(symbols) - set(symbols_with_ok)),
        "funding_source_status_counts": status_counts,
        "funding_zero_reason": "no overlapping local funding timestamps" if funding_rows_total == 0 and status_counts.get("no_overlap", 0) > 0 else ("local funding files missing or unreadable" if funding_rows_total == 0 else ""),
    }
    summary = pl.DataFrame({"metric": list(perf.keys()), "value": [json.dumps(v) if isinstance(v, (list, dict)) else str(v) for v in perf.values()]})
    quality = pl.DataFrame({"metric": ["future_data_complete_rate", "duplicate_rows"], "value": [perf["future_data_complete_rate"], float(dup)]})
    return summary, quality, perf


def write_summary(root: Path) -> dict:
    summary, quality, perf = build_summaries(root)
    out = root / "summary"
    out.mkdir(parents=True, exist_ok=True)
    summary.write_parquet(out / "outcome_summary.parquet")
    quality.write_parquet(out / "outcome_quality_summary.parquet")
    (out / "outcome_perf.json").write_text(json.dumps(perf, indent=2, ensure_ascii=False, default=str) + "\n")
    return perf
