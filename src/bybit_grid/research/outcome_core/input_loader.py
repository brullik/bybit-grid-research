from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl


@dataclass(frozen=True)
class SymbolInputDiagnostics:
    symbol: str
    kline_file_refs_found: int
    kline_unique_files: int
    kline_duplicate_file_refs_removed: int
    kline_rows_before_timestamp_dedupe: int
    kline_rows_after_timestamp_dedupe: int
    kline_duplicate_timestamps_removed: int
    mark_file_refs_found: int
    mark_unique_files: int
    mark_duplicate_file_refs_removed: int
    mark_rows_before_timestamp_dedupe: int
    mark_rows_after_timestamp_dedupe: int
    mark_duplicate_timestamps_removed: int
    funding_file_refs_found: int
    funding_unique_files: int
    funding_duplicate_file_refs_removed: int
    funding_rows_before_timestamp_dedupe: int
    funding_rows_after_timestamp_dedupe: int
    funding_duplicate_timestamps_removed: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _discover_file_refs(base: Path, symbol: str) -> list[Path]:
    return (
        list(base.glob(f"**/{symbol}*.parquet"))
        + list(base.glob(f"symbol={symbol}/**/*.parquet"))
        + list(base.glob(f"**/symbol={symbol}/**/*.parquet"))
    )


def discover_unique_parquet_files(base: Path, symbol: str) -> list[Path]:
    """Discover symbol parquet files once, despite overlapping legacy glob patterns."""
    seen: dict[str, Path] = {}
    for path in _discover_file_refs(base, symbol):
        resolved = path.resolve()
        seen[str(resolved)] = resolved
    return sorted(seen.values(), key=lambda p: str(p))


def _timestamp_column(
    df: pl.DataFrame, candidates: tuple[str, ...], kind: str
) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    if df.is_empty():
        return None
    raise ValueError(
        f"{kind} frame missing canonical timestamp column; expected one of {candidates}"
    )


def _canonicalize(
    df: pl.DataFrame, ts_candidates: tuple[str, ...], kind: str, symbol: str
) -> pl.DataFrame:
    ts = _timestamp_column(df, ts_candidates, kind)
    if ts is None:
        return df
    dup = df.filter(pl.col(ts).is_duplicated())
    if not dup.is_empty():
        value_cols = [c for c in df.columns if c != ts]
        if value_cols:
            conflicts = (
                dup.group_by(ts)
                .agg([pl.col(c).n_unique().alias(c) for c in value_cols])
                .filter(pl.any_horizontal([pl.col(c) > 1 for c in value_cols]))
            )
            if not conflicts.is_empty():
                raise ValueError(
                    f"conflicting duplicate {kind} timestamps for {symbol}: "
                    f"{conflicts.select(ts).head(5).to_series().to_list()}"
                )
    return df.sort(ts).unique(subset=[ts], keep="first", maintain_order=True).sort(ts)


def _load_source(
    base: Path, symbol: str, ts_candidates: tuple[str, ...], kind: str
) -> tuple[pl.DataFrame, dict[str, int]]:
    refs = _discover_file_refs(base, symbol)
    files = discover_unique_parquet_files(base, symbol)
    df = pl.scan_parquet([str(p) for p in files]).collect() if files else pl.DataFrame()
    before = df.height
    df = _canonicalize(df, ts_candidates, kind, symbol)
    after = df.height
    return df, {
        "file_refs_found": len(refs),
        "unique_files": len(files),
        "duplicate_file_refs_removed": len(refs) - len(files),
        "rows_before_timestamp_dedupe": before,
        "rows_after_timestamp_dedupe": after,
        "duplicate_timestamps_removed": before - after,
    }


def load_canonical_symbol_frames(
    symbol: str,
    *,
    klines_root: Path,
    mark_root: Path,
    funding_root: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, SymbolInputDiagnostics]:
    klines, kd = _load_source(
        klines_root, symbol, ("open_time_ms", "start_time_ms"), "kline"
    )
    marks, md = _load_source(
        mark_root, symbol, ("open_time_ms", "start_time_ms"), "mark"
    )
    funding, fd = _load_source(
        funding_root,
        symbol,
        ("funding_rate_timestamp_ms", "funding_time_ms", "start_time_ms"),
        "funding",
    )
    diag = SymbolInputDiagnostics(
        symbol=symbol,
        kline_file_refs_found=kd["file_refs_found"],
        kline_unique_files=kd["unique_files"],
        kline_duplicate_file_refs_removed=kd["duplicate_file_refs_removed"],
        kline_rows_before_timestamp_dedupe=kd["rows_before_timestamp_dedupe"],
        kline_rows_after_timestamp_dedupe=kd["rows_after_timestamp_dedupe"],
        kline_duplicate_timestamps_removed=kd["duplicate_timestamps_removed"],
        mark_file_refs_found=md["file_refs_found"],
        mark_unique_files=md["unique_files"],
        mark_duplicate_file_refs_removed=md["duplicate_file_refs_removed"],
        mark_rows_before_timestamp_dedupe=md["rows_before_timestamp_dedupe"],
        mark_rows_after_timestamp_dedupe=md["rows_after_timestamp_dedupe"],
        mark_duplicate_timestamps_removed=md["duplicate_timestamps_removed"],
        funding_file_refs_found=fd["file_refs_found"],
        funding_unique_files=fd["unique_files"],
        funding_duplicate_file_refs_removed=fd["duplicate_file_refs_removed"],
        funding_rows_before_timestamp_dedupe=fd["rows_before_timestamp_dedupe"],
        funding_rows_after_timestamp_dedupe=fd["rows_after_timestamp_dedupe"],
        funding_duplicate_timestamps_removed=fd["duplicate_timestamps_removed"],
    )
    return klines, marks, funding, diag
