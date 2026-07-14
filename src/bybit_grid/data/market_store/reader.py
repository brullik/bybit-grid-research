from __future__ import annotations
import json
import hashlib
from pathlib import Path
import pyarrow.parquet as pq
from .models import MarketDatasetKind, MarketStoreError
from .schemas import schema_for
from .canonical import logical_rows_sha256, row_key


def _chunk_dirs(root, kind):
    return sorted((Path(root) / "datasets" / MarketDatasetKind(kind).value).glob("**/chunk=*"))


def _read_chunk(d, kind):
    mf = json.loads((d / "chunk_manifest.json").read_text())
    data = d / "data.parquet"
    if hashlib.sha256(data.read_bytes()).hexdigest() != mf["parquet_sha256"]:
        raise MarketStoreError("parquet_sha256_mismatch")
    t = pq.read_table(data)
    if t.schema != schema_for(kind):
        raise MarketStoreError("schema_mismatch")
    rows = tuple(t.to_pylist())
    if logical_rows_sha256(kind, rows) != mf["logical_rows_sha256"]:
        raise MarketStoreError("logical_hash_mismatch")
    return rows


def read_dataset(root, kind, *, symbol=None, start_ms=None, end_ms=None):
    kind = MarketDatasetKind(kind)
    rows = []
    seen = {}
    for d in _chunk_dirs(root, kind):
        for r in _read_chunk(d, kind):
            if symbol is not None and r.get("symbol") != symbol:
                continue
            ts = r.get("open_time_ms", r.get("funding_time_ms", r.get("snapshot_server_time_ms")))
            if start_ms is not None and ts < start_ms:
                continue
            if end_ms is not None and ts > end_ms:
                continue
            k = row_key(kind, r)
            if k in seen and seen[k] != r:
                raise MarketStoreError("store_row_conflict")
            if k in seen:
                raise MarketStoreError("duplicate_committed_key")
            seen[k] = r
            rows.append(r)
    return tuple(sorted(rows, key=lambda r: row_key(kind, r)))


def read_replay_slice(root, *, symbol, start_ms, end_ms, snapshot_server_time_ms):
    if snapshot_server_time_ms is None:
        raise MarketStoreError("explicit_instrument_snapshot_required")
    tr = read_dataset(
        root, MarketDatasetKind.trade_kline_1m, symbol=symbol, start_ms=start_ms, end_ms=end_ms
    )
    mk = read_dataset(
        root, MarketDatasetKind.mark_kline_1m, symbol=symbol, start_ms=start_ms, end_ms=end_ms
    )
    exp = tuple(range(start_ms, end_ms + 1, 60000))
    if tuple(r["open_time_ms"] for r in tr) != exp:
        raise MarketStoreError("incomplete_trade_coverage")
    if tuple(r["open_time_ms"] for r in mk) != exp:
        raise MarketStoreError("incomplete_mark_coverage")
    return {
        "trade_klines": tr,
        "mark_klines": mk,
        "funding_rates": read_dataset(
            root, MarketDatasetKind.funding_rate, symbol=symbol, start_ms=start_ms, end_ms=end_ms
        ),
    }
