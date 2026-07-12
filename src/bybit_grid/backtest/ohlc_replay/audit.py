from __future__ import annotations
from dataclasses import dataclass
from .envelope import MinimalPathAmbiguityEnvelope, _build
from .models import MinimalPathPolicy
from .paths import minimal_paths_are_distinct
from .replay import (
    OhlcReplayResult,
    ReplayEventKind,
    _execute_ohlc_replay_core,
    reconstruct_expected_event_schedule,
    validate_candle_sequence,
    validate_funding_observations,
    validate_replay_provenance,
)
from bybit_grid.backtest.neutral_grid.audit import audit_simulation_result


@dataclass(frozen=True)
class OhlcReplayAuditResult:
    passed_bool: bool
    failures: tuple[str, ...]


def audit_ohlc_replay_result(result: OhlcReplayResult) -> OhlcReplayAuditResult:
    f = []
    try:
        cs = validate_candle_sequence(result.source_candles, result.entry_time_ms)
        validate_replay_provenance(result.state_machine_result.config, cs)
        fs = validate_funding_observations(
            result.source_funding_observations, cs, result.entry_time_ms
        )
        fresh = _execute_ohlc_replay_core(
            result.state_machine_result.config, result.entry_time_ms, cs, result.path_policies, fs
        )
        expected = reconstruct_expected_event_schedule(cs, result.path_policies, fs)
        if result.generated_events != expected[: len(result.generated_events)]:
            f.append("generated event stream mismatch")
        if len(result.generated_events) > len(expected):
            f.append("generated event stream too long")
        for e, next_e in zip(result.generated_events, result.generated_events[1:], strict=False):
            if e.sequence_id + 1 != next_e.sequence_id:
                f.append("sequence ids not strict from 1")
            if (
                e.time_ms == next_e.time_ms
                and e.kind is ReplayEventKind.price
                and next_e.kind is ReplayEventKind.funding
            ):
                f.append("funding after price at boundary")
        if result.generated_events and result.generated_events[0].sequence_id != 1:
            f.append("sequence ids not strict from 1")
        for name in (
            "category",
            "symbol",
            "entry_time_ms",
            "path_policies",
            "candle_count_input",
            "candle_count_processed",
            "candles_not_processed_after_termination",
            "generated_price_event_count",
            "funding_event_count",
            "ambiguous_candle_count",
            "final_mark_price",
            "final_total_pnl_usdt",
            "terminated_bool",
            "termination_reason",
            "generated_events",
        ):
            if getattr(result, name) != getattr(fresh, name):
                f.append(f"{name} mismatch")
        if result.category != cs[0].category or result.symbol != cs[0].symbol:
            f.append("provenance mismatch")
        if result.candle_count_input != len(cs) or result.ambiguous_candle_count != sum(
            1 for c in cs if minimal_paths_are_distinct(c)
        ):
            f.append("source-derived counts mismatch")
        if result.generated_price_event_count != sum(
            1 for e in result.generated_events if e.kind is ReplayEventKind.price
        ):
            f.append("price count mismatch")
        if result.funding_event_count != sum(
            1 for e in result.generated_events if e.kind is ReplayEventKind.funding
        ):
            f.append("funding count mismatch")
        processed = (
            max(
                (
                    e.candle_index
                    for e in result.generated_events
                    if e.kind is ReplayEventKind.price
                ),
                default=-1,
            )
            + 1
        )
        if (
            result.candle_count_processed != processed
            or result.candles_not_processed_after_termination != len(cs) - processed
        ):
            f.append("processed/unprocessed mismatch")
        sm_audit = audit_simulation_result(result.state_machine_result, result.final_mark_price)
        if sm_audit.passed_bool is not True or result.state_machine_audit_passed_bool is not True:
            f.append("state-machine audit failed")
    except Exception as exc:
        f.append(f"audit failed closed: {type(exc).__name__}: {exc}")
    return OhlcReplayAuditResult(not f, tuple(dict.fromkeys(f)))


def audit_minimal_path_ambiguity_envelope(
    env: MinimalPathAmbiguityEnvelope,
) -> OhlcReplayAuditResult:
    f = []
    try:
        rs = tuple(env.assignment_results)
        if not rs:
            f.append("assignment_results empty")
            return OhlcReplayAuditResult(False, tuple(f))
        first = rs[0]
        cs = first.source_candles
        fs = first.source_funding_observations
        cfg = first.state_machine_result.config
        amb = [i for i, c in enumerate(cs) if minimal_paths_are_distinct(c)]
        expected = []
        from itertools import product

        base = [MinimalPathPolicy.open_high_low_close] * len(cs)
        for choices in product(
            (MinimalPathPolicy.open_high_low_close, MinimalPathPolicy.open_low_high_close),
            repeat=len(amb),
        ):
            a = list(base)
            for idx, ch in zip(amb, choices, strict=True):
                a[idx] = ch
            expected.append(tuple(a))
        if len(rs) != 2 ** len(amb) or env.exact_assignment_count != len(rs):
            f.append("exact enumeration count mismatch")
        if [r.path_policies for r in rs] != expected:
            f.append("assignment order/set mismatch")
        if len({r.path_policies for r in rs}) != len(rs):
            f.append("duplicate assignment policy tuple")
        for r in rs:
            if (
                r.source_candles != cs
                or r.source_funding_observations != fs
                or r.state_machine_result.config != cfg
            ):
                f.append("assignment source mismatch")
            ar = audit_ohlc_replay_result(r)
            if not ar.passed_bool:
                f.append("assignment replay audit failed")
        recomputed = _build(list(rs), len(amb))
        for name in (
            "ambiguous_candle_count",
            "exact_assignment_count",
            "minimal_path_pnl_min_usdt",
            "minimal_path_pnl_max_usdt",
            "minimal_path_pnl_width_usdt",
            "min_assignment",
            "max_assignment",
            "completed_cycle_count_min",
            "completed_cycle_count_max",
            "trading_fees_min_usdt",
            "trading_fees_max_usdt",
            "termination_reasons_observed",
            "path_sensitive_bool",
        ):
            if getattr(env, name) != getattr(recomputed, name):
                f.append(f"{name} mismatch")
        for name in ("exact_enumeration_complete_bool", "minimal_path_enumeration_complete_bool"):
            if getattr(env, name) is not True:
                f.append(f"{name} invalid")
        for name in (
            "full_intrabar_path_reconstructed_bool",
            "arbitrary_intrabar_oscillation_bounded_bool",
            "global_true_worst_case_proven_bool",
            "global_true_best_case_proven_bool",
        ):
            if getattr(env, name) is not False:
                f.append(f"{name} must be false")
    except Exception as exc:
        f.append(f"audit failed closed: {type(exc).__name__}: {exc}")
    return OhlcReplayAuditResult(not f, tuple(dict.fromkeys(f)))
