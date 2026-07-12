from __future__ import annotations
from decimal import Decimal
from .models import BybitFundingRate, BybitInstrumentMeta, BybitMarkKline1m, BybitServerTime, BybitTradeKline1m, MINUTE_MS, PublicBatchError


def _dict(x, n):
    if type(x) is not dict:
        raise PublicBatchError(f"{n}_not_dict")
    return x


def _ret(raw):
    r = _dict(raw, "response")
    if r.get("retCode") not in (0, "0"):
        raise PublicBatchError("retCode_not_zero")
    return _dict(r.get("result"), "result")


def _tok(x, n):
    if type(x) is float:
        raise PublicBatchError(f"{n}_float_rejected")
    if type(x) is not str or x == "":
        raise PublicBatchError(f"{n}_not_string")
    return Decimal(x)


def _ms(x, n):
    if type(x) is bool:
        raise PublicBatchError(f"{n}_bool_rejected")
    if type(x) is int:
        return x
    if type(x) is str and x.isdigit():
        return int(x)
    raise PublicBatchError(f"{n}_invalid_ms")


def parse_server_time(raw, tolerance_ms=999):
    res = _ret(raw)
    tn = _ms(res.get("timeNano"), "timeNano")
    ts = _ms(res.get("timeSecond"), "timeSecond")
    top = _ms(_dict(raw, "response").get("time"), "time")
    ms = tn // 1_000_000
    if abs(ms - ts * 1000) > tolerance_ms or abs(ms - top) > tolerance_ms:
        raise PublicBatchError("server_time_inconsistent")
    return BybitServerTime(ms, ts, tn, top, (ms // MINUTE_MS) * MINUTE_MS - MINUTE_MS)


def parse_instrument_page(raw, category, snapshot_server_time_ms):
    res = _ret(raw)
    if res.get("category") != category:
        raise PublicBatchError("instrument_category_mismatch")
    rows = res.get("list")
    if type(rows) is not list:
        raise PublicBatchError("instrument_list_not_list")
    out = []
    for it in rows:
        it = _dict(it, "instrument")
        pf = _dict(it.get("priceFilter"), "priceFilter")
        lf = _dict(it.get("lotSizeFilter"), "lotSizeFilter")
        lev = _dict(it.get("leverageFilter"), "leverageFilter")
        out.append(
            BybitInstrumentMeta(
                category,
                it["symbol"],
                it["contractType"],
                it["status"],
                it["baseCoin"],
                it["quoteCoin"],
                it["settleCoin"],
                _ms(it["launchTime"], "launchTime"),
                _ms(it["deliveryTime"], "deliveryTime"),
                it["isPreListing"],
                _ms(it["fundingInterval"], "fundingInterval"),
                _tok(pf["tickSize"], "tickSize"),
                _tok(lf["qtyStep"], "qtyStep"),
                _tok(lf["minOrderQty"], "minOrderQty"),
                _tok(lf["minNotionalValue"], "minNotionalValue"),
                _tok(lev["minLeverage"], "minLeverage"),
                _tok(lev["maxLeverage"], "maxLeverage"),
                _tok(lev["leverageStep"], "leverageStep"),
                snapshot_server_time_ms,
            )
        )
    return tuple(out), res.get("nextPageCursor") or None


def _parse_k(raw, category, symbol, window, last_closed, mark=False):
    res = _ret(raw)
    if res.get("category") != category or res.get("symbol") != symbol:
        raise PublicBatchError("kline_category_symbol_mismatch")
    rows = res.get("list")
    if type(rows) is not list:
        raise PublicBatchError("kline_list_not_list")
    seen = set()
    out = []
    need = 5 if mark else 7
    for row in rows:
        if type(row) is not list or len(row) != need:
            raise PublicBatchError("kline_row_length_invalid")
        t = _ms(row[0], "startTime")
        if t in seen:
            raise PublicBatchError("duplicate_kline_timestamp")
        seen.add(t)
        if t < window.start_open_time_ms or t > window.end_open_time_ms:
            raise PublicBatchError("kline_outside_requested_window")
        if t > last_closed:
            raise PublicBatchError("kline_unclosed")
        vals = [_tok(v, "kline_numeric") for v in row[1:]]
        cls = BybitMarkKline1m if mark else BybitTradeKline1m
        out.append(cls(category, symbol, t, *vals, True))
    return tuple(sorted(out, key=lambda x: x.open_time_ms))


def parse_trade_kline_page(raw, category, symbol, window, last_closed_open_time_ms):
    return _parse_k(raw, category, symbol, window, last_closed_open_time_ms, False)


def parse_mark_kline_page(raw, category, symbol, window, last_closed_open_time_ms):
    return _parse_k(raw, category, symbol, window, last_closed_open_time_ms, True)


def parse_funding_page(raw, category, symbol, start_ms, end_ms):
    res = _ret(raw)
    rows = res.get("list")
    if type(rows) is not list:
        raise PublicBatchError("funding_list_not_list")
    seen = set()
    out = []
    for it in rows:
        it = _dict(it, "funding_row")
        if it.get("category", category) != category or it.get("symbol") != symbol:
            raise PublicBatchError("funding_category_symbol_mismatch")
        t = _ms(it["fundingRateTimestamp"], "fundingRateTimestamp")
        if t in seen:
            raise PublicBatchError("duplicate_funding_timestamp")
        seen.add(t)
        if t < start_ms or t > end_ms:
            raise PublicBatchError("funding_outside_requested_range")
        out.append(BybitFundingRate(category, symbol, t, _tok(it["fundingRate"], "fundingRate")))
    return tuple(sorted(out, key=lambda x: x.funding_time_ms))
