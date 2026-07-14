from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

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


def strict_str(v, n):
    if type(v) is not str or not v or "/" in v or "\\" in v or ".." in v:
        raise MarketStoreError(f"{n}_unsafe")
    return v


def strict_dec(v, n):
    if type(v) is not Decimal or not v.is_finite():
        raise MarketStoreError(f"{n}_not_decimal")
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


@dataclass(frozen=True)
class StoreImportReceipt:
    run_id: str
    source_review_pack_sha256: str
    chunks: tuple[StoreChunkManifest, ...]
    storage_schema_version: str = STORE_SCHEMA_VERSION


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


@dataclass(frozen=True)
class StoreRoundTripAudit:
    ok: bool
    failures: tuple[str, ...]
    dataset_hashes: dict


@dataclass(frozen=True)
class StoreReproducibilityAudit:
    ok: bool
    failures: tuple[str, ...]
    values: dict
