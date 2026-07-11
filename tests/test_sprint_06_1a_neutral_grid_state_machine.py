from __future__ import annotations
from decimal import Decimal
import pytest

from bybit_grid.backtest.neutral_grid import (
    NeutralGridReferenceEngine,
    audit_simulation_result,
    geometric_grid_levels_decimal,
)
from bybit_grid.backtest.neutral_grid.models import (
    FundingEvent,
    LiquidityRole,
    NeutralGridConfig,
    OrderSide,
    PriceEvent,
    QuantitySource,
    ZERO,
)
from bybit_grid.research.outcome_core.grid_crossings import geometric_grid_levels

D = Decimal


def cfg(lower_term=D("70"), upper_term=D("130")):
    lower = D("80")
    upper = D("125")
    base = geometric_grid_levels_decimal(lower, upper, 4).levels[2]
    return NeutralGridConfig(
        "linear",
        "BTCUSDT",
        lower,
        upper,
        base,
        4,
        D("1"),
        QuantitySource.synthetic_explicit,
        D("2"),
        D("0.001"),
        D("0.002"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("10"),
        lower_term,
        upper_term,
    )


def run(events, c=None):
    return NeutralGridReferenceEngine(c or cfg()).run(events)


def test_geometry_n_plus_one_strict_exact_and_numpy_compatible():
    g = geometric_grid_levels_decimal(D("90"), D("110"), 4)
    assert len(g.levels) == 5 and g.levels[0] == D("90") and g.levels[-1] == D("110")
    assert all(g.levels[i] < g.levels[i + 1] for i in range(4))
    np = geometric_grid_levels(90.0, 110.0, 4)
    for a, b in zip(g.levels, np, strict=True):
        assert abs(float(a) - float(b)) < 1e-10
    ratios = [g.levels[i + 1] / g.levels[i] for i in range(3)]
    assert max(ratios) - min(ratios) < D("1e-40")
    assert not g.geometry_rounding_applied_bool


def test_neutral_initialization_order_book_invariants():
    r = run([])
    a = r.initialization_audit
    assert r.signed_position == ZERO and r.average_entry is None
    assert (
        a["initial_position_zero_bool"]
        and a["buy_orders_below_base_bool"]
        and a["sell_orders_above_base_bool"]
    )
    assert (
        a["base_level_has_no_order_bool"]
        and a["one_active_order_per_level_bool"]
        and a["constant_quantity_per_grid_bool"]
    )
    assert all(o.side is OrderSide.buy for o in r.active_orders.values() if o.price < D("100"))
    assert all(o.side is OrderSide.sell for o in r.active_orders.values() if o.price > D("100"))


def test_buy_then_adjacent_sell_opens_long_closes_and_exact_long_cycle_fee_once():
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    r = run([PriceEvent(1, 1, levels[1]), PriceEvent(2, 2, levels[2])], c)
    assert r.signed_position == ZERO and len(r.completed_cycles) == 1
    assert [e.side for e in r.ledger if e.side] == [OrderSide.buy, OrderSide.sell]
    cyc = r.completed_cycles[0]
    assert cyc.gross_usdt == levels[2] - levels[1]
    assert cyc.open_fee_usdt == levels[1] * D("0.001") and cyc.close_fee_usdt == levels[2] * D(
        "0.001"
    )
    assert cyc.net_usdt == cyc.gross_usdt - cyc.open_fee_usdt - cyc.close_fee_usdt
    assert r.cumulative_trading_fees_usdt == levels[1] * D("0.001") + levels[2] * D("0.001")
    assert audit_simulation_result(r).passed_bool


def test_sell_then_adjacent_buy_opens_short_closes_and_exact_short_cycle():
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    r = run([PriceEvent(1, 1, levels[3]), PriceEvent(2, 2, levels[2])], c)
    assert r.signed_position == ZERO and len(r.completed_cycles) == 1
    cyc = r.completed_cycles[0]
    assert cyc.gross_usdt == levels[3] - levels[2]
    assert cyc.net_usdt == cyc.gross_usdt - levels[3] * D("0.001") - levels[2] * D("0.001")
    assert audit_simulation_result(r).passed_bool


def test_multiple_down_and_up_fills_accumulate_long_and_short_path_order():
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    down = run([PriceEvent(1, 1, levels[0])], c)
    assert down.signed_position == D("2")
    assert [e.level_index for e in down.ledger if e.side] == [1, 0]
    up = run([PriceEvent(1, 1, levels[4])], c)
    assert up.signed_position == D("-2")
    assert [e.level_index for e in up.ledger if e.side] == [3, 4]


def test_reversal_no_double_count_and_rearmed_second_cycle_boundary_no_double_fill():
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    r = run(
        [
            PriceEvent(1, 1, levels[1]),
            PriceEvent(2, 2, levels[2]),
            PriceEvent(3, 3, levels[1]),
            PriceEvent(4, 4, levels[2]),
            PriceEvent(5, 5, levels[2]),
        ],
        c,
    )
    assert r.signed_position == ZERO and len(r.completed_cycles) == 2
    assert len({cyc.open_fill_id for cyc in r.completed_cycles}) == 2
    assert [e.price for e in r.ledger if e.side][-1] == levels[2]


def test_ordering_validation_and_same_timestamp_funding_order():
    e = NeutralGridReferenceEngine(cfg())
    e.process(PriceEvent(1, 1, D("95")))
    with pytest.raises(ValueError):
        e.process(PriceEvent(1, 2, D("96")))
    with pytest.raises(ValueError):
        run([PriceEvent(2, 1, D("95")), PriceEvent(1, 2, D("96"))])
    with pytest.raises(ValueError):
        run([PriceEvent(1, 2, D("95")), PriceEvent(2, 1, D("96"))])
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    r = run([PriceEvent(1, 1, levels[1]), FundingEvent(2, 1, D("100"), D("0.01"))], c)
    assert r.cumulative_funding_pnl_usdt == D("-1.00")


def test_funding_long_short_flat_signs_and_sequence_same_timestamp():
    c = cfg()
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    assert run(
        [PriceEvent(1, 1, levels[1]), FundingEvent(2, 1, D("100"), D("0.01"))], c
    ).cumulative_funding_pnl_usdt == D("-1.00")
    assert run(
        [PriceEvent(1, 1, levels[3]), FundingEvent(2, 1, D("100"), D("0.01"))], c
    ).cumulative_funding_pnl_usdt == D("1.00")
    assert run([FundingEvent(1, 1, D("100"), D("0.01"))], c).cumulative_funding_pnl_usdt == ZERO


def test_lower_and_upper_termination_close_residual_flat_fee_slippage_once_and_cancel():
    c = cfg()
    lower = run([PriceEvent(1, 1, D("69"))], c)
    assert (
        lower.terminated_bool
        and lower.signed_position == ZERO
        and lower.termination.position_flat_after_termination_bool
    )
    assert (
        lower.termination.residual_quantity_closed == D("2")
        and lower.termination.termination_trading_fee_usdt > ZERO
    )
    assert (
        lower.termination.termination_slippage_cost_usdt == D("0.140") and not lower.active_orders
    )
    upper = run([PriceEvent(1, 1, D("131"))], c)
    assert (
        upper.terminated_bool
        and upper.signed_position == ZERO
        and upper.termination.residual_quantity_closed == D("2")
    )
    eng = NeutralGridReferenceEngine(c)
    eng.terminate_now(1, 1, D("100"))
    flat = eng.result()
    assert (
        flat.termination.residual_quantity_closed == ZERO
        and flat.termination.termination_trading_fee_usdt == ZERO
    )
    e = NeutralGridReferenceEngine(c)
    e.process(PriceEvent(1, 1, D("69")))
    with pytest.raises(ValueError):
        e.process(PriceEvent(2, 2, D("100")))


def test_realized_net_total_identity_one_sided_flags_and_false_readiness():
    c = cfg(lower_term=None)
    levels = geometric_grid_levels_decimal(c.lower_price, c.upper_price, c.grid_cell_number).levels
    r = run([PriceEvent(1, 1, levels[1]), FundingEvent(2, 2, D("100"), D("0.01"))], c)
    assert r.proof_flags["two_sided_termination_configured_bool"] is False
    for k, v in r.proof_flags.items():
        if k != "two_sided_termination_configured_bool":
            assert v is False
    assert (
        r.realized_net_pnl()
        == r.cumulative_realized_position_pnl_gross_usdt
        - r.cumulative_trading_fees_usdt
        + r.cumulative_funding_pnl_usdt
    )
    assert r.total_pnl(D("101")) == r.realized_net_pnl() + r.unrealized_pnl(D("101"))
    assert audit_simulation_result(r, D("101")).passed_bool


def test_no_live_private_api_surface_in_reference_modules():
    import pathlib

    text = "\n".join(
        p.read_text() for p in pathlib.Path("src/bybit_grid/backtest/neutral_grid").glob("*.py")
    )
    forbidden = [
        "/v5/fgridbot/create",
        "/v5/fgridbot/close",
        "api_key",
        "api_secret",
        "order/create",
        "order/cancel",
        "telegram",
    ]
    assert not any(x in text for x in forbidden)
