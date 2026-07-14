from __future__ import annotations
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from .models import MarketDatasetKind, MarketStoreError, StoreChunkManifest
from .schemas import schema_for, ensure_decimal128_38_18
from .canonical import logical_rows_sha256, row_key, canonical_json_bytes
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


def _rows_to_table(kind, rows):
    kind = MarketDatasetKind(kind)
    sch = schema_for(kind)
    cols = {n: [] for n in sch.names}
    seen = set()
    for r in rows:
        d = dict(r)
        k = row_key(kind, d)
        if k in seen:
            raise MarketStoreError("duplicate_incoming_key")
        seen.add(k)
        for f in DEC_FIELDS[kind.value]:
            ensure_decimal128_38_18(d[f])
        for n in cols:
            v = d.get(n)
            if type(v) is float or type(v) is bool and sch.field(n).type == pa.int64():
                raise MarketStoreError("type_invalid")
            cols[n].append(v)
    arrays = [pa.array(cols[n], type=sch.field(n).type) for n in sch.names]
    return pa.Table.from_arrays(arrays, schema=sch)


def write_chunk_atomic(store_root, kind, rows):
    store_root = Path(store_root)
    kind = MarketDatasetKind(kind)
    rows = tuple(sorted(rows, key=lambda r: row_key(kind, r)))
    if not rows:
        return None
    lh = logical_rows_sha256(kind, rows)
    keys = [row_key(kind, r) for r in rows]
    d0 = dict(rows[0])
    sym = d0.get("symbol")
    if kind is MarketDatasetKind.instrument_snapshot:
        rel = rel_chunk_path(
            kind, snapshot_server_time_ms=d0["snapshot_server_time_ms"], logical_hash=lh
        )
    else:
        rel = rel_chunk_path(
            kind, symbol=sym, min_ms=keys[0][1], max_ms=keys[-1][1], logical_hash=lh
        )
    final = store_root / rel
    manifest = StoreChunkManifest(
        kind.value,
        rel.as_posix(),
        len(rows),
        tuple(
            ["symbol", "open_time_ms"]
            if kind in (MarketDatasetKind.trade_kline_1m, MarketDatasetKind.mark_kline_1m)
            else ["symbol", "funding_time_ms"]
            if kind is MarketDatasetKind.funding_rate
            else ["snapshot_server_time_ms", "symbol"]
        ),
        keys[0],
        keys[-1],
        "",
        lh,
    )
    if final.exists():
        mf = json.loads((final / "chunk_manifest.json").read_text())
        if mf.get("logical_rows_sha256") == lh:
            return StoreChunkManifest(**mf)
        raise MarketStoreError("immutable_chunk_path_conflict")
    staging = store_root / ".building" / str(uuid.uuid4()) / rel
    staging.mkdir(parents=True)
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
    back = pq.read_table(staging / "data.parquet")
    if back.schema != schema_for(kind) or back.num_rows != len(rows):
        raise MarketStoreError("parquet_readback_invalid")
    psha = hashlib.sha256((staging / "data.parquet").read_bytes()).hexdigest()
    manifest = StoreChunkManifest(**{**asdict(manifest), "parquet_sha256": psha})
    (staging / "chunk_manifest.json").write_bytes(canonical_json_bytes(asdict(manifest)))
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, final)
    shutil.rmtree(store_root / ".building" / str(uuid.uuid4()), ignore_errors=True)
    return manifest
