from __future__ import annotations
from collections import Counter
from types import MappingProxyType
from .models import (
    BybitInstrumentMeta,
    BybitInstrumentUniverseAudit,
    BybitPublicBatchAudit,
    BybitPublicReplayBatch,
    MINUTE_MS,
)


def _frozen_counts(values):
    return MappingProxyType(dict(sorted(Counter(values).items(), key=lambda kv: kv[0])))


def _is_replay_candidate(row):
    return (
        type(row) is BybitInstrumentMeta
        and row.contract_type == "LinearPerpetual"
        and row.status == "Trading"
        and row.quote_coin == "USDT"
        and row.settle_coin == "USDT"
        and row.is_pre_listing is False
    )


def audit_instrument_universe(instruments):
    rows = tuple(instruments)
    failures = []
    exact = all(type(row) is BybitInstrumentMeta for row in rows)
    if not exact:
        failures.append("all_rows_exact_public_models_bool")
    valid = tuple(row for row in rows if type(row) is BybitInstrumentMeta)
    symbols = tuple(row.symbol for row in valid)
    unique = len(symbols) == len(set(symbols))
    if not unique:
        failures.append("symbols_unique_bool")
    unknown_contracts = tuple(
        sorted({row.contract_type for row in valid if row.contract_type not in {"LinearPerpetual", "LinearFutures"}})
    )
    if unknown_contracts:
        failures.append("unknown_contract_type")
    zero_rows = tuple(row for row in valid if row.funding_interval_minutes == 0)
    zero_symbols = tuple(sorted(row.symbol for row in zero_rows))
    zero_by_contract = _frozen_counts(row.contract_type for row in zero_rows)
    replay_candidates = tuple(row for row in valid if _is_replay_candidate(row))
    replay_eligible = tuple(row for row in replay_candidates if row.funding_interval_minutes > 0)
    replay_candidate_zero = tuple(sorted(row.symbol for row in replay_candidates if row.funding_interval_minutes == 0))
    if replay_candidate_zero:
        failures.append("replay_candidate_zero_funding_interval")
    replay_eligible_zero = sum(1 for row in replay_eligible if row.funding_interval_minutes <= 0)
    if replay_eligible_zero:
        failures.append("replay_eligible_non_positive_funding_interval")
    return BybitInstrumentUniverseAudit(
        instrument_count=len(rows),
        contract_type_counts=_frozen_counts(row.contract_type for row in valid),
        status_counts=_frozen_counts(row.status for row in valid),
        quote_coin_counts=_frozen_counts(row.quote_coin for row in valid),
        settle_coin_counts=_frozen_counts(row.settle_coin for row in valid),
        funding_interval_counts=_frozen_counts(row.funding_interval_minutes for row in valid),
        zero_funding_interval_count=len(zero_rows),
        zero_funding_interval_symbols=zero_symbols,
        zero_funding_interval_by_contract_type=zero_by_contract,
        linear_perpetual_count=sum(1 for row in valid if row.contract_type == "LinearPerpetual"),
        linear_futures_count=sum(1 for row in valid if row.contract_type == "LinearFutures"),
        usdt_linear_perpetual_count=sum(
            1
            for row in valid
            if row.contract_type == "LinearPerpetual" and row.quote_coin == "USDT" and row.settle_coin == "USDT"
        ),
        replay_eligible_count=len(replay_eligible),
        replay_eligible_zero_funding_interval_count=replay_eligible_zero,
        replay_candidate_zero_funding_interval_symbols=replay_candidate_zero,
        symbols_unique_bool=unique,
        all_rows_exact_public_models_bool=exact,
        universe_audit_ok=not failures,
        failures=tuple(dict.fromkeys(failures)),
    )
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
        type(batch.instrument) is BybitInstrumentMeta
        and batch.instrument.eligible_for_replay()
        and batch.instrument.funding_interval_minutes > 0,
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
        for x in (*batch.trade_klines, *batch.mark_klines, *batch.funding_rates, *batch.funding_observations)
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
            and o.category == batch.instrument.category
            and o.symbol == batch.instrument.symbol
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
