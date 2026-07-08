from __future__ import annotations

import argparse
import glob
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.config import load_settings

ONE_MINUTE_MS = 60_000
EIGHT_HOURS_MS = 8 * 60 * 60_000
QUALITY_SCHEMA = {
    "symbol": pl.Utf8,
    "dataset": pl.Utf8,
    "rows": pl.Int64,
    "expected_rows": pl.Int64,
    "missing_gaps": pl.Int64,
    "duplicate_candles": pl.Int64,
    "bad_ohlc": pl.Int64,
    "zero_volume_rows": pl.Int64,
    "disk_bytes": pl.Int64,
    "requires_reload": pl.Boolean,
    "excluded_due_to_quality": pl.Boolean,
    "funding_rows_expected_approx": pl.Int64,
    "funding_rows_actual": pl.Int64,
    "funding_rows_status": pl.Utf8,
    "min_ts": pl.Int64,
    "max_ts": pl.Int64,
    "expected_start_ms": pl.Int64,
    "expected_end_ms": pl.Int64,
    "boundary_start_gap": pl.Int64,
    "boundary_end_gap": pl.Int64,
}


def _empty_summary() -> pl.DataFrame:
    return pl.DataFrame(schema=QUALITY_SCHEMA)


def _manifest_bounds(row: dict[str, object]) -> tuple[int | None, int | None]:
    start = row.get("expected_start_ms", row.get("start_ms"))
    end = row.get("expected_end_ms", row.get("end_ms"))
    return (int(start) if start is not None else None, int(end) if end is not None else None)


def _expected_1m_rows(start_ms: int | None, end_ms: int | None) -> int | None:
    if start_ms is None or end_ms is None or end_ms < start_ms:
        return None
    return ((end_ms - start_ms) // ONE_MINUTE_MS) + 1


def _expected_funding_rows(start_ms: int | None, end_ms: int | None) -> int | None:
    if start_ms is None or end_ms is None or end_ms < start_ms:
        return None
    return max(1, ((end_ms - start_ms) // EIGHT_HOURS_MS) + 1)


def _disk_bytes(files: list[str]) -> int:
    return sum(Path(f).stat().st_size for f in files if Path(f).exists())


def _base_row(symbol: str, dataset: str, start_ms: int | None, end_ms: int | None) -> dict[str, object]:
    return {k: None for k in QUALITY_SCHEMA} | {
        "symbol": symbol,
        "dataset": dataset,
        "rows": 0,
        "expected_rows": _expected_1m_rows(start_ms, end_ms) if dataset != "funding" else None,
        "missing_gaps": 0,
        "duplicate_candles": 0,
        "bad_ohlc": 0,
        "zero_volume_rows": 0,
        "disk_bytes": 0,
        "requires_reload": dataset != "funding",
        "excluded_due_to_quality": dataset != "funding",
        "funding_rows_expected_approx": _expected_funding_rows(start_ms, end_ms) if dataset == "funding" else None,
        "funding_rows_actual": 0 if dataset == "funding" else None,
        "funding_rows_status": "none" if dataset == "funding" else None,
        "expected_start_ms": start_ms,
        "expected_end_ms": end_ms,
        "boundary_start_gap": 0,
        "boundary_end_gap": 0,
    }


def summarize_1m_dataset(data_dir: Path, dataset: str, symbol: str, start_ms: int | None, end_ms: int | None) -> dict[str, object]:
    files = glob.glob(str(data_dir / f"raw/{dataset}/symbol={symbol}/year=*/month=*/*.parquet"))
    row = _base_row(symbol, dataset, start_ms, end_ms)
    row["disk_bytes"] = _disk_bytes(files)
    if not files:
        row["missing_gaps"] = int(row["expected_rows"] or 0)
        return row
    lf = pl.scan_parquet(files)
    bad = ((pl.col("high") < pl.col("low")) | (pl.col("high") < pl.col("open")) | (pl.col("high") < pl.col("close")) | (pl.col("low") > pl.col("open")) | (pl.col("low") > pl.col("close"))).sum().alias("bad_ohlc")
    aggs = [pl.len().alias("rows"), pl.col("open_time_ms").n_unique().alias("unique_open_times"), pl.col("open_time_ms").min().alias("min_ts"), pl.col("open_time_ms").max().alias("max_ts"), bad]
    if dataset == "klines" and "volume" in lf.collect_schema().names():
        aggs.append((pl.col("volume").fill_null(0) == 0).sum().alias("zero_volume_rows"))
    out = lf.select(aggs).collect().to_dicts()[0]
    rows = int(out["rows"] or 0)
    uniq = int(out["unique_open_times"] or 0)
    min_ts = int(out["min_ts"]) if out["min_ts"] is not None else None
    max_ts = int(out["max_ts"]) if out["max_ts"] is not None else None
    expected = _expected_1m_rows(start_ms, end_ms)
    row.update({"rows": rows, "expected_rows": expected, "duplicate_candles": max(0, rows - uniq), "min_ts": min_ts, "max_ts": max_ts, "bad_ohlc": int(out["bad_ohlc"] or 0), "zero_volume_rows": int(out.get("zero_volume_rows") or 0)})
    row["missing_gaps"] = max(0, int(expected or 0) - uniq)
    row["boundary_start_gap"] = max(0, ((min_ts - start_ms) // ONE_MINUTE_MS)) if min_ts is not None and start_ms is not None else 0
    row["boundary_end_gap"] = max(0, ((end_ms - max_ts) // ONE_MINUTE_MS)) if max_ts is not None and end_ms is not None else 0
    row["requires_reload"] = bool(row["duplicate_candles"] or row["bad_ohlc"] or row["missing_gaps"])
    row["excluded_due_to_quality"] = bool(row["requires_reload"])
    return row


def summarize_funding(data_dir: Path, symbol: str, start_ms: int | None, end_ms: int | None) -> dict[str, object]:
    files = glob.glob(str(data_dir / f"raw/funding/symbol={symbol}/year=*/*.parquet"))
    row = _base_row(symbol, "funding", start_ms, end_ms)
    row["disk_bytes"] = _disk_bytes(files)
    expected = _expected_funding_rows(start_ms, end_ms)
    if not files:
        return row
    out = pl.scan_parquet(files).select(pl.len().alias("rows"), pl.col("funding_rate_timestamp_ms").min().alias("min_ts"), pl.col("funding_rate_timestamp_ms").max().alias("max_ts")).collect().to_dicts()[0]
    actual = int(out["rows"] or 0)
    status = ("none" if actual == 0 else "ok") if not expected else ("none" if actual == 0 else "low" if actual < expected * 0.5 else "ok")
    row.update({"rows": actual, "funding_rows_actual": actual, "funding_rows_expected_approx": expected, "funding_rows_status": status, "min_ts": out["min_ts"], "max_ts": out["max_ts"], "requires_reload": False, "excluded_due_to_quality": False})
    return row


def load_manifest(path: Path | None) -> pl.DataFrame:
    if path and path.exists():
        return pl.read_parquet(path)
    return pl.DataFrame()


def discover_manifest_from_raw(data_dir: Path) -> pl.DataFrame:
    symbols = set()
    for dataset in ("klines", "mark_klines", "funding"):
        for p in (data_dir / f"raw/{dataset}").glob("symbol=*"):
            symbols.add(p.name.removeprefix("symbol="))
    return pl.DataFrame({"symbol": sorted(symbols), "start_ms": [None] * len(symbols), "end_ms": [None] * len(symbols)}) if symbols else pl.DataFrame()


def build_quality_summary(manifest: pl.DataFrame, data_dir: Path) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    if manifest.is_empty():
        return _empty_summary()
    for mrow in manifest.to_dicts():
        symbol = str(mrow["symbol"])
        start_ms, end_ms = _manifest_bounds(mrow)
        rows.append(summarize_1m_dataset(data_dir, "klines", symbol, start_ms, end_ms))
        rows.append(summarize_1m_dataset(data_dir, "mark_klines", symbol, start_ms, end_ms))
        rows.append(summarize_funding(data_dir, symbol, start_ms, end_ms))
    return pl.DataFrame(rows, schema=QUALITY_SCHEMA)


def markdown_table(df: pl.DataFrame) -> str:
    if df.is_empty():
        return "No manifest symbols found."
    cols = ["symbol", "dataset", "rows", "expected_rows", "missing_gaps", "duplicate_candles", "bad_ohlc", "zero_volume_rows", "funding_rows_status", "requires_reload"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for row in df.select(cols).to_dicts():
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/processed/research_download_manifest.parquet")
    parser.add_argument("--fast", action="store_true", help="Use manifest-driven lazy aggregate checks (default).")
    args, _ = parser.parse_known_args()
    data_dir = load_settings().data_dir
    manifest = load_manifest(Path(args.manifest))
    if manifest.is_empty():
        manifest = discover_manifest_from_raw(data_dir)
    df = build_quality_summary(manifest, data_dir)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    df.write_parquet("data/processed/universe_quality_summary.parquet")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_02_universe_quality_report.md").write_text("# Sprint 02 Universe Quality Report\n\n" + markdown_table(df) + "\n", encoding="utf-8")
    dup = int(df["duplicate_candles"].sum()) if not df.is_empty() else 0
    bad = int(df["bad_ohlc"].sum()) if not df.is_empty() else 0
    rows_scanned = int(df["rows"].sum()) if not df.is_empty() else 0
    print(f"quality_report status=ok manifest_symbols={manifest.height} rows_scanned_approx={rows_scanned} duplicate_count_total={dup} bad_ohlc_count_total={bad}")


if __name__ == "__main__":
    main()
