from __future__ import annotations
from collections import Counter
from .paths import safe_symbol
from .models import (
    CoverageInterval,
    FundingObservedRangeAudit,
    MarketStoreError,
    MinuteCoverageAudit,
    MissingMinuteWindow,
)


def _validate_symbol(symbol):
    return safe_symbol(symbol)


def _validate_minute_ts(v, name="timestamp"):
    if type(v) is not int:
        raise MarketStoreError(f"{name}_not_exact_int")
    if v < 0:
        raise MarketStoreError(f"{name}_negative")
    if v % 60000:
        raise MarketStoreError(f"{name}_unaligned")
    return v


def _validate_window(symbol, start_ms, end_ms):
    _validate_symbol(symbol)
    _validate_minute_ts(start_ms, "start")
    _validate_minute_ts(end_ms, "end")
    if start_ms > end_ms:
        raise MarketStoreError("timestamp_range_reversed")


def _validate_observed(timestamps, start_ms=None, end_ms=None, reject_duplicates=True):
    out = []
    for ts in timestamps:
        _validate_minute_ts(ts)
        if start_ms is not None and (ts < start_ms or ts > end_ms):
            raise MarketStoreError("timestamp_out_of_window")
        out.append(ts)
    c = Counter(out)
    dups = tuple(sorted(k for k, v in c.items() if v > 1))
    if dups and reject_duplicates:
        raise MarketStoreError("duplicate_timestamp")
    return tuple(out)


def scan_minute_coverage(symbol, start_ms, end_ms, timestamps):
    _validate_window(symbol, start_ms, end_ms)
    present = sorted(_validate_observed(timestamps, start_ms, end_ms))
    miss = []
    ints = []

    def add(seq, cls, out):
        if not seq:
            return
        s = p = seq[0]
        for x in seq[1:]:
            if x == p + 60000:
                p = x
            else:
                out.append(cls(s, p, (p - s) // 60000 + 1))
                s = p = x
        out.append(cls(s, p, (p - s) // 60000 + 1))

    add(present, CoverageInterval, ints)
    expected = set(range(start_ms, end_ms + 1, 60000))
    add(sorted(expected - set(present)), MissingMinuteWindow, miss)
    return MinuteCoverageAudit(symbol, start_ms, end_ms, tuple(ints), tuple(miss), (), not miss)


def plan_missing_minute_windows(audit, max_rows=1000):
    if type(audit) is not MinuteCoverageAudit:
        raise MarketStoreError("minute_coverage_audit_invalid")
    if type(max_rows) is not int or max_rows <= 0 or max_rows > 1000:
        raise MarketStoreError("max_rows_invalid")
    out = []
    for w in audit.missing_windows:
        s = w.start_open_time_ms
        while s <= w.end_open_time_ms:
            e = min(w.end_open_time_ms, s + (max_rows - 1) * 60000)
            out.append(MissingMinuteWindow(s, e, (e - s) // 60000 + 1))
            s = e + 60000
    return tuple(out)


def plan_trade_mark_repairs(trade_audit, mark_audit, max_rows=1000):
    if type(trade_audit) is not MinuteCoverageAudit or type(mark_audit) is not MinuteCoverageAudit:
        raise MarketStoreError("minute_coverage_audit_invalid")
    if (trade_audit.symbol, trade_audit.start_open_time_ms, trade_audit.end_open_time_ms) != (mark_audit.symbol, mark_audit.start_open_time_ms, mark_audit.end_open_time_ms):
        raise MarketStoreError("coverage_window_mismatch")
    return {
        "trade_missing_windows": plan_missing_minute_windows(trade_audit, max_rows),
        "mark_missing_windows": plan_missing_minute_windows(mark_audit, max_rows),
        "replay_ready_bool": trade_audit.complete_bool
        and mark_audit.complete_bool
        and trade_audit.present_intervals == mark_audit.present_intervals,
    }


def scan_funding_observed_range(symbol, timestamps):
    _validate_symbol(symbol)
    observed = _validate_observed(timestamps, reject_duplicates=False)
    c = Counter(observed)
    dups = tuple(sorted(k for k, v in c.items() if v > 1))
    u = sorted(c)
    return FundingObservedRangeAudit(
        symbol, len(observed), u[0] if u else None, u[-1] if u else None, dups, False
    )
