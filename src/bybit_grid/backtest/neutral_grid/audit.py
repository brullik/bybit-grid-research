from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .accounting import apply_fill, funding_pnl, trading_fee
from .geometry import validate_grid_geometry
from .models import EventType, OrderSide, OrderState, SimulationResult, ZERO, _finite_decimal
from .engine import FALSE_FLAGS


@dataclass(frozen=True)
class AuditResult:
    passed_bool: bool
    failures: tuple[str, ...]
    total_pnl_identity_recomputed_bool: bool


def _fail(failures: list[str], msg: str) -> None:
    if msg not in failures:
        failures.append(msg)


def audit_simulation_result(result: SimulationResult, mark_price: Decimal | None = None) -> AuditResult:
    failures: list[str] = []
    try:
        validate_grid_geometry(result.levels, result.config.lower_price, result.config.upper_price, result.config.grid_cell_number)
    except Exception as exc:
        _fail(failures, f"geometry invalid: {exc}")

    # proof and initialization guardrails
    for k, v in FALSE_FLAGS.items():
        if result.proof_flags.get(k) is not v:
            _fail(failures, f"proof flag {k} must be false")
    expected_two_sided = result.config.lower_termination_price is not None and result.config.upper_termination_price is not None
    if result.proof_flags.get("two_sided_termination_configured_bool") is not expected_two_sided:
        _fail(failures, "two-sided termination flag mismatch")
    expected_init = {
        "initial_position_zero_bool": True,
        "buy_orders_below_base_bool": all(o.side is OrderSide.buy and o.price < result.config.base_price for o in result.active_orders.values() if o.price < result.config.base_price),
        "sell_orders_above_base_bool": all(o.side is OrderSide.sell and o.price > result.config.base_price for o in result.active_orders.values() if o.price > result.config.base_price),
        "base_level_has_no_order_bool": True,
        "one_active_order_per_level_bool": len(result.active_orders) == len(set(result.active_orders)),
        "constant_quantity_per_grid_bool": result.config.quantity_per_grid_base > ZERO,
    }
    for k, v in expected_init.items():
        if result.initialization_audit.get(k) is not v:
            _fail(failures, f"initialization flag {k} mismatch")

    order_ids = [o.order_id for o in result.all_orders]
    if len(order_ids) != len(set(order_ids)):
        _fail(failures, "duplicate order_id")
    active_seen: set[str] = set()
    for idx, o in result.active_orders.items():
        if idx != o.level_index or o.state is not OrderState.active:
            _fail(failures, "active order key/state invalid")
        if not (0 <= o.level_index < len(result.levels)) or o.price != result.levels[o.level_index]:
            _fail(failures, "active order level/price invalid")
        if o.filled_sequence_id is not None:
            _fail(failures, "active order has filled_sequence_id")
        active_seen.add(o.order_id)
    if len(active_seen) != len(result.active_orders):
        _fail(failures, "more than one active order per level")
    all_by_id = {o.order_id: o for o in result.all_orders}
    if not active_seen.issubset(all_by_id):
        _fail(failures, "all_orders missing active order")
    for o in result.all_orders:
        if o.state is OrderState.filled and o.filled_sequence_id is None:
            _fail(failures, "filled order missing filled_sequence_id")
        if o.state in (OrderState.active, OrderState.cancelled) and o.filled_sequence_id is not None:
            _fail(failures, "active/cancelled order has filled state")
    if result.terminated_bool and result.active_orders:
        _fail(failures, "terminated result has active orders")

    ids = [e.ledger_event_id for e in result.ledger]
    if len(ids) != len(set(ids)):
        _fail(failures, "duplicate ledger_event_id")
    ledger_by_id = {e.ledger_event_id: (i, e) for i, e in enumerate(result.ledger)}
    pos = ZERO
    avg = None
    realized = ZERO
    fees = ZERO
    funding = ZERO
    cycle_gross = ZERO
    term_fills = []
    for e in result.ledger:
        try:
            for name in ("price","quantity_base","signed_position_before","signed_position_after","realized_position_pnl_gross_usdt","completed_grid_cycle_gross_usdt","grid_cycle_open_fee_usdt","grid_cycle_close_fee_usdt","trading_fee_usdt","funding_pnl_usdt","cumulative_realized_position_pnl_gross_usdt","cumulative_completed_grid_cycle_gross_usdt","cumulative_trading_fees_usdt","cumulative_funding_pnl_usdt"):
                _finite_decimal(getattr(e, name), name)
        except Exception:
            _fail(failures, "non-finite/non-Decimal ledger accounting values")
        if e.signed_position_before != pos or e.average_entry_before != avg:
            _fail(failures, "ledger before state mismatch")
        if e.event_type in (EventType.grid_fill, EventType.termination_fill):
            expected_role = result.config.grid_fill_liquidity_role if e.event_type is EventType.grid_fill else result.config.termination_liquidity_role
            if e.liquidity_role is not expected_role:
                _fail(failures, "liquidity role mismatch")
            try:
                acc = apply_fill(e.side, e.quantity_base, e.price, pos, avg)  # type: ignore[arg-type]
                fee = trading_fee(e.quantity_base, e.price, expected_role, result.config.maker_fee_rate, result.config.taker_fee_rate)
                if (acc.new_signed_position != e.signed_position_after or acc.new_average_entry != e.average_entry_after or acc.position_effect is not e.position_effect or acc.realized_position_pnl_gross_usdt != e.realized_position_pnl_gross_usdt or fee != e.trading_fee_usdt):
                    _fail(failures, "fill accounting mismatch")
                pos = acc.new_signed_position
                avg = acc.new_average_entry
                realized += acc.realized_position_pnl_gross_usdt
                fees += fee
            except Exception as exc:
                _fail(failures, f"fill replay failed: {exc}")
            if e.event_type is EventType.termination_fill:
                term_fills.append(e)
        elif e.event_type is EventType.funding:
            if e.quantity_base != ZERO or e.side is not None or e.funding_rate is None:
                _fail(failures, "funding provenance/state invalid")
            try:
                fp = funding_pnl(pos, e.price, e.funding_rate)  # type: ignore[arg-type]
                if e.signed_position_after != pos or e.average_entry_after != avg or fp != e.funding_pnl_usdt:
                    _fail(failures, "funding replay mismatch")
                funding += fp
            except Exception as exc:
                _fail(failures, f"funding replay failed: {exc}")
        elif e.event_type is EventType.termination_trigger:
            if e.quantity_base != ZERO or e.side is not None or e.signed_position_after != pos or e.average_entry_after != avg or e.trading_fee_usdt != ZERO or e.funding_pnl_usdt != ZERO or e.realized_position_pnl_gross_usdt != ZERO:
                _fail(failures, "termination trigger mutated accounting")
        else:
            _fail(failures, "unsupported ledger event type")
        cycle_gross += e.completed_grid_cycle_gross_usdt
        if e.cumulative_realized_position_pnl_gross_usdt != realized or e.cumulative_trading_fees_usdt != fees or e.cumulative_funding_pnl_usdt != funding or e.cumulative_completed_grid_cycle_gross_usdt != cycle_gross:
            _fail(failures, "cumulative ledger fields mismatch")

    if pos != result.signed_position or avg != result.average_entry or realized != result.cumulative_realized_position_pnl_gross_usdt or fees != result.cumulative_trading_fees_usdt or funding != result.cumulative_funding_pnl_usdt:
        _fail(failures, "final replay totals mismatch")

    # cycles
    cycle_ids: set[str] = set()
    open_ids: set[str] = set()
    close_ids: set[str] = set()
    cycle_sum = ZERO
    for c in result.completed_cycles:
        if c.cycle_id in cycle_ids or c.open_fill_id in open_ids or c.close_fill_id in close_ids:
            _fail(failures, "duplicate cycle identifiers")
        cycle_ids.add(c.cycle_id)
        open_ids.add(c.open_fill_id)
        close_ids.add(c.close_fill_id)
        if c.open_fill_id not in ledger_by_id or c.close_fill_id not in ledger_by_id:
            _fail(failures, "cycle fill missing")
            continue
        oi, oe = ledger_by_id[c.open_fill_id]
        ci, ce = ledger_by_id[c.close_fill_id]
        if oe.event_type is not EventType.grid_fill or ce.event_type is not EventType.grid_fill or oi >= ci or oe.side is ce.side or abs((oe.level_index or 0) - (ce.level_index or 0)) != 1 or oe.quantity_base != ce.quantity_base:
            _fail(failures, "cycle structural mismatch")
        buy = oe.price if oe.side is OrderSide.buy else ce.price
        sell = oe.price if oe.side is OrderSide.sell else ce.price
        gross = oe.quantity_base * (sell - buy)
        if c.gross_usdt != gross or c.open_fee_usdt != oe.trading_fee_usdt or c.close_fee_usdt != ce.trading_fee_usdt or c.net_usdt != gross - c.open_fee_usdt - c.close_fee_usdt:
            _fail(failures, "cycle accounting mismatch")
        if ce.completed_grid_cycle_gross_usdt != c.gross_usdt or ce.grid_cycle_open_fee_usdt != c.open_fee_usdt or ce.grid_cycle_close_fee_usdt != c.close_fee_usdt:
            _fail(failures, "close ledger cycle fields mismatch")
        cycle_sum += c.gross_usdt
    if cycle_sum != result.cumulative_completed_grid_cycle_gross_usdt or cycle_gross != result.cumulative_completed_grid_cycle_gross_usdt:
        _fail(failures, "completed cycle total mismatch")

    if result.terminated_bool:
        if result.signed_position != ZERO or result.average_entry is not None:
            _fail(failures, "terminated result not flat")
        if not result.termination.all_orders_cancelled_bool or not result.termination.position_flat_after_termination_bool:
            _fail(failures, "termination summary flags invalid")
        expected_count = 0 if result.termination.residual_quantity_closed == ZERO else 1
        if len(term_fills) != expected_count:
            _fail(failures, "termination fill count mismatch")
        if term_fills:
            tf = term_fills[0]
            if tf.quantity_base != result.termination.residual_quantity_closed or tf.trading_fee_usdt != result.termination.termination_trading_fee_usdt or tf.price != result.termination.termination_execution_price:
                _fail(failures, "termination fill summary mismatch")
            if result.termination.termination_trigger_price is not None and abs(tf.price - result.termination.termination_trigger_price) * tf.quantity_base != result.termination.termination_slippage_cost_usdt:
                _fail(failures, "termination slippage summary mismatch")

    try:
        mark = mark_price if mark_price is not None else result.last_price
        _finite_decimal(mark, "mark_price")
        if mark <= ZERO:
            raise ValueError
        unreal = ZERO if result.terminated_bool else (pos * (mark - avg) if pos > ZERO and avg is not None else (abs(pos) * (avg - mark) if pos < ZERO and avg is not None else ZERO))
        identity_ok = result.total_pnl(mark) == realized - fees + funding + unreal
    except Exception:
        identity_ok = False
    if not identity_ok:
        _fail(failures, "total PnL identity mismatch")
    return AuditResult(not failures, tuple(failures), not failures and identity_ok)
