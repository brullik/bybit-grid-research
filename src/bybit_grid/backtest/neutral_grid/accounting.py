from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .models import LiquidityRole, OrderSide, PositionEffect, ZERO, _finite_decimal


@dataclass(frozen=True)
class FillAccountingResult:
    closed_quantity: Decimal
    opened_quantity: Decimal
    position_effect: PositionEffect
    realized_position_pnl_gross_usdt: Decimal
    new_signed_position: Decimal
    new_average_entry: Decimal | None


def _validate_position_state(signed_position: Decimal, average_entry: Decimal | None) -> None:
    _finite_decimal(signed_position, "signed_position")
    if signed_position == ZERO and average_entry is not None:
        raise ValueError("flat position requires average_entry=None")
    if signed_position != ZERO:
        if average_entry is None:
            raise ValueError("nonzero position requires average_entry")
        _finite_decimal(average_entry, "average_entry")
        if average_entry <= ZERO:
            raise ValueError("average_entry must be positive")


def selected_fee_rate(role: LiquidityRole, maker_fee_rate: Decimal, taker_fee_rate: Decimal) -> Decimal:
    _finite_decimal(maker_fee_rate, "maker_fee_rate")
    _finite_decimal(taker_fee_rate, "taker_fee_rate")
    if maker_fee_rate < ZERO or taker_fee_rate < ZERO:
        raise ValueError("fee rates must be non-negative")
    if role is LiquidityRole.maker:
        return maker_fee_rate
    if role is LiquidityRole.taker:
        return taker_fee_rate
    raise ValueError("role must be LiquidityRole.maker or LiquidityRole.taker")


def trading_fee(quantity: Decimal, price: Decimal, role: LiquidityRole, maker_fee_rate: Decimal, taker_fee_rate: Decimal) -> Decimal:
    _finite_decimal(quantity, "quantity")
    _finite_decimal(price, "price")
    if quantity <= ZERO or price <= ZERO:
        raise ValueError("quantity and price must be positive")
    return quantity * price * selected_fee_rate(role, maker_fee_rate, taker_fee_rate)


def apply_fill(side: OrderSide, quantity: Decimal, price: Decimal, signed_position: Decimal, average_entry: Decimal | None) -> FillAccountingResult:
    if not isinstance(side, OrderSide):
        raise ValueError("side must be OrderSide")
    _finite_decimal(quantity, "quantity")
    _finite_decimal(price, "price")
    if quantity <= ZERO or price <= ZERO:
        raise ValueError("quantity and price must be positive")
    _validate_position_state(signed_position, average_entry)
    delta = quantity if side is OrderSide.buy else -quantity
    if signed_position == ZERO:
        return FillAccountingResult(ZERO, quantity, PositionEffect.open_long if delta > 0 else PositionEffect.open_short, ZERO, delta, price)
    if signed_position > ZERO and delta > ZERO:
        new_pos = signed_position + delta
        avg = ((signed_position * average_entry) + (quantity * price)) / new_pos  # type: ignore[operator]
        return FillAccountingResult(ZERO, quantity, PositionEffect.add_long, ZERO, new_pos, avg)
    if signed_position < ZERO and delta < ZERO:
        new_abs = abs(signed_position) + quantity
        avg = ((abs(signed_position) * average_entry) + (quantity * price)) / new_abs  # type: ignore[operator]
        return FillAccountingResult(ZERO, quantity, PositionEffect.add_short, ZERO, signed_position + delta, avg)
    if signed_position > ZERO:
        closed = min(signed_position, quantity)
        opened = quantity - closed
        pnl = closed * (price - average_entry)  # type: ignore[operator]
        new_pos = signed_position + delta
        if new_pos > ZERO:
            return FillAccountingResult(closed, opened, PositionEffect.close_long, pnl, new_pos, average_entry)
        if new_pos == ZERO:
            return FillAccountingResult(closed, opened, PositionEffect.close_long, pnl, new_pos, None)
        return FillAccountingResult(closed, opened, PositionEffect.flip_long_to_short, pnl, new_pos, price)
    closed = min(abs(signed_position), quantity)
    opened = quantity - closed
    pnl = closed * (average_entry - price)  # type: ignore[operator]
    new_pos = signed_position + delta
    if new_pos < ZERO:
        return FillAccountingResult(closed, opened, PositionEffect.close_short, pnl, new_pos, average_entry)
    if new_pos == ZERO:
        return FillAccountingResult(closed, opened, PositionEffect.close_short, pnl, new_pos, None)
    return FillAccountingResult(closed, opened, PositionEffect.flip_short_to_long, pnl, new_pos, price)


def funding_pnl(signed_position: Decimal, mark_price: Decimal, funding_rate: Decimal) -> Decimal:
    _validate_position_state(signed_position, None if signed_position == ZERO else Decimal("1"))
    _finite_decimal(mark_price, "mark_price")
    _finite_decimal(funding_rate, "funding_rate")
    if mark_price <= ZERO:
        raise ValueError("mark_price must be positive")
    return -signed_position * mark_price * funding_rate
