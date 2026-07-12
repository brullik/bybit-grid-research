from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from bybit_grid.backtest.ohlc_replay.models import (
    CandleSource,
    FundingMarkPriceSource,
    FundingObservation,
    FundingRateSource,
    OhlcCandle1m,
)

MINUTE_MS = 60000


class PublicBatchError(ValueError):
    pass


class InstrumentContractType(str, Enum):
    LinearPerpetual = "LinearPerpetual"
    LinearFutures = "LinearFutures"


class InstrumentStatus(str, Enum):
    Trading = "Trading"


class PublicSource(str, Enum):
    bybit_trade_kline_1m = "bybit_trade_kline_1m"
    bybit_mark_price_kline_1m = "bybit_mark_price_kline_1m"
    bybit_funding_history = "bybit_funding_history"


def _int(v, n, *, minute=False, positive=False):
    if type(v) is not int:
        raise PublicBatchError(f"{n}_not_exact_int")
    if v < (1 if positive else 0) or (minute and v % MINUTE_MS):
        raise PublicBatchError(f"{n}_out_of_range")


def _bool(v, n):
    if type(v) is not bool:
        raise PublicBatchError(f"{n}_not_exact_bool")


def _str(v, n, *, upper=False):
    if type(v) is not str or not v or v != v.strip() or (upper and v != v.upper()):
        raise PublicBatchError(f"{n}_invalid")


def _dec(v, n, *, positive=False, nonnegative=False):
    if type(v) is not Decimal or not v.is_finite():
        raise PublicBatchError(f"{n}_not_finite_decimal")
    if positive and v <= 0:
        raise PublicBatchError(f"{n}_not_positive")
    if nonnegative and v < 0:
        raise PublicBatchError(f"{n}_negative")


def _ohlc(o, h, low, c):
    for n, v in (("open", o), ("high", h), ("low", low), ("close", c)):
        _dec(v, n, positive=True)
    if not (low <= o <= h and low <= c <= h and low <= h):
        raise PublicBatchError("ohlc_relationship_invalid")


@dataclass(frozen=True)
class InclusiveMinuteWindow:
    start_open_time_ms: int
    end_open_time_ms: int

    def __post_init__(self):
        _int(self.start_open_time_ms, "start_open_time_ms", minute=True)
        _int(self.end_open_time_ms, "end_open_time_ms", minute=True)
        if self.end_open_time_ms < self.start_open_time_ms:
            raise PublicBatchError("window_end_before_start")

    @property
    def row_count(self):
        return ((self.end_open_time_ms - self.start_open_time_ms) // MINUTE_MS) + 1

    def timestamps(self):
        return tuple(range(self.start_open_time_ms, self.end_open_time_ms + 1, MINUTE_MS))


@dataclass(frozen=True)
class BybitServerTime:
    server_time_ms: int
    time_second: int
    time_nano: int
    top_level_time_ms: int
    last_closed_open_time_ms: int

    def __post_init__(self):
        for n in (
            "server_time_ms",
            "time_second",
            "time_nano",
            "top_level_time_ms",
            "last_closed_open_time_ms",
        ):
            _int(getattr(self, n), n)
        if (
            self.last_closed_open_time_ms
            != (self.server_time_ms // MINUTE_MS) * MINUTE_MS - MINUTE_MS
        ):
            raise PublicBatchError("last_closed_cutoff_mismatch")


@dataclass(frozen=True)
class BybitInstrumentMeta:
    category: str
    symbol: str
    contract_type: str
    status: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    launch_time_ms: int
    delivery_time_ms: int
    is_pre_listing: bool
    funding_interval_minutes: int
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    min_notional_value: Decimal
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal
    snapshot_server_time_ms: int

    def __post_init__(self):
        if self.category != "linear":
            raise PublicBatchError("instrument_category_invalid")
        for n in ("symbol", "base_coin", "quote_coin", "settle_coin"):
            _str(getattr(self, n), n, upper=True)
        _str(self.contract_type, "contract_type")
        if self.contract_type not in {"LinearPerpetual", "LinearFutures"}:
            raise PublicBatchError("contract_type_unknown")
        _str(self.status, "status")
        _bool(self.is_pre_listing, "is_pre_listing")
        for n in ("launch_time_ms", "delivery_time_ms", "snapshot_server_time_ms"):
            _int(getattr(self, n), n)
        _int(self.funding_interval_minutes, "funding_interval_minutes")
        for n in (
            "tick_size",
            "qty_step",
            "min_order_qty",
            "min_notional_value",
            "min_leverage",
            "max_leverage",
            "leverage_step",
        ):
            _dec(getattr(self, n), n, positive=True)

    def eligible_for_replay(self):
        return (
            self.contract_type == "LinearPerpetual"
            and self.status == "Trading"
            and self.quote_coin == "USDT"
            and self.settle_coin == "USDT"
            and self.is_pre_listing is False
            and self.funding_interval_minutes > 0
        )


@dataclass(frozen=True)
class BybitTradeKline1m:
    category: str
    symbol: str
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal
    closed_bool: bool
    source: PublicSource = PublicSource.bybit_trade_kline_1m

    def __post_init__(self):
        if self.category != "linear":
            raise PublicBatchError("kline_category_invalid")
        _str(self.symbol, "symbol", upper=True)
        _int(self.open_time_ms, "open_time_ms", minute=True)
        _bool(self.closed_bool, "closed_bool")
        if self.closed_bool is not True:
            raise PublicBatchError("kline_unclosed")
        _ohlc(self.open, self.high, self.low, self.close)
        _dec(self.volume, "volume", nonnegative=True)
        _dec(self.turnover, "turnover", nonnegative=True)
        if self.source is not PublicSource.bybit_trade_kline_1m:
            raise PublicBatchError("trade_source_invalid")

    def to_ohlc_candle(self):
        return OhlcCandle1m(
            self.category,
            self.symbol,
            self.open_time_ms,
            self.open,
            self.high,
            self.low,
            self.close,
            True,
            CandleSource.bybit_trade_kline_1m,
        )


@dataclass(frozen=True)
class BybitMarkKline1m:
    category: str
    symbol: str
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    closed_bool: bool
    source: PublicSource = PublicSource.bybit_mark_price_kline_1m

    def __post_init__(self):
        if self.category != "linear":
            raise PublicBatchError("mark_category_invalid")
        _str(self.symbol, "symbol", upper=True)
        _int(self.open_time_ms, "open_time_ms", minute=True)
        _bool(self.closed_bool, "closed_bool")
        if self.closed_bool is not True:
            raise PublicBatchError("mark_unclosed")
        _ohlc(self.open, self.high, self.low, self.close)
        if self.source is not PublicSource.bybit_mark_price_kline_1m:
            raise PublicBatchError("mark_source_invalid")


@dataclass(frozen=True)
class BybitFundingRate:
    category: str
    symbol: str
    funding_time_ms: int
    funding_rate: Decimal
    source: PublicSource = PublicSource.bybit_funding_history

    def __post_init__(self):
        if self.category != "linear":
            raise PublicBatchError("funding_category_invalid")
        _str(self.symbol, "symbol", upper=True)
        _int(self.funding_time_ms, "funding_time_ms", minute=True)
        _dec(self.funding_rate, "funding_rate")
        if self.source is not PublicSource.bybit_funding_history:
            raise PublicBatchError("funding_source_invalid")

    def to_observation(self, mark_price: Decimal):
        return FundingObservation(
            self.category,
            self.symbol,
            self.funding_time_ms,
            self.funding_rate,
            mark_price,
            FundingRateSource.bybit_funding_history,
            FundingMarkPriceSource.bybit_mark_price_kline_1m,
        )


@dataclass(frozen=True)
class BybitInstrumentUniverseAudit:
    instrument_count: int
    contract_type_counts: Mapping[str, int]
    status_counts: Mapping[str, int]
    quote_coin_counts: Mapping[str, int]
    settle_coin_counts: Mapping[str, int]
    funding_interval_counts: Mapping[int, int]
    zero_funding_interval_count: int
    zero_funding_interval_symbols: tuple[str, ...]
    zero_funding_interval_by_contract_type: Mapping[str, int]
    linear_perpetual_count: int
    linear_futures_count: int
    usdt_linear_perpetual_count: int
    replay_eligible_count: int
    replay_eligible_zero_funding_interval_count: int
    replay_candidate_zero_funding_interval_symbols: tuple[str, ...]
    symbols_unique_bool: bool
    all_rows_exact_public_models_bool: bool
    universe_audit_ok: bool
    failures: tuple[str, ...]

    def __post_init__(self):
        for name in (
            "contract_type_counts",
            "status_counts",
            "quote_coin_counts",
            "settle_coin_counts",
            "funding_interval_counts",
            "zero_funding_interval_by_contract_type",
        ):
            value = getattr(self, name)
            if not isinstance(value, MappingProxyType):
                object.__setattr__(self, name, MappingProxyType(dict(value)))


@dataclass(frozen=True)
class PublicRequestPageAudit:
    endpoint: str
    category: str
    symbol: str | None
    cursor: str | None
    start_ms: int | None
    end_ms: int | None
    limit: int
    row_count: int
    next_cursor: str | None


@dataclass(frozen=True)
class BybitPublicReplayBatch:
    instrument: BybitInstrumentMeta
    trade_klines: tuple
    mark_klines: tuple
    funding_rates: tuple
    funding_observations: tuple
    request_page_audits: tuple
    server_time: BybitServerTime
    requested_window: InclusiveMinuteWindow
    funding_mark_alignment_method: str = (
        "mark_kline_open_at_funding_timestamp_minute_data_approximation"
    )

    def __post_init__(self):
        for n in (
            "trade_klines",
            "mark_klines",
            "funding_rates",
            "funding_observations",
            "request_page_audits",
        ):
            if type(getattr(self, n)) is not tuple:
                raise PublicBatchError(f"{n}_not_tuple")


@dataclass(frozen=True)
class BybitPublicBatchAudit:
    public_batch_audit_ok: bool
    instrument_contract_ok: bool
    closed_candle_cutoff_ok: bool
    trade_kline_coverage_ok: bool
    mark_kline_coverage_ok: bool
    trade_mark_timestamp_sets_equal_bool: bool
    funding_pagination_range_covered_bool: bool
    funding_interval_consistent_bool: bool
    funding_mark_boundary_join_ok: bool
    replay_inputs_ready_bool: bool
    failures: tuple[str, ...]
