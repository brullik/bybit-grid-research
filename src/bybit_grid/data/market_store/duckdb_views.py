from __future__ import annotations
from pathlib import Path
import duckdb
from .models import MarketStoreError

VIEWS = {
    "instrument_snapshot": "bybit_instrument_snapshots",
    "trade_kline_1m": "bybit_trade_kline_1m",
    "mark_kline_1m": "bybit_mark_kline_1m",
    "funding_rate": "bybit_funding_rates",
}


def open_readonly_duckdb_views(store_root):
    root = Path(store_root)
    con = duckdb.connect(":memory:")
    for ds, view in VIEWS.items():
        files = list((root / "datasets" / ds).glob("**/data.parquet"))
        if not files:
            raise MarketStoreError("empty_store_dataset")
        glob = (root / "datasets" / ds / "**" / "data.parquet").as_posix()
        con.execute(
            f"CREATE VIEW {view} AS SELECT * FROM read_parquet(?, hive_partitioning=true, union_by_name=true)",
            [glob],
        )
    return con


def duckdb_smoke_audit(store_root):
    con = open_readonly_duckdb_views(store_root)
    return {v: con.execute(f"SELECT count(*) FROM {v}").fetchone()[0] for v in VIEWS.values()}
