from __future__ import annotations
import hashlib
from pathlib import Path
import pyarrow.parquet as pq
from .models import MarketDatasetKind, MarketStoreError, FundingReplayObservation, ReplaySlice, freeze_immutable
from .schemas import schema_for
from .parsing import parse_chunk_manifest_bytes
from .canonical import logical_rows_sha256, row_key
from .paths import rel_chunk_path


def _chunk_dirs(root, kind):
    return sorted((Path(root) / "datasets" / MarketDatasetKind(kind).value).glob("**/chunk=*"))


def read_and_validate_chunk(store_root: Path, chunk_dir: Path, *, expected_manifest=None):
    store_root = Path(store_root)
    d = Path(chunk_dir)
    if not d.is_dir() or d.is_symlink():
        raise MarketStoreError("chunk_dir_contract_invalid")
    try:
        rel = d.relative_to(store_root).as_posix()
    except ValueError as e:
        raise MarketStoreError("chunk_dir_contract_invalid") from e
    entries = sorted(d.iterdir(), key=lambda p: p.name)
    if [p.name for p in entries] != ["chunk_manifest.json", "data.parquet"]:
        raise MarketStoreError("chunk_dir_contract_invalid")
    for f in entries:
        if f.is_symlink() or not f.is_file():
            raise MarketStoreError("chunk_dir_contract_invalid")
    mf = parse_chunk_manifest_bytes((d / "chunk_manifest.json").read_bytes())
    if expected_manifest is not None and mf != expected_manifest:
        raise MarketStoreError("manifest_expected_mismatch")
    kind = MarketDatasetKind(mf.dataset)
    if mf.relative_path != rel:
        raise MarketStoreError("manifest_relative_path_invalid")
    data = d / "data.parquet"
    if hashlib.sha256(data.read_bytes()).hexdigest() != mf.parquet_sha256:
        raise MarketStoreError("parquet_sha256_mismatch")
    t = pq.read_table(data)
    if t.schema != schema_for(kind):
        raise MarketStoreError("schema_mismatch")
    rows = tuple(freeze_immutable(r, field_name="row") for r in t.to_pylist())
    if not rows:
        raise MarketStoreError("empty_chunk")
    keys = tuple(row_key(kind, r) for r in rows)
    if tuple(sorted(keys)) != keys or len(set(keys)) != len(keys):
        raise MarketStoreError("primary_key_order_invalid")
    if len(rows) != mf.row_count or keys[0] != mf.min_key or keys[-1] != mf.max_key:
        raise MarketStoreError("manifest_row_bounds_invalid")
    if tuple(mf.primary_key_columns) != {
        MarketDatasetKind.instrument_snapshot:("snapshot_server_time_ms","symbol"),
        MarketDatasetKind.trade_kline_1m:("symbol","open_time_ms"),
        MarketDatasetKind.mark_kline_1m:("symbol","open_time_ms"),
        MarketDatasetKind.funding_rate:("symbol","funding_time_ms"),
    }[kind]:
        raise MarketStoreError("primary_key_schema_invalid")
    logical_hash = logical_rows_sha256(kind, rows)
    if logical_hash != mf.logical_rows_sha256:
        raise MarketStoreError("logical_hash_mismatch")
    first = rows[0]
    if kind is MarketDatasetKind.instrument_snapshot:
        snaps = {r["snapshot_server_time_ms"] for r in rows}
        if len(snaps) != 1:
            raise MarketStoreError("chunk_path_semantic_mismatch")
        expected_rel = rel_chunk_path(kind, snapshot_server_time_ms=first["snapshot_server_time_ms"], logical_hash=logical_hash).as_posix()
    else:
        ts_name = "funding_time_ms" if kind is MarketDatasetKind.funding_rate else "open_time_ms"
        symbols = {r["symbol"] for r in rows}
        if len(symbols) != 1:
            raise MarketStoreError("chunk_path_semantic_mismatch")
        expected_rel = rel_chunk_path(kind, symbol=first["symbol"], min_ms=keys[0][1], max_ms=keys[-1][1], logical_hash=logical_hash).as_posix()
        if any(r[ts_name] < keys[0][1] or r[ts_name] > keys[-1][1] for r in rows):
            raise MarketStoreError("chunk_path_semantic_mismatch")
    if mf.relative_path != rel or rel != expected_rel:
        raise MarketStoreError("chunk_path_semantic_mismatch")
    return mf, rows


def _read_chunk(d, kind):
    d = Path(d)
    parts = d.parts
    if "datasets" not in parts:
        raise MarketStoreError("chunk_dir_contract_invalid")
    root = Path(*parts[:parts.index("datasets")])
    mf, rows = read_and_validate_chunk(root, d)
    if mf.dataset != MarketDatasetKind(kind).value:
        raise MarketStoreError("manifest_schema_invalid")
    return rows


def read_dataset(root, kind, *, symbol=None, start_ms=None, end_ms=None):
    kind = MarketDatasetKind(kind)
    rows = []
    seen = {}
    for d in _chunk_dirs(root, kind):
        for r in read_and_validate_chunk(Path(root), d)[1]:
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
    for name, value in (("start", start_ms), ("end", end_ms)):
        if type(value) is not int:
            raise MarketStoreError(f"{name}_not_exact_int")
        if value < 0:
            raise MarketStoreError(f"{name}_negative")
        if value % 60000:
            raise MarketStoreError(f"{name}_unaligned")
    if type(snapshot_server_time_ms) is not int or snapshot_server_time_ms < 0:
        raise MarketStoreError("snapshot_invalid")
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
        funding.append(FundingReplayObservation(ts, r["funding_rate"], mark_by_ts[ts]["open"]))
    return ReplaySlice(inst[0], tr, mk, tuple(funding))
