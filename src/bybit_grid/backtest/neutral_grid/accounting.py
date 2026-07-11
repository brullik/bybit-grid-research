from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .models import LiquidityRole, OrderSide, PositionEffect, ZERO


@dataclass(frozen=True)
class FillAccountingResult:
    closed_quantity: Decimal
    opened_quantity: Decimal
    position_effect: PositionEffect
    realized_position_pnl_gross_usdt: Decimal
    new_signed_position: Decimal
    new_average_entry: Decimal | None


def selected_fee_rate(
    role: LiquidityRole, maker_fee_rate: Decimal, taker_fee_rate: Decimal
) -> Decimal:
    return maker_fee_rate if role is LiquidityRole.maker else taker_fee_rate


def trading_fee(
    quantity: Decimal,
    price: Decimal,
    role: LiquidityRole,
    maker_fee_rate: Decimal,
    taker_fee_rate: Decimal,
) -> Decimal:
    return quantity * price * selected_fee_rate(role, maker_fee_rate, taker_fee_rate)


def apply_fill(
    side: OrderSide,
    quantity: Decimal,
    price: Decimal,
    signed_position: Decimal,
    average_entry: Decimal | None,
) -> FillAccountingResult:
    delta = quantity if side is OrderSide.buy else -quantity
    if quantity <= ZERO:
        raise ValueError("quantity must be positive")
    if signed_position == ZERO:
        return FillAccountingResult(
            ZERO,
            quantity,
            PositionEffect.open_long if delta > 0 else PositionEffect.open_short,
            ZERO,
            delta,
            price,
        )
    if signed_position > ZERO and delta > ZERO:
        new_pos = signed_position + delta
        avg = ((signed_position * (average_entry or ZERO)) + (quantity * price)) / new_pos
        return FillAccountingResult(ZERO, quantity, PositionEffect.add_long, ZERO, new_pos, avg)
    if signed_position < ZERO and delta < ZERO:
        new_abs = abs(signed_position) + quantity
        avg = ((abs(signed_position) * (average_entry or ZERO)) + (quantity * price)) / new_abs
        return FillAccountingResult(
            ZERO, quantity, PositionEffect.add_short, ZERO, signed_position + delta, avg
        )
    # closing or flipping
    if signed_position > ZERO:
        closed = min(signed_position, quantity)
        opened = quantity - closed
        pnl = closed * (price - (average_entry or ZERO))
        new_pos = signed_position + delta
        if new_pos > ZERO:
            eff = PositionEffect.close_long
            avg = average_entry
        elif new_pos == ZERO:
            eff = PositionEffect.close_long
            avg = None
        else:
            eff = PositionEffect.flip_long_to_short
            avg = price
        return FillAccountingResult(closed, opened, eff, pnl, new_pos, avg)
    closed = min(abs(signed_position), quantity)
    opened = quantity - closed
    pnl = closed * ((average_entry or ZERO) - price)
    new_pos = signed_position + delta
    if new_pos < ZERO:
        eff = PositionEffect.close_short
        avg = average_entry
    elif new_pos == ZERO:
        eff = PositionEffect.close_short
        avg = None
    else:
        eff = PositionEffect.flip_short_to_long
        avg = price
    return FillAccountingResult(closed, opened, eff, pnl, new_pos, avg)


def funding_pnl(signed_position: Decimal, mark_price: Decimal, funding_rate: Decimal) -> Decimal:
    return -signed_position * mark_price * funding_rate
