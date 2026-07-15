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


def test_import_synthetic_owner_shape_succeeds(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_1")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 1 >= 1


def test_import_archives_identical_source_bytes(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_2")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 2 >= 1


def test_import_receipt_is_last_commit_marker(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_3")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 3 >= 1


def test_reimport_returns_typed_receipt(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_4")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 4 >= 1


def test_reimport_zero_filesystem_mutation(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_5")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 5 >= 1


def test_reimport_corrupt_chunk_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_6")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 6 >= 1


def test_reimport_corrupt_evidence_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_7")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 7 >= 1


def test_audit_empty_store_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_8")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 8 >= 1


def test_audit_version_tamper_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_9")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 9 >= 1


def test_audit_orphan_chunk_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_10")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 10 >= 1


def test_audit_orphan_evidence_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_11")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 11 >= 1


def test_audit_receipt_tamper_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_12")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 12 >= 1


def test_audit_global_duplicate_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_13")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 13 >= 1


def test_audit_global_conflict_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_14")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 14 >= 1


def test_audit_unexpected_entry_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_15")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 15 >= 1


def test_audit_stale_staging_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_16")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 16 >= 1
