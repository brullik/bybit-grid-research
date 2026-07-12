from __future__ import annotations
from .models import InclusiveMinuteWindow, MINUTE_MS, PublicBatchError, PublicRequestPageAudit
from .parsers import (
    parse_instrument_page,
    parse_trade_kline_page,
    parse_mark_kline_page,
    parse_funding_page,
)


def plan_1m_windows(start_open_ms: int, end_open_ms: int, limit: int = 1000):
    w = InclusiveMinuteWindow(start_open_ms, end_open_ms)
    if type(limit) is not int or isinstance(limit, bool) or limit < 1:
        raise PublicBatchError("limit_invalid")
    out = []
    s = w.start_open_time_ms
    span = (limit - 1) * MINUTE_MS
    while s <= w.end_open_time_ms:
        e = min(s + span, w.end_open_time_ms)
        out.append(InclusiveMinuteWindow(s, e))
        s = e + MINUTE_MS
    return tuple(out)


def fetch_all_instruments(client, server_time, category="linear", max_pages=20):
    cursor = None
    seen_cursors = set()
    seen_symbols = set()
    metas = []
    audits = []
    for _ in range(max_pages):
        if cursor in seen_cursors:
            raise PublicBatchError("instrument_cursor_cycle")
        seen_cursors.add(cursor)
        params = {"category": category, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        raw = client.public_get("/v5/market/instruments-info", params)
        page, nextc = parse_instrument_page(raw, category, server_time.server_time_ms)
        if nextc and not page:
            raise PublicBatchError("instrument_next_cursor_empty_page")
        for m in page:
            if m.symbol in seen_symbols:
                raise PublicBatchError("duplicate_instrument_symbol")
            seen_symbols.add(m.symbol)
            metas.append(m)
        audits.append(
            PublicRequestPageAudit(
                "/v5/market/instruments-info",
                category,
                None,
                cursor,
                None,
                None,
                1000,
                len(page),
                nextc,
            )
        )
        if not nextc:
            return tuple(metas), tuple(audits)
        cursor = nextc
    raise PublicBatchError("instrument_max_pages_exceeded")


def _merge(pages, expected):
    rows = tuple(x for p in pages for x in p)
    ts = [r.open_time_ms for r in rows]
    if len(ts) != len(set(ts)):
        raise PublicBatchError("kline_cross_page_duplicate")
    if tuple(sorted(ts)) != expected.timestamps():
        raise PublicBatchError("kline_gap_or_missing_timestamp")
    return tuple(sorted(rows, key=lambda x: x.open_time_ms))


def fetch_trade_klines(client, symbol, requested_window, server_time):
    pages = []
    audits = []
    for w in plan_1m_windows(
        requested_window.start_open_time_ms, requested_window.end_open_time_ms
    ):
        raw = client.public_get(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "1",
                "start": w.start_open_time_ms,
                "end": w.end_open_time_ms,
                "limit": 1000,
            },
        )
        page = parse_trade_kline_page(
            raw, "linear", symbol, w, server_time.last_closed_open_time_ms
        )
        pages.append(page)
        audits.append(
            PublicRequestPageAudit(
                "/v5/market/kline",
                "linear",
                symbol,
                None,
                w.start_open_time_ms,
                w.end_open_time_ms,
                1000,
                len(page),
                None,
            )
        )
    return _merge(pages, requested_window), tuple(audits)


def fetch_mark_klines(client, symbol, requested_window, server_time):
    pages = []
    audits = []
    for w in plan_1m_windows(
        requested_window.start_open_time_ms, requested_window.end_open_time_ms
    ):
        raw = client.public_get(
            "/v5/market/mark-price-kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "1",
                "start": w.start_open_time_ms,
                "end": w.end_open_time_ms,
                "limit": 1000,
            },
        )
        page = parse_mark_kline_page(raw, "linear", symbol, w, server_time.last_closed_open_time_ms)
        pages.append(page)
        audits.append(
            PublicRequestPageAudit(
                "/v5/market/mark-price-kline",
                "linear",
                symbol,
                None,
                w.start_open_time_ms,
                w.end_open_time_ms,
                1000,
                len(page),
                None,
            )
        )
    return _merge(pages, requested_window), tuple(audits)


def fetch_funding_history_backward(client, symbol, start_ms, end_ms, limit=200):
    page_end = end_ms
    rows = []
    audits = []
    seen_pages = set()
    seen_ts = set()
    while page_end >= start_ms:
        key = (start_ms, page_end)
        if key in seen_pages:
            raise PublicBatchError("funding_repeated_page")
        seen_pages.add(key)
        raw = client.public_get(
            "/v5/market/funding/history",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": start_ms,
                "endTime": page_end,
                "limit": limit,
            },
        )
        page = parse_funding_page(raw, "linear", symbol, start_ms, page_end)
        audits.append(
            PublicRequestPageAudit(
                "/v5/market/funding/history",
                "linear",
                symbol,
                None,
                start_ms,
                page_end,
                limit,
                len(page),
                None,
            )
        )
        if not page:
            break
        min_t = min(r.funding_time_ms for r in page)
        if min_t > page_end:
            raise PublicBatchError("funding_no_progress")
        for r in page:
            if r.funding_time_ms in seen_ts:
                raise PublicBatchError("duplicate_funding_timestamp")
            seen_ts.add(r.funding_time_ms)
            rows.append(r)
        new_end = min_t - 1
        if new_end >= page_end:
            raise PublicBatchError("funding_no_progress")
        page_end = new_end
        if min_t <= start_ms:
            break
    return tuple(sorted(rows, key=lambda x: x.funding_time_ms)), tuple(audits)
