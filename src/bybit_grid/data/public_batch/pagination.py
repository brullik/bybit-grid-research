from __future__ import annotations
from .models import InclusiveMinuteWindow, MINUTE_MS, PublicBatchError, PublicRequestPageAudit
from .parsers import (
    parse_instrument_page,
    parse_trade_kline_page,
    parse_mark_kline_page,
    parse_funding_page,
)


def _validate_limit(limit, name, maximum):
    if type(limit) is not int or limit < 1 or limit > maximum:
        raise PublicBatchError(f"{name}_invalid")


def plan_1m_windows(start_open_ms: int, end_open_ms: int, limit: int = 1000):
    w = InclusiveMinuteWindow(start_open_ms, end_open_ms)
    _validate_limit(limit, "limit", 1000)
    out = []
    s = w.start_open_time_ms
    span = (limit - 1) * MINUTE_MS
    while s <= w.end_open_time_ms:
        e = min(s + span, w.end_open_time_ms)
        out.append(InclusiveMinuteWindow(s, e))
        s = e + MINUTE_MS
    return tuple(out)


def fetch_all_instruments(client, server_time, category="linear", max_pages=20, limit=1000):
    _validate_limit(limit, "instrument_limit", 1000)
    cursor = None
    seen_cursors = set()
    seen_symbols = set()
    metas = []
    audits = []
    for _ in range(max_pages):
        if cursor in seen_cursors:
            raise PublicBatchError("instrument_cursor_cycle")
        seen_cursors.add(cursor)
        params = {"category": category, "status": "Trading", "limit": limit}
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
                limit,
                len(page),
                nextc,
                getattr(client, "plan_id", ""),
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


def fetch_trade_klines(client, symbol, requested_window, server_time, page_limit=1000):
    _validate_limit(page_limit, "kline_limit", 1000)
    pages = []
    audits = []
    for w in plan_1m_windows(
        requested_window.start_open_time_ms, requested_window.end_open_time_ms, page_limit
    ):
        raw = client.public_get(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "1",
                "start": w.start_open_time_ms,
                "end": w.end_open_time_ms,
                "limit": page_limit,
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
                page_limit,
                len(page),
                None,
                getattr(client, "plan_id", ""),
            )
        )
    return _merge(pages, requested_window), tuple(audits)


def fetch_mark_klines(client, symbol, requested_window, server_time, page_limit=1000):
    _validate_limit(page_limit, "kline_limit", 1000)
    pages = []
    audits = []
    for w in plan_1m_windows(
        requested_window.start_open_time_ms, requested_window.end_open_time_ms, page_limit
    ):
        raw = client.public_get(
            "/v5/market/mark-price-kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "1",
                "start": w.start_open_time_ms,
                "end": w.end_open_time_ms,
                "limit": page_limit,
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
                page_limit,
                len(page),
                None,
                getattr(client, "plan_id", ""),
            )
        )
    return _merge(pages, requested_window), tuple(audits)


def fetch_funding_history_backward(client, symbol, start_ms, end_ms, limit=200):
    _validate_limit(limit, "funding_limit", 200)
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
                getattr(client, "plan_id", ""),
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


def fetch_funding_history_chunked(
    client,
    symbol,
    start_ms,
    end_ms,
    funding_interval_minutes,
    *,
    target_records_per_window=100,
    page_limit=200,
):
    if type(start_ms) is not int or type(end_ms) is not int or start_ms > end_ms:
        raise PublicBatchError("funding_chunk_range_invalid")
    if type(funding_interval_minutes) is not int or funding_interval_minutes <= 0:
        raise PublicBatchError("funding_interval_invalid")
    _validate_limit(target_records_per_window, "funding_target_records", 200)
    _validate_limit(page_limit, "funding_limit", 200)
    if target_records_per_window >= page_limit:
        raise PublicBatchError("funding_chunk_truncation_risk")
    interval_ms = funding_interval_minutes * MINUTE_MS
    chunk_span = (target_records_per_window - 1) * interval_ms
    rows = []
    audits = []
    seen = set()
    chunk_start = start_ms
    while chunk_start <= end_ms:
        chunk_end = min(chunk_start + chunk_span, end_ms)
        raw = client.public_get(
            "/v5/market/funding/history",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": chunk_start,
                "endTime": chunk_end,
                "limit": page_limit,
            },
        )
        page = parse_funding_page(raw, "linear", symbol, chunk_start, chunk_end)
        if len(page) >= page_limit:
            raise PublicBatchError("funding_chunk_truncation_risk")
        audits.append(
            PublicRequestPageAudit(
                "/v5/market/funding/history",
                "linear",
                symbol,
                None,
                chunk_start,
                chunk_end,
                page_limit,
                len(page),
                None,
                getattr(client, "plan_id", ""),
            )
        )
        for row in page:
            if row.funding_time_ms < chunk_start or row.funding_time_ms > chunk_end:
                raise PublicBatchError("funding_outside_requested_range")
            if row.funding_time_ms in seen:
                raise PublicBatchError("duplicate_funding_timestamp")
            seen.add(row.funding_time_ms)
            rows.append(row)
        new_start = chunk_end + 1
        if new_start <= chunk_start:
            raise PublicBatchError("funding_no_progress")
        chunk_start = new_start
    return tuple(sorted(rows, key=lambda x: x.funding_time_ms)), tuple(audits)
