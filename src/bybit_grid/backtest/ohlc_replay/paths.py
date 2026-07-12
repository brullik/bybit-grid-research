from __future__ import annotations
from decimal import Decimal
from .models import MinimalPathPolicy, OhlcCandle1m


def normalize_consecutive_duplicates(prices: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    out: list[Decimal] = []
    for p in prices:
        if not out or out[-1] != p:
            out.append(p)
    return tuple(out)


def minimal_path_prices(candle: OhlcCandle1m, policy: MinimalPathPolicy) -> tuple[Decimal, ...]:
    if not isinstance(policy, MinimalPathPolicy):
        raise ValueError("policy must be MinimalPathPolicy")
    raw = (
        (candle.open, candle.high, candle.low, candle.close)
        if policy is MinimalPathPolicy.open_high_low_close
        else (candle.open, candle.low, candle.high, candle.close)
    )
    return normalize_consecutive_duplicates(raw)


def minimal_paths_are_distinct(candle: OhlcCandle1m) -> bool:
    return minimal_path_prices(
        candle, MinimalPathPolicy.open_high_low_close
    ) != minimal_path_prices(candle, MinimalPathPolicy.open_low_high_close)
