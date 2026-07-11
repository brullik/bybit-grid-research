from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class DecimalGridGeometry:
    levels: tuple[Decimal, ...]
    ratio: Decimal
    geometry_rounding_applied_bool: bool = False
    ratio_tolerance: Decimal = Decimal("1e-40")


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
