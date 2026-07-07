from __future__ import annotations

from pathlib import Path

import polars as pl

from bybit_grid.config import load_settings
from bybit_grid.data.quality import detect_1m_gaps, detect_bad_ohlc, detect_duplicate_candles


def read_glob(pattern: str) -> pl.DataFrame:
    files = list(Path().glob(pattern))
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(path) for path in files], how="diagonal_relaxed")


def summarize(name: str, df: pl.DataFrame) -> list[dict[str, object]]:
    if df.is_empty():
        return []
    rows = []
    for symbol_key, part in df.partition_by("symbol", as_dict=True).items():
        symbol = symbol_key[0] if isinstance(symbol_key, tuple) else symbol_key
        zero_volume_rows = 0
        if "volume" in part.columns and part["volume"].null_count() < part.height:
            zero_volume_rows = part.filter(pl.col("volume") == 0).height
        rows.append(
            {
                "symbol": symbol,
                "dataset": name,
                "rows": part.height,
                "missing_gaps": detect_1m_gaps(part).height if "open_time_ms" in part.columns else 0,
                "duplicate_candles": (
                    detect_duplicate_candles(part).height if "open_time_ms" in part.columns else 0
                ),
                "bad_ohlc": detect_bad_ohlc(part).height if "open" in part.columns else 0,
                "zero_volume_rows": zero_volume_rows,
                "disk_bytes": 0,
                "requires_reload": False,
                "excluded_due_to_quality": False,
            }
        )
    return rows


def main() -> None:
    data_dir = load_settings().data_dir
    rows = []
    rows += summarize(
        "klines", read_glob(str(data_dir / "raw/klines/symbol=*/year=*/month=*/part.parquet"))
    )
    rows += summarize(
        "mark_klines",
        read_glob(str(data_dir / "raw/mark_klines/symbol=*/year=*/month=*/part.parquet")),
    )
    rows += summarize(
        "funding", read_glob(str(data_dir / "raw/funding/symbol=*/year=*/part.parquet"))
    )
    df = pl.DataFrame(rows) if rows else pl.DataFrame({"symbol": [], "dataset": [], "rows": []})
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    df.write_parquet("data/processed/universe_quality_summary.parquet")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_02_universe_quality_report.md").write_text(
        "# Sprint 02 Universe Quality Report\n\n"
        + (repr(df) if not df.is_empty() else "No downloaded data found.")
        + "\n"
    )


if __name__ == "__main__":
    main()
