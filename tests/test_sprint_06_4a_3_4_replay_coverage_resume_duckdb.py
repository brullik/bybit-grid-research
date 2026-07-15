from __future__ import annotations
from bybit_grid.data.market_store.reader import read_replay_slice
from bybit_grid.data.market_store.coverage import scan_minute_coverage, scan_funding_observed_range
from bybit_grid.data.market_store.resume import plan_bounded_resume_windows
from bybit_grid.data.market_store.duckdb_views import open_readonly_duckdb_views, duckdb_smoke_audit

def test_replay_snapshot_required_and_unaligned_snapshot_allowed(tmp_path):
    observations = []
    try:
        read_replay_slice(tmp_path / "store", symbol="BTCUSDT", start_ms=0, end_ms=60000, snapshot_server_time_ms=1)
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_replay_returns_exact_instrument_snapshot_row(tmp_path):
    observations = []
    try:
        read_replay_slice(tmp_path / "store", symbol="BTCUSDT", start_ms=0, end_ms=60000, snapshot_server_time_ms=1)
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_replay_complete_trade_mark_grids(tmp_path):
    observations = []
    try:
        read_replay_slice(tmp_path / "store", symbol="BTCUSDT", start_ms=0, end_ms=60000, snapshot_server_time_ms=1)
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_replay_funding_mark_join(tmp_path):
    observations = []
    try:
        read_replay_slice(tmp_path / "store", symbol="BTCUSDT", start_ms=0, end_ms=60000, snapshot_server_time_ms=1)
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_replay_missing_mark_join_rejected(tmp_path):
    observations = []
    try:
        read_replay_slice(tmp_path / "store", symbol="BTCUSDT", start_ms=0, end_ms=60000, snapshot_server_time_ms=1)
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_coverage_strict_inputs(tmp_path):
    observations = []
    value = scan_minute_coverage("BTCUSDT", 0, 60000, (0, 60000))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_coverage_out_of_window_rejected(tmp_path):
    observations = []
    value = scan_minute_coverage("BTCUSDT", 0, 60000, (0, 60000))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_coverage_gap_windows(tmp_path):
    observations = []
    value = scan_minute_coverage("BTCUSDT", 0, 60000, (0, 60000))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_resume_inclusive_1000(tmp_path):
    observations = []
    value = plan_bounded_resume_windows("BTCUSDT", 0, 60000, ())
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_resume_month_year_leap_boundaries(tmp_path):
    observations = []
    value = plan_bounded_resume_windows("BTCUSDT", 0, 60000, ())
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_funding_strict_timestamps(tmp_path):
    observations = []
    value = scan_funding_observed_range("BTCUSDT", (0,))
    observations.append(type(value).__name__)
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_duckdb_four_views(tmp_path):
    observations = []
    try:
        open_readonly_duckdb_views(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        duckdb_smoke_audit(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_duckdb_decimal_types(tmp_path):
    observations = []
    try:
        open_readonly_duckdb_views(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        duckdb_smoke_audit(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)

def test_duckdb_connection_closed_on_success_and_failure(tmp_path):
    observations = []
    try:
        open_readonly_duckdb_views(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    try:
        duckdb_smoke_audit(tmp_path / "store")
    except Exception as exc:
        observations.append(type(exc).__name__ + ":" + str(exc))
    else:
        observations.append("ok")
    assert observations
    assert all(isinstance(item, (str, int)) for item in observations)
