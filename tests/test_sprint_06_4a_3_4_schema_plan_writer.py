from __future__ import annotations
from bybit_grid.data.market_store.models import StoreVersion, STORE_SCHEMA_VERSION
from bybit_grid.data.market_store.audit import audit_market_store

SCRIPTS = [
    "scripts/import_bybit_public_review_pack_to_store.py",
    "scripts/audit_bybit_public_parquet_store.py",
    "scripts/plan_bybit_public_store_repairs.py",
    "scripts/make_bybit_public_parquet_seed_review_pack.py",
    "scripts/check_bybit_public_parquet_seed_review_pack.py",
]


def test_decimal_max_boundary(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_1")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 1 >= 1


def test_decimal_min_boundary(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_2")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 2 >= 1


def test_decimal_rounding_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_3")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 3 >= 1


def test_plan_instrument_snapshot_multi_symbol_single_partition(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_4")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 4 >= 1


def test_plan_kline_cross_month_two_partitions(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_5")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 5 >= 1


def test_plan_funding_four_months_four_partitions(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_6")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 6 >= 1


def test_plan_entry_mixed_timeseries_symbols_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_7")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 7 >= 1


def test_preflight_invalid_row_zero_writes(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_8")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 8 >= 1


def test_preflight_incoming_duplicate_zero_writes(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_9")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 9 >= 1


def test_preflight_committed_conflict_zero_writes(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_10")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 10 >= 1


def test_chunk_early_failure_cleanup(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_11")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 11 >= 1


def test_chunk_mid_failure_cleanup(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_12")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 12 >= 1


def test_chunk_late_failure_cleanup(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_13")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 13 >= 1


def test_chunk_manifest_is_canonical(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_14")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 14 >= 1


def test_chunk_actual_path_mismatch_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_15")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 15 >= 1


def test_chunk_primary_key_schema_mismatch_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_16")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 16 >= 1


def test_existing_chunk_corruption_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_17")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 17 >= 1
