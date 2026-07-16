from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any

from bybit_grid.config import load_settings


def _decimal(value: Decimal | str | int | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def round_down_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    return (value / tick_size).to_integral_value(rounding=ROUND_FLOOR) * tick_size


def round_up_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    return (value / tick_size).to_integral_value(rounding=ROUND_CEILING) * tick_size


def build_fgrid_validate_payload(
    symbol: str,
    last_price: Decimal,
    tick_size: Decimal,
    leverage: Decimal | int = 1,
    grid_mode: int | str | None = None,
    grid_type: int | str | None = None,
    cell_number: int = 10,
    init_margin: Decimal | str = "100",
    lower_mult: Decimal = Decimal("0.90"),
    upper_mult: Decimal = Decimal("1.10"),
    stop_loss_mult: Decimal = Decimal("0.85"),
) -> dict[str, Any]:
    settings = load_settings()
    last_price = _decimal(last_price)
    tick_size = _decimal(tick_size)
    lower_mult = _decimal(lower_mult)
    upper_mult = _decimal(upper_mult)
    stop_loss_mult = _decimal(stop_loss_mult)
    if last_price <= 0:
        raise ValueError("last_price must be positive")
    if lower_mult >= upper_mult:
        raise ValueError("lower_mult must be less than upper_mult")

    min_price = round_down_to_tick(last_price * lower_mult, tick_size)
    max_price = round_up_to_tick(last_price * upper_mult, tick_size)
    stop_loss_price = round_down_to_tick(last_price * stop_loss_mult, tick_size)

    if not min_price < last_price < max_price:
        raise ValueError("dynamic fgrid payload invalid: expected min_price < last_price < max_price")
    if not stop_loss_price < min_price:
        raise ValueError("dynamic fgrid payload invalid: expected stop_loss_price < min_price")

    return {
        "symbol": symbol,
        "leverage": _format_decimal(_decimal(leverage)),
        "grid_mode": settings.bybit_fgrid_grid_mode_neutral if grid_mode is None else grid_mode,
        "grid_type": settings.bybit_fgrid_grid_type_geometric if grid_type is None else grid_type,
        "min_price": _format_decimal(min_price),
        "max_price": _format_decimal(max_price),
        "cell_number": cell_number,
        "init_margin": _format_decimal(_decimal(init_margin)),
        "stop_loss_price": _format_decimal(stop_loss_price),
    }
# RED probe only: no behavior
