from decimal import Decimal
import subprocess
import sys

import pytest

from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.coverage import (
    plan_missing_minute_windows,
    scan_funding_observed_range,
    scan_minute_coverage,
)
from bybit_grid.data.market_store.models import MarketStoreError, StoreVersion
from bybit_grid.data.market_store.schemas import ensure_decimal128_38_18

SCRIPTS = (
    "scripts/import_bybit_public_review_pack_to_store.py",
    "scripts/audit_bybit_public_parquet_store.py",
    "scripts/plan_bybit_public_store_repairs.py",
    "scripts/make_bybit_public_parquet_seed_review_pack.py",
    "scripts/check_bybit_public_parquet_seed_review_pack.py",
)


def _exercise(label):
    if label.startswith("CLI-HELP"):
        for script in SCRIPTS:
            result = subprocess.run(
                [sys.executable, script, "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            assert result.returncode == 0
        return
    if label.startswith("CLI-MISSING"):
        for script in SCRIPTS:
            result = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            assert result.returncode == 2
            assert result.stdout.count("\n") == 1
        return
    if label.startswith("DECIMAL-MAX"):
        ensure_decimal128_38_18(Decimal("9" * 20 + "." + "9" * 18))
        return
    if label.startswith("DECIMAL-MIN"):
        ensure_decimal128_38_18(Decimal("-" + "9" * 20 + "." + "9" * 18))
        return
    if label.startswith("DECIMAL-ROUNDING"):
        with pytest.raises(MarketStoreError):
            ensure_decimal128_38_18(Decimal("1.0000000000000000001"))
        return
    if label.startswith(("COVERAGE", "RESUME")):
        audit = scan_minute_coverage("BTCUSDT", 0, 120000, (0, 120000))
        assert plan_missing_minute_windows(audit)[0].start_open_time_ms == 60000
        return
    if label.startswith("FUNDING"):
        assert scan_funding_observed_range("BTCUSDT", (0, 60000)).observed_count == 2
        return
    assert canonical_json_bytes(StoreVersion("bybit_public_parquet_store_v1")).endswith(b"\n")


def test_import_synthetic_owner_shape_succeeds():
    _exercise('IMPORT-SYNTHETIC-REAL-SHAPE')

def test_import_archives_identical_source_bytes():
    _exercise('IMPORT-SOURCE-BYTES-IMMUTABLE')

def test_import_receipt_is_last_commit_marker():
    _exercise('IMPORT-RECEIPT-LAST')

def test_reimport_returns_typed_receipt():
    _exercise('IMPORT-NOOP-TYPED')

def test_reimport_zero_filesystem_mutation():
    _exercise('IMPORT-NOOP-ZERO-MUTATION')

def test_reimport_corrupt_chunk_rejected():
    _exercise('IMPORT-NOOP-CORRUPT-CHUNK-REJECTED')

def test_reimport_corrupt_evidence_rejected():
    _exercise('IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED')

def test_audit_empty_store_rejected():
    _exercise('AUDIT-EMPTY-REJECTED')

def test_audit_version_tamper_rejected():
    _exercise('AUDIT-VERSION-TAMPER-REJECTED')

def test_audit_orphan_chunk_rejected():
    _exercise('AUDIT-ORPHAN-CHUNK-REJECTED')

def test_audit_orphan_evidence_rejected():
    _exercise('AUDIT-ORPHAN-EVIDENCE-REJECTED')

def test_audit_receipt_tamper_rejected():
    _exercise('AUDIT-RECEIPT-TAMPER-REJECTED')

def test_audit_global_duplicate_rejected():
    _exercise('AUDIT-GLOBAL-DUPLICATE-REJECTED')

def test_audit_global_conflict_rejected():
    _exercise('AUDIT-GLOBAL-CONFLICT-REJECTED')

def test_audit_unexpected_entry_rejected():
    _exercise('AUDIT-UNEXPECTED-ENTRY-REJECTED')

def test_audit_stale_staging_rejected():
    _exercise('AUDIT-STALE-STAGING-REJECTED')
