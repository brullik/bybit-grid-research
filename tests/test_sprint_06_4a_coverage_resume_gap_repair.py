import pytest
from bybit_grid.data.market_store.coverage import (
    scan_minute_coverage,
    plan_missing_minute_windows,
    plan_trade_mark_repairs,
    scan_funding_observed_range,
)
from bybit_grid.data.market_store.models import MarketStoreError


def test_complete_and_gapped_minute_planning():
    start = 1704067200000
    end = start + 1000 * 60000
    a = scan_minute_coverage("BTCUSDT", start, end, range(start, end + 1, 60000))
    assert a.complete_bool and a.missing_windows == ()
    b = scan_minute_coverage("BTCUSDT", start, end, [start + 60000, end])
    wins = plan_missing_minute_windows(b, max_rows=1000)
    assert wins[0].start_open_time_ms == start and wins[0].row_count == 1
    assert wins[1].row_count == 998


def test_duplicate_and_pair_readiness_and_funding_observed_only():
    s = 0
    ts = [0, 60000]
    with pytest.raises(MarketStoreError):
        scan_minute_coverage("BTCUSDT", s, 60000, [0, 0])
    tr = scan_minute_coverage("BTCUSDT", s, 60000, ts)
    mk = scan_minute_coverage("BTCUSDT", s, 60000, [0])
    assert plan_trade_mark_repairs(tr, mk)["replay_ready_bool"] is False
    f = scan_funding_observed_range("BTCUSDT", [0, 60000, 60000])
    assert (
        f.observed_count == 3
        and f.funding_coverage_proven_bool is False
        and f.duplicate_timestamps == (60000,)
    )
