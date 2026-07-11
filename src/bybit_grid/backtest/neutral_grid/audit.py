from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .accounting import apply_fill, funding_pnl, trading_fee
from .geometry import validate_grid_geometry
from .models import (
    EventType,
    OrderSide,
    OrderState,
    PositionEffect,
    SimulationResult,
    TerminationReason,
    ZERO,
    _finite_decimal,
)
from .engine import FALSE_FLAGS

INIT_KEYS = {
    "initial_position_zero_bool",
    "buy_orders_below_base_bool",
    "sell_orders_above_base_bool",
    "base_level_has_no_order_bool",
    "one_active_order_per_level_bool",
    "constant_quantity_per_grid_bool",
}
PROOF_KEYS = set(FALSE_FLAGS) | {"two_sided_termination_configured_bool"}


@dataclass(frozen=True)
class AuditResult:
    passed_bool: bool
    failures: tuple[str, ...]
    total_pnl_identity_recomputed_bool: bool


def _fail(failures: list[str], msg: str) -> None:
    if msg not in failures:
        failures.append(msg)


def _non_bool_int(value: int, name: str) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _zero_none_contract(e, failures: list[str]) -> None:
    zero_names = (
        "completed_grid_cycle_gross_usdt",
        "grid_cycle_open_fee_usdt",
        "grid_cycle_close_fee_usdt",
    )
    if e.event_type is EventType.funding:
        if (
            e.order_id is not None
            or e.level_index is not None
            or e.side is not None
            or e.quantity_base != ZERO
            or e.liquidity_role is not None
        ):
            _fail(failures, "funding stray order/fill fields")
        if (
            e.position_effect is not PositionEffect.none
            or e.realized_position_pnl_gross_usdt != ZERO
            or e.trading_fee_usdt != ZERO
        ):
            _fail(failures, "funding stray accounting fields")
    if e.event_type is EventType.termination_trigger:
        if (
            e.order_id is not None
            or e.level_index is not None
            or e.side is not None
            or e.quantity_base != ZERO
            or e.liquidity_role is not None
            or e.funding_rate is not None
        ):
            _fail(failures, "termination trigger stray fields")
    if e.event_type not in (EventType.grid_fill, EventType.termination_fill):
        for n in zero_names:
            if getattr(e, n) != ZERO:
                _fail(failures, "non-cycle event has cycle fields")


def _audit_simulation_result_inner(
    result: SimulationResult, mark_price: Decimal | None = None
) -> AuditResult:
    failures: list[str] = []
    try:
        validate_grid_geometry(
            result.levels,
            result.config.lower_price,
            result.config.upper_price,
            result.config.grid_cell_number,
        )
    except Exception as exc:
        _fail(failures, f"geometry invalid: {exc}")
    if result.geometry_rounding_applied_bool is not False:
        _fail(failures, "geometry_rounding_applied_bool must be false")
    if not _non_bool_int(
        result.events_rejected_after_termination_count, "events_rejected_after_termination_count"
    ):
        _fail(failures, "events_rejected_after_termination_count invalid")
    if set(result.proof_flags) != PROOF_KEYS:
        _fail(failures, "proof_flags key set mismatch")
    for k, v in FALSE_FLAGS.items():
        if result.proof_flags.get(k) is not v:
            _fail(failures, f"proof flag {k} must be false")
    expected_two_sided = (
        result.config.lower_termination_price is not None
        and result.config.upper_termination_price is not None
    )
    if result.proof_flags.get("two_sided_termination_configured_bool") is not expected_two_sided:
        _fail(failures, "two-sided termination flag mismatch")

    initial_orders = [o for o in result.all_orders if o.activation_sequence_id == 0]
    expected_indices = {i for i, p in enumerate(result.levels) if p != result.config.base_price}
    init_by_idx = {o.level_index: o for o in initial_orders}
    expected_init = {
        "initial_position_zero_bool": True,
        "buy_orders_below_base_bool": all(
            init_by_idx.get(i) is not None and init_by_idx[i].side is OrderSide.buy
            for i, p in enumerate(result.levels)
            if p < result.config.base_price
        ),
        "sell_orders_above_base_bool": all(
            init_by_idx.get(i) is not None and init_by_idx[i].side is OrderSide.sell
            for i, p in enumerate(result.levels)
            if p > result.config.base_price
        ),
        "base_level_has_no_order_bool": all(
            o.price != result.config.base_price and o.level_index in expected_indices
            for o in initial_orders
        ),
        "one_active_order_per_level_bool": len(initial_orders) == len(expected_indices)
        and len(init_by_idx) == len(initial_orders),
        "constant_quantity_per_grid_bool": result.config.quantity_per_grid_base > ZERO,
    }
    if set(result.initialization_audit) != INIT_KEYS:
        _fail(failures, "initialization_audit key set mismatch")
    for k, v in expected_init.items():
        if result.initialization_audit.get(k) is not v:
            _fail(failures, f"initialization flag {k} mismatch")

    order_ids = [o.order_id for o in result.all_orders]
    if any(type(x) is not str or x == "" for x in order_ids) or len(order_ids) != len(
        set(order_ids)
    ):
        _fail(failures, "duplicate/empty order_id")
    all_by_id = {o.order_id: o for o in result.all_orders}
    active_ids_from_all = {o.order_id for o in result.all_orders if o.state is OrderState.active}
    active_ids_from_map: set[str] = set()
    active_levels: set[int] = set()
    for idx, o in result.active_orders.items():
        if not isinstance(idx, int) or isinstance(idx, bool):
            _fail(failures, "active mapping level index invalid")
            continue
        if type(getattr(o, "order_id", None)) is str and o.order_id:
            active_ids_from_map.add(o.order_id)
        if getattr(o, "state", None) is OrderState.active:
            if o.level_index in active_levels:
                _fail(failures, "multiple active orders for one level")
            active_levels.add(o.level_index)
    if active_ids_from_all != active_ids_from_map:
        _fail(failures, "active-order bijection mismatch")
    if result.terminated_bool and (active_ids_from_all or active_ids_from_map):
        _fail(failures, "terminated result has active orders")
    for o in result.all_orders:
        if (
            not (0 <= o.level_index < len(result.levels))
            or o.price != result.levels[o.level_index]
            or not isinstance(o.side, OrderSide)
            or not isinstance(o.state, OrderState)
        ):
            _fail(failures, "order structural fields invalid")
        if not _non_bool_int(o.activation_sequence_id, "activation_sequence_id"):
            _fail(failures, "order activation_sequence_id invalid")
        if (o.state is OrderState.filled) != (o.filled_sequence_id is not None):
            _fail(failures, "filled state iff filled_sequence_id mismatch")
        if o.filled_sequence_id is not None and (
            not _non_bool_int(o.filled_sequence_id, "filled_sequence_id")
            or o.activation_sequence_id > o.filled_sequence_id
        ):
            _fail(failures, "filled order chronology invalid")
    for idx, o in result.active_orders.items():
        if idx != o.level_index or o.order_id not in all_by_id or o != all_by_id.get(o.order_id):
            _fail(failures, "active-order/all-order mismatch")
        if o.state is not OrderState.active or o.filled_sequence_id is not None:
            _fail(failures, "active order state invalid")
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
    grid_fills = []
    term_fills = []
    term_triggers = []
    last_seq = last_time = -1
    seq_time: dict[int, int] = {}
    for e in result.ledger:
        if not _non_bool_int(e.sequence_id, "sequence_id") or not _non_bool_int(
            e.time_ms, "time_ms"
        ):
            _fail(failures, "ledger sequence/time invalid")
        if e.sequence_id < last_seq or e.time_ms < last_time:
            _fail(failures, "ledger sequence/time not non-decreasing")
        if e.sequence_id in seq_time and seq_time[e.sequence_id] != e.time_ms:
            _fail(failures, "ledger rows sharing sequence_id must share time_ms")
        seq_time[e.sequence_id] = e.time_ms
        last_seq, last_time = e.sequence_id, e.time_ms
        try:
            for name in (
                "price",
                "quantity_base",
                "signed_position_before",
                "signed_position_after",
                "realized_position_pnl_gross_usdt",
                "completed_grid_cycle_gross_usdt",
                "grid_cycle_open_fee_usdt",
                "grid_cycle_close_fee_usdt",
                "trading_fee_usdt",
                "funding_pnl_usdt",
                "cumulative_realized_position_pnl_gross_usdt",
                "cumulative_completed_grid_cycle_gross_usdt",
                "cumulative_trading_fees_usdt",
                "cumulative_funding_pnl_usdt",
            ):
                _finite_decimal(getattr(e, name), name)
        except Exception:
            _fail(failures, "non-finite/non-Decimal ledger accounting values")
        _zero_none_contract(e, failures)
        if e.signed_position_before != pos or e.average_entry_before != avg:
            _fail(failures, "ledger before state mismatch")
        if e.event_type in (EventType.grid_fill, EventType.termination_fill):
            expected_role = (
                result.config.grid_fill_liquidity_role
                if e.event_type is EventType.grid_fill
                else result.config.termination_liquidity_role
            )
            if e.liquidity_role is not expected_role:
                _fail(failures, "liquidity role mismatch")
            if e.event_type is EventType.grid_fill:
                grid_fills.append(e)
                o = all_by_id.get(e.order_id or "")
                if (
                    o is None
                    or o.state is not OrderState.filled
                    or o.filled_sequence_id != e.sequence_id
                    or o.level_index != e.level_index
                    or o.price != e.price
                    or e.level_index is None
                    or e.price != result.levels[e.level_index]
                    or o.side is not e.side
                    or e.quantity_base != result.config.quantity_per_grid_base
                    or e.liquidity_role is not result.config.grid_fill_liquidity_role
                ):
                    _fail(failures, "grid-fill provenance mismatch")
            try:
                acc = apply_fill(e.side, e.quantity_base, e.price, pos, avg)  # type: ignore[arg-type]
                fee = trading_fee(
                    e.quantity_base,
                    e.price,
                    expected_role,
                    result.config.maker_fee_rate,
                    result.config.taker_fee_rate,
                )
                if (
                    acc.new_signed_position != e.signed_position_after
                    or acc.new_average_entry != e.average_entry_after
                    or acc.position_effect is not e.position_effect
                    or acc.realized_position_pnl_gross_usdt != e.realized_position_pnl_gross_usdt
                    or fee != e.trading_fee_usdt
                ):
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
            try:
                fp = funding_pnl(pos, e.price, e.funding_rate)  # type: ignore[arg-type]
                if (
                    e.signed_position_after != pos
                    or e.average_entry_after != avg
                    or fp != e.funding_pnl_usdt
                ):
                    _fail(failures, "funding replay mismatch")
                funding += fp
            except Exception as exc:
                _fail(failures, f"funding replay failed: {exc}")
        elif e.event_type is EventType.termination_trigger:
            term_triggers.append(e)
            if (
                e.signed_position_after != pos
                or e.average_entry_after != avg
                or e.trading_fee_usdt != ZERO
                or e.funding_pnl_usdt != ZERO
                or e.realized_position_pnl_gross_usdt != ZERO
            ):
                _fail(failures, "termination trigger mutated accounting")
        else:
            _fail(failures, "unsupported ledger event type")
        cycle_gross += e.completed_grid_cycle_gross_usdt
        if (
            e.cumulative_realized_position_pnl_gross_usdt != realized
            or e.cumulative_trading_fees_usdt != fees
            or e.cumulative_funding_pnl_usdt != funding
            or e.cumulative_completed_grid_cycle_gross_usdt != cycle_gross
        ):
            _fail(failures, "cumulative ledger fields mismatch")
    opening_effects = {
        PositionEffect.open_long,
        PositionEffect.add_long,
        PositionEffect.open_short,
        PositionEffect.add_short,
        PositionEffect.flip_long_to_short,
        PositionEffect.flip_short_to_long,
    }
    for o in result.all_orders:
        if o.linked_open_fill_id is None:
            continue
        ref = ledger_by_id.get(o.linked_open_fill_id)
        if ref is None:
            _fail(failures, "linked open fill missing")
            continue
        _, le = ref
        if le.event_type is not EventType.grid_fill:
            _fail(failures, "linked open fill is not grid fill")
            continue
        if le.sequence_id > o.activation_sequence_id:
            _fail(failures, "linked open fill later than activation")
        if o.activation_sequence_id != le.sequence_id:
            _fail(failures, "replacement activation sequence must equal linked fill sequence")
        if o.side is le.side:
            _fail(failures, "linked open fill same side")
        expected_level = (
            (le.level_index + 1)
            if le.side is OrderSide.buy and le.level_index is not None
            else (le.level_index - 1 if le.level_index is not None else None)
        )
        if o.level_index != expected_level:
            _fail(failures, "linked open fill non-adjacent replacement")
        if le.position_effect not in opening_effects:
            _fail(failures, "linked fill did not open/add exposure")

    filled_order_ids = [o.order_id for o in result.all_orders if o.state is OrderState.filled]
    fill_order_ids = [e.order_id for e in grid_fills]
    if sorted(filled_order_ids) != sorted(fill_order_ids):
        _fail(failures, "filled grid order ledger mapping mismatch")

    if (
        pos != result.signed_position
        or avg != result.average_entry
        or realized != result.cumulative_realized_position_pnl_gross_usdt
        or fees != result.cumulative_trading_fees_usdt
        or funding != result.cumulative_funding_pnl_usdt
    ):
        _fail(failures, "final replay totals mismatch")

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
        if (
            oe.event_type is not EventType.grid_fill
            or ce.event_type is not EventType.grid_fill
            or oi >= ci
            or oe.side is ce.side
            or abs((oe.level_index or 0) - (ce.level_index or 0)) != 1
            or oe.quantity_base != ce.quantity_base
        ):
            _fail(failures, "cycle structural mismatch")
        gross = oe.quantity_base * (
            (oe.price if oe.side is OrderSide.sell else ce.price)
            - (oe.price if oe.side is OrderSide.buy else ce.price)
        )
        if c.open_level_index != oe.level_index or c.close_level_index != ce.level_index:
            _fail(failures, "cycle level provenance mismatch")
        if (
            c.gross_usdt != gross
            or c.open_fee_usdt != oe.trading_fee_usdt
            or c.close_fee_usdt != ce.trading_fee_usdt
            or c.net_usdt != gross - c.open_fee_usdt - c.close_fee_usdt
        ):
            _fail(failures, "cycle accounting mismatch")
        if (
            ce.completed_grid_cycle_gross_usdt != c.gross_usdt
            or ce.grid_cycle_open_fee_usdt != c.open_fee_usdt
            or ce.grid_cycle_close_fee_usdt != c.close_fee_usdt
        ):
            _fail(failures, "cycle close ledger fields mismatch")
        cycle_sum += c.gross_usdt
    close_cycle_ids = {c.close_fill_id for c in result.completed_cycles}
    for e in grid_fills:
        if e.ledger_event_id not in close_cycle_ids and (
            e.completed_grid_cycle_gross_usdt != ZERO
            or e.grid_cycle_open_fee_usdt != ZERO
            or e.grid_cycle_close_fee_usdt != ZERO
        ):
            _fail(failures, "non-cycle-close grid fill has cycle fields")
    if (
        cycle_sum != result.cumulative_completed_grid_cycle_gross_usdt
        or cycle_gross != result.cumulative_completed_grid_cycle_gross_usdt
    ):
        _fail(failures, "completed cycle total mismatch")

    if result.terminated_bool:
        if not isinstance(result.termination.termination_reason, TerminationReason):
            _fail(failures, "termination reason invalid")
        if len(term_triggers) != 1:
            _fail(failures, "termination trigger count mismatch")
        else:
            tt = term_triggers[0]
            if result.termination.termination_trigger_price != tt.price:
                _fail(failures, "termination trigger price mismatch")
            if result.termination.termination_reason is TerminationReason.lower_boundary and (
                result.config.lower_termination_price is None
                or tt.price != result.config.lower_termination_price
            ):
                _fail(failures, "lower termination reason/price mismatch")
            if result.termination.termination_reason is TerminationReason.upper_boundary and (
                result.config.upper_termination_price is None
                or tt.price != result.config.upper_termination_price
            ):
                _fail(failures, "upper termination reason/price mismatch")
            if (
                result.termination.termination_reason is TerminationReason.explicit_manual_synthetic
                and (tt.price <= ZERO)
            ):
                _fail(failures, "manual termination trigger invalid")
        if (
            result.signed_position != ZERO
            or result.average_entry is not None
            or not result.termination.all_orders_cancelled_bool
            or not result.termination.position_flat_after_termination_bool
        ):
            _fail(failures, "termination summary state invalid")
        expected_count = 0 if result.termination.residual_quantity_closed == ZERO else 1
        if len(term_fills) != expected_count:
            _fail(failures, "termination fill count mismatch")
        if expected_count == 0 and (
            result.termination.termination_execution_price is not None
            or result.termination.termination_trading_fee_usdt != ZERO
            or result.termination.termination_slippage_cost_usdt != ZERO
        ):
            _fail(failures, "flat termination fabricated execution fields")
        if term_fills:
            tf = term_fills[0]
            if (
                tf.quantity_base != result.termination.residual_quantity_closed
                or tf.trading_fee_usdt != result.termination.termination_trading_fee_usdt
                or tf.price != result.termination.termination_execution_price
            ):
                _fail(failures, "termination fill summary mismatch")
            trigger = result.termination.termination_trigger_price
            if trigger is not None:
                expected_price = (
                    trigger
                    * (Decimal("1") - result.config.termination_slippage_bps / Decimal("10000"))
                    if tf.side is OrderSide.sell
                    else trigger
                    * (Decimal("1") + result.config.termination_slippage_bps / Decimal("10000"))
                )
                if (
                    tf.price != expected_price
                    or abs(tf.price - trigger) * tf.quantity_base
                    != result.termination.termination_slippage_cost_usdt
                ):
                    _fail(failures, "termination slippage summary mismatch")
    else:
        if term_triggers or term_fills or result.termination != result.termination.__class__():
            _fail(failures, "nonterminated termination fields not empty")

    try:
        mark = mark_price if mark_price is not None else result.last_price
        _finite_decimal(mark, "mark_price")
        if mark <= ZERO:
            raise ValueError
        unreal = (
            ZERO
            if result.terminated_bool
            else (
                pos * (mark - avg)
                if pos > ZERO and avg is not None
                else (abs(pos) * (avg - mark) if pos < ZERO and avg is not None else ZERO)
            )
        )
        identity_ok = result.total_pnl(mark) == realized - fees + funding + unreal
    except Exception:
        identity_ok = False
    if not identity_ok:
        _fail(failures, "total PnL identity mismatch")
    return AuditResult(not failures, tuple(failures), not failures and identity_ok)


def audit_simulation_result(
    result: SimulationResult, mark_price: Decimal | None = None
) -> AuditResult:
    try:
        return _audit_simulation_result_inner(result, mark_price)
    except Exception as exc:  # public audit boundary fails closed for malformed snapshots
        return AuditResult(False, (f"audit failed closed: {type(exc).__name__}: {exc}",), False)
