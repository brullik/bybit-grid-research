from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
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


class ReplayEventKind(str, Enum):
    price = "price"
    funding = "funding"


def _nb_int(v: object, name: str, *, minute: bool = False, min_: int = 0) -> None:
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValueError(f"{name} must be int, not bool")
    if v < min_ or (minute and v % MINUTE_MS != 0):
        raise ValueError(f"{name} out of range")


def _dec(v: object, name: str, *, positive: bool) -> None:
    if not isinstance(v, Decimal) or isinstance(v, bool) or not v.is_finite():
        raise ValueError(f"{name} must be finite Decimal")
    if positive and v <= Decimal("0"):
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class GeneratedReplayEvent:
    sequence_id: int
    time_ms: int
    kind: ReplayEventKind
    candle_index: int
    price: Decimal
    funding_rate: Decimal | None = None

    def __post_init__(self) -> None:
        _nb_int(self.sequence_id, "sequence_id", min_=1)
        _nb_int(self.time_ms, "time_ms", minute=True)
        if not isinstance(self.kind, ReplayEventKind):
            raise ValueError("kind must be ReplayEventKind")
        _nb_int(self.candle_index, "candle_index")
        _dec(self.price, "price", positive=True)
        if self.kind is ReplayEventKind.price:
            if self.funding_rate is not None:
                raise ValueError("price events require funding_rate None")
        else:
            _dec(self.funding_rate, "funding_rate", positive=False)


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
    source_candles: tuple[OhlcCandle1m, ...]
    source_funding_observations: tuple[FundingObservation, ...]


def validate_candle_sequence(
    candles: Sequence[OhlcCandle1m], entry_time_ms: int
) -> tuple[OhlcCandle1m, ...]:
    _nb_int(entry_time_ms, "entry_time_ms", minute=True)
    try:
        cs = tuple(candles)
    except TypeError as exc:
        raise ValueError("candles must be a sequence") from exc
    if not cs:
        raise ValueError("at least one candle required")
    expected = entry_time_ms
    seen: set[int] = set()
    cat = sym = None
    for c in cs:
        if not isinstance(c, OhlcCandle1m):
            raise ValueError("candles must be OhlcCandle1m")
        if cat is None:
            cat, sym = c.category, c.symbol
        if c.category != cat or c.symbol != sym:
            raise ValueError("all candles same category and symbol")
        if c.open_time_ms in seen:
            raise ValueError("duplicate candle timestamp")
        if c.open_time_ms != expected:
            raise ValueError("candles must be sorted contiguous from entry")
        seen.add(c.open_time_ms)
        expected += MINUTE_MS
    return cs


def validate_replay_provenance(
    config: NeutralGridConfig, candles: tuple[OhlcCandle1m, ...]
) -> None:
    if type(config) is not NeutralGridConfig:
        raise ValueError("config must be exactly NeutralGridConfig")
    if (
        type(config.symbol) is not str
        or config.symbol == ""
        or config.symbol != config.symbol.strip()
    ):
        raise ValueError("config symbol must be stripped non-empty str")
    if config.category != "linear":
        raise ValueError("config category must be linear")
    for c in candles:
        if c.category != "linear" or c.category != config.category or c.symbol != config.symbol:
            raise ValueError("config/candle category or symbol mismatch")


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


def reconstruct_expected_event_schedule(
    candles: tuple[OhlcCandle1m, ...],
    path_policies: tuple[MinimalPathPolicy, ...],
    funding_observations: tuple[FundingObservation, ...],
) -> tuple[GeneratedReplayEvent, ...]:
    fmap = {f.time_ms: f for f in funding_observations}
    out = []
    seq = 1
    for i, (c, p) in enumerate(zip(candles, path_policies, strict=True)):
        if c.open_time_ms in fmap:
            f = fmap[c.open_time_ms]
            out.append(
                GeneratedReplayEvent(
                    seq, f.time_ms, ReplayEventKind.funding, i, f.mark_price, f.funding_rate
                )
            )
            seq += 1
        for price in minimal_path_prices(c, p):
            out.append(GeneratedReplayEvent(seq, c.open_time_ms, ReplayEventKind.price, i, price))
            seq += 1
    return tuple(out)


def _execute_ohlc_replay_core(
    config: NeutralGridConfig,
    entry_time_ms: int,
    candles: Sequence[OhlcCandle1m],
    path_policies: MinimalPathPolicy | Sequence[MinimalPathPolicy],
    funding_observations: Sequence[FundingObservation] | None = None,
) -> OhlcReplayResult:
    cs = validate_candle_sequence(candles, entry_time_ms)
    validate_replay_provenance(config, cs)
    ps = _policies(path_policies, len(cs))
    fs = validate_funding_observations(funding_observations, cs, entry_time_ms)
    engine = NeutralGridReferenceEngine(config)
    events = []
    price_n = fund_n = processed = 0
    for e in reconstruct_expected_event_schedule(cs, ps, fs):
        if e.kind is ReplayEventKind.funding:
            engine.process(FundingEvent(e.sequence_id, e.time_ms, e.price, e.funding_rate))
            events.append(e)
            fund_n += 1
        else:
            engine.process(PriceEvent(e.sequence_id, e.time_ms, e.price))
            events.append(e)
            price_n += 1
            processed = max(processed, e.candle_index + 1)
        if engine.terminated:
            break
    smr = engine.result()
    mark = (
        smr.last_price
        if smr.terminated_bool
        else (cs[processed - 1].close if processed else config.base_price)
    )
    audit = audit_simulation_result(smr, mark)
    pnl = smr.realized_net_pnl() if smr.terminated_bool else smr.total_pnl(mark)
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
        smr.terminated_bool,
        smr.termination.termination_reason.value if smr.termination.termination_reason else None,
        smr,
        audit.passed_bool,
        tuple(events),
        cs,
        fs,
    )


def replay_ohlc_minimal_path(
    config: NeutralGridConfig,
    entry_time_ms: int,
    candles: Sequence[OhlcCandle1m],
    path_policies: MinimalPathPolicy | Sequence[MinimalPathPolicy],
    funding_observations: Sequence[FundingObservation] | None = None,
) -> OhlcReplayResult:
    result = _execute_ohlc_replay_core(
        config, entry_time_ms, candles, path_policies, funding_observations
    )
    if not result.state_machine_audit_passed_bool:
        raise ValueError("state machine audit failed")
    return result
