import polars as pl

from bybit_grid.data.storage import ts_label

ONE_MINUTE_MS = 60_000


def _empty_gaps() -> pl.DataFrame:
    return pl.DataFrame(
        {"symbol": [], "start_ms": [], "end_ms": [], "missing_minutes": [], "gap_type": []}
    )


def detect_1m_gaps(
    df: pl.DataFrame,
    expected_start_ms: int | None = None,
    expected_end_ms: int | None = None,
    symbol_col="symbol",
    time_col="open_time_ms",
) -> pl.DataFrame:
    reports = []
    if df.is_empty():
        return _empty_gaps()
    for sym, part in df.sort([symbol_col, time_col]).partition_by(symbol_col, as_dict=True).items():
        symbol = sym[0] if isinstance(sym, tuple) else sym
        vals = sorted(set(part[time_col].to_list()))
        if expected_start_ms is not None and vals and vals[0] > expected_start_ms:
            reports.append(
                {
                    "symbol": symbol,
                    "start_ms": expected_start_ms,
                    "end_ms": vals[0] - ONE_MINUTE_MS,
                    "missing_minutes": (vals[0] - expected_start_ms) // ONE_MINUTE_MS,
                    "gap_type": "start_boundary",
                }
            )
        for prev, cur in zip(vals, vals[1:]):
            if cur - prev > ONE_MINUTE_MS:
                reports.append(
                    {
                        "symbol": symbol,
                        "start_ms": prev + ONE_MINUTE_MS,
                        "end_ms": cur - ONE_MINUTE_MS,
                        "missing_minutes": (cur - prev) // ONE_MINUTE_MS - 1,
                        "gap_type": "internal",
                    }
                )
        if expected_end_ms is not None and vals and vals[-1] < expected_end_ms:
            reports.append(
                {
                    "symbol": symbol,
                    "start_ms": vals[-1] + ONE_MINUTE_MS,
                    "end_ms": expected_end_ms,
                    "missing_minutes": (expected_end_ms - vals[-1]) // ONE_MINUTE_MS,
                    "gap_type": "end_boundary",
                }
            )
    return pl.DataFrame(reports) if reports else _empty_gaps()


def detect_duplicate_candles(df: pl.DataFrame) -> pl.DataFrame:
    keys = [c for c in ["symbol", "open_time_ms", "source"] if c in df.columns]
    if not keys or df.is_empty():
        return pl.DataFrame()
    return df.group_by(keys).len().filter(pl.col("len") > 1)


def detect_bad_ohlc(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    bad = (
        (pl.col("high") < pl.col("low"))
        | (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
        | (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
    )
    return df.filter(bad)


def build_quality_report(
    df: pl.DataFrame, expected_start_ms: int | None = None, expected_end_ms: int | None = None
) -> dict[str, object]:
    gaps = detect_1m_gaps(df, expected_start_ms, expected_end_ms)
    duplicates = detect_duplicate_candles(df)
    bad_ohlc = detect_bad_ohlc(df)
    return {
        "gap_count": gaps.height,
        "duplicate_count": duplicates.height,
        "bad_ohlc_count": bad_ohlc.height,
        "gaps": gaps.to_dicts(),
        "duplicates": duplicates.to_dicts(),
        "bad_ohlc": bad_ohlc.to_dicts(),
    }


def save_gap_report(
    data_dir,
    df: pl.DataFrame,
    expected_start_ms: int | None = None,
    expected_end_ms: int | None = None,
) -> pl.DataFrame:
    report = detect_1m_gaps(df, expected_start_ms, expected_end_ms)
    path = data_dir / "quality" / f"gap_report_{ts_label()}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    report.write_parquet(path)
    return report
