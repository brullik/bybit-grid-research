from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
from types import MappingProxyType
import re as _re

STORE_SCHEMA_VERSION = "bybit_public_parquet_store_v1"
MINUTE_MS = 60000


class MarketStoreError(ValueError):
    pass


class MarketDatasetKind(str, Enum):
    instrument_snapshot = "instrument_snapshot"
    trade_kline_1m = "trade_kline_1m"
    mark_kline_1m = "mark_kline_1m"
    funding_rate = "funding_rate"


def strict_int(v, n):
    if type(v) is not int:
        raise MarketStoreError(f"{n}_not_exact_int")
    return v


def strict_bool(v, n):
    if type(v) is not bool:
        raise MarketStoreError(f"{n}_not_exact_bool")
    return v


def strict_str(v, n):
    if type(v) is not str or not v or "/" in v or "\\" in v or ".." in v:
        raise MarketStoreError(f"{n}_unsafe")
    return v


def strict_dec(v, n):
    if type(v) is not Decimal or not v.is_finite():
        raise MarketStoreError(f"{n}_not_decimal")
    return v


_SHA_RE = _re.compile(r"^[0-9a-f]{64}$")


def _sha(v, n):
    if type(v) is not str or not _SHA_RE.fullmatch(v):
        raise MarketStoreError(f"{n}_invalid")
    return v


def _tuple_exact(v, n):
    if type(v) is not tuple:
        raise MarketStoreError(f"{n}_not_tuple")
    return v


def _strict_failures(v, n="failures"):
    _tuple_exact(v, n)
    if any(type(x) is not str or not x for x in v):
        raise MarketStoreError(f"{n}_invalid")


def _strict_mapping(v, n):
    if type(v) is dict:
        v = MappingProxyType(dict(v))
    if type(v) is not MappingProxyType:
        raise MarketStoreError(f"{n}_not_immutable_mapping")
    if any(type(k) is not str or not k for k in v):
        raise MarketStoreError(f"{n}_key_invalid")
    return v


@dataclass(frozen=True)
class StoreChunkManifest:
    dataset: str
    relative_path: str
    row_count: int
    primary_key_columns: tuple[str, ...]
    min_key: tuple
    max_key: tuple
    parquet_sha256: str
    logical_rows_sha256: str
    storage_schema_version: str = STORE_SCHEMA_VERSION

    def __post_init__(self):
        if self.storage_schema_version != STORE_SCHEMA_VERSION:
            raise MarketStoreError("storage_schema_version_invalid")
        MarketDatasetKind(self.dataset)
        if (
            type(self.relative_path) is not str
            or not self.relative_path
            or "\\" in self.relative_path
            or ".." in self.relative_path.split("/")
            or not self.relative_path.startswith("datasets/")
        ):
            raise MarketStoreError("relative_path_invalid")
        strict_int(self.row_count, "row_count")
        if self.row_count <= 0:
            raise MarketStoreError("row_count_invalid")
        _tuple_exact(self.primary_key_columns, "primary_key_columns")
        if any(type(x) is not str or not x for x in self.primary_key_columns):
            raise MarketStoreError("primary_key_columns_invalid")
        _tuple_exact(self.min_key, "min_key")
        _tuple_exact(self.max_key, "max_key")
        if self.min_key > self.max_key:
            raise MarketStoreError("key_order_invalid")
        _sha(self.parquet_sha256, "parquet_sha256")
        _sha(self.logical_rows_sha256, "logical_rows_sha256")


@dataclass(frozen=True)
class StoreImportReceipt:
    run_id: str
    source_review_pack_sha256: str
    chunks: tuple[StoreChunkManifest, ...]
    storage_schema_version: str = STORE_SCHEMA_VERSION

    def __post_init__(self):
        if self.storage_schema_version != STORE_SCHEMA_VERSION:
            raise MarketStoreError("storage_schema_version_invalid")
        strict_str(self.run_id, "run_id")
        _sha(self.source_review_pack_sha256, "source_review_pack_sha256")
        _tuple_exact(self.chunks, "chunks")
        if any(type(c) is not StoreChunkManifest for c in self.chunks):
            raise MarketStoreError("chunks_invalid")


@dataclass(frozen=True)
class StoreChunkInventoryRow:
    dataset: str
    relative_path: str
    row_count: int
    logical_rows_sha256: str


@dataclass(frozen=True)
class CoverageInterval:
    start_open_time_ms: int
    end_open_time_ms: int
    row_count: int

    def __post_init__(self):
        strict_int(self.start_open_time_ms, "start_open_time_ms")
        strict_int(self.end_open_time_ms, "end_open_time_ms")
        strict_int(self.row_count, "row_count")


@dataclass(frozen=True)
class MissingMinuteWindow(CoverageInterval):
    pass


@dataclass(frozen=True)
class MinuteCoverageAudit:
    symbol: str
    start_open_time_ms: int
    end_open_time_ms: int
    present_intervals: tuple[CoverageInterval, ...]
    missing_windows: tuple[MissingMinuteWindow, ...]
    duplicate_timestamps: tuple[int, ...]
    complete_bool: bool
    historical_market_data_coverage_proven_bool: bool = False


@dataclass(frozen=True)
class ReplayPairCoverageAudit:
    symbol: str
    trade_complete_bool: bool
    mark_complete_bool: bool
    timestamp_sets_equal_bool: bool
    replay_ready_bool: bool


@dataclass(frozen=True)
class FundingObservedRangeAudit:
    symbol: str
    observed_count: int
    min_funding_time_ms: int | None
    max_funding_time_ms: int | None
    duplicate_timestamps: tuple[int, ...]
    funding_coverage_proven_bool: bool = False


@dataclass(frozen=True)
class MarketStoreAudit:
    ok: bool
    failures: tuple[str, ...]
    chunk_count: int = 0
    receipt_count: int = 0
    historical_market_data_coverage_proven_bool: bool = False
    funding_coverage_proven_bool: bool = False
    live_authorized_bool: bool = False

    def __post_init__(self):
        strict_bool(self.ok, "ok")
        _strict_failures(self.failures)
        strict_int(self.chunk_count, "chunk_count")
        strict_int(self.receipt_count, "receipt_count")


@dataclass(frozen=True)
class StoreRoundTripAudit:
    ok: bool
    failures: tuple[str, ...]
    dataset_hashes: MappingProxyType

    def __post_init__(self):
        strict_bool(self.ok, "ok")
        _strict_failures(self.failures)
        object.__setattr__(self, "dataset_hashes", _strict_mapping(self.dataset_hashes, "dataset_hashes"))


@dataclass(frozen=True)
class StoreReproducibilityAudit:
    ok: bool
    failures: tuple[str, ...]
    values: MappingProxyType

    def __post_init__(self):
        strict_bool(self.ok, "ok")
        _strict_failures(self.failures)
        object.__setattr__(self, "values", _strict_mapping(self.values, "values"))


@dataclass(frozen=True)
class FundingReplayObservation:
    funding_time_ms: int
    funding_rate: Decimal
    mark_open: Decimal

    def __post_init__(self):
        strict_int(self.funding_time_ms, "funding_time_ms")
        strict_dec(self.funding_rate, "funding_rate")
        strict_dec(self.mark_open, "mark_open")


@dataclass(frozen=True)
class ReplaySlice:
    instrument: MappingProxyType
    trade_klines: tuple[MappingProxyType, ...]
    mark_klines: tuple[MappingProxyType, ...]
    funding_observations: tuple[FundingReplayObservation, ...]

    def __post_init__(self):
        object.__setattr__(self, "instrument", _strict_mapping(self.instrument, "instrument"))
        _tuple_exact(self.trade_klines, "trade_klines")
        _tuple_exact(self.mark_klines, "mark_klines")
        _tuple_exact(self.funding_observations, "funding_observations")
