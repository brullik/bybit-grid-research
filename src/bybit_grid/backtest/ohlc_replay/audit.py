from __future__ import annotations
from dataclasses import dataclass
from .envelope import MinimalPathAmbiguityEnvelope
from .models import MinimalPathPolicy
from .replay import OhlcReplayResult


@dataclass(frozen=True)
class OhlcReplayAuditResult:
    passed_bool: bool
    failures: tuple[str, ...]


def audit_ohlc_replay_result(result: OhlcReplayResult) -> OhlcReplayAuditResult:
    failures = []
    try:
        if len(result.path_policies) != result.candle_count_input:
            failures.append("policy count mismatch")
        if any(not isinstance(p, MinimalPathPolicy) for p in result.path_policies):
            failures.append("policy enum type invalid")
        seqs = [e.sequence_id for e in result.generated_events]
        if seqs != list(range(1, len(seqs) + 1)):
            failures.append("sequence ids not strict from 1")
        if [e.time_ms for e in result.generated_events] != sorted(
            e.time_ms for e in result.generated_events
        ):
            failures.append("event time buckets decreased")
        if (
            sum(1 for e in result.generated_events if e.kind == "price")
            != result.generated_price_event_count
        ):
            failures.append("price event count mismatch")
        if (
            sum(1 for e in result.generated_events if e.kind == "funding")
            != result.funding_event_count
        ):
            failures.append("funding event count mismatch")
        if any(
            e.kind == "funding" and e.time_ms == result.entry_time_ms
            for e in result.generated_events
        ):
            failures.append("funding at entry boundary")
        if (
            result.candles_not_processed_after_termination
            != result.candle_count_input - result.candle_count_processed
        ):
            failures.append("processed/unprocessed mismatch")
        expected = (
            result.state_machine_result.realized_net_pnl()
            if result.terminated_bool
            else result.state_machine_result.total_pnl(result.final_mark_price)
        )
        if expected != result.final_total_pnl_usdt:
            failures.append("final pnl identity mismatch")
        if not result.state_machine_audit_passed_bool:
            failures.append("state-machine audit failed")
    except Exception as exc:
        failures.append(f"audit failed closed: {type(exc).__name__}: {exc}")
    return OhlcReplayAuditResult(not failures, tuple(failures))


def audit_minimal_path_ambiguity_envelope(
    env: MinimalPathAmbiguityEnvelope,
) -> OhlcReplayAuditResult:
    failures = []
    try:
        if env.exact_assignment_count != 2**env.ambiguous_candle_count:
            failures.append("exact enumeration count mismatch")
        assignments = {r.path_policies for r in env.assignment_results}
        if env.min_assignment not in assignments or env.max_assignment not in assignments:
            failures.append("min/max assignment missing")
        if env.minimal_path_pnl_min_usdt > env.minimal_path_pnl_max_usdt:
            failures.append("min greater than max")
        if (
            env.minimal_path_pnl_width_usdt
            != env.minimal_path_pnl_max_usdt - env.minimal_path_pnl_min_usdt
        ):
            failures.append("width mismatch")
        for flag in (
            env.full_intrabar_path_reconstructed_bool,
            env.arbitrary_intrabar_oscillation_bounded_bool,
            env.global_true_worst_case_proven_bool,
            env.global_true_best_case_proven_bool,
        ):
            if flag is not False:
                failures.append("guardrail flag must be false")
        if (
            env.exact_enumeration_complete_bool is not True
            or env.minimal_path_enumeration_complete_bool is not True
        ):
            failures.append("enumeration completion flag invalid")
    except Exception as exc:
        failures.append(f"audit failed closed: {type(exc).__name__}: {exc}")
    return OhlcReplayAuditResult(not failures, tuple(failures))
