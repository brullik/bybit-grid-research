from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from enum import Enum
from .models import MarketStoreError, MarketDatasetKind

PK = {
    MarketDatasetKind.instrument_snapshot: ("snapshot_server_time_ms", "symbol"),
    MarketDatasetKind.trade_kline_1m: ("symbol", "open_time_ms"),
    MarketDatasetKind.mark_kline_1m: ("symbol", "open_time_ms"),
    MarketDatasetKind.funding_rate: ("symbol", "funding_time_ms"),
}


def decimal_to_text(d: Decimal) -> str:
    if type(d) is not Decimal or not d.is_finite():
        raise MarketStoreError("decimal_invalid")
    if d == 0:
        return "0"
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def plain(v):
    if v is None or type(v) is str:
        if v == "":
            raise MarketStoreError("empty_string")
        return v
    if type(v) is bool:
        return v
    if type(v) is int:
        return v
    if type(v) is float:
        raise MarketStoreError("type_forbidden")
    if isinstance(v, Decimal):
        return decimal_to_text(v)
    if isinstance(v, Enum):
        return v.value
    if is_dataclass(v):
        return plain(asdict(v))
    if isinstance(v, dict):
        out = {}
        for k in sorted(v):
            if type(k) is not str or not k:
                raise MarketStoreError("mapping_key_invalid")
            out[k] = plain(v[k])
        return out
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (bytes, bytearray, set, frozenset, Path)):
        raise MarketStoreError("type_forbidden")
    raise MarketStoreError(f"type_unknown:{type(v).__name__}")


def row_key(kind, row):
    d = asdict(row) if is_dataclass(row) else dict(row)
    return tuple(d[k] for k in PK[MarketDatasetKind(kind)])


def canonical_jsonl_bytes(kind, rows) -> bytes:
    kind = MarketDatasetKind(kind)
    out = []
    for r in sorted(rows, key=lambda x: row_key(kind, x)):
        d = asdict(r) if is_dataclass(r) else dict(r)
        out.append(
            json.dumps(
                plain(d), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
        )
    return ("\n".join(out) + "\n").encode() if out else b""


def logical_rows_sha256(kind, rows):
    return hashlib.sha256(canonical_jsonl_bytes(kind, rows)).hexdigest()


def canonical_json_bytes(obj) -> bytes:
    return (
        json.dumps(
            plain(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
        + b"\n"
    )
