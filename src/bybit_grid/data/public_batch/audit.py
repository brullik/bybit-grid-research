from __future__ import annotations
from .models import BybitInstrumentMeta, BybitPublicBatchAudit, BybitPublicReplayBatch, MINUTE_MS


def audit_bybit_public_replay_batch(batch):
    fails = []

    def flag(name, ok):
        if not ok:
            fails.append(name)
        return ok

    type_ok = type(batch) is BybitPublicReplayBatch
    if not type_ok:
        return BybitPublicBatchAudit(
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("batch_type_invalid",),
        )
    inst_ok = flag(
        "instrument_contract_ok",
        type(batch.instrument) is BybitInstrumentMeta and batch.instrument.eligible_for_replay(),
    )
    cutoff_ok = flag(
        "closed_candle_cutoff_ok",
        batch.requested_window.end_open_time_ms <= batch.server_time.last_closed_open_time_ms
        and all(
            t.closed_bool is True and t.open_time_ms <= batch.server_time.last_closed_open_time_ms
            for t in batch.trade_klines
        )
        and all(
            m.closed_bool is True and m.open_time_ms <= batch.server_time.last_closed_open_time_ms
            for m in batch.mark_klines
        ),
    )
    exp = batch.requested_window.timestamps()
    tts = tuple(t.open_time_ms for t in batch.trade_klines)
    mts = tuple(m.open_time_ms for m in batch.mark_klines)
    trade_ok = flag("trade_kline_coverage_ok", tts == exp and len(tts) == len(set(tts)))
    mark_ok = flag("mark_kline_coverage_ok", mts == exp and len(mts) == len(set(mts)))
    sets_ok = flag("trade_mark_timestamp_sets_equal_bool", tts == mts)
    sym_ok = all(
        x.category == "linear" and x.symbol == batch.instrument.symbol
        for x in (*batch.trade_klines, *batch.mark_klines, *batch.funding_rates)
    )
    flag("category_symbol_consistency_ok", sym_ok)
    fund_ts = tuple(f.funding_time_ms for f in batch.funding_rates)
    fund_range = flag(
        "funding_pagination_range_covered_bool",
        fund_ts == tuple(sorted(fund_ts)) and len(fund_ts) == len(set(fund_ts)),
    )
    interval_ok = flag(
        "funding_interval_consistent_bool",
        all(
            (b - a) % (batch.instrument.funding_interval_minutes * MINUTE_MS) == 0
            for a, b in zip(fund_ts, fund_ts[1:])
        ),
    )
    mark_by = {m.open_time_ms: m for m in batch.mark_klines}
    join_ok = True
    for o in batch.funding_observations:
        m = mark_by.get(o.time_ms)
        join_ok &= bool(
            m
            and o.mark_price == m.open
            and o.funding_rate_source.value == "bybit_funding_history"
            and o.mark_price_source.value == "bybit_mark_price_kline_1m"
        )
    join_ok = flag("funding_mark_boundary_join_ok", join_ok)
    replay_ok = flag(
        "replay_inputs_ready_bool",
        all(t.to_ohlc_candle().open_time_ms == t.open_time_ms for t in batch.trade_klines),
    )
    ok = not fails
    return BybitPublicBatchAudit(
        ok,
        inst_ok,
        cutoff_ok,
        trade_ok,
        mark_ok,
        sets_ok,
        fund_range,
        interval_ok,
        join_ok,
        replay_ok,
        tuple(dict.fromkeys(fails)),
    )
