from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from .envelope import MinimalPathAmbiguityEnvelope, _build
from .models import CandleSource, FundingObservation, MinimalPathPolicy, OhlcCandle1m
from .paths import minimal_paths_are_distinct
from .replay import (
    GeneratedReplayEvent,
    OhlcReplayResult,
    ReplayEventKind,
    _execute_ohlc_replay_core,
    reconstruct_expected_event_schedule,
    validate_candle_sequence,
    validate_funding_observations,
    validate_replay_provenance,
)
from bybit_grid.backtest.neutral_grid.audit import audit_simulation_result
from bybit_grid.backtest.neutral_grid.models import NeutralGridConfig, SimulationResult


@dataclass(frozen=True)
class OhlcReplayAuditResult:
    passed_bool: bool
    failures: tuple[str, ...]


def _finite_dec(v: object) -> bool:
    return type(v) is Decimal and v.is_finite()


def _strict_equal(left: object, right: object, path: str = "$.") -> str | None:
    if type(left) is not type(right):
        return f"{path} type mismatch"
    if isinstance(left, Decimal):
        return None if left == right else f"{path} value mismatch"
    if isinstance(left, Enum):
        return None if left is right else f"{path} value mismatch"
    if is_dataclass(left) and not isinstance(left, type):
        for field in fields(left):
            m = _strict_equal(getattr(left, field.name), getattr(right, field.name), f"{path}{field.name}.")
            if m:
                return m
        return None
    if isinstance(left, tuple):
        if len(left) != len(right):
            return f"{path} length mismatch"
        for i, (l_item, r_item) in enumerate(zip(left, right, strict=True)):
            m = _strict_equal(l_item, r_item, f"{path}{i}.")
            if m:
                return m
        return None
    if isinstance(left, Mapping):
        if set(left.keys()) != set(right.keys()):
            return f"{path} key mismatch"
        for key in left:
            m = _strict_equal(left[key], right[key], f"{path}{key}.")
            if m:
                return m
        return None
    return None if left == right else f"{path} value mismatch"


def _exact_int(v: object) -> bool:
    return type(v) is int and v >= 0


def _validate_replay_snapshot_shape(result: object) -> list[str]:
    f: list[str] = []
    if type(result) is not OhlcReplayResult:
        return ["replay_scalar_type_mismatch"]
    for name in ("category", "symbol"):
        if type(getattr(result, name)) is not str:
            f.append("replay_scalar_type_mismatch")
    for name in (
        "entry_time_ms", "candle_count_input", "candle_count_processed",
        "candles_not_processed_after_termination", "generated_price_event_count",
        "funding_event_count", "ambiguous_candle_count",
    ):
        if not _exact_int(getattr(result, name)):
            f.append("replay_scalar_type_mismatch")
    for name in ("terminated_bool", "state_machine_audit_passed_bool"):
        if type(getattr(result, name)) is not bool:
            f.append("replay_scalar_type_mismatch")
    for name in ("final_mark_price", "final_total_pnl_usdt"):
        if not _finite_dec(getattr(result, name)):
            f.append("replay_scalar_type_mismatch")
    if result.termination_reason is not None and type(result.termination_reason) is not str:
        f.append("replay_scalar_type_mismatch")
    tuple_specs = (
        ("path_policies", MinimalPathPolicy), ("source_candles", OhlcCandle1m),
        ("source_funding_observations", FundingObservation), ("generated_events", GeneratedReplayEvent),
    )
    for name, typ in tuple_specs:
        val = getattr(result, name)
        if type(val) is not tuple or any(type(x) is not typ for x in val):
            f.append("source_container_type_mismatch")
    if type(result.state_machine_result) is not SimulationResult:
        f.append("state_machine_result_mismatch")
    if type(result.source_config) is not NeutralGridConfig:
        f.append("source_config_mismatch")
    if not isinstance(result.candle_source, CandleSource):
        f.append("source_config_mismatch")
    if result.candle_count_processed > result.candle_count_input:
        f.append("replay_scalar_type_mismatch")
    return f


def audit_ohlc_replay_result(result: OhlcReplayResult) -> OhlcReplayAuditResult:
    f = _validate_replay_snapshot_shape(result)
    if f:
        return OhlcReplayAuditResult(False, tuple(dict.fromkeys(f)))
    try:
        cs = validate_candle_sequence(result.source_candles, result.entry_time_ms)
        validate_replay_provenance(result.source_config, cs)
        if result.candle_source is not cs[0].source:
            f.append("source_config_mismatch")
        fs = validate_funding_observations(result.source_funding_observations, cs, result.entry_time_ms)
        if _strict_equal(result.source_config, result.state_machine_result.config):
            f.append("source_config_mismatch")
        fresh = _execute_ohlc_replay_core(result.source_config, result.entry_time_ms, cs, result.path_policies, fs)
        expected = reconstruct_expected_event_schedule(cs, result.path_policies, fs)
        if _strict_equal(result.generated_events, expected[: len(result.generated_events)]):
            f.append("generated_event_stream_mismatch")
        if len(result.generated_events) > len(expected):
            f.append("generated_event_stream_mismatch")
        for e, next_e in zip(result.generated_events, result.generated_events[1:], strict=False):
            if e.sequence_id + 1 != next_e.sequence_id:
                f.append("generated_event_stream_mismatch")
            if e.time_ms == next_e.time_ms and e.kind is ReplayEventKind.price and next_e.kind is ReplayEventKind.funding:
                f.append("generated_event_stream_mismatch")
        if result.generated_events and result.generated_events[0].sequence_id != 1:
            f.append("generated_event_stream_mismatch")
        sm_audit = audit_simulation_result(result.state_machine_result, result.final_mark_price)
        if sm_audit.passed_bool is not True or result.state_machine_audit_passed_bool is not True:
            f.append("state_machine_audit_failed")
        mismatch = _strict_equal(result, fresh)
        if mismatch:
            if "state_machine_result" in mismatch:
                f.append("state_machine_result_mismatch")
            elif "generated_events" in mismatch:
                f.append("generated_event_stream_mismatch")
            elif any(x in mismatch for x in ("source_candles", "source_funding", "path_policies")):
                f.append("source_container_type_mismatch")
            elif "source_config" in mismatch:
                f.append("source_config_mismatch")
            else:
                f.append("replay_scalar_type_mismatch")
    except Exception as exc:
        msg = str(exc)
        if "config/candle" in msg or "funding category/symbol" in msg:
            f.append("source_config_mismatch")
        else:
            f.append(f"audit_failed_closed:{type(exc).__name__}:{exc}")
    return OhlcReplayAuditResult(not f, tuple(dict.fromkeys(f)))


def _validate_envelope_shape(env: object) -> list[str]:
    f: list[str] = []
    if type(env) is not MinimalPathAmbiguityEnvelope:
        return ["envelope_type_mismatch"]
    for name in ("ambiguous_candle_count", "exact_assignment_count", "completed_cycle_count_min", "completed_cycle_count_max"):
        if not _exact_int(getattr(env, name)):
            f.append("envelope_scalar_type_mismatch")
    for name in (
        "exact_enumeration_complete_bool", "path_sensitive_bool", "full_intrabar_path_reconstructed_bool",
        "arbitrary_intrabar_oscillation_bounded_bool", "global_true_worst_case_proven_bool",
        "global_true_best_case_proven_bool", "minimal_path_enumeration_complete_bool",
    ):
        if type(getattr(env, name)) is not bool:
            f.append("envelope_scalar_type_mismatch")
    for name in ("minimal_path_pnl_min_usdt", "minimal_path_pnl_max_usdt", "minimal_path_pnl_width_usdt", "trading_fees_min_usdt", "trading_fees_max_usdt"):
        if not _finite_dec(getattr(env, name)):
            f.append("envelope_scalar_type_mismatch")
    for name in ("min_assignment", "max_assignment"):
        val = getattr(env, name)
        if type(val) is not tuple or any(type(x) is not MinimalPathPolicy for x in val):
            f.append("envelope_container_type_mismatch")
    if type(env.termination_reasons_observed) is not tuple or any(x is not None and type(x) is not str for x in env.termination_reasons_observed):
        f.append("envelope_container_type_mismatch")
    if type(env.assignment_results) is not tuple or any(type(x) is not OhlcReplayResult for x in env.assignment_results):
        f.append("envelope_container_type_mismatch")
    return f


def audit_minimal_path_ambiguity_envelope(env: MinimalPathAmbiguityEnvelope) -> OhlcReplayAuditResult:
    f = _validate_envelope_shape(env)
    if f:
        return OhlcReplayAuditResult(False, tuple(dict.fromkeys(f)))
    try:
        rs = env.assignment_results
        if not rs:
            f.append("assignment_results empty")
            return OhlcReplayAuditResult(False, tuple(f))
        first = rs[0]
        cs = first.source_candles
        fs = first.source_funding_observations
        cfg = first.source_config
        amb = [i for i, c in enumerate(cs) if minimal_paths_are_distinct(c)]
        from itertools import product
        base = [MinimalPathPolicy.open_high_low_close] * len(cs)
        expected = []
        for choices in product((MinimalPathPolicy.open_high_low_close, MinimalPathPolicy.open_low_high_close), repeat=len(amb)):
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
            if _strict_equal(r.source_candles, cs) or _strict_equal(r.source_funding_observations, fs) or _strict_equal(r.source_config, cfg):
                f.append("assignment source mismatch")
            ar = audit_ohlc_replay_result(r)
            if not ar.passed_bool:
                f.append("assignment replay audit failed")
        recomputed = _build(list(rs), len(amb))
        mismatch = _strict_equal(env, recomputed)
        if mismatch:
            f.append("envelope_strict_identity_mismatch")
        for name in ("exact_enumeration_complete_bool", "minimal_path_enumeration_complete_bool"):
            if getattr(env, name) is not True:
                f.append(f"{name} invalid")
        for name in ("full_intrabar_path_reconstructed_bool", "arbitrary_intrabar_oscillation_bounded_bool", "global_true_worst_case_proven_bool", "global_true_best_case_proven_bool"):
            if getattr(env, name) is not False:
                f.append(f"{name} must be false")
    except Exception as exc:
        f.append(f"audit_failed_closed:{type(exc).__name__}:{exc}")
    return OhlcReplayAuditResult(not f, tuple(dict.fromkeys(f)))
