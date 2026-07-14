from __future__ import annotations
from collections import Counter
from .models import (
    CoverageInterval,
    FundingObservedRangeAudit,
    MarketStoreError,
    MinuteCoverageAudit,
    MissingMinuteWindow,
)


def scan_minute_coverage(symbol, start_ms, end_ms, timestamps):
    for n, v in [("start", start_ms), ("end", end_ms)]:
        if type(v) is not int or v % 60000:
            raise MarketStoreError(f"{n}_invalid")
    c = Counter(timestamps)
    dups = tuple(sorted(k for k, v in c.items() if v > 1))
    if dups:
        raise MarketStoreError("duplicate_timestamp")
    present = sorted(set(timestamps))
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

    add([x for x in present if start_ms <= x <= end_ms], CoverageInterval, ints)
    expected = set(range(start_ms, end_ms + 1, 60000))
    add(sorted(expected - set(present)), MissingMinuteWindow, miss)
    return MinuteCoverageAudit(symbol, start_ms, end_ms, tuple(ints), tuple(miss), dups, not miss)


def plan_missing_minute_windows(audit, max_rows=1000):
    if type(max_rows) is not int or max_rows <= 0:
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
    return {
        "trade_missing_windows": plan_missing_minute_windows(trade_audit, max_rows),
        "mark_missing_windows": plan_missing_minute_windows(mark_audit, max_rows),
        "replay_ready_bool": trade_audit.complete_bool
        and mark_audit.complete_bool
        and trade_audit.present_intervals == mark_audit.present_intervals,
    }


def scan_funding_observed_range(symbol, timestamps):
    c = Counter(timestamps)
    d = tuple(sorted(k for k, v in c.items() if v > 1))
    u = sorted(c)
    return FundingObservedRangeAudit(
        symbol, len(timestamps), u[0] if u else None, u[-1] if u else None, d, False
    )
