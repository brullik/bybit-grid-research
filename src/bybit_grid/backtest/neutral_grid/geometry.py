from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class DecimalGridGeometry:
    levels: tuple[Decimal, ...]
    ratio: Decimal
    geometry_rounding_applied_bool: bool = False
    ratio_tolerance: Decimal = Decimal("0.03")


def geometric_grid_levels_decimal(
    lower: Decimal, upper: Decimal, cell_number: int
) -> DecimalGridGeometry:
    if not isinstance(lower, Decimal) or not isinstance(upper, Decimal):
        raise ValueError("lower and upper must be Decimal")
    if cell_number < 2 or lower <= 0 or upper <= lower:
        raise ValueError("invalid geometric grid inputs")
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


def validate_grid_geometry(
    levels: tuple[Decimal, ...],
    lower: Decimal,
    upper: Decimal,
    cell_number: int,
    ratio_tolerance: Decimal = Decimal("0.03"),
) -> None:
    geom = geometric_grid_levels_decimal(lower, upper, cell_number)
    if len(levels) != cell_number + 1:
        raise ValueError("expected N+1 levels")
    if levels[0] != lower or levels[-1] != upper:
        raise ValueError("levels must preserve exact lower/upper endpoints")
    if any(levels[i] >= levels[i + 1] for i in range(len(levels) - 1)):
        raise ValueError("levels must strictly increase")
    for i in range(cell_number):
        ratio = levels[i + 1] / levels[i]
        if abs(ratio - geom.ratio) > ratio_tolerance:
            raise ValueError("adjacent ratio outside tolerance")
