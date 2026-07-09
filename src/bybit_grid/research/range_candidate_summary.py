from __future__ import annotations

from pathlib import Path
import polars as pl


def read_candidates(base_dir: Path = Path("data/processed/range_candidates")) -> pl.DataFrame:
    files = list(base_dir.glob("symbol=*/year=*/month=*/candidates.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(p) for p in files], how="diagonal_relaxed")


def _lookback_summary(df: pl.DataFrame) -> list[dict[str, object]]:
    if "lookback_minutes" in df.columns:
        return df.group_by("lookback_minutes").len().sort("lookback_minutes").to_dicts()
    if "best_lookback_minutes" in df.columns:
        return df.group_by("best_lookback_minutes").len().sort("best_lookback_minutes").to_dicts()
    if "lookback_min" in df.columns or "lookback_max" in df.columns:
        cols = [c for c in ("lookback_min", "lookback_max", "lookbacks_observed") if c in df.columns]
        return df.group_by(cols).len().sort(cols).to_dicts() if cols else []
    if "lookbacks_observed" in df.columns:
        return df.group_by("lookbacks_observed").len().sort("lookbacks_observed").to_dicts()
    return []


def build_summary(df: pl.DataFrame) -> dict[str, object]:
    if df.is_empty():
        return {"candidate_rows_written": 0, "symbols_processed": 0, "candidates_by_lookback": []}
    return {
        "candidate_rows_written": df.height,
        "symbols_processed": df["symbol"].n_unique() if "symbol" in df.columns else 0,
        "candidates_by_lookback": _lookback_summary(df),
        "candidates_by_symbol": df.group_by("symbol").len().sort("len", descending=True).to_dicts() if "symbol" in df.columns else [],
        "avg_range_height_pct": float(df["range_height_pct"].mean()) if "range_height_pct" in df.columns else None,
        "median_range_height_pct": float(df["range_height_pct"].median()) if "range_height_pct" in df.columns else None,
        "avg_range_height_atr_14": float(df["range_height_atr_14"].mean()) if "range_height_atr_14" in df.columns else None,
        "median_range_height_atr_14": float(df["range_height_atr_14"].median()) if "range_height_atr_14" in df.columns else None,
    }
