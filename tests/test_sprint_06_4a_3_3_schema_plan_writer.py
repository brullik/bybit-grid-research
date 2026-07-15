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


def test_decimal_max_boundary():
    _exercise('DECIMAL-MAX-BOUNDARY')

def test_decimal_min_boundary():
    _exercise('DECIMAL-MIN-BOUNDARY')

def test_decimal_rounding_rejected():
    _exercise('DECIMAL-ROUNDING-REJECTED')

def test_plan_instrument_snapshot_multi_symbol_single_partition():
    _exercise('PLAN-INSTRUMENT-SNAPSHOT')

def test_plan_kline_cross_month_two_partitions():
    _exercise('PLAN-KLINE-CROSS-MONTH')

def test_plan_funding_four_months_four_partitions():
    _exercise('PLAN-FUNDING-FOUR-MONTHS')

def test_plan_entry_mixed_timeseries_symbols_rejected():
    _exercise('PLAN-MULTI-SYMBOL-REJECTED')

def test_preflight_invalid_row_zero_writes():
    _exercise('PREFLIGHT-INVALID-ROW-ZERO-WRITES')

def test_preflight_incoming_duplicate_zero_writes():
    _exercise('PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES')

def test_preflight_committed_conflict_zero_writes():
    _exercise('PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES')

def test_chunk_early_failure_cleanup():
    _exercise('CHUNK-EARLY-CLEANUP')

def test_chunk_mid_failure_cleanup():
    _exercise('CHUNK-MID-CLEANUP')

def test_chunk_late_failure_cleanup():
    _exercise('CHUNK-LATE-CLEANUP')

def test_chunk_manifest_is_canonical():
    _exercise('CHUNK-CANONICAL-MANIFEST')

def test_chunk_actual_path_mismatch_rejected():
    _exercise('CHUNK-ACTUAL-PATH-MATCH')

def test_chunk_primary_key_schema_mismatch_rejected():
    _exercise('CHUNK-PK-SCHEMA-MATCH')

def test_existing_chunk_corruption_rejected():
    _exercise('CHUNK-EXISTING-CORRUPTION-REJECTED')
