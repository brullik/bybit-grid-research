from decimal import Decimal
from bybit_grid.data.market_store.writer import write_chunk_atomic
from bybit_grid.data.market_store.reader import read_dataset
from bybit_grid.data.market_store.models import MarketDatasetKind
from bybit_grid.data.market_store.audit import audit_market_store


def row(t=0):
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "open_time_ms": t,
        "open": Decimal("1"),
        "high": Decimal("1"),
        "low": Decimal("1"),
        "close": Decimal("1"),
        "volume": Decimal("2"),
        "turnover": Decimal("2"),
        "closed_bool": True,
        "source_run_id": "r",
        "source_review_pack_sha256": "a" * 64,
        "source_plan_id": "p",
        "source_name": "n",
        "storage_schema_version": "bybit_public_parquet_store_v1",
    }


def test_atomic_chunk_roundtrip_and_idempotent_reuse(tmp_path):
    m1 = write_chunk_atomic(tmp_path, MarketDatasetKind.trade_kline_1m, [row(0), row(60000)])
    m2 = write_chunk_atomic(tmp_path, MarketDatasetKind.trade_kline_1m, [row(0), row(60000)])
    assert m1.logical_rows_sha256 == m2.logical_rows_sha256
    rows = read_dataset(
        tmp_path, MarketDatasetKind.trade_kline_1m, symbol="BTCUSDT", start_ms=0, end_ms=60000
    )
    assert rows[0]["open"] == Decimal("1.000000000000000000")
    audit = audit_market_store(tmp_path)
    assert not audit.ok
    assert "chunks_without_receipt" in audit.failures
