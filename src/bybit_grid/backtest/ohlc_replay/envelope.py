from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Sequence
from bybit_grid.backtest.neutral_grid.models import NeutralGridConfig
from .models import FundingObservation, MinimalPathPolicy, OhlcCandle1m
from .paths import minimal_paths_are_distinct
from .replay import OhlcReplayResult, replay_ohlc_minimal_path


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


def enumerate_minimal_path_ambiguity_envelope(
    config: NeutralGridConfig,
    entry_time_ms: int,
    candles: Sequence[OhlcCandle1m],
    funding_observations: Sequence[FundingObservation] | None = None,
    max_exact_ambiguous_candles: int = 12,
) -> MinimalPathAmbiguityEnvelope:
    cs = tuple(candles)
    amb_idx = [i for i, c in enumerate(cs) if minimal_paths_are_distinct(c)]
    if len(amb_idx) > max_exact_ambiguous_candles:
        raise MinimalPathEnumerationCapExceededError("ambiguous candle count exceeds cap")
    base = [MinimalPathPolicy.open_high_low_close] * len(cs)
    results = []
    for choices in product(
        (MinimalPathPolicy.open_high_low_close, MinimalPathPolicy.open_low_high_close),
        repeat=len(amb_idx),
    ):
        assignment = list(base)
        for idx, choice in zip(amb_idx, choices, strict=True):
            assignment[idx] = choice
        results.append(
            replay_ohlc_minimal_path(
                config, entry_time_ms, cs, tuple(assignment), funding_observations
            )
        )

    def key(r: OhlcReplayResult):
        return tuple(p.value for p in r.path_policies)

    minr = min(results, key=lambda r: (r.final_total_pnl_usdt, key(r)))
    maxr = min(results, key=lambda r: (-r.final_total_pnl_usdt, key(r)))
    return MinimalPathAmbiguityEnvelope(
        len(amb_idx),
        len(results),
        True,
        minr.final_total_pnl_usdt,
        maxr.final_total_pnl_usdt,
        maxr.final_total_pnl_usdt - minr.final_total_pnl_usdt,
        minr.path_policies,
        maxr.path_policies,
        len(minr.state_machine_result.completed_cycles),
        len(maxr.state_machine_result.completed_cycles),
        min(r.state_machine_result.cumulative_trading_fees_usdt for r in results),
        max(r.state_machine_result.cumulative_trading_fees_usdt for r in results),
        tuple(
            sorted({r.termination_reason for r in results}, key=lambda x: "" if x is None else x)
        ),
        len({r.final_total_pnl_usdt for r in results}) > 1,
        assignment_results=tuple(results),
    )
