from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
from bybit_grid.backtest.neutral_grid.audit import audit_simulation_result
from bybit_grid.backtest.neutral_grid.engine import NeutralGridReferenceEngine
from bybit_grid.backtest.neutral_grid.models import (
    FundingEvent,
    NeutralGridConfig,
    PriceEvent,
    SimulationResult,
)
from .models import MINUTE_MS, FundingObservation, MinimalPathPolicy, OhlcCandle1m
from .paths import minimal_path_prices, minimal_paths_are_distinct


@dataclass(frozen=True)
class GeneratedReplayEvent:
    sequence_id: int
    time_ms: int
    kind: str
    candle_index: int | None
    price: Decimal | None = None


@dataclass(frozen=True)
class OhlcReplayResult:
    category: str
    symbol: str
    entry_time_ms: int
    path_policies: tuple[MinimalPathPolicy, ...]
    candle_count_input: int
    candle_count_processed: int
    candles_not_processed_after_termination: int
    generated_price_event_count: int
    funding_event_count: int
    ambiguous_candle_count: int
    final_mark_price: Decimal
    final_total_pnl_usdt: Decimal
    terminated_bool: bool
    termination_reason: str | None
    state_machine_result: SimulationResult
    state_machine_audit_passed_bool: bool
    generated_events: tuple[GeneratedReplayEvent, ...]


def validate_candle_sequence(
    candles: Sequence[OhlcCandle1m], entry_time_ms: int
) -> tuple[OhlcCandle1m, ...]:
    if (
        not isinstance(entry_time_ms, int)
        or isinstance(entry_time_ms, bool)
        or entry_time_ms < 0
        or entry_time_ms % MINUTE_MS
    ):
        raise ValueError("entry_time_ms must be non-negative minute-aligned int")
    cs = tuple(candles)
    if not cs:
        raise ValueError("at least one candle required")
    cat, sym = cs[0].category, cs[0].symbol
    expected = entry_time_ms
    seen: set[int] = set()
    for c in cs:
        if not isinstance(c, OhlcCandle1m):
            raise ValueError("candles must be OhlcCandle1m")
        if c.category != cat or c.symbol != sym:
            raise ValueError("all candles same category and symbol")
        if not c.closed_bool:
            raise ValueError("all candles closed")
        if c.open_time_ms in seen:
            raise ValueError("duplicate candle timestamp")
        if c.open_time_ms != expected:
            raise ValueError("candles must be sorted contiguous from entry")
        seen.add(c.open_time_ms)
        expected += MINUTE_MS
    return cs


def _policies(
    policies: MinimalPathPolicy | Sequence[MinimalPathPolicy], n: int
) -> tuple[MinimalPathPolicy, ...]:
    if isinstance(policies, MinimalPathPolicy):
        return (policies,) * n
    ps = tuple(policies)
    if len(ps) != n or any(not isinstance(p, MinimalPathPolicy) for p in ps):
        raise ValueError("invalid path policies")
    return ps


def validate_funding_observations(
    funding: Sequence[FundingObservation] | None,
    candles: tuple[OhlcCandle1m, ...],
    entry_time_ms: int,
) -> tuple[FundingObservation, ...]:
    fs = tuple(funding or ())
    boundaries = {c.open_time_ms for c in candles}
    prev = -1
    final_close = candles[-1].close_boundary_ms
    for f in fs:
        if not isinstance(f, FundingObservation):
            raise ValueError("funding must be FundingObservation")
        if f.time_ms <= prev:
            raise ValueError("funding observations sorted strictly by time")
        if f.time_ms == entry_time_ms:
            raise ValueError("funding at entry boundary rejected")
        if f.time_ms not in boundaries or f.time_ms <= entry_time_ms or f.time_ms >= final_close:
            raise ValueError(
                "funding time must match replay candle open boundary after entry before final close"
            )
        prev = f.time_ms
    return fs


def replay_ohlc_minimal_path(
    config: NeutralGridConfig,
    entry_time_ms: int,
    candles: Sequence[OhlcCandle1m],
    path_policies: MinimalPathPolicy | Sequence[MinimalPathPolicy],
    funding_observations: Sequence[FundingObservation] | None = None,
) -> OhlcReplayResult:
    cs = validate_candle_sequence(candles, entry_time_ms)
    ps = _policies(path_policies, len(cs))
    fs = validate_funding_observations(funding_observations, cs, entry_time_ms)
    fmap = {f.time_ms: f for f in fs}
    engine = NeutralGridReferenceEngine(config)
    seq = 1
    price_n = fund_n = processed = 0
    events: list[GeneratedReplayEvent] = []
    for i, (c, p) in enumerate(zip(cs, ps, strict=True)):
        if c.open_time_ms in fmap:
            f = fmap[c.open_time_ms]
            engine.process(FundingEvent(seq, f.time_ms, f.mark_price, f.funding_rate))
            events.append(GeneratedReplayEvent(seq, f.time_ms, "funding", i, f.mark_price))
            seq += 1
            fund_n += 1
            if engine.terminated:
                break
        any_price = False
        for price in minimal_path_prices(c, p):
            engine.process(PriceEvent(seq, c.open_time_ms, price))
            events.append(GeneratedReplayEvent(seq, c.open_time_ms, "price", i, price))
            seq += 1
            price_n += 1
            any_price = True
            if engine.terminated:
                break
        if any_price:
            processed += 1
        if engine.terminated:
            break
    result = engine.result()
    mark = (
        result.last_price
        if result.terminated_bool
        else cs[processed - 1].close
        if processed
        else config.base_price
    )
    audit = audit_simulation_result(result, mark)
    if not audit.passed_bool:
        raise ValueError(f"state machine audit failed: {audit.failures}")
    pnl = result.realized_net_pnl() if result.terminated_bool else result.total_pnl(mark)
    return OhlcReplayResult(
        cs[0].category,
        cs[0].symbol,
        entry_time_ms,
        ps,
        len(cs),
        processed,
        len(cs) - processed,
        price_n,
        fund_n,
        sum(1 for c in cs if minimal_paths_are_distinct(c)),
        mark,
        pnl,
        result.terminated_bool,
        result.termination.termination_reason.value
        if result.termination.termination_reason
        else None,
        result,
        True,
        tuple(events),
    )
