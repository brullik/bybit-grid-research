from decimal import Decimal
import pytest
from bybit_grid.backtest.neutral_grid.models import LiquidityRole, NeutralGridConfig, QuantitySource
from bybit_grid.backtest.ohlc_replay import (
    CandleSource,
    FundingObservation,
    MinimalPathEnumerationCapExceededError,
    MinimalPathPolicy,
    OhlcCandle1m,
    audit_minimal_path_ambiguity_envelope,
    audit_ohlc_replay_result,
    enumerate_minimal_path_ambiguity_envelope,
    minimal_path_prices,
    minimal_paths_are_distinct,
    replay_ohlc_minimal_path,
    validate_candle_sequence,
)


def D(x):
    return Decimal(str(x))


def cfg(low=D("90"), high=D("110"), base=D("100"), lower_term=None, upper_term=None):
    return NeutralGridConfig(
        "linear",
        "BTCUSDT",
        low,
        high,
        base,
        4,
        D("0.01"),
        QuantitySource.synthetic_explicit,
        D("1"),
        D("0.001"),
        D("0.001"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("0"),
        lower_term,
        upper_term,
    )


def c(t=60000, o="100", h="105", low="95", cl="100"):
    return OhlcCandle1m(
        "linear", "BTCUSDT", t, D(o), D(h), D(low), D(cl), True, CandleSource.synthetic_1m
    )


def test_valid_decimal_and_reject_bad_values():
    assert c().close_boundary_ms == 120000
    for bad in (1, 1.0, True):
        with pytest.raises(ValueError):
            OhlcCandle1m(
                "linear", "BTCUSDT", 60000, bad, D(1), D(1), D(1), True, CandleSource.synthetic_1m
            )
    with pytest.raises(ValueError):
        OhlcCandle1m(
            "linear", "BTCUSDT", 60000, D(10), D(9), D(8), D(9), True, CandleSource.synthetic_1m
        )
    with pytest.raises(ValueError):
        OhlcCandle1m(
            "linear", "BTCUSDT", 60000, D(1), D(1), D(1), D(1), False, CandleSource.synthetic_1m
        )
    with pytest.raises(ValueError):
        OhlcCandle1m(
            "linear", "BTCUSDT", 1, D(1), D(1), D(1), D(1), True, CandleSource.synthetic_1m
        )
    with pytest.raises(ValueError):
        OhlcCandle1m("linear", "BTCUSDT", 60000, D(1), D(1), D(1), D(1), True, "synthetic_1m")


def test_sequence_validation_duplicate_unsorted_gapped_and_gap_observable():
    validate_candle_sequence([c(60000), c(120000, o="101", h="102", low="99", cl="100")], 60000)
    for seq in ([c(60000), c(60000)], [c(120000), c(60000)], [c(60000), c(180000)]):
        with pytest.raises(ValueError):
            validate_candle_sequence(seq, 60000)
    r = replay_ohlc_minimal_path(
        cfg(),
        60000,
        [c(60000, o="100", h="101", low="99", cl="101"), c(120000, o="95", h="96", low="94", cl="95")],
        MinimalPathPolicy.open_high_low_close,
    )
    assert any(e.time_ms == 120000 and e.price == D("95") for e in r.generated_events)


def test_path_generation_ordering_and_duplicate_rules():
    x = c(o="100", h="105", low="95", cl="100")
    assert minimal_path_prices(x, MinimalPathPolicy.open_high_low_close) == (
        D(100),
        D(105),
        D(95),
        D(100),
    )
    assert minimal_path_prices(x, MinimalPathPolicy.open_low_high_close) == (
        D(100),
        D(95),
        D(105),
        D(100),
    )
    assert minimal_path_prices(
        c(o="100", h="100", low="95", cl="100"), MinimalPathPolicy.open_high_low_close
    ) == (D(100), D(95), D(100))
    assert minimal_paths_are_distinct(c(o="100", h="100", low="100", cl="100")) is False


def test_fixed_replay_invariant_ambiguous_no_double_fill_and_termination():
    flat = [c(o="100", h="100", low="100", cl="100")]
    a = replay_ohlc_minimal_path(cfg(), 60000, flat, MinimalPathPolicy.open_high_low_close)
    b = replay_ohlc_minimal_path(cfg(), 60000, flat, MinimalPathPolicy.open_low_high_close)
    assert a.final_total_pnl_usdt == b.final_total_pnl_usdt
    amb = [c(o="100", h="109", low="91", cl="100")]
    r1 = replay_ohlc_minimal_path(cfg(), 60000, amb, MinimalPathPolicy.open_high_low_close)
    r2 = replay_ohlc_minimal_path(cfg(), 60000, amb, MinimalPathPolicy.open_low_high_close)
    assert [e.side.value for e in r1.state_machine_result.ledger] != [
        e.side.value for e in r2.state_machine_result.ledger
    ]
    same = replay_ohlc_minimal_path(
        cfg(),
        60000,
        [c(o="100", h="100", low="95", cl="100")],
        MinimalPathPolicy.open_high_low_close,
    )
    assert len(same.state_machine_result.ledger) <= 2
    lo = replay_ohlc_minimal_path(
        cfg(lower_term=D("89")),
        60000,
        [c(o="100", h="101", low="80", cl="100"), c(120000)],
        MinimalPathPolicy.open_high_low_close,
    )
    up = replay_ohlc_minimal_path(
        cfg(upper_term=D("111")),
        60000,
        [c(o="100", h="120", low="99", cl="100"), c(120000)],
        MinimalPathPolicy.open_high_low_close,
    )
    assert lo.terminated_bool and lo.candle_count_processed == 1
    assert up.terminated_bool and up.candle_count_processed == 1


def test_funding_order_and_rejections():
    fs = [FundingObservation(120000, D("0.01"), D("100"))]
    r = replay_ohlc_minimal_path(
        cfg(), 60000, [c(60000), c(120000)], MinimalPathPolicy.open_high_low_close, fs
    )
    kinds = [(e.kind, e.time_ms) for e in r.generated_events]
    assert kinds.index(("funding", 120000)) < next(
        i for i, x in enumerate(kinds) if x == ("price", 120000)
    )
    with pytest.raises(ValueError):
        replay_ohlc_minimal_path(
            cfg(),
            60000,
            [c(60000)],
            MinimalPathPolicy.open_high_low_close,
            [FundingObservation(60000, D("0"), D("100"))],
        )
    with pytest.raises(ValueError):
        replay_ohlc_minimal_path(
            cfg(),
            60000,
            [c(60000), c(120000)],
            MinimalPathPolicy.open_high_low_close,
            [FundingObservation(180000, D("0"), D("100"))],
        )
    with pytest.raises(ValueError):
        FundingObservation(1, D("0"), D("100"))


def test_deterministic_detached_envelope_audit_and_guardrails():
    candles = [
        c(60000, o="100", h="109", low="91", cl="100"),
        c(120000, o="100", h="105", low="95", cl="100"),
    ]
    r1 = replay_ohlc_minimal_path(cfg(), 60000, candles, MinimalPathPolicy.open_high_low_close)
    r2 = replay_ohlc_minimal_path(cfg(), 60000, candles, MinimalPathPolicy.open_high_low_close)
    assert r1 == r2 and audit_ohlc_replay_result(r1).passed_bool
    env = enumerate_minimal_path_ambiguity_envelope(
        cfg(), 60000, candles, max_exact_ambiguous_candles=2
    )
    assert env.exact_assignment_count == 2**env.ambiguous_candle_count
    assert (
        env.minimal_path_pnl_width_usdt
        == env.minimal_path_pnl_max_usdt - env.minimal_path_pnl_min_usdt
    )
    assert audit_minimal_path_ambiguity_envelope(env).passed_bool
    assert all(
        audit_ohlc_replay_result(x).passed_bool and x.state_machine_audit_passed_bool
        for x in env.assignment_results
    )
    with pytest.raises(MinimalPathEnumerationCapExceededError):
        enumerate_minimal_path_ambiguity_envelope(
            cfg(), 60000, candles, max_exact_ambiguous_candles=1
        )
    flags = r1.state_machine_result.proof_flags
    for k in (
        "native_equivalence_proven_bool",
        "native_quantity_mapping_proven_bool",
        "native_termination_mapping_proven_bool",
        "liquidation_modeled_bool",
        "risk_budget_proven_bool",
        "parameter_selection_performed_bool",
        "profitability_claims_present_bool",
        "live_execution_present_bool",
    ):
        assert flags[k] is False
    assert (
        not env.full_intrabar_path_reconstructed_bool and not env.global_true_best_case_proven_bool
    )


def test_low_price_and_tight_high_price_and_no_live_surface():
    low_cfg = cfg(D("0.09"), D("0.11"), D("0.10"))
    assert replay_ohlc_minimal_path(
        low_cfg,
        60000,
        [c(o="0.10", h="0.105", low="0.095", cl="0.10")],
        MinimalPathPolicy.open_high_low_close,
    ).state_machine_audit_passed_bool
    high_cfg = cfg(D("99990"), D("100010"), D("100000"))
    assert replay_ohlc_minimal_path(
        high_cfg,
        60000,
        [c(o="100000", h="100005", low="99995", cl="100000")],
        MinimalPathPolicy.open_low_high_close,
    ).state_machine_audit_passed_bool
