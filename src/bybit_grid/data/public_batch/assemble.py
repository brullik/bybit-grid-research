from __future__ import annotations
from .models import BybitPublicReplayBatch, MINUTE_MS, PublicBatchError
from .parsers import parse_server_time
from .pagination import (
    fetch_all_instruments,
    fetch_trade_klines,
    fetch_mark_klines,
    fetch_funding_history_backward,
)


def fetch_bybit_public_replay_batch(
    client, symbol, requested_window, *, server_time=None, instrument=None
):
    if server_time is None:
        server_time = parse_server_time(client.public_get("/v5/market/time", {}))
    if requested_window.end_open_time_ms > server_time.last_closed_open_time_ms:
        raise PublicBatchError("requested_window_after_closed_cutoff")
    audits = ()
    if instrument is None:
        instruments, ia = fetch_all_instruments(client, server_time)
        audits += ia
        matches = [m for m in instruments if m.symbol == symbol]
        if len(matches) != 1:
            raise PublicBatchError("instrument_match_not_unique")
        instrument = matches[0]
    if not instrument.eligible_for_replay():
        raise PublicBatchError("instrument_not_eligible")
    trade, ta = fetch_trade_klines(client, symbol, requested_window, server_time)
    mark, ma = fetch_mark_klines(client, symbol, requested_window, server_time)
    audits += ta + ma
    if tuple(t.open_time_ms for t in trade) != tuple(m.open_time_ms for m in mark):
        raise PublicBatchError("trade_mark_timestamp_mismatch")
    funding, fa = fetch_funding_history_backward(
        client, symbol, requested_window.start_open_time_ms, requested_window.end_open_time_ms
    )
    audits += fa
    mark_by_time = {m.open_time_ms: m for m in mark}
    obs = []
    final_close = requested_window.end_open_time_ms + MINUTE_MS
    for f in funding:
        if (
            f.funding_time_ms <= requested_window.start_open_time_ms
            or f.funding_time_ms >= final_close
        ):
            continue
        if f.funding_time_ms not in mark_by_time:
            raise PublicBatchError("funding_boundary_mark_missing")
        obs.append(f.to_observation(mark_by_time[f.funding_time_ms].open))
    return BybitPublicReplayBatch(
        instrument,
        tuple(trade),
        tuple(mark),
        tuple(funding),
        tuple(obs),
        tuple(audits),
        server_time,
        requested_window,
    )
