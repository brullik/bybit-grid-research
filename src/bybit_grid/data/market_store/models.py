from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
from types import MappingProxyType
import re as _re
from pathlib import Path

STORE_SCHEMA_VERSION = "bybit_public_parquet_store_v1"
MINUTE_MS = 60000


class MarketStoreError(ValueError):
    """Stable market-store contract violation."""



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




def freeze_immutable(value, *, field_name):
    if type(value) is MappingProxyType:
        out = {}
        for k, v in value.items():
            if type(k) is not str or not k:
                raise MarketStoreError(f"{field_name}_key_invalid")
            out[k] = freeze_immutable(v, field_name=field_name)
        return MappingProxyType(out)
    if type(value) is dict:
        out = {}
        for k, v in value.items():
            if type(k) is not str or not k:
                raise MarketStoreError(f"{field_name}_key_invalid")
            out[k] = freeze_immutable(v, field_name=field_name)
        return MappingProxyType(out)
    if type(value) is tuple:
        return tuple(freeze_immutable(v, field_name=field_name) for v in value)
    if type(value) is list:
        raise MarketStoreError(f"{field_name}_mutable_sequence_forbidden")
    if value is None or type(value) in (str, int, bool, Decimal) or isinstance(value, Enum):
        return value
    if isinstance(value, (float, bytes, bytearray, Path, set, frozenset)):
        raise MarketStoreError(f"{field_name}_type_forbidden")
    raise MarketStoreError(f"{field_name}_type_unknown:{type(value).__name__}")

def _safe_relative(v, n):
    if type(v) is not str or not v or v.startswith('/') or '\\' in v or ':' in v or any(part in ('', '.', '..') for part in v.split('/')):
        raise MarketStoreError(f"{n}_invalid")
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
    frozen = freeze_immutable(v, field_name=n)
    if type(frozen) is not MappingProxyType:
        raise MarketStoreError(f"{n}_not_immutable_mapping")
    return frozen




@dataclass(frozen=True)
class StoreVersion:
    storage_schema_version: str

    def __post_init__(self):
        if type(self.storage_schema_version) is not str or self.storage_schema_version != STORE_SCHEMA_VERSION:
            raise MarketStoreError("storage_schema_version_invalid")


@dataclass(frozen=True)
class StoreEvidenceReference:
    run_id: str
    source_review_pack_sha256: str

    def __post_init__(self):
        strict_str(self.run_id, "run_id")
        _sha(self.source_review_pack_sha256, "source_review_pack_sha256")


@dataclass(frozen=True)
class StoreFileInventoryEntry:
    relative_path: str
    entry_type: str
    size: int
    sha256: str | None
    mtime_ns: int

    def __post_init__(self):
        _safe_relative(self.relative_path, "relative_path")
        if self.entry_type not in ("file", "directory") or type(self.entry_type) is not str:
            raise MarketStoreError("entry_type_invalid")
        strict_int(self.size, "size")
        strict_int(self.mtime_ns, "mtime_ns")
        if self.entry_type == "file":
            _sha(self.sha256, "sha256")
        elif self.sha256 is not None:
            raise MarketStoreError("sha256_invalid")


@dataclass(frozen=True)
class PlannedChunk:
    dataset: MarketDatasetKind
    rows: tuple[MappingProxyType, ...]
    manifest: StoreChunkManifest
    parquet_bytes: bytes
    manifest_bytes: bytes
    reuse_existing_bool: bool

    def __post_init__(self):
        if type(self.dataset) is not MarketDatasetKind:
            raise MarketStoreError("dataset_invalid")
        _tuple_exact(self.rows, "rows")
        object.__setattr__(self, "rows", tuple(_strict_mapping(r, "rows") for r in self.rows))
        if type(self.manifest) is not StoreChunkManifest:
            raise MarketStoreError("manifest_invalid")
        if type(self.parquet_bytes) is not bytes or not self.parquet_bytes:
            raise MarketStoreError("parquet_bytes_invalid")
        if type(self.manifest_bytes) is not bytes or not self.manifest_bytes:
            raise MarketStoreError("manifest_bytes_invalid")
        strict_bool(self.reuse_existing_bool, "reuse_existing_bool")


@dataclass(frozen=True)
class ImportPreflightPlan:
    evidence: object
    store_root: Path
    version: StoreVersion
    chunks: tuple[PlannedChunk, ...]
    evidence_reference: StoreEvidenceReference
    receipt: StoreImportReceipt
    receipt_bytes: bytes
    evidence_reference_bytes: bytes
    source_archive_bytes: bytes
    existing_store_bool: bool

    def __post_init__(self):
        if type(self.store_root) is not Path:
            raise MarketStoreError("store_root_invalid")
        if type(self.version) is not StoreVersion:
            raise MarketStoreError("version_invalid")
        _tuple_exact(self.chunks, "chunks")
        if any(type(c) is not PlannedChunk for c in self.chunks):
            raise MarketStoreError("chunks_invalid")
        if type(self.evidence_reference) is not StoreEvidenceReference:
            raise MarketStoreError("evidence_reference_invalid")
        if type(self.receipt) is not StoreImportReceipt:
            raise MarketStoreError("receipt_invalid")
        for name in ("receipt_bytes", "evidence_reference_bytes", "source_archive_bytes"):
            if type(getattr(self, name)) is not bytes or not getattr(self, name):
                raise MarketStoreError(f"{name}_invalid")
        strict_bool(self.existing_store_bool, "existing_store_bool")


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

    def __post_init__(self):
        MarketDatasetKind(self.dataset)
        _safe_relative(self.relative_path, "relative_path")
        strict_int(self.row_count, "row_count")
        if self.row_count <= 0:
            raise MarketStoreError("row_count_invalid")
        _sha(self.logical_rows_sha256, "logical_rows_sha256")


@dataclass(frozen=True)
class CoverageInterval:
    start_open_time_ms: int
    end_open_time_ms: int
    row_count: int

    def __post_init__(self):
        strict_int(self.start_open_time_ms, "start_open_time_ms")
        strict_int(self.end_open_time_ms, "end_open_time_ms")
        strict_int(self.row_count, "row_count")
        if self.start_open_time_ms < 0 or self.end_open_time_ms < 0:
            raise MarketStoreError("timestamp_negative")
        if self.start_open_time_ms % MINUTE_MS or self.end_open_time_ms % MINUTE_MS:
            raise MarketStoreError("timestamp_unaligned")
        if self.start_open_time_ms > self.end_open_time_ms:
            raise MarketStoreError("coverage_interval_reversed")
        expected = (self.end_open_time_ms - self.start_open_time_ms) // MINUTE_MS + 1
        if self.row_count <= 0 or self.row_count != expected:
            raise MarketStoreError("row_count_invalid")


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

    def __post_init__(self):
        strict_str(self.symbol, "symbol")
        strict_int(self.start_open_time_ms, "start_open_time_ms")
        strict_int(self.end_open_time_ms, "end_open_time_ms")
        if self.start_open_time_ms % MINUTE_MS or self.end_open_time_ms % MINUTE_MS or self.start_open_time_ms > self.end_open_time_ms:
            raise MarketStoreError("coverage_window_invalid")
        for name, typ in (("present_intervals", CoverageInterval), ("missing_windows", MissingMinuteWindow)):
            xs = _tuple_exact(getattr(self, name), name)
            prev = None
            for x in xs:
                if type(x) is not typ:
                    raise MarketStoreError(f"{name}_invalid")
                if x.start_open_time_ms < self.start_open_time_ms or x.end_open_time_ms > self.end_open_time_ms:
                    raise MarketStoreError(f"{name}_outside_window")
                if prev is not None and x.start_open_time_ms <= prev:
                    raise MarketStoreError(f"{name}_not_ordered")
                prev = x.end_open_time_ms
        _tuple_exact(self.duplicate_timestamps, "duplicate_timestamps")
        if any(type(x) is not int for x in self.duplicate_timestamps) or tuple(sorted(set(self.duplicate_timestamps))) != self.duplicate_timestamps:
            raise MarketStoreError("duplicate_timestamps_invalid")
        strict_bool(self.complete_bool, "complete_bool")
        strict_bool(self.historical_market_data_coverage_proven_bool, "historical_market_data_coverage_proven_bool")
        if self.historical_market_data_coverage_proven_bool:
            raise MarketStoreError("historical_coverage_proven_forbidden")
        if self.complete_bool != (self.missing_windows == ()):
            raise MarketStoreError("complete_bool_invalid")


@dataclass(frozen=True)
class ReplayPairCoverageAudit:
    symbol: str
    trade_complete_bool: bool
    mark_complete_bool: bool
    timestamp_sets_equal_bool: bool
    replay_ready_bool: bool

    def __post_init__(self):
        strict_str(self.symbol, "symbol")
        for n in ("trade_complete_bool", "mark_complete_bool", "timestamp_sets_equal_bool", "replay_ready_bool"):
            strict_bool(getattr(self, n), n)
        if self.replay_ready_bool != (self.trade_complete_bool and self.mark_complete_bool and self.timestamp_sets_equal_bool):
            raise MarketStoreError("replay_ready_bool_invalid")


@dataclass(frozen=True)
class FundingObservedRangeAudit:
    symbol: str
    observed_count: int
    min_funding_time_ms: int | None
    max_funding_time_ms: int | None
    duplicate_timestamps: tuple[int, ...]
    funding_coverage_proven_bool: bool = False

    def __post_init__(self):
        strict_str(self.symbol, "symbol")
        strict_int(self.observed_count, "observed_count")
        if self.observed_count < 0:
            raise MarketStoreError("observed_count_invalid")
        if self.observed_count == 0:
            if self.min_funding_time_ms is not None or self.max_funding_time_ms is not None:
                raise MarketStoreError("funding_range_invalid")
        else:
            strict_int(self.min_funding_time_ms, "min_funding_time_ms")
            strict_int(self.max_funding_time_ms, "max_funding_time_ms")
            if self.min_funding_time_ms > self.max_funding_time_ms or self.min_funding_time_ms % MINUTE_MS or self.max_funding_time_ms % MINUTE_MS:
                raise MarketStoreError("funding_range_invalid")
        _tuple_exact(self.duplicate_timestamps, "duplicate_timestamps")
        if any(type(x) is not int or x % MINUTE_MS for x in self.duplicate_timestamps) or tuple(sorted(set(self.duplicate_timestamps))) != self.duplicate_timestamps:
            raise MarketStoreError("duplicate_timestamps_invalid")
        strict_bool(self.funding_coverage_proven_bool, "funding_coverage_proven_bool")
        if self.funding_coverage_proven_bool:
            raise MarketStoreError("funding_coverage_proven_forbidden")


@dataclass(frozen=True)
class MarketStoreAudit:
    ok: bool
    failures: tuple[str, ...]
    chunk_count: int = 0
    receipt_count: int = 0
    evidence_archive_count: int = 0
    evidence_reference_count: int = 0
    orphan_chunk_count: int = 0
    orphan_evidence_count: int = 0
    stale_transaction_count: int = 0
    dataset_row_counts: MappingProxyType = None
    historical_market_data_coverage_proven_bool: bool = False
    funding_coverage_proven_bool: bool = False
    live_authorized_bool: bool = False

    def __post_init__(self):
        strict_bool(self.ok, "ok")
        _strict_failures(self.failures)
        if self.ok != (not self.failures):
            raise MarketStoreError("audit_ok_invalid")
        for n in ("chunk_count", "receipt_count", "evidence_archive_count", "evidence_reference_count", "orphan_chunk_count", "orphan_evidence_count", "stale_transaction_count"):
            strict_int(getattr(self, n), n)
        object.__setattr__(self, "dataset_row_counts", _strict_mapping(self.dataset_row_counts or {}, "dataset_row_counts"))
        for n in ("historical_market_data_coverage_proven_bool", "funding_coverage_proven_bool", "live_authorized_bool"):
            strict_bool(getattr(self, n), n)
            if getattr(self, n):
                raise MarketStoreError(f"{n}_forbidden")


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
