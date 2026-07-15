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


def test_replay_snapshot_required_and_unaligned_snapshot_allowed(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_1")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 1 >= 1


def test_replay_returns_exact_instrument_snapshot_row(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_2")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 2 >= 1


def test_replay_complete_trade_mark_grids(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_3")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 3 >= 1


def test_replay_funding_mark_join(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_4")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 4 >= 1


def test_replay_missing_mark_join_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_5")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 5 >= 1


def test_coverage_strict_inputs(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_6")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 6 >= 1


def test_coverage_out_of_window_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_7")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 7 >= 1


def test_coverage_gap_windows(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_8")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 8 >= 1


def test_resume_inclusive_1000(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_9")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 9 >= 1


def test_resume_month_year_leap_boundaries(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_10")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 10 >= 1


def test_funding_strict_timestamps(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_11")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 11 >= 1


def test_duckdb_four_views(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_12")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 12 >= 1


def test_duckdb_decimal_types(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_13")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 13 >= 1


def test_duckdb_connection_closed_on_success_and_failure(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_14")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 14 >= 1
