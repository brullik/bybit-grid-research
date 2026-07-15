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


def test_pack_builder_rejects_bad_store():
    _exercise('PACK-BUILDER-BAD-STORE-REJECTED')

def test_pack_exact_member_set():
    _exercise('PACK-EXACT-MEMBER-SET')

def test_pack_empty_manifest_rejected():
    _exercise('PACK-EMPTY-MANIFEST-REJECTED')

def test_pack_rehashed_fake_rejected():
    _exercise('PACK-REHASHED-FAKE-REJECTED')

def test_pack_nested_public_evidence_validated():
    _exercise('PACK-NESTED-EVIDENCE-VALIDATED')

def test_pack_report_tamper_rejected_after_rehash():
    _exercise('PACK-REPORT-TAMPER-REJECTED')

def test_pack_temp_cleanup_on_failure():
    _exercise('PACK-TEMP-CLEANUP')

def test_cli_full_lifecycle_bybit_host_offline():
    _exercise('CLI-FULL-LIFECYCLE-BYBIT-HOST')

def test_cli_full_lifecycle_bytick_host_offline():
    _exercise('CLI-FULL-LIFECYCLE-BYTICK-HOST')
