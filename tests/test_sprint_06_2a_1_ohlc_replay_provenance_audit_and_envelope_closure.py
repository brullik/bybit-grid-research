from dataclasses import replace
from decimal import Decimal
import pytest
from bybit_grid.backtest.neutral_grid.models import LiquidityRole, NeutralGridConfig, QuantitySource
from bybit_grid.backtest.ohlc_replay import (
    CandleSource,
    FundingObservation,
    GeneratedReplayEvent,
    MinimalPathPolicy,
    OhlcCandle1m,
    ReplayEventKind,
    audit_minimal_path_ambiguity_envelope,
    audit_ohlc_replay_result,
    enumerate_minimal_path_ambiguity_envelope,
    replay_ohlc_minimal_path,
    validate_candle_sequence,
)


def D(x):
    return Decimal(str(x))


def cfg(sym="BTCUSDT", low="90", high="110", base="100", cells=4, lt=None, ut=None):
    return NeutralGridConfig(
        "linear",
        sym,
        D(low),
        D(high),
        D(base),
        cells,
        D("0.01"),
        QuantitySource.synthetic_explicit,
        D("1"),
        D("0.001"),
        D("0.001"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("0"),
        lt,
        ut,
    )


def c(t=60000, sym="BTCUSDT", o="100", h="105", low="95", cl="100"):
    return OhlcCandle1m(
        "linear", sym, t, D(o), D(h), D(low), D(cl), True, CandleSource.synthetic_1m
    )


def ok_result():
    return replay_ohlc_minimal_path(
        cfg(),
        60000,
        [c(), c(120000, o="100", h="106", low="94", cl="101")],
        MinimalPathPolicy.open_high_low_close,
        [FundingObservation("linear", "BTCUSDT", 120000, D("0.01"), D("100"))],
    )


def test_stripped_symbol_and_mismatch_and_stable_object_validation():
    with pytest.raises(ValueError):
        OhlcCandle1m(
            "linear", " BTCUSDT ", 60000, D(1), D(1), D(1), D(1), True, CandleSource.synthetic_1m
        )
    with pytest.raises(ValueError):
        replay_ohlc_minimal_path(
            cfg("ETHUSDT"), 60000, [c()], MinimalPathPolicy.open_high_low_close
        )
    with pytest.raises(ValueError, match="OhlcCandle1m"):
        validate_candle_sequence([object()], 60000)


def test_strict_cap_types_and_negative_rejected():
    for bad in (True, 1.5, "12", -1):
        with pytest.raises(ValueError):
            enumerate_minimal_path_ambiguity_envelope(
                cfg(), 60000, [c()], max_exact_ambiguous_candles=bad
            )


def test_generated_event_contract_and_funding_rate_retained():
    with pytest.raises(ValueError):
        GeneratedReplayEvent(1, 60000, "price", 0, D("1"))
    with pytest.raises(ValueError):
        GeneratedReplayEvent(True, 60000, ReplayEventKind.price, 0, D("1"))
    r = ok_result()
    fe = next(e for e in r.generated_events if e.kind is ReplayEventKind.funding)
    assert fe.funding_rate == D("0.01") and fe.price == D("100")


def test_replay_audit_rejects_provenance_path_event_order_and_value_tamper():
    r = ok_result()
    assert audit_ohlc_replay_result(r).passed_bool
    tampered = [
        replace(r, symbol="ETHUSDT"),
        replace(r, path_policies=(MinimalPathPolicy.open_low_high_close,) * r.candle_count_input),
        replace(
            r,
            generated_events=r.generated_events
            + (GeneratedReplayEvent(99, 120000, ReplayEventKind.price, 1, D("100")),),
        ),
        replace(
            r,
            generated_events=(r.generated_events[0], r.generated_events[2], r.generated_events[1])
            + r.generated_events[3:],
        ),
        replace(
            r,
            generated_events=tuple(
                replace(e, candle_index=e.candle_index + 1) if i == 0 else e
                for i, e in enumerate(r.generated_events)
            ),
        ),
        replace(
            r,
            generated_events=tuple(
                replace(e, price=D("101")) if i == 0 else e
                for i, e in enumerate(r.generated_events)
            ),
        ),
        replace(r, final_mark_price=D("1")),
        replace(r, final_total_pnl_usdt=D("999")),
        replace(r, termination_reason="fake"),
        replace(
            r,
            state_machine_result=replace(
                r.state_machine_result,
                proof_flags={**r.state_machine_result.proof_flags, "risk_budget_proven_bool": True},
            ),
        ),
        replace(
            r,
            state_machine_result=replace(
                r.state_machine_result, cumulative_trading_fees_usdt=D("999")
            ),
        ),
    ]
    for t in tampered:
        assert not audit_ohlc_replay_result(t).passed_bool


def test_termination_prefix_rejects_event_after_terminated_replay():
    r = replay_ohlc_minimal_path(
        cfg(low="95", lt=D("93")),
        60000,
        [c(o="100", h="101", low="92", cl="94"), c(120000)],
        MinimalPathPolicy.open_high_low_close,
    )
    assert r.terminated_bool
    bad = replace(
        r,
        generated_events=r.generated_events
        + (
            GeneratedReplayEvent(
                r.generated_events[-1].sequence_id + 1, 120000, ReplayEventKind.price, 1, D("100")
            ),
        ),
    )
    assert not audit_ohlc_replay_result(bad).passed_bool


def test_fresh_replay_valid_low_and_tight_high_cases():
    for r in [
        replay_ohlc_minimal_path(
            cfg(low="95", lt=D("93")),
            60000,
            [c(o="100", h="101", low="92", cl="94")],
            MinimalPathPolicy.open_high_low_close,
        ),
        replay_ohlc_minimal_path(
            cfg(high="105", ut=D("106")),
            60000,
            [c(o="100", h="107", low="99", cl="105")],
            MinimalPathPolicy.open_high_low_close,
        ),
    ]:
        assert audit_ohlc_replay_result(r).passed_bool


def test_envelope_assignment_aggregates_and_tampers():
    env = enumerate_minimal_path_ambiguity_envelope(
        cfg(),
        60000,
        [c(o="100", h="109", low="91", cl="100"), c(120000, o="100", h="106", low="94", cl="100")],
    )
    assert audit_minimal_path_ambiguity_envelope(env).passed_bool
    assert all(audit_ohlc_replay_result(r).passed_bool for r in env.assignment_results)
    tampered = [
        replace(env, assignment_results=env.assignment_results[:-1]),
        replace(env, assignment_results=env.assignment_results + (env.assignment_results[0],)),
        replace(env, minimal_path_pnl_min_usdt=D("-999")),
        replace(env, completed_cycle_count_min=99),
        replace(env, trading_fees_min_usdt=D("-1")),
        replace(env, termination_reasons_observed=("fake",)),
        replace(env, path_sensitive_bool=not env.path_sensitive_bool),
        replace(env, ambiguous_candle_count=99),
    ]
    for t in tampered:
        assert not audit_minimal_path_ambiguity_envelope(t).passed_bool
    keys = [r.path_policies for r in env.assignment_results]
    assert keys == sorted(
        keys,
        key=lambda ps: tuple(0 if p is MinimalPathPolicy.open_high_low_close else 1 for p in ps),
    )


def test_concrete_cycle_bound_regression_and_guardrails_false():
    env = enumerate_minimal_path_ambiguity_envelope(
        cfg(low="80", high="120", base="100", cells=6),
        60000,
        [c(o="98", h="115", low="96", cl="107.4")],
    )
    assert env.completed_cycle_count_min == 1 and env.completed_cycle_count_max == 2
    for r in env.assignment_results:
        pf = r.state_machine_result.proof_flags
        for k in (
            "native_equivalence_proven_bool",
            "native_quantity_mapping_proven_bool",
            "native_termination_mapping_proven_bool",
            "liquidation_modeled_bool",
            "event_path_completeness_proven_bool",
            "risk_budget_proven_bool",
            "parameter_selection_performed_bool",
            "profitability_claims_present_bool",
            "live_execution_present_bool",
        ):
            assert pf[k] is False
    assert env.full_intrabar_path_reconstructed_bool is False
    assert env.arbitrary_intrabar_oscillation_bounded_bool is False
    assert env.global_true_worst_case_proven_bool is False
    assert env.global_true_best_case_proven_bool is False
