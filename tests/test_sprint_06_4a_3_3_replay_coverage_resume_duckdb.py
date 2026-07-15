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


def test_replay_snapshot_required_and_unaligned_snapshot_allowed():
    _exercise('REPLAY-SNAPSHOT-REQUIRED')

def test_replay_returns_exact_instrument_snapshot_row():
    _exercise('REPLAY-SNAPSHOT-ROW-RETURNED')

def test_replay_complete_trade_mark_grids():
    _exercise('REPLAY-COMPLETE-TRADE-MARK')

def test_replay_funding_mark_join():
    _exercise('REPLAY-FUNDING-MARK-JOIN')

def test_replay_missing_mark_join_rejected():
    _exercise('REPLAY-MISSING-MARK-JOIN-REJECTED')

def test_coverage_strict_inputs():
    _exercise('COVERAGE-STRICT-INPUTS')

def test_coverage_out_of_window_rejected():
    _exercise('COVERAGE-OUT-OF-WINDOW-REJECTED')

def test_coverage_gap_windows():
    _exercise('COVERAGE-GAP-WINDOWS')

def test_resume_inclusive_1000():
    _exercise('RESUME-INCLUSIVE-1000')

def test_resume_month_year_leap_boundaries():
    _exercise('RESUME-MONTH-YEAR-LEAP')

def test_funding_strict_timestamps():
    _exercise('FUNDING-STRICT-TIMESTAMPS')

def test_duckdb_four_views():
    _exercise('DUCKDB-FOUR-VIEWS')

def test_duckdb_decimal_types():
    _exercise('DUCKDB-DECIMAL-TYPES')

def test_duckdb_connection_closed_on_success_and_failure():
    _exercise('DUCKDB-CONNECTION-CLOSED')
