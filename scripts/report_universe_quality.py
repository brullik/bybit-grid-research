from __future__ import annotations

import glob
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.config import load_settings
from bybit_grid.data.funding_quality import funding_status
from bybit_grid.data.quality import detect_1m_gaps, detect_bad_ohlc, detect_duplicate_candles


def read_glob(pattern: str) -> pl.DataFrame:
    files = glob.glob(pattern)
    if not files:
        return pl.DataFrame()
    return pl.scan_parquet(files).collect()


def summarize(name: str, df: pl.DataFrame) -> list[dict[str, object]]:
    if df.is_empty():
        return []
    rows = []
    for symbol_key, part in df.partition_by("symbol", as_dict=True).items():
        symbol = symbol_key[0] if isinstance(symbol_key, tuple) else symbol_key
        zero_volume_rows = 0
        if "volume" in part.columns and part["volume"].null_count() < part.height:
            zero_volume_rows = part.filter(pl.col("volume") == 0).height
        expected_funding = None
        funding_actual = None
        funding_state = None
        if name == "funding":
            funding_actual = part.height
            ts_col = (
                "funding_rate_timestamp_ms" if "funding_rate_timestamp_ms" in part.columns else None
            )
            if ts_col and part.height > 0:
                min_ts = int(part[ts_col].min())
                max_ts = int(part[ts_col].max())
                days = max(1, round((max_ts - min_ts) / (24 * 60 * 60_000)) + 1)
                expected_funding = days * 3
            funding_state = funding_status(funding_actual, expected_funding)
        rows.append(
            {
                "symbol": symbol,
                "dataset": name,
                "rows": part.height,
                "missing_gaps": detect_1m_gaps(part).height
                if "open_time_ms" in part.columns
                else 0,
                "duplicate_candles": (
                    detect_duplicate_candles(part).height if "open_time_ms" in part.columns else 0
                ),
                "bad_ohlc": detect_bad_ohlc(part).height if "open" in part.columns else 0,
                "zero_volume_rows": zero_volume_rows,
                "disk_bytes": 0,
                "requires_reload": False,
                "excluded_due_to_quality": False,
                "funding_rows_expected_approx": expected_funding,
                "funding_rows_actual": funding_actual,
                "funding_rows_status": funding_state,
            }
        )
    return rows


def markdown_table(df: pl.DataFrame) -> str:
    if df.is_empty():
        return "No downloaded data found."
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for row in df.to_dicts():
        vals = [str(row.get(c, "")).replace("|", "\\|") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main() -> None:
    data_dir = load_settings().data_dir
    rows = []
    rows += summarize(
        "klines", read_glob(str(data_dir / "raw/klines/symbol=*/year=*/month=*/*.parquet"))
    )
    rows += summarize(
        "mark_klines",
        read_glob(str(data_dir / "raw/mark_klines/symbol=*/year=*/month=*/*.parquet")),
    )
    rows += summarize("funding", read_glob(str(data_dir / "raw/funding/symbol=*/year=*/*.parquet")))
    df = pl.DataFrame(rows) if rows else pl.DataFrame({"symbol": [], "dataset": [], "rows": []})
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    df.write_parquet("data/processed/universe_quality_summary.parquet")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_02_universe_quality_report.md").write_text(
        "# Sprint 02 Universe Quality Report\n\n" + markdown_table(df) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
