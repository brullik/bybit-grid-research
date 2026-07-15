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
    kind = MarketDatasetKind(kind)
    if sorted(p.name for p in Path(d).iterdir()) != ["chunk_manifest.json", "data.parquet"]:
        raise MarketStoreError("chunk_dir_contract_invalid")
    mf = json.loads((d / "chunk_manifest.json").read_text())
    required = {"dataset","relative_path","row_count","primary_key_columns","min_key","max_key","parquet_sha256","logical_rows_sha256","storage_schema_version"}
    if set(mf) != required or mf["dataset"] != kind.value:
        raise MarketStoreError("manifest_schema_invalid")
    if type(mf["relative_path"]) is not str or not mf["relative_path"].startswith("datasets/"):
        raise MarketStoreError("manifest_relative_path_invalid")
    data = d / "data.parquet"
    if hashlib.sha256(data.read_bytes()).hexdigest() != mf["parquet_sha256"]:
        raise MarketStoreError("parquet_sha256_mismatch")
    t = pq.read_table(data)
    if t.schema != schema_for(kind):
        raise MarketStoreError("schema_mismatch")
    rows = tuple(t.to_pylist())
    keys = tuple(row_key(kind, r) for r in rows)
    if tuple(sorted(keys)) != keys or len(set(keys)) != len(keys):
        raise MarketStoreError("primary_key_order_invalid")
    if len(rows) != mf["row_count"] or list(keys[0]) != mf["min_key"] or list(keys[-1]) != mf["max_key"]:
        raise MarketStoreError("manifest_row_bounds_invalid")
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


def _validate_replay_args(symbol, start_ms, end_ms, snapshot_server_time_ms):
    if type(symbol) is not str or not symbol or "/" in symbol or "\\" in symbol or ".." in symbol:
        raise MarketStoreError("unsafe_symbol")
    for name, value in (("start", start_ms), ("end", end_ms), ("snapshot", snapshot_server_time_ms)):
        if type(value) is not int:
            raise MarketStoreError(f"{name}_not_exact_int")
        if value < 0:
            raise MarketStoreError(f"{name}_negative")
        if value % 60000:
            raise MarketStoreError(f"{name}_unaligned")
    if start_ms > end_ms:
        raise MarketStoreError("timestamp_range_reversed")


def read_replay_slice(root, *, symbol, start_ms, end_ms, snapshot_server_time_ms):
    _validate_replay_args(symbol, start_ms, end_ms, snapshot_server_time_ms)
    inst = tuple(
        r for r in read_dataset(root, MarketDatasetKind.instrument_snapshot, symbol=symbol)
        if r["snapshot_server_time_ms"] == snapshot_server_time_ms
    )
    if len(inst) != 1:
        raise MarketStoreError("instrument_snapshot_match_invalid")
    tr = read_dataset(root, MarketDatasetKind.trade_kline_1m, symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    mk = read_dataset(root, MarketDatasetKind.mark_kline_1m, symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    exp = tuple(range(start_ms, end_ms + 1, 60000))
    if tuple(r["open_time_ms"] for r in tr) != exp:
        raise MarketStoreError("incomplete_trade_coverage")
    if tuple(r["open_time_ms"] for r in mk) != exp:
        raise MarketStoreError("incomplete_mark_coverage")
    mark_by_ts = {}
    for r in mk:
        ts = r["open_time_ms"]
        if ts in mark_by_ts:
            raise MarketStoreError("duplicate_mark_join")
        mark_by_ts[ts] = r
    funding = []
    for r in read_dataset(root, MarketDatasetKind.funding_rate, symbol=symbol, start_ms=start_ms, end_ms=end_ms):
        ts = r["funding_time_ms"]
        if ts not in mark_by_ts:
            raise MarketStoreError("funding_mark_join_missing")
        funding.append({"funding_time_ms": ts, "funding_rate": r["funding_rate"], "mark_open": mark_by_ts[ts]["open"]})
    return {"instrument": inst[0], "trade_klines": tr, "mark_klines": mk, "funding_observations": tuple(funding)}
