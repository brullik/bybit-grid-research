from __future__ import annotations
from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType

import pytest

from bybit_grid.backtest.neutral_grid import NeutralGridReferenceEngine, audit_simulation_result, geometric_grid_levels_decimal
from bybit_grid.backtest.neutral_grid.geometry import validate_grid_geometry
from bybit_grid.backtest.neutral_grid.models import FundingEvent, LiquidityRole, NeutralGridConfig, OrderSide, PriceEvent, QuantitySource, TerminationReason

D = Decimal


def cfg(**kw):
    d = dict(category="linear", symbol="BTCUSDT", lower_price=D("80"), upper_price=D("120"), base_price=D("100"), grid_cell_number=4, quantity_per_grid_base=D("1"), quantity_source=QuantitySource.synthetic_explicit, leverage=D("1"), maker_fee_rate=D("0.001"), taker_fee_rate=D("0.002"), grid_fill_liquidity_role=LiquidityRole.maker, termination_liquidity_role=LiquidityRole.taker, termination_slippage_bps=D("10"), lower_termination_price=D("70"), upper_termination_price=D("130"))
    d.update(kw)
    return NeutralGridConfig(**d)


def assert_audits(e):
    r = e.result()
    a = audit_simulation_result(r)
    assert a.passed_bool, a.failures
    return r


def test_canonical_levels_not_snapped_low_price_and_tight_range():
    for c in [cfg(), cfg(lower_price=D("0.08"), upper_price=D("0.12"), base_price=D("0.10"), lower_termination_price=D("0.07"), upper_termination_price=D("0.13")), cfg(lower_price=D("9998"), upper_price=D("10002"), base_price=D("10000"), grid_cell_number=8, lower_termination_price=D("9997"), upper_termination_price=D("10003"))]:
        e = NeutralGridReferenceEngine(c)
        canonical = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
        assert e.levels == canonical
        assert c.base_price not in e.levels or c.base_price in canonical
        assert len(e.levels) == c.grid_cell_number + 1
        assert all(e.levels[i] < e.levels[i + 1] for i in range(c.grid_cell_number))
        assert e.orders
        assert_audits(e)
    assert D("100") not in NeutralGridReferenceEngine(cfg()).levels


def test_exact_base_level_has_no_order_and_between_level_not_moved():
    g = geometric_grid_levels_decimal(D("80"), D("125"), 4).levels
    exact = cfg(upper_price=D("125"), base_price=g[2], upper_termination_price=D("130"))
    e = NeutralGridReferenceEngine(exact)
    assert g[2] in e.levels and 2 not in e.orders
    assert_audits(e)
    between = cfg(base_price=D("100"))
    e2 = NeutralGridReferenceEngine(between)
    assert D("100") not in e2.levels and e2.levels == geometric_grid_levels_decimal(D("80"), D("120"), 4).levels


def test_geometry_validation_rejects_arithmetic_altered_and_bad_types():
    with pytest.raises(ValueError):
        validate_grid_geometry((D("80"), D("90"), D("100"), D("110"), D("120")), D("80"), D("120"), 4)
    levels = list(geometric_grid_levels_decimal(D("80"), D("120"), 4).levels)
    levels[2] += D("0.0000000000001")
    with pytest.raises(ValueError):
        validate_grid_geometry(tuple(levels), D("80"), D("120"), 4)
    bads = [(D("NaN"), D("120"), 4), (D("80"), D("Infinity"), 4), (80, D("120"), 4), (D("80"), D("120"), True), (D("80"), D("120"), 4.0)]
    for lower, upper, n in bads:
        with pytest.raises(ValueError):
            geometric_grid_levels_decimal(lower, upper, n)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_grid_geometry((D("80"), D("80"), D("100")), D("80"), D("120"), 2)


def test_invalid_termination_config_rejected():
    for kwargs in [dict(lower_termination_price=D("0")), dict(lower_termination_price=D("80")), dict(upper_termination_price=D("120")), dict(termination_slippage_bps=D("10000"))]:
        with pytest.raises(ValueError):
            cfg(**kwargs)


def test_duck_typed_event_rejected_without_state_mutation():
    class Duck:
        sequence_id = 1
        time_ms = 1
        price = D("90")
    e = NeutralGridReferenceEngine(cfg())
    before = e.result()
    with pytest.raises(TypeError):
        e.process(Duck())  # type: ignore[arg-type]
    after = e.result()
    assert after == before


def test_prefix_audit_matrix_valid_paths():
    paths = [
        [PriceEvent(1, 1, cfg().lower_price)],
        [PriceEvent(1, 1, cfg().upper_price)],
        [PriceEvent(1, 1, cfg().lower_price), PriceEvent(2, 2, D("100"))],
        [PriceEvent(1, 1, D("90")), FundingEvent(2, 2, D("100"), D("0.01"))],
        [PriceEvent(1, 1, D("69"))],
        [PriceEvent(1, 1, D("131"))],
    ]
    for events in paths:
        e = NeutralGridReferenceEngine(cfg())
        for ev in events:
            e.process(ev)
            assert_audits(e)
    e = NeutralGridReferenceEngine(cfg())
    e.terminate_now(1, 1, D("100"))
    assert_audits(e)


def test_audit_rejects_order_ledger_active_and_metadata_tamper():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, e.levels[1]))
    r = e.result()
    assert audit_simulation_result(r).passed_bool
    bad_ledger = list(r.ledger)
    bad_ledger[0] = replace(bad_ledger[0], sequence_id=99)
    assert not audit_simulation_result(replace(r, ledger=tuple(bad_ledger))).passed_bool
    bad_ledger = list(r.ledger)
    bad_ledger[0] = replace(bad_ledger[0], order_id="missing")
    assert not audit_simulation_result(replace(r, ledger=tuple(bad_ledger))).passed_bool
    bad_orders = list(r.all_orders)
    bad_orders[0] = replace(bad_orders[0], price=D("1"))
    assert not audit_simulation_result(replace(r, all_orders=tuple(bad_orders))).passed_bool
    ao = dict(r.active_orders)
    k = next(iter(ao))
    ao[k] = replace(ao[k], side=OrderSide.sell if ao[k].side is OrderSide.buy else OrderSide.buy)
    assert not audit_simulation_result(replace(r, active_orders=MappingProxyType(ao))).passed_bool


def test_termination_and_proof_metadata_tamper_rejected():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, D("69")))
    r = e.result()
    assert audit_simulation_result(r).passed_bool
    assert not audit_simulation_result(replace(r, termination=replace(r.termination, termination_reason=TerminationReason.upper_boundary))).passed_bool
    bad = list(r.ledger)
    bad[2] = replace(bad[2], price=D("71"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad))).passed_bool
    bad = list(r.ledger)
    bad[-1] = replace(bad[-1], price=D("1"))
    assert not audit_simulation_result(replace(r, ledger=tuple(bad))).passed_bool
    assert not audit_simulation_result(replace(r, proof_flags=MappingProxyType({**r.proof_flags, "extra_bool": True}))).passed_bool
    pf = dict(r.proof_flags)
    pf.pop("event_path_completeness_proven_bool")
    assert not audit_simulation_result(replace(r, proof_flags=MappingProxyType(pf))).passed_bool
    assert not audit_simulation_result(replace(r, events_rejected_after_termination_count=True)).passed_bool
    assert not audit_simulation_result(replace(r, events_rejected_after_termination_count=-1)).passed_bool
    assert not audit_simulation_result(replace(r, geometry_rounding_applied_bool=True)).passed_bool
    assert r.proof_flags["event_path_completeness_proven_bool"] is False
