from decimal import Decimal
import pytest
from bybit_grid.data.market_store.schemas import SCHEMAS, ensure_decimal128_38_18
from bybit_grid.data.market_store.models import MarketDatasetKind, MarketStoreError
from bybit_grid.data.market_store.canonical import decimal_to_text
from bybit_grid.data.market_store.paths import rel_chunk_path


def test_exact_arrow_schema_for_all_four_datasets():
    assert set(SCHEMAS) == set(MarketDatasetKind)
    for s in SCHEMAS.values():
        assert all(not f.nullable for f in s)
        assert "storage_schema_version" in s.names


def test_decimal_policy_and_canonical_negative_zero():
    assert ensure_decimal128_38_18(Decimal("1.000000000000000001")) == Decimal(
        "1.000000000000000001"
    )
    with pytest.raises(MarketStoreError):
        ensure_decimal128_38_18(Decimal("1.0000000000000000001"))
    with pytest.raises(MarketStoreError):
        ensure_decimal128_38_18(Decimal("123456789012345678901.000000000000000001"))
    assert decimal_to_text(Decimal("-0.0000")) == "0"
    with pytest.raises(MarketStoreError):
        ensure_decimal128_38_18(1.0)


def test_safe_paths():
    p = rel_chunk_path(
        MarketDatasetKind.trade_kline_1m,
        symbol="BTCUSDT",
        min_ms=1704067200000,
        max_ms=1704067200000,
        logical_hash="a" * 64,
    )
    assert p.as_posix().startswith("datasets/trade_kline_1m/symbol=BTCUSDT/year=2024/month=01/")
    with pytest.raises(MarketStoreError):
        rel_chunk_path(
            MarketDatasetKind.trade_kline_1m,
            symbol="../BTC",
            min_ms=0,
            max_ms=0,
            logical_hash="a" * 64,
        )
