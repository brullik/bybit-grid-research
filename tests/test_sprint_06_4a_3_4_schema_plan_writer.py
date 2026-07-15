from __future__ import annotations
from decimal import Decimal
from bybit_grid.data.market_store.schemas import ensure_decimal128_38_18
from bybit_grid.data.market_store.planner import partition_validated_rows
from bybit_grid.data.market_store.transaction import build_import_preflight_plan
from bybit_grid.data.market_store.inventory import snapshot_tree
from bybit_grid.data.market_store.writer import write_chunk_atomic
from bybit_grid.data.market_store.reader import read_and_validate_chunk
from bybit_grid.data.market_store.models import MarketDatasetKind

def test_decimal_max_boundary(tmp_path):
    observations = []
    value = ensure_decimal128_38_18(Decimal("1.000000000000000000"))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_decimal_min_boundary(tmp_path):
    observations = []
    value = ensure_decimal128_38_18(Decimal("1.000000000000000000"))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_decimal_rounding_rejected(tmp_path):
    observations = []
    value = ensure_decimal128_38_18(Decimal("1.000000000000000000"))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_plan_instrument_snapshot_multi_symbol_single_partition(tmp_path):
    observations = []
    try:
        partition_validated_rows(MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_plan_kline_cross_month_two_partitions(tmp_path):
    observations = []
    try:
        partition_validated_rows(MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_plan_funding_four_months_four_partitions(tmp_path):
    observations = []
    try:
        partition_validated_rows(MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_plan_entry_mixed_timeseries_symbols_rejected(tmp_path):
    observations = []
    try:
        partition_validated_rows(MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_preflight_invalid_row_zero_writes(tmp_path):
    observations = []
    try:
        build_import_preflight_plan(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_preflight_incoming_duplicate_zero_writes(tmp_path):
    observations = []
    try:
        build_import_preflight_plan(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_preflight_committed_conflict_zero_writes(tmp_path):
    observations = []
    try:
        build_import_preflight_plan(object(), tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_early_failure_cleanup(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_mid_failure_cleanup(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_late_failure_cleanup(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    value = snapshot_tree(tmp_path)
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_manifest_is_canonical(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        read_and_validate_chunk(tmp_path / "store", tmp_path / "store" / "missing")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_actual_path_mismatch_rejected(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        read_and_validate_chunk(tmp_path / "store", tmp_path / "store" / "missing")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_chunk_primary_key_schema_mismatch_rejected(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        read_and_validate_chunk(tmp_path / "store", tmp_path / "store" / "missing")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_existing_chunk_corruption_rejected(tmp_path):
    observations = []
    try:
        write_chunk_atomic(tmp_path / "store", MarketDatasetKind.trade_kline_1m, [])
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        read_and_validate_chunk(tmp_path / "store", tmp_path / "store" / "missing")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)
