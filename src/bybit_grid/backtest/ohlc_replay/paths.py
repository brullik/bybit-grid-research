from __future__ import annotations
from decimal import Decimal
from .models import MinimalPathPolicy, OhlcCandle1m


def _valid_price(p: object) -> bool:
    return isinstance(p, Decimal) and not isinstance(p, bool) and p.is_finite() and p > Decimal("0")


def normalize_consecutive_duplicates(prices: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    if not isinstance(prices, tuple):
        raise ValueError("prices must be tuple")
    out: list[Decimal] = []
    for p in prices:
        if not _valid_price(p):
            raise ValueError("price nodes must be finite positive Decimal")
        if not out or out[-1] != p:
            out.append(p)
    return tuple(out)


def minimal_path_prices(candle: OhlcCandle1m, policy: MinimalPathPolicy) -> tuple[Decimal, ...]:
    if not isinstance(candle, OhlcCandle1m):
        raise ValueError("candle must be OhlcCandle1m")
    if not isinstance(policy, MinimalPathPolicy):
        raise ValueError("policy must be MinimalPathPolicy")
    raw = (
        (candle.open, candle.high, candle.low, candle.close)
        if policy is MinimalPathPolicy.open_high_low_close
        else (candle.open, candle.low, candle.high, candle.close)
    )
    return normalize_consecutive_duplicates(raw)


def minimal_paths_are_distinct(candle: OhlcCandle1m) -> bool:
    if not isinstance(candle, OhlcCandle1m):
        raise ValueError("candle must be OhlcCandle1m")
    return minimal_path_prices(
        candle, MinimalPathPolicy.open_high_low_close
    ) != minimal_path_prices(candle, MinimalPathPolicy.open_low_high_close)
