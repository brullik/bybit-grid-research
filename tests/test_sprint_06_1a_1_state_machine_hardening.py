from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType

import pytest

from bybit_grid.backtest.neutral_grid import (
    FundingEvent,
    LiquidityRole,
    NeutralGridConfig,
    NeutralGridReferenceEngine,
    PriceEvent,
    QuantitySource,
    audit_simulation_result,
)
from bybit_grid.backtest.neutral_grid.accounting import apply_fill, selected_fee_rate, trading_fee
from bybit_grid.backtest.neutral_grid.geometry import validate_grid_geometry

D = Decimal


def cfg(**kw):
    lower = D("80")
    upper = D("125")
    base_price = __import__("bybit_grid.backtest.neutral_grid", fromlist=["geometric_grid_levels_decimal"]).geometric_grid_levels_decimal(lower, upper, 4).levels[2]
    base = dict(
        category="linear",
        symbol="BTCUSDT",
        lower_price=lower,
        upper_price=upper,
        base_price=base_price,
        grid_cell_number=4,
        quantity_per_grid_base=D("1"),
        quantity_source=QuantitySource.synthetic_explicit,
        leverage=D("1"),
        maker_fee_rate=D("0.001"),
        taker_fee_rate=D("0.002"),
        grid_fill_liquidity_role=LiquidityRole.maker,
        termination_liquidity_role=LiquidityRole.taker,
        termination_slippage_bps=D("10"),
        lower_termination_price=D("70"),
        upper_termination_price=D("130"),
    )
    base.update(kw)
    return NeutralGridConfig(**base)


def engine_with_cycle():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, e.levels[1]))
    e.process(PriceEvent(2, 2, e.levels[2]))
    return e


@pytest.mark.parametrize("field,value", [("grid_fill_liquidity_role", "maker"), ("termination_liquidity_role", "taker"), ("quantity_source", "synthetic_explicit")])
def test_plain_string_enums_rejected(field, value):
    with pytest.raises(ValueError):
        cfg(**{field: value})


@pytest.mark.parametrize("field,value", [("maker_fee_rate", 1), ("taker_fee_rate", 0.1), ("quantity_per_grid_base", "1")])
def test_non_decimal_accounting_values_rejected(field, value):
    with pytest.raises(ValueError):
        cfg(**{field: value})


@pytest.mark.parametrize("seq", [True, 1.5, -1])
def test_bad_sequence_rejected(seq):
    with pytest.raises(ValueError):
        PriceEvent(seq, 0, D("100"))


@pytest.mark.parametrize("time", [True, 1.5, -1])
def test_bad_time_rejected(time):
    with pytest.raises(ValueError):
        PriceEvent(1, time, D("100"))


def test_accounting_invalid_average_entry_and_fee_fallback_rejected():
    with pytest.raises(ValueError):
        apply_fill(side="buy", quantity=D("1"), price=D("1"), signed_position=D("1"), average_entry=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        trading_fee(D("1"), D("1"), "maker", D("0.1"), D("0.2"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        selected_fee_rate("maker", D("0.1"), D("0.2"))  # type: ignore[arg-type]


def test_termination_guards_and_invalid_manual_prices_leave_state_unchanged():
    e = NeutralGridReferenceEngine(cfg())
    e.terminate_now(1, 1, D("100"))
    before = e.result()
    with pytest.raises(ValueError):
        e.terminate_now(2, 2, D("100"))
    with pytest.raises(ValueError):
        e.process(PriceEvent(3, 3, D("101")))
    assert e.result().ledger == before.ledger
    for bad in ["100", D("NaN"), D("Infinity"), D("0"), D("-1")]:
        e2 = NeutralGridReferenceEngine(cfg())
        before2 = e2.result()
        with pytest.raises(ValueError):
            e2.terminate_now(1, 1, bad)  # type: ignore[arg-type]
        assert e2.result().ledger == before2.ledger


def test_terminate_after_boundary_rejected():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, D("131")))
    before = e.result()
    with pytest.raises(ValueError):
        e.terminate_now(2, 2, D("131"))
    assert e.result().termination == before.termination


def test_result_snapshot_detached_and_immutable_containers():
    e = NeutralGridReferenceEngine(cfg())
    r1 = e.result()
    e.process(PriceEvent(1, 1, e.levels[1]))
    assert r1.ledger == ()
    assert len(r1.all_orders) == 4
    with pytest.raises(TypeError):
        r1.active_orders[0] = next(iter(r1.all_orders))  # type: ignore[index]
    with pytest.raises(AttributeError):
        r1.all_orders.clear()  # type: ignore[attr-defined]
    assert len(e.result().all_orders) > len(r1.all_orders)


def test_audit_rejects_tampered_final_and_ledger_fields():
    r = engine_with_cycle().result()
    assert audit_simulation_result(r).passed_bool
    assert not audit_simulation_result(replace(r, average_entry=D("99"))).passed_bool
    bad_ledger = list(r.ledger)
    bad_ledger[0] = replace(bad_ledger[0], signed_position_after=D("99"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad_ledger))).passed_bool
    bad_ledger = list(r.ledger)
    bad_ledger[0] = replace(bad_ledger[0], trading_fee_usdt=D("99"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad_ledger))).passed_bool


def test_audit_rejects_funding_cumulative_proof_init_termination_and_cycles():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, e.levels[1]))
    e.process(FundingEvent(2, 2, D("100"), D("0.01")))
    r = e.result()
    bad = list(r.ledger)
    bad[1] = replace(bad[1], funding_rate=D("0.02"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad))).passed_bool
    bad[1] = replace(r.ledger[1], cumulative_funding_pnl_usdt=D("99"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad))).passed_bool
    assert not audit_simulation_result(replace(r, proof_flags=MappingProxyType({**r.proof_flags, "risk_budget_proven_bool": True}))).passed_bool
    assert not audit_simulation_result(replace(r, initialization_audit=MappingProxyType({**r.initialization_audit, "initial_position_zero_bool": False}))).passed_bool
    cyc = engine_with_cycle().result()
    assert not audit_simulation_result(replace(cyc, cumulative_completed_grid_cycle_gross_usdt=D("99"))).passed_bool
    assert not audit_simulation_result(replace(cyc, completed_cycles=(replace(cyc.completed_cycles[0], gross_usdt=D("99")),))).passed_bool
    term_e = NeutralGridReferenceEngine(cfg())
    term_e.terminate_now(1, 1, D("100"))
    term = term_e.result()
    assert not audit_simulation_result(replace(term, termination=replace(term.termination, all_orders_cancelled_bool=False))).passed_bool


def test_geometry_final_ratio_and_altered_final_level():
    r = NeutralGridReferenceEngine(cfg()).result()
    validate_grid_geometry(r.levels, r.config.lower_price, r.config.upper_price, r.config.grid_cell_number)
    with pytest.raises(ValueError):
        validate_grid_geometry((*r.levels[:-1], D("121")), r.config.lower_price, r.config.upper_price, r.config.grid_cell_number)


def test_valid_scenarios_and_no_live_surface():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, e.levels[1]))
    e.process(FundingEvent(2, 2, D("100"), D("0.01")))
    assert audit_simulation_result(e.result()).passed_bool
    import bybit_grid.backtest.neutral_grid as ng
    assert not any(name in dir(ng) for name in ["create_order", "cancel_order", "private_api"])
