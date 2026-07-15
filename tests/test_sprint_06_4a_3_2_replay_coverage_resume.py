from bybit_grid.data.market_store.coverage import scan_minute_coverage, scan_funding_observed_range
from bybit_grid.data.market_store.resume import plan_bounded_resume_windows
from bybit_grid.data.market_store.models import MarketStoreError
import pytest


def test_resume_rejects_unaligned_observed_timestamp():
    with pytest.raises(MarketStoreError, match="timestamp_unaligned"):
        plan_bounded_resume_windows("BTCUSDT", 0, 60000, (1,))


def test_coverage_rejects_reversed_and_out_of_window():
    with pytest.raises(MarketStoreError, match="timestamp_range_reversed"):
        scan_minute_coverage("BTCUSDT", 60000, 0, ())
    with pytest.raises(MarketStoreError, match="timestamp_out_of_window"):
        scan_minute_coverage("BTCUSDT", 0, 60000, (120000,))


def test_funding_rejects_bad_timestamp_aliases():
    for bad in (True, "0", -60000, 1):
        with pytest.raises(MarketStoreError):
            scan_funding_observed_range("BTCUSDT", (bad,))
