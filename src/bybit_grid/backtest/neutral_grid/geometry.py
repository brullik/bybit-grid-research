from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class DecimalGridGeometry:
    levels: tuple[Decimal, ...]
    ratio: Decimal
    geometry_rounding_applied_bool: bool = False
    ratio_tolerance: Decimal = Decimal("0")


def _finite_positive_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or isinstance(value, bool) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _cell_number(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("cell_number must be int, not bool")
    if value < 2:
        raise ValueError("cell_number must be >= 2")


def geometric_grid_levels_decimal(lower: Decimal, upper: Decimal, cell_number: int) -> DecimalGridGeometry:
    _finite_positive_decimal(lower, "lower")
    _finite_positive_decimal(upper, "upper")
    _cell_number(cell_number)
    if not lower < upper:
        raise ValueError("requires 0 < lower < upper")
    with localcontext() as ctx:
        ctx.prec = 80
        ratio = (upper / lower).ln().__truediv__(Decimal(cell_number)).exp()
        levels = [lower]
        for i in range(1, cell_number):
            levels.append(lower * (ratio**i))
        levels.append(upper)
    if any(levels[i] >= levels[i + 1] for i in range(len(levels) - 1)):
        raise ValueError("Decimal grid levels must be strictly increasing")
    return DecimalGridGeometry(tuple(levels), ratio)


def validate_grid_geometry(levels: tuple[Decimal, ...], lower: Decimal, upper: Decimal, cell_number: int) -> None:
    if not isinstance(levels, tuple):
        raise ValueError("levels must be a tuple")
    geom = geometric_grid_levels_decimal(lower, upper, cell_number)
    if len(levels) != cell_number + 1:
        raise ValueError("expected N+1 levels")
    for i, level in enumerate(levels):
        _finite_positive_decimal(level, f"levels[{i}]")
    if any(levels[i] >= levels[i + 1] for i in range(len(levels) - 1)):
        raise ValueError("levels must strictly increase")
    if levels != geom.levels:
        raise ValueError("levels must exactly match canonical Decimal geometric levels")
