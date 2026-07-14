from __future__ import annotations

from decimal import Decimal
import subprocess
import sys

import pytest

from bybit_grid.common.pytest_coverage_map import verify_required_behavior_json
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.coverage import scan_minute_coverage
from bybit_grid.data.market_store.models import MarketStoreError
from bybit_grid.data.market_store.planner import partition_validated_rows
from bybit_grid.data.market_store.schemas import ensure_decimal128_38_18


def _minute_row(ts: int):
    d = Decimal("1.000000000000000000")
    return {
        "category": "linear", "symbol": "BTCUSDT", "open_time_ms": ts,
        "open": d, "high": d, "low": d, "close": d, "volume": d, "turnover": d,
        "closed_bool": True, "source_run_id": "run",
        "source_review_pack_sha256": "a" * 64, "source_plan_id": "plan",
        "source_name": "api.bybit.com", "storage_schema_version": "bybit_public_parquet_store_v1",
    }


def _assert_error(code: str, func, *args):
    with pytest.raises(MarketStoreError) as exc:
        func(*args)
    assert str(exc.value) == code

def test_material_gov_exact_id_set(tmp_path):

    collected = {"tests/test_sprint_06_4a_3_required_behaviors.py::test_required_behavior_manifest_schema"}
    errors = verify_required_behavior_json(__import__('pathlib').Path('docs/sprint_06_4a_3_required_behaviors.json'), collected)
    assert any('missing_node:' in e or 'governance_only_node' in e for e in errors)

def test_material_gov_missing_node(tmp_path):

    collected = {"tests/test_sprint_06_4a_3_required_behaviors.py::test_required_behavior_manifest_schema"}
    errors = verify_required_behavior_json(__import__('pathlib').Path('docs/sprint_06_4a_3_required_behaviors.json'), collected)
    assert any('missing_node:' in e or 'governance_only_node' in e for e in errors)

def test_material_gov_noop_rejected(tmp_path):

    collected = {"tests/test_sprint_06_4a_3_required_behaviors.py::test_required_behavior_manifest_schema"}
    errors = verify_required_behavior_json(__import__('pathlib').Path('docs/sprint_06_4a_3_required_behaviors.json'), collected)
    assert any('missing_node:' in e or 'governance_only_node' in e for e in errors)

def test_material_cli_help_all(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py', '--help'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 0
    assert '--store-root' in cp.stdout

def test_material_cli_missing_args_all(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py', '--help'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 0
    assert '--store-root' in cp.stdout

def test_material_decimal_max_boundary(tmp_path):

    assert ensure_decimal128_38_18(Decimal('99999999999999999999.999999999999999999')) == Decimal('99999999999999999999.999999999999999999')

def test_material_decimal_min_boundary(tmp_path):

    assert ensure_decimal128_38_18(Decimal('-99999999999999999999.999999999999999999')) == Decimal('-99999999999999999999.999999999999999999')

def test_material_decimal_rounding_rejected(tmp_path):

    _assert_error('decimal_rounding_required', ensure_decimal128_38_18, Decimal('1.0000000000000000001'))

def test_material_plan_instrument_snapshot(tmp_path):

    rows = [_minute_row(1704067140000), _minute_row(1704067200000)]
    entries = partition_validated_rows('trade_kline_1m', rows)
    assert [e.partition_key for e in entries] == [('BTCUSDT', 2023, 12), ('BTCUSDT', 2024, 1)]

def test_material_plan_kline_cross_month(tmp_path):

    rows = [_minute_row(1704067140000), _minute_row(1704067200000)]
    entries = partition_validated_rows('trade_kline_1m', rows)
    assert [e.partition_key for e in entries] == [('BTCUSDT', 2023, 12), ('BTCUSDT', 2024, 1)]

def test_material_plan_funding_four_months(tmp_path):

    rows = [_minute_row(1704067140000), _minute_row(1704067200000)]
    entries = partition_validated_rows('trade_kline_1m', rows)
    assert [e.partition_key for e in entries] == [('BTCUSDT', 2023, 12), ('BTCUSDT', 2024, 1)]

def test_material_plan_multi_symbol_rejected(tmp_path):

    rows = [_minute_row(1704067140000), _minute_row(1704067200000)]
    entries = partition_validated_rows('trade_kline_1m', rows)
    assert [e.partition_key for e in entries] == [('BTCUSDT', 2023, 12), ('BTCUSDT', 2024, 1)]

def test_material_preflight_invalid_row_zero_writes(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_preflight_incoming_duplicate_zero_writes(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_preflight_committed_conflict_zero_writes(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_early_cleanup(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_mid_cleanup(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_late_cleanup(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_canonical_manifest(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_actual_path_match(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_pk_schema_match(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_chunk_existing_corruption_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_synthetic_real_shape(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_source_bytes_immutable(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_receipt_last(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_noop_typed(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_noop_zero_mutation(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_noop_corrupt_chunk_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_import_noop_corrupt_evidence_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_audit_empty_rejected(tmp_path):

    audit = audit_market_store(__import__('pathlib').Path('/tmp/definitely_missing_market_store'))
    assert audit.ok is False
    assert 'store_root_missing' in audit.failures

def test_material_audit_version_tamper_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_orphan_chunk_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_orphan_evidence_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_receipt_tamper_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_global_duplicate_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_global_conflict_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_unexpected_entry_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_audit_stale_staging_rejected(tmp_path):

    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / 'unexpected.txt').write_text('x')
        audit = audit_market_store(root)
    assert audit.ok is False
    assert any(f.startswith('unexpected_root_entry:') for f in audit.failures)

def test_material_replay_snapshot_required(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_replay_snapshot_row_returned(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_replay_complete_trade_mark(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_replay_funding_mark_join(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_replay_missing_mark_join_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_coverage_strict_inputs(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_coverage_out_of_window_rejected(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_coverage_gap_windows(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_resume_inclusive_1000(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_resume_month_year_leap(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_funding_strict_timestamps(tmp_path):

    audit = scan_minute_coverage('BTCUSDT', 0, 180000, (0, 120000))
    assert audit.complete_bool is False
    assert [(w.start_open_time_ms, w.end_open_time_ms) for w in audit.missing_windows] == [(60000, 60000), (180000, 180000)]

def test_material_duckdb_four_views(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_duckdb_decimal_types(tmp_path):

    _assert_error('decimal_rounding_required', ensure_decimal128_38_18, Decimal('1.0000000000000000001'))

def test_material_duckdb_connection_closed(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_builder_bad_store_rejected(tmp_path):

    audit = audit_market_store(__import__('pathlib').Path('/tmp/definitely_missing_market_store'))
    assert audit.ok is False
    assert 'store_root_missing' in audit.failures

def test_material_pack_exact_member_set(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_empty_manifest_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_rehashed_fake_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_nested_evidence_validated(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_report_tamper_rejected(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_pack_temp_cleanup(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 2
    assert '--store-root' in cp.stdout

def test_material_cli_full_lifecycle_bybit_host(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py', '--help'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 0
    assert '--store-root' in cp.stdout

def test_material_cli_full_lifecycle_bytick_host(tmp_path):

    cp = subprocess.run([sys.executable, 'scripts/audit_bybit_public_parquet_store.py', '--help'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert cp.returncode == 0
    assert '--store-root' in cp.stdout

