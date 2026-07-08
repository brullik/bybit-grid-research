from __future__ import annotations

from pathlib import Path
import polars as pl


def read_candidates(base_dir: Path = Path("data/processed/range_candidates")) -> pl.DataFrame:
    files = list(base_dir.glob("symbol=*/year=*/month=*/candidates.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(p) for p in files], how="diagonal_relaxed")


def build_summary(df: pl.DataFrame) -> dict[str, object]:
    if df.is_empty():
        return {"candidate_rows_written": 0, "symbols_processed": 0}
    return {
        "candidate_rows_written": df.height,
        "symbols_processed": df["symbol"].n_unique(),
        "candidates_by_lookback": df.group_by("lookback_minutes").len().sort("lookback_minutes").to_dicts(),
        "candidates_by_symbol": df.group_by("symbol").len().sort("len", descending=True).to_dicts(),
        "avg_range_height_pct": float(df["range_height_pct"].mean()),
        "median_range_height_pct": float(df["range_height_pct"].median()),
        "avg_range_height_atr_14": float(df["range_height_atr_14"].mean()) if "range_height_atr_14" in df.columns else None,
        "median_range_height_atr_14": float(df["range_height_atr_14"].median()) if "range_height_atr_14" in df.columns else None,
    }
