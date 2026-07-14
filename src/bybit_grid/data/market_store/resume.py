from __future__ import annotations

from .coverage import plan_missing_minute_windows, scan_minute_coverage
from .models import MarketStoreError


def plan_bounded_resume_windows(symbol, start_ms, end_ms, observed_timestamps, max_rows=1000):
    """Return bounded inclusive missing-minute windows for deterministic repair/resume.

    The planner is intentionally network-free. It validates the requested symbol and
    millisecond bounds exactly, rejects aliases through the lower-level coverage
    scanner, and splits each missing interval into chunks of at most ``max_rows``
    rows.
    """
    if type(symbol) is not str or not symbol or "/" in symbol or ".." in symbol:
        raise MarketStoreError("unsafe_symbol")
    if type(max_rows) is not int or max_rows <= 0 or max_rows > 1000:
        raise MarketStoreError("max_rows_invalid")
    if type(start_ms) is not int or type(end_ms) is not int:
        raise MarketStoreError("timestamp_not_exact_int")
    if start_ms < 0 or end_ms < 0:
        raise MarketStoreError("timestamp_negative")
    if start_ms > end_ms:
        raise MarketStoreError("timestamp_range_reversed")
    for ts in observed_timestamps:
        if type(ts) is not int:
            raise MarketStoreError("timestamp_not_exact_int")
        if ts < start_ms or ts > end_ms:
            raise MarketStoreError("timestamp_out_of_window")
    audit = scan_minute_coverage(symbol, start_ms, end_ms, tuple(observed_timestamps))
    return plan_missing_minute_windows(audit, max_rows=max_rows)
