from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Sequence
from bybit_grid.backtest.neutral_grid.models import NeutralGridConfig
from .models import FundingObservation, MinimalPathPolicy, OhlcCandle1m
from .paths import minimal_path_prices, minimal_paths_are_distinct
from .replay import (
    OhlcReplayResult,
    replay_ohlc_minimal_path,
    validate_candle_sequence,
    validate_replay_provenance,
)


class MinimalPathEnumerationCapExceededError(ValueError):
    pass


@dataclass(frozen=True)
class MinimalPathAmbiguityEnvelope:
    ambiguous_candle_count: int
    exact_assignment_count: int
    exact_enumeration_complete_bool: bool
    minimal_path_pnl_min_usdt: Decimal
    minimal_path_pnl_max_usdt: Decimal
    minimal_path_pnl_width_usdt: Decimal
    min_assignment: tuple[MinimalPathPolicy, ...]
    max_assignment: tuple[MinimalPathPolicy, ...]
    completed_cycle_count_min: int
    completed_cycle_count_max: int
    trading_fees_min_usdt: Decimal
    trading_fees_max_usdt: Decimal
    termination_reasons_observed: tuple[str | None, ...]
    path_sensitive_bool: bool
    full_intrabar_path_reconstructed_bool: bool = False
    arbitrary_intrabar_oscillation_bounded_bool: bool = False
    global_true_worst_case_proven_bool: bool = False
    global_true_best_case_proven_bool: bool = False
    minimal_path_enumeration_complete_bool: bool = True
    assignment_results: tuple[OhlcReplayResult, ...] = ()


def _cap(cap: int) -> None:
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise ValueError("max_exact_ambiguous_candles must be int, not bool, >= 0")


def _assignment_key(r: OhlcReplayResult):
    return tuple(0 if p is MinimalPathPolicy.open_high_low_close else 1 for p in r.path_policies)


def _material(r: OhlcReplayResult):
    return (
        r.final_total_pnl_usdt,
        r.termination_reason,
        len(r.state_machine_result.completed_cycles),
        r.state_machine_result.cumulative_trading_fees_usdt,
        r.state_machine_result.signed_position,
    )


def _build(results: list[OhlcReplayResult], amb_count: int) -> MinimalPathAmbiguityEnvelope:
    minr = min(results, key=lambda r: (r.final_total_pnl_usdt, _assignment_key(r)))
    maxr = min(results, key=lambda r: (-r.final_total_pnl_usdt, _assignment_key(r)))
    fees = [r.state_machine_result.cumulative_trading_fees_usdt for r in results]
    cycles = [len(r.state_machine_result.completed_cycles) for r in results]
    return MinimalPathAmbiguityEnvelope(
        amb_count,
        len(results),
        True,
        minr.final_total_pnl_usdt,
        maxr.final_total_pnl_usdt,
        maxr.final_total_pnl_usdt - minr.final_total_pnl_usdt,
        minr.path_policies,
        maxr.path_policies,
        min(cycles),
        max(cycles),
        min(fees),
        max(fees),
        tuple(
            sorted({r.termination_reason for r in results}, key=lambda x: "" if x is None else x)
        ),
        len({_material(r) for r in results}) > 1,
        assignment_results=tuple(results),
    )


def enumerate_minimal_path_ambiguity_envelope(
    config: NeutralGridConfig,
    entry_time_ms: int,
    candles: Sequence[OhlcCandle1m],
    funding_observations: Sequence[FundingObservation] | None = None,
    max_exact_ambiguous_candles: int = 12,
) -> MinimalPathAmbiguityEnvelope:
    _cap(max_exact_ambiguous_candles)
    cs = validate_candle_sequence(candles, entry_time_ms)
    validate_replay_provenance(config, cs)
    amb_idx = [i for i, c in enumerate(cs) if minimal_paths_are_distinct(c)]
    if len(amb_idx) > max_exact_ambiguous_candles:
        raise MinimalPathEnumerationCapExceededError("ambiguous candle count exceeds cap")
    canonical = [
        MinimalPathPolicy.open_high_low_close
        if len(set(minimal_path_prices(c, MinimalPathPolicy.open_high_low_close))) == 1
        or not minimal_paths_are_distinct(c)
        else MinimalPathPolicy.open_high_low_close
        for c in cs
    ]
    results = []
    for choices in product(
        (MinimalPathPolicy.open_high_low_close, MinimalPathPolicy.open_low_high_close),
        repeat=len(amb_idx),
    ):
        a = list(canonical)
        for idx, ch in zip(amb_idx, choices, strict=True):
            a[idx] = ch
        results.append(
            replay_ohlc_minimal_path(config, entry_time_ms, cs, tuple(a), funding_observations)
        )
    return _build(results, len(amb_idx))
