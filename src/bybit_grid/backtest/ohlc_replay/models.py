from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

MINUTE_MS = 60_000
ZERO = Decimal("0")


class CandleSource(Enum):
    synthetic_1m = "synthetic_1m"
    bybit_trade_kline_1m = "bybit_trade_kline_1m"


class MinimalPathPolicy(Enum):
    open_high_low_close = "open_high_low_close"
    open_low_high_close = "open_low_high_close"


def _int_minute(value: Any, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be int, not bool")
    if value < 0 or value % MINUTE_MS != 0:
        raise ValueError(f"{name} must be non-negative and minute-aligned")


def _dec(value: Any, name: str, *, positive: bool) -> None:
    if not isinstance(value, Decimal) or isinstance(value, bool) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if positive and value <= ZERO:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class OhlcCandle1m:
    category: str
    symbol: str
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    closed_bool: bool
    source: CandleSource

    def __post_init__(self) -> None:
        if type(self.category) is not str or self.category != "linear":
            raise ValueError("category must be exactly str 'linear'")
        if (
            type(self.symbol) is not str
            or self.symbol.strip() == ""
            or self.symbol != self.symbol.strip()
        ):
            raise ValueError("symbol must be a non-empty stripped str")
        _int_minute(self.open_time_ms, "open_time_ms")
        if type(self.closed_bool) is not bool or self.closed_bool is not True:
            raise ValueError("closed_bool must be exactly true")
        if not isinstance(self.source, CandleSource):
            raise ValueError("source must be CandleSource")
        for n in ("open", "high", "low", "close"):
            _dec(getattr(self, n), n, positive=True)
        if not (
            self.low <= self.open <= self.high
            and self.low <= self.close <= self.high
            and self.low <= self.high
        ):
            raise ValueError("invalid OHLC relationships")
        if self.low == self.high and not (self.open == self.high == self.close):
            raise ValueError("flat candle must have all OHLC equal")

    @property
    def close_boundary_ms(self) -> int:
        return self.open_time_ms + MINUTE_MS


@dataclass(frozen=True)
class FundingObservation:
    time_ms: int
    funding_rate: Decimal
    mark_price: Decimal

    def __post_init__(self) -> None:
        _int_minute(self.time_ms, "time_ms")
        _dec(self.funding_rate, "funding_rate", positive=False)
        _dec(self.mark_price, "mark_price", positive=True)
