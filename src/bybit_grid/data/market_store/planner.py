from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from .models import MarketDatasetKind, MarketStoreError
from .writer import _validate_row
from .canonical import row_key


@dataclass(frozen=True)
class PartitionPlanEntry:
    dataset: MarketDatasetKind
    partition_key: tuple
    rows: tuple[dict, ...]


def _month(ms: int):
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.year, dt.month


def partition_validated_rows(kind, rows):
    kind = MarketDatasetKind(kind)
    buckets = {}
    for r0 in rows:
        r = _validate_row(kind, r0)
        if kind is MarketDatasetKind.instrument_snapshot:
            key = (r["snapshot_server_time_ms"],)
        elif kind is MarketDatasetKind.funding_rate:
            key = (r["symbol"],) + _month(r["funding_time_ms"])
        else:
            key = (r["symbol"],) + _month(r["open_time_ms"])
        buckets.setdefault(key, []).append(r)
    entries = []
    for key, rs in sorted(buckets.items(), key=lambda kv: kv[0]):
        if (
            kind is not MarketDatasetKind.instrument_snapshot
            and len({r["symbol"] for r in rs}) != 1
        ):
            raise MarketStoreError("multi_symbol_chunk")
        entries.append(
            PartitionPlanEntry(kind, key, tuple(sorted(rs, key=lambda r: row_key(kind, r))))
        )
    return tuple(entries)


def partition_import_rows(rowsets: dict):
    out = []
    for kind, rows in rowsets.items():
        out.extend(partition_validated_rows(kind, rows))
    return tuple(out)
