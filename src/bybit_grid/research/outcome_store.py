from __future__ import annotations

from pathlib import Path

import polars as pl


def read_outcomes(root: Path) -> pl.DataFrame:
    files = list((root / "outcomes").glob("**/*.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.scan_parquet([str(p) for p in files]).collect()


def write_partitioned_outcomes(df: pl.DataFrame, base_dir: Path, skip_existing_ok: bool = False) -> list[Path]:
    if df.is_empty():
        return []
    enriched = df.with_columns(
        pl.from_epoch("entry_time_ms", time_unit="ms").dt.year().alias("_year"),
        pl.from_epoch("entry_time_ms", time_unit="ms").dt.month().alias("_month"),
    )
    paths: list[Path] = []
    for row in enriched.select(["symbol", "_year", "_month"]).unique().to_dicts():
        path = base_dir / f"symbol={row['symbol']}" / f"year={int(row['_year']):04d}" / f"month={int(row['_month']):02d}" / "outcomes.parquet"
        part = enriched.filter((pl.col("symbol") == row["symbol"]) & (pl.col("_year") == row["_year"]) & (pl.col("_month") == row["_month"])).drop(["_year", "_month"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if skip_existing_ok:
                old = pl.read_parquet(path)
                part = pl.concat([old, part], how="diagonal_relaxed").unique("outcome_id", keep="first")
            else:
                old = pl.read_parquet(path)
                part = pl.concat([old, part], how="diagonal_relaxed").unique("outcome_id", keep="last")
        part.sort(["symbol", "entry_time_ms", "range_action_event_id", "future_horizon_minutes", "grid_count", "sl_atr_buffer"]).write_parquet(path)
        paths.append(path)
    return paths
