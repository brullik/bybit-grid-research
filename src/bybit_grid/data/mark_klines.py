from datetime import datetime, timezone

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.storage import kline_partition_path, utc_now_ms, write_parquet_merge


def normalize_mark_kline_rows(rows, symbol: str, category: str) -> pl.DataFrame:
    fetched = utc_now_ms()
    out = []
    for row in rows:
        if len(row) < 5:
            raise ValueError(f"mark-price kline row must have at least 5 fields, got {len(row)}")
        ms = int(row[0])
        out.append(
            {
                "symbol": symbol,
                "category": category,
                "open_time_ms": ms,
                "open_time_utc": datetime.fromtimestamp(ms / 1000, tz=timezone.utc),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": None,
                "turnover": None,
                "source": "mark-price-kline",
                "fetched_at_ms": fetched,
            }
        )
    return pl.DataFrame(out).sort("open_time_ms") if out else pl.DataFrame()


def download_mark_kline_range(
    client: BybitClient, symbol: str, start_ms: int, end_ms: int, category="linear"
):
    all_dfs = []
    cur = start_ms
    step = 999 * 60_000
    while cur <= end_ms:
        chunk_end = min(end_ms, cur + step)
        rows = client.public_get(
            "/v5/market/mark-price-kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": "1",
                "start": cur,
                "end": chunk_end,
                "limit": 1000,
            },
        )["result"].get("list", [])
        df = normalize_mark_kline_rows(rows, symbol, category)
        if not df.is_empty():
            all_dfs.append(df)
        cur = chunk_end + 60_000
    df = (
        pl.concat(all_dfs).unique(["symbol", "open_time_ms"]).sort("open_time_ms")
        if all_dfs
        else pl.DataFrame()
    )
    if not df.is_empty():
        partitioned = df.with_columns(
            pl.col("open_time_utc").dt.year().alias("_partition_year"),
            pl.col("open_time_utc").dt.month().alias("_partition_month"),
        )
        for part in partitioned.partition_by(
            ["_partition_year", "_partition_month"], as_dict=False, maintain_order=True
        ):
            clean_part = part.drop(["_partition_year", "_partition_month"])
            write_parquet_merge(
                kline_partition_path(
                    client.settings.data_dir,
                    "mark_klines",
                    symbol,
                    int(clean_part["open_time_ms"][0]),
                ),
                clean_part,
                ["symbol", "open_time_ms"],
            )
    return df
