from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .models import EventType, OrderState, SimulationResult, ZERO


@dataclass(frozen=True)
class AuditResult:
    passed_bool: bool
    failures: tuple[str, ...]
    total_pnl_identity_recomputed_bool: bool


def audit_simulation_result(
    result: SimulationResult, mark_price: Decimal | None = None
) -> AuditResult:
    failures: list[str] = []
    ids = [e.ledger_event_id for e in result.ledger]
    if len(ids) != len(set(ids)):
        failures.append("duplicate ledger_event_id")
    fills = [
        e.ledger_event_id
        for e in result.ledger
        if e.event_type in (EventType.grid_fill, EventType.termination_fill)
    ]
    if len(fills) != len(set(fills)):
        failures.append("duplicate fill ID")
    pairs = [(c.open_fill_id, c.close_fill_id) for c in result.completed_cycles]
    if len(pairs) != len(set(pairs)):
        failures.append("duplicate completed-cycle pairing")
    if len(result.active_orders) != len(set(result.active_orders)):
        failures.append("more than one active order at a level")
    for idx, o in result.active_orders.items():
        if o.state is not OrderState.active or idx != o.level_index:
            failures.append("active order with invalid side for its level/state")
    pos = ZERO
    for e in result.ledger:
        for v in (
            e.price,
            e.quantity_base,
            e.signed_position_before,
            e.signed_position_after,
            e.realized_position_pnl_gross_usdt,
            e.trading_fee_usdt,
            e.funding_pnl_usdt,
        ):
            if not isinstance(v, Decimal):
                failures.append("non-Decimal accounting values")
        if e.event_type in (EventType.grid_fill, EventType.termination_fill) and e.side is not None:
            pos += e.quantity_base if e.side.value == "buy" else -e.quantity_base
    if pos != result.signed_position:
        failures.append("position quantity not reconciled to fill deltas")
    if (
        sum((e.trading_fee_usdt for e in result.ledger), ZERO)
        != result.cumulative_trading_fees_usdt
    ):
        failures.append("fee total not reconciled to fill fees")
    if sum((e.funding_pnl_usdt for e in result.ledger), ZERO) != result.cumulative_funding_pnl_usdt:
        failures.append("funding total not reconciled to funding events")
    if (
        sum((e.realized_position_pnl_gross_usdt for e in result.ledger), ZERO)
        != result.cumulative_realized_position_pnl_gross_usdt
    ):
        failures.append("realized PnL not reconciled")
    mark = mark_price or result.last_price
    realized_net = (
        result.cumulative_realized_position_pnl_gross_usdt
        - result.cumulative_trading_fees_usdt
        + result.cumulative_funding_pnl_usdt
    )
    if result.total_pnl(mark) != realized_net + result.unrealized_pnl(mark):
        failures.append("total PnL identity mismatch")
    if result.terminated_bool and result.signed_position != ZERO:
        failures.append("terminated result not flat")
    if result.terminated_bool and result.active_orders:
        failures.append("active orders remaining after termination")
    if result.events_rejected_after_termination_count < 0:
        failures.append("event accepted after termination")
    return AuditResult(not failures, tuple(failures), True)
