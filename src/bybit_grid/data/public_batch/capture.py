from __future__ import annotations

from .assemble import assemble_bybit_public_replay_batch_from_rows
from .audit import audit_instrument_universe
from .models import InclusiveMinuteWindow, MINUTE_MS, PublicBatchError
from .pagination import (
    fetch_all_instruments,
    fetch_funding_history_backward,
    fetch_funding_history_chunked,
    fetch_mark_klines,
    fetch_trade_klines,
)
from .parsers import parse_server_time

SYMBOL = "BTCUSDT"


def derive_closed_window(server_time, row_count: int) -> InclusiveMinuteWindow:
    if type(row_count) is not int or row_count < 1:
        raise PublicBatchError("kline_row_count_invalid")
    end = server_time.last_closed_open_time_ms
    return InclusiveMinuteWindow(end - (row_count - 1) * MINUTE_MS, end)


def run_capture_plans(client, *, symbol=SYMBOL, kline_row_count=1001, funding_lookback_days=100):
    server_payload = client.for_plan("server_time_snapshot").public_get("/v5/market/time", {})
    server_time = parse_server_time(server_payload)
    window = derive_closed_window(server_time, kline_row_count)
    ip, ip_aud = fetch_all_instruments(
        client.for_plan("instrument_primary_1000"), server_time, limit=1000
    )
    ia, ia_aud = fetch_all_instruments(
        client.for_plan("instrument_alternate_200"), server_time, limit=200
    )
    if tuple(sorted(ip, key=lambda x: x.symbol)) != tuple(sorted(ia, key=lambda x: x.symbol)):
        raise PublicBatchError("instrument_primary_alternate_mismatch")
    inst_audit = audit_instrument_universe(ip)
    alt_audit = audit_instrument_universe(ia)
    if not inst_audit.universe_audit_ok or not alt_audit.universe_audit_ok:
        raise PublicBatchError("instrument_universe_audit_failed")
    matches = [m for m in ip if m.symbol == symbol]
    if len(matches) != 1:
        raise PublicBatchError("instrument_match_not_unique")
    instrument = matches[0]
    tp, tp_aud = fetch_trade_klines(
        client.for_plan("trade_primary_1000"), symbol, window, server_time, page_limit=1000
    )
    ta, ta_aud = fetch_trade_klines(
        client.for_plan("trade_alternate_251"), symbol, window, server_time, page_limit=251
    )
    mp, mp_aud = fetch_mark_klines(
        client.for_plan("mark_primary_1000"), symbol, window, server_time, page_limit=1000
    )
    ma, ma_aud = fetch_mark_klines(
        client.for_plan("mark_alternate_251"), symbol, window, server_time, page_limit=251
    )
    if tp != ta or mp != ma:
        raise PublicBatchError("kline_primary_alternate_mismatch")
    fund_start = window.end_open_time_ms - funding_lookback_days * 24 * 60 * MINUTE_MS
    fp, fp_aud = fetch_funding_history_backward(
        client.for_plan("funding_primary_backward_200"),
        symbol,
        fund_start,
        window.end_open_time_ms,
        limit=200,
    )
    fa, fa_aud = fetch_funding_history_chunked(
        client.for_plan("funding_alternate_chunked_100"),
        symbol,
        fund_start,
        window.end_open_time_ms,
        instrument.funding_interval_minutes,
        target_records_per_window=100,
        page_limit=200,
    )
    if fp != fa:
        raise PublicBatchError("funding_primary_alternate_mismatch")
    batch = assemble_bybit_public_replay_batch_from_rows(
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        trade_rows=tp,
        mark_rows=mp,
        funding_rows=fp,
        request_page_audits=ip_aud + tp_aud + mp_aud + fp_aud,
    )
    return {
        "server_time": server_time,
        "window": window,
        "instrument": instrument,
        "instrument_rows": ip,
        "instrument_audit": inst_audit,
        "trade_rows": tp,
        "mark_rows": mp,
        "funding_rows": fp,
        "funding_observations": batch.funding_observations,
        "request_audits": ip_aud + ia_aud + tp_aud + ta_aud + mp_aud + ma_aud + fp_aud + fa_aud,
        "batch": batch,
    }
