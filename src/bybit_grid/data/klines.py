from datetime import datetime, timezone
import polars as pl
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.storage import kline_partition_path, utc_now_ms, write_parquet_merge


def normalize_kline_rows(rows, symbol: str, category: str, source: str) -> pl.DataFrame:
    fetched = utc_now_ms()
    out = []
    for r in rows:
        ms = int(r[0])
        out.append(
            {
                "symbol": symbol,
                "category": category,
                "open_time_ms": ms,
                "open_time_utc": datetime.fromtimestamp(ms / 1000, tz=timezone.utc),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
                "turnover": float(r[6]),
                "source": source,
                "fetched_at_ms": fetched,
            }
        )
    return pl.DataFrame(out).sort("open_time_ms") if out else pl.DataFrame()


def download_kline_range(
    client: BybitClient,
    symbol: str,
    start_ms: int,
    end_ms: int,
    category="linear",
    dataset="klines",
    endpoint="/v5/market/kline",
) -> pl.DataFrame:
    all_dfs = []
    cur = start_ms
    step = 999 * 60_000
    while cur <= end_ms:
        chunk_end = min(end_ms, cur + step)
        res = client.public_get(
            endpoint,
            {
                "category": category,
                "symbol": symbol,
                "interval": "1",
                "start": cur,
                "end": chunk_end,
                "limit": 1000,
            },
        )["result"].get("list", [])
        df = normalize_kline_rows(res, symbol, category, endpoint.rsplit("/", 1)[-1])
        if not df.is_empty():
            all_dfs.append(df)
        cur = chunk_end + 60_000
    df = (
        pl.concat(all_dfs).unique(["symbol", "open_time_ms"]).sort("open_time_ms")
        if all_dfs
        else pl.DataFrame()
    )
    if not df.is_empty():
        for part in df.partition_by(
            [
                pl.col("open_time_utc").dt.year().alias("year"),
                pl.col("open_time_utc").dt.month().alias("month"),
            ],
            as_dict=False,
        ):
            write_parquet_merge(
                kline_partition_path(
                    client.settings.data_dir, dataset, symbol, int(part["open_time_ms"][0])
                ),
                part,
                ["symbol", "open_time_ms"],
            )
    return df
