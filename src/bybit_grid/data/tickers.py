import polars as pl
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.storage import metadata_path, ts_label


def download_tickers(client: BybitClient, category: str = "linear") -> pl.DataFrame:
    rows = client.public_get("/v5/market/tickers", {"category": category})["result"].get("list", [])
    df = pl.DataFrame(rows) if rows else pl.DataFrame()
    out = metadata_path(
        client.settings.data_dir, f"tickers_{category}_snapshot_{ts_label()}.parquet"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out)
    return df
