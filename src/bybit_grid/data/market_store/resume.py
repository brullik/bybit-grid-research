from __future__ import annotations

from .coverage import _validate_observed, _validate_window, plan_missing_minute_windows, scan_minute_coverage
from .models import MarketStoreError


def plan_bounded_resume_windows(symbol, start_ms, end_ms, observed_timestamps, max_rows=1000):
    """Return bounded inclusive missing-minute windows for deterministic repair/resume."""
    if type(max_rows) is not int or max_rows <= 0 or max_rows > 1000:
        raise MarketStoreError("max_rows_invalid")
    _validate_window(symbol, start_ms, end_ms)
    if type(observed_timestamps) not in (tuple, list):
        raise MarketStoreError("observed_timestamps_invalid")
    observed = _validate_observed(observed_timestamps, start_ms, end_ms)
    audit = scan_minute_coverage(symbol, start_ms, end_ms, observed)
    return plan_missing_minute_windows(audit, max_rows=max_rows)
