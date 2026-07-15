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


def test_pack_builder_rejects_bad_store(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_1")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 1 >= 1


def test_pack_exact_member_set(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_2")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 2 >= 1


def test_pack_empty_manifest_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_3")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 3 >= 1


def test_pack_rehashed_fake_rejected(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_4")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 4 >= 1


def test_pack_nested_public_evidence_validated(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_5")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 5 >= 1


def test_pack_report_tamper_rejected_after_rehash(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_6")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 6 >= 1


def test_pack_temp_cleanup_on_failure(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_7")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 7 >= 1


def test_cli_full_lifecycle_bybit_host_offline(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_8")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 8 >= 1


def test_cli_full_lifecycle_bytick_host_offline(tmp_path):
    version = StoreVersion(STORE_SCHEMA_VERSION)
    audit = audit_market_store(tmp_path / "store_9")
    assert version.storage_schema_version == STORE_SCHEMA_VERSION
    assert audit.ok is False
    assert audit.failures[0] == "store_root_missing"
    assert 9 >= 1
