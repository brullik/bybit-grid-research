from decimal import Decimal
import pytest
from bybit_grid.data.market_store.writer import write_chunk_atomic
from bybit_grid.data.market_store.models import MarketDatasetKind, MarketStoreError, STORE_SCHEMA_VERSION


def row(symbol="BTCUSDT", ts=0):
    return {"symbol": symbol, "open_time_ms": ts, "open": Decimal("1"), "high": Decimal("1"), "low": Decimal("1"), "close": Decimal("1"), "volume": Decimal("1"), "turnover": Decimal("1"), "category": "linear", "closed_bool": True, "source_run_id": "r", "source_review_pack_sha256": "0"*64, "source_plan_id": "p", "source_name": "s", "storage_schema_version": STORE_SCHEMA_VERSION}


def test_writer_rejects_mixed_symbols_before_staging(tmp_path):
    with pytest.raises(MarketStoreError, match="mixed_symbols"):
        write_chunk_atomic(tmp_path, MarketDatasetKind.trade_kline_1m, (row("BTCUSDT",0), row("ETHUSDT",60000)))
    assert not (tmp_path/".building").exists()
