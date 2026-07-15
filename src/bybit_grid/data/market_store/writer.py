from __future__ import annotations
import hashlib
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from .models import (
    MarketDatasetKind,
    MarketStoreError,
    StoreChunkManifest,
    STORE_SCHEMA_VERSION,
    PlannedChunk,
    freeze_immutable,
)
from .schemas import schema_for, ensure_decimal128_38_18
from .canonical import logical_rows_sha256, row_key, canonical_json_bytes
from .parsing import parse_chunk_manifest_bytes
from .paths import rel_chunk_path

DEC_FIELDS = {
    "instrument_snapshot": (
        "tick_size",
        "qty_step",
        "min_order_qty",
        "min_notional_value",
        "min_leverage",
        "max_leverage",
        "leverage_step",
    ),
    "trade_kline_1m": ("open", "high", "low", "close", "volume", "turnover"),
    "mark_kline_1m": ("open", "high", "low", "close"),
    "funding_rate": ("funding_rate",),
}
PK_COLUMNS = {
    MarketDatasetKind.instrument_snapshot: ("snapshot_server_time_ms", "symbol"),
    MarketDatasetKind.trade_kline_1m: ("symbol", "open_time_ms"),
    MarketDatasetKind.mark_kline_1m: ("symbol", "open_time_ms"),
    MarketDatasetKind.funding_rate: ("symbol", "funding_time_ms"),
}


def _validate_row(kind, r):
    sch = schema_for(kind)
    d = dict(r)
    if set(d) != set(sch.names):
        raise MarketStoreError("store_row_field_set_invalid")
    for f in sch:
        v = d[f.name]
        if pa.types.is_int64(f.type):
            if type(v) is not int or v < 0:
                raise MarketStoreError("type_invalid")
        elif pa.types.is_boolean(f.type):
            if type(v) is not bool:
                raise MarketStoreError("type_invalid")
        elif pa.types.is_string(f.type):
            if type(v) is not str or not v:
                raise MarketStoreError("type_invalid")
        elif pa.types.is_decimal(f.type):
            ensure_decimal128_38_18(v)
    if d["storage_schema_version"] != STORE_SCHEMA_VERSION:
        raise MarketStoreError("storage_schema_version_invalid")
    if kind in (MarketDatasetKind.trade_kline_1m, MarketDatasetKind.mark_kline_1m):
        if d["open_time_ms"] % 60000:
            raise MarketStoreError("timestamp_unaligned")
    if kind is MarketDatasetKind.funding_rate and d["funding_time_ms"] % 60000:
        raise MarketStoreError("timestamp_unaligned")
    return d


def _rows_to_table(kind, rows):
    sch = schema_for(kind)
    cols = {n: [] for n in sch.names}
    seen = set()
    for r in rows:
        d = _validate_row(kind, r)
        k = row_key(kind, d)
        if k in seen:
            raise MarketStoreError("duplicate_incoming_key")
        seen.add(k)
        for n in cols:
            cols[n].append(d[n])
    arrays = [pa.array(cols[n], type=sch.field(n).type) for n in sch.names]
    return pa.Table.from_arrays(arrays, schema=sch)


def _semantic_validate_chunk_dir(d, kind, manifest):
    if sorted(p.name for p in d.iterdir()) != ["chunk_manifest.json", "data.parquet"]:
        raise MarketStoreError("chunk_dir_contract_invalid")
    mb = (d / "chunk_manifest.json").read_bytes()
    if mb != canonical_json_bytes(manifest):
        raise MarketStoreError("manifest_canonical_mismatch")
    data = d / "data.parquet"
    if hashlib.sha256(data.read_bytes()).hexdigest() != manifest.parquet_sha256:
        raise MarketStoreError("parquet_sha256_mismatch")
    t = pq.read_table(data)
    if t.schema != schema_for(kind):
        raise MarketStoreError("schema_mismatch")
    rows = tuple(t.to_pylist())
    keys = tuple(row_key(kind, r) for r in rows)
    if tuple(sorted(keys)) != keys or len(set(keys)) != len(keys):
        raise MarketStoreError("primary_key_order_invalid")
    if (
        len(rows) != manifest.row_count
        or keys[0] != tuple(manifest.min_key)
        or keys[-1] != tuple(manifest.max_key)
    ):
        raise MarketStoreError("manifest_row_bounds_invalid")
    if logical_rows_sha256(kind, rows) != manifest.logical_rows_sha256:
        raise MarketStoreError("logical_hash_mismatch")
    return rows


def _one_month(rows, kind):
    if kind is MarketDatasetKind.instrument_snapshot:
        snaps = {r["snapshot_server_time_ms"] for r in rows}
        if len(snaps) != 1:
            raise MarketStoreError("snapshot_chunk_timestamp_invalid")
        return
    symbols = {r.get("symbol") for r in rows}
    if len(symbols) != 1:
        raise MarketStoreError("mixed_symbols")
    tsname = (
        "funding_time_ms" if kind is MarketDatasetKind.funding_rate else "open_time_ms"
    )
    months = {
        (
            datetime.fromtimestamp(r[tsname] / 1000, tz=timezone.utc).year,
            datetime.fromtimestamp(r[tsname] / 1000, tz=timezone.utc).month,
        )
        for r in rows
    }
    if len(months) != 1:
        raise MarketStoreError("chunk_crosses_utc_month")


def _planned_table_bytes(kind, rows):
    table = _rows_to_table(kind, rows)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd", compression_level=6, use_dictionary=True, write_statistics=True, row_group_size=131072)
    return sink.getvalue().to_pybytes()


def build_planned_chunk(kind, rows, *, existing_store_root=None):
    kind = MarketDatasetKind(kind)
    rows = tuple(sorted((_validate_row(kind, r) for r in rows), key=lambda r: row_key(kind, r)))
    if not rows:
        raise MarketStoreError("empty_chunk_input")
    _one_month(rows, kind)
    keys = [row_key(kind, r) for r in rows]
    if len(set(keys)) != len(keys):
        raise MarketStoreError("duplicate_incoming_key")
    lh = logical_rows_sha256(kind, rows)
    d0 = rows[0]
    if kind is MarketDatasetKind.instrument_snapshot:
        rel = rel_chunk_path(kind, snapshot_server_time_ms=d0["snapshot_server_time_ms"], logical_hash=lh)
    else:
        rel = rel_chunk_path(kind, symbol=d0["symbol"], min_ms=keys[0][1], max_ms=keys[-1][1], logical_hash=lh)
    parquet_bytes = _planned_table_bytes(kind, rows)
    psha = hashlib.sha256(parquet_bytes).hexdigest()
    manifest = StoreChunkManifest(kind.value, rel.as_posix(), len(rows), PK_COLUMNS[kind], keys[0], keys[-1], psha, lh)
    manifest_bytes = canonical_json_bytes(manifest)
    reuse = False
    if existing_store_root is not None and (Path(existing_store_root) / rel).exists():
        from .reader import read_and_validate_chunk
        read_and_validate_chunk(Path(existing_store_root), Path(existing_store_root)/rel, expected_manifest=manifest)
        reuse = True
    frozen_rows = tuple(freeze_immutable(r, field_name="rows") for r in rows)
    return PlannedChunk(kind, frozen_rows, manifest, parquet_bytes, manifest_bytes, reuse)


def write_chunk_atomic(store_root, kind, rows, *, fail_at=None):
    store_root = Path(store_root)
    kind = MarketDatasetKind(kind)
    rows = tuple(
        sorted((_validate_row(kind, r) for r in rows), key=lambda r: row_key(kind, r))
    )
    if not rows:
        raise MarketStoreError("empty_chunk_input")
    _one_month(rows, kind)
    keys = [row_key(kind, r) for r in rows]
    if len(set(keys)) != len(keys):
        raise MarketStoreError("duplicate_incoming_key")
    if fail_at == "early":
        raise MarketStoreError("injected_chunk_failure_early")
    lh = logical_rows_sha256(kind, rows)
    d0 = rows[0]
    if kind is MarketDatasetKind.instrument_snapshot:
        rel = rel_chunk_path(
            kind, snapshot_server_time_ms=d0["snapshot_server_time_ms"], logical_hash=lh
        )
    else:
        tsidx = 1
        rel = rel_chunk_path(
            kind,
            symbol=d0["symbol"],
            min_ms=keys[0][tsidx],
            max_ms=keys[-1][tsidx],
            logical_hash=lh,
        )
    final = store_root / rel
    if final.exists():
        mf = parse_chunk_manifest_bytes((final / "chunk_manifest.json").read_bytes())
        _semantic_validate_chunk_dir(final, kind, mf)
        if mf.logical_rows_sha256 == lh:
            return mf
        raise MarketStoreError("immutable_chunk_path_conflict")
    staging_root = store_root / ".building" / str(uuid.uuid4())
    staging = staging_root / rel
    try:
        staging.mkdir(parents=True)
        if fail_at == "mid":
            raise MarketStoreError("injected_chunk_failure_mid")
        table = _rows_to_table(kind, rows)
        pq.write_table(
            table,
            staging / "data.parquet",
            compression="zstd",
            compression_level=6,
            use_dictionary=True,
            write_statistics=True,
            row_group_size=131072,
        )
        psha = hashlib.sha256((staging / "data.parquet").read_bytes()).hexdigest()
        manifest = StoreChunkManifest(
            kind.value,
            rel.as_posix(),
            len(rows),
            PK_COLUMNS[kind],
            keys[0],
            keys[-1],
            psha,
            lh,
        )
        (staging / "chunk_manifest.json").write_bytes(
            canonical_json_bytes(manifest)
        )
        _semantic_validate_chunk_dir(staging, kind, manifest)
        if fail_at == "late":
            raise MarketStoreError("injected_chunk_failure_late")
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final)
        return manifest
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
# RED acceptance probe only: no behavioral implementation; do not merge.
