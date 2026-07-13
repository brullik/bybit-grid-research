from __future__ import annotations
from .models import BybitPublicReplayBatch, MINUTE_MS, PublicBatchError
from .parsers import parse_server_time
from .pagination import (
    fetch_all_instruments,
    fetch_trade_klines,
    fetch_mark_klines,
    fetch_funding_history_backward,
)


def assemble_bybit_public_replay_batch_from_rows(
    *,
    instrument,
    server_time,
    requested_window,
    trade_rows,
    mark_rows,
    funding_rows,
    request_page_audits,
):
    from .audit import audit_bybit_public_replay_batch
    from .models import (
        BybitFundingRate,
        BybitInstrumentMeta,
        BybitMarkKline1m,
        BybitServerTime,
        BybitTradeKline1m,
        InclusiveMinuteWindow,
        PublicRequestPageAudit,
    )

    if (
        type(instrument) is not BybitInstrumentMeta
        or type(server_time) is not BybitServerTime
        or type(requested_window) is not InclusiveMinuteWindow
    ):
        raise PublicBatchError("assembler_model_type_invalid")
    if not instrument.eligible_for_replay():
        raise PublicBatchError("instrument_not_eligible")
    trade = tuple(trade_rows)
    mark = tuple(mark_rows)
    funding = tuple(funding_rows)
    audits = tuple(request_page_audits)
    if (
        not all(type(x) is BybitTradeKline1m for x in trade)
        or not all(type(x) is BybitMarkKline1m for x in mark)
        or not all(type(x) is BybitFundingRate for x in funding)
        or not all(type(x) is PublicRequestPageAudit for x in audits)
    ):
        raise PublicBatchError("assembler_row_type_invalid")
    if requested_window.end_open_time_ms > server_time.last_closed_open_time_ms:
        raise PublicBatchError("requested_window_after_closed_cutoff")
    exp = requested_window.timestamps()
    tts = tuple(x.open_time_ms for x in trade)
    mts = tuple(x.open_time_ms for x in mark)
    if tts != exp or mts != exp:
        raise PublicBatchError("kline_gap_or_missing_timestamp")
    if tts != mts:
        raise PublicBatchError("trade_mark_timestamp_mismatch")
    if len(set(tts)) != len(trade) or len(set(mts)) != len(mark) or len({x.funding_time_ms for x in funding}) != len(funding):
        raise PublicBatchError("duplicate_timestamp")
    if any(x.category != instrument.category or x.symbol != instrument.symbol for x in (*trade, *mark, *funding)):
        raise PublicBatchError("category_symbol_consistency")
    if any(x.open_time_ms > server_time.last_closed_open_time_ms for x in (*trade, *mark)):
        raise PublicBatchError("kline_unclosed")
    mark_by_time = {m.open_time_ms: m for m in mark}
    obs = []
    final_close = requested_window.end_open_time_ms + MINUTE_MS
    for f in funding:
        if requested_window.start_open_time_ms <= f.funding_time_ms < final_close:
            if f.funding_time_ms not in mark_by_time:
                raise PublicBatchError("funding_boundary_mark_missing")
            obs.append(f.to_observation(mark_by_time[f.funding_time_ms].open))
    batch = BybitPublicReplayBatch(instrument, trade, mark, funding, tuple(obs), audits, server_time, requested_window)
    audit = audit_bybit_public_replay_batch(batch)
    if not audit.public_batch_audit_ok:
        raise PublicBatchError("public_batch_audit_failed")
    return batch


def fetch_bybit_public_replay_batch(client, symbol, requested_window, *, server_time=None, instrument=None):
    if server_time is None:
        server_time = parse_server_time(client.public_get("/v5/market/time", {}))
    audits = ()
    if instrument is None:
        instruments, ia = fetch_all_instruments(client, server_time)
        audits += ia
        matches = [m for m in instruments if m.symbol == symbol]
        if len(matches) != 1:
            raise PublicBatchError("instrument_match_not_unique")
        instrument = matches[0]
    trade, ta = fetch_trade_klines(client, symbol, requested_window, server_time)
    mark, ma = fetch_mark_klines(client, symbol, requested_window, server_time)
    funding, fa = fetch_funding_history_backward(
        client, symbol, requested_window.start_open_time_ms, requested_window.end_open_time_ms
    )
    return assemble_bybit_public_replay_batch_from_rows(
        instrument=instrument,
        server_time=server_time,
        requested_window=requested_window,
        trade_rows=trade,
        mark_rows=mark,
        funding_rows=funding,
        request_page_audits=audits + ta + ma + fa,
    )
