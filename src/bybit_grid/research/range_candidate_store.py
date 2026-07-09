from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl


def output_path(base_dir: Path, symbol: str, signal_time_ms: int) -> Path:
    dt = datetime.fromtimestamp(signal_time_ms / 1000, tz=timezone.utc)
    return (
        base_dir
        / f"symbol={symbol}"
        / f"year={dt.year:04d}"
        / f"month={dt.month:02d}"
        / "candidates.parquet"
    )


def write_partitioned_candidates(df: pl.DataFrame, base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    if df.is_empty():
        return paths
    enriched = df.with_columns(
        pl.from_epoch("signal_time_ms", time_unit="ms").dt.year().alias("_year"),
        pl.from_epoch("signal_time_ms", time_unit="ms").dt.month().alias("_month"),
    )
    for row in enriched.select(["symbol", "_year", "_month"]).unique().to_dicts():
        path = (
            base_dir
            / f"symbol={row['symbol']}"
            / f"year={int(row['_year']):04d}"
            / f"month={int(row['_month']):02d}"
            / "candidates.parquet"
        )
        part = enriched.filter(
            (pl.col("symbol") == row["symbol"])
            & (pl.col("_year") == row["_year"])
            & (pl.col("_month") == row["_month"])
        ).drop(["_year", "_month"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            part = (
                pl.concat([pl.read_parquet(path), part], how="diagonal_relaxed")
                .unique("range_action_event_id" if "range_action_event_id" in part.columns else ("range_event_id" if "range_event_id" in part.columns else ("range_regime_id" if "range_regime_id" in part.columns else "candidate_id")), keep="last")
                .sort([c for c in ["signal_time_ms", "lookback_minutes", "best_lookback_minutes"] if c in part.columns])
            )
        part.write_parquet(path)
        paths.append(path)
    return sorted(set(paths))
