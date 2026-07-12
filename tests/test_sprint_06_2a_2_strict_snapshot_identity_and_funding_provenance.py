from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import random

import pytest

from bybit_grid.backtest.neutral_grid.models import LiquidityRole, NeutralGridConfig, QuantitySource
from bybit_grid.backtest.ohlc_replay import (
    CandleSource,
    FundingObservation,
    MinimalPathPolicy,
    OhlcCandle1m,
    audit_minimal_path_ambiguity_envelope,
    audit_ohlc_replay_result,
    enumerate_minimal_path_ambiguity_envelope,
    replay_ohlc_minimal_path,
)


def D(x: object) -> Decimal:
    return Decimal(str(x))


def cfg(sym: str = "BTCUSDT", low: str = "90", high: str = "110", base: str = "100", cells: int = 4) -> NeutralGridConfig:
    return NeutralGridConfig("linear", sym, D(low), D(high), D(base), cells, D("0.01"), QuantitySource.synthetic_explicit, D("1"), D("0.001"), D("0.001"), LiquidityRole.maker, LiquidityRole.taker, D("0"), None, None)


def candle(t: int = 60000, *, sym: str = "BTCUSDT", o: str = "100", h: str = "105", low: str = "95", cl: str = "100", source: CandleSource = CandleSource.synthetic_1m) -> OhlcCandle1m:
    return OhlcCandle1m("linear", sym, t, D(o), D(h), D(low), D(cl), True, source)


def ambiguous_result():
    return replay_ohlc_minimal_path(cfg(), 60000, [candle()], MinimalPathPolicy.open_high_low_close)


def flat_zero_result():
    return replay_ohlc_minimal_path(cfg(), 60000, [candle(o="100", h="100", low="100", cl="100")], MinimalPathPolicy.open_high_low_close)


def assert_bad(obj, code: str | None = None) -> None:
    audit = audit_ohlc_replay_result(obj)
    assert not audit.passed_bool
    if code:
        assert code in audit.failures


def test_replay_scalar_aliases_are_rejected_separately():
    r = ambiguous_result()
    assert_bad(replace(r, candle_count_input=True), "replay_scalar_type_mismatch")
    assert_bad(replace(r, candle_count_processed=True), "replay_scalar_type_mismatch")
    assert_bad(replace(r, candles_not_processed_after_termination=False), "replay_scalar_type_mismatch")
    assert_bad(replace(r, ambiguous_candle_count=True), "replay_scalar_type_mismatch")
    assert_bad(replace(r, terminated_bool=0), "replay_scalar_type_mismatch")


class StrSubclass(str):
    pass


def test_replay_exact_str_and_decimal_zero_are_rejected():
    r = flat_zero_result()
    assert_bad(replace(r, category=StrSubclass("linear")), "replay_scalar_type_mismatch")
    assert_bad(replace(r, symbol=StrSubclass("BTCUSDT")), "replay_scalar_type_mismatch")
    assert r.final_total_pnl_usdt == D("0")
    assert_bad(replace(r, final_total_pnl_usdt=0), "replay_scalar_type_mismatch")


def test_replay_evidence_container_aliases_are_rejected():
    r = ambiguous_result()
    for kwargs in (
        {"source_candles": list(r.source_candles)},
        {"source_funding_observations": list(r.source_funding_observations)},
        {"generated_events": list(r.generated_events)},
        {"path_policies": list(r.path_policies)},
    ):
        assert_bad(replace(r, **kwargs), "source_container_type_mismatch")


def test_alternate_path_nested_simulation_result_substitution_is_rejected():
    config = cfg(low="80", high="120", base="100", cells=6)
    c = candle(o="94", h="96", low="82", cl="92")
    ohlc = replay_ohlc_minimal_path(config, 60000, [c], MinimalPathPolicy.open_high_low_close)
    olhc = replay_ohlc_minimal_path(config, 60000, [c], MinimalPathPolicy.open_low_high_close)
    assert ohlc.final_total_pnl_usdt == olhc.final_total_pnl_usdt
    assert ohlc.state_machine_result != olhc.state_machine_result
    assert_bad(replace(ohlc, state_machine_result=olhc.state_machine_result), "state_machine_result_mismatch")


def test_nested_config_mismatch_rejected():
    r = ambiguous_result()
    bad_config = cfg(sym="ETHUSDT")
    assert_bad(replace(r, source_config=bad_config), "source_config_mismatch")


def test_valid_fresh_replay_passes_ohlc_and_olhc():
    c = candle(o="94", h="96", low="82", cl="92")
    config = cfg(low="80", high="120", base="100", cells=6)
    for policy in (MinimalPathPolicy.open_high_low_close, MinimalPathPolicy.open_low_high_close):
        assert audit_ohlc_replay_result(replay_ohlc_minimal_path(config, 60000, [c], policy)).passed_bool


def test_funding_invalid_containers_are_value_error():
    for bad in (False, 0, "", b"", {}):
        with pytest.raises(ValueError, match="funding_observations"):
            replay_ohlc_minimal_path(cfg(), 60000, [candle(), candle(120000)], MinimalPathPolicy.open_high_low_close, bad)


def test_funding_provenance_rejections():
    with pytest.raises(ValueError):
        replay_ohlc_minimal_path(cfg(), 60000, [candle(), candle(120000)], MinimalPathPolicy.open_high_low_close, [FundingObservation("linear", "ETHUSDT", 120000, D("0"), D("100"))])
    with pytest.raises(ValueError):
        FundingObservation("inverse", "BTCUSDT", 120000, D("0"), D("100"))
    with pytest.raises(ValueError):
        FundingObservation("linear", " BTCUSDT ", 120000, D("0"), D("100"))


def test_mixed_source_rejected_and_same_source_passes():
    with pytest.raises(ValueError, match="CandleSource"):
        replay_ohlc_minimal_path(cfg(), 60000, [candle(), candle(120000, source=CandleSource.bybit_trade_kline_1m)], MinimalPathPolicy.open_high_low_close)
    for src in (CandleSource.synthetic_1m, CandleSource.bybit_trade_kline_1m):
        r = replay_ohlc_minimal_path(cfg(), 60000, [candle(source=src), candle(120000, source=src)], MinimalPathPolicy.open_high_low_close)
        assert r.candle_source is src
        assert audit_ohlc_replay_result(r).passed_bool


def envelope():
    return enumerate_minimal_path_ambiguity_envelope(cfg(), 60000, [candle(o="100", h="109", low="91", cl="100")])


def assert_bad_env(env_obj):
    assert not audit_minimal_path_ambiguity_envelope(env_obj).passed_bool


def test_envelope_type_aliases_rejected():
    e = envelope()
    assert_bad_env(replace(e, ambiguous_candle_count=True))
    assert_bad_env(replace(e, exact_assignment_count=2.0))
    assert_bad_env(replace(e, minimal_path_pnl_width_usdt=0))
    assert_bad_env(replace(e, path_sensitive_bool=0))
    assert_bad_env(replace(e, assignment_results=list(e.assignment_results)))
    assert_bad_env(replace(e, completed_cycle_count_min=True))


def test_valid_assignments_envelope_reconstruction_cycle_bounds_and_flags():
    e = enumerate_minimal_path_ambiguity_envelope(cfg(low="80", high="120", base="100", cells=6), 60000, [candle(o="98", h="115", low="96", cl="107.4")])
    assert all(audit_ohlc_replay_result(r).passed_bool for r in e.assignment_results)
    assert audit_minimal_path_ambiguity_envelope(e).passed_bool
    assert e.completed_cycle_count_min == 1
    assert e.completed_cycle_count_max == 2
    assert e.full_intrabar_path_reconstructed_bool is False
    assert e.arbitrary_intrabar_oscillation_bounded_bool is False
    assert e.global_true_worst_case_proven_bool is False
    assert e.global_true_best_case_proven_bool is False
    for r in e.assignment_results:
        flags = r.state_machine_result.proof_flags
        assert flags["risk_budget_proven_bool"] is False
        assert flags["parameter_selection_performed_bool"] is False
        assert flags["profitability_claims_present_bool"] is False
        assert flags["live_execution_present_bool"] is False


def test_seeded_randomized_short_path_smoke_valid_audits_pass():
    rng = random.Random(60202)
    for i in range(8):
        spread = rng.randint(4, 9)
        c = candle(o="100", h=str(100 + spread), low=str(100 - spread), cl="100")
        e = enumerate_minimal_path_ambiguity_envelope(cfg(), 60000, [c], max_exact_ambiguous_candles=1)
        assert audit_minimal_path_ambiguity_envelope(e).passed_bool
        assert all(audit_ohlc_replay_result(r).passed_bool for r in e.assignment_results)


def test_no_private_live_api_or_telegram_surface_in_replay_results():
    text = repr(ambiguous_result()).lower()
    assert "api_key" not in text
    assert "secret" not in text
    assert "telegram" not in text
    assert "testnet" not in text
