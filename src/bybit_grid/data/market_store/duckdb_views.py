from __future__ import annotations
from pathlib import Path
import duckdb
from .models import MarketStoreError
from .audit import audit_market_store

VIEWS = {
    "instrument_snapshot": "bybit_instrument_snapshots",
    "trade_kline_1m": "bybit_trade_kline_1m",
    "mark_kline_1m": "bybit_mark_kline_1m",
    "funding_rate": "bybit_funding_rates",
}


def open_readonly_duckdb_views(store_root):
    root = Path(store_root)
    aud = audit_market_store(root)
    if not aud.ok:
        raise MarketStoreError("store_audit_failed")
    con = duckdb.connect(":memory:")
    try:
        for ds, view in VIEWS.items():
            files = list((root / "datasets" / ds).glob("**/data.parquet"))
            if not files:
                raise MarketStoreError("empty_store_dataset")
            glob = (root / "datasets" / ds / "**" / "data.parquet").as_posix().replace("'", "''")
            con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet('" + glob + "', hive_partitioning=true, union_by_name=true)")
        return con
    except Exception:
        con.close()
        raise


def duckdb_smoke_audit(store_root):
    con = open_readonly_duckdb_views(store_root)
    try:
        return {v: con.execute(f"SELECT count(*) FROM {v}").fetchone()[0] for v in VIEWS.values()}
    finally:
        con.close()
