from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import re
from .models import MarketDatasetKind, MarketStoreError

SYM = re.compile(r"^[A-Z0-9]{2,32}$")


def safe_symbol(s):
    if type(s) is not str or not SYM.match(s):
        raise MarketStoreError("unsafe_symbol")
    return s


def rel_chunk_path(
    kind, *, symbol=None, snapshot_server_time_ms=None, min_ms=None, max_ms=None, logical_hash=""
):
    kind = MarketDatasetKind(kind)
    pref = logical_hash[:16]
    if kind is MarketDatasetKind.instrument_snapshot:
        return (
            Path("datasets")
            / kind.value
            / f"snapshot_server_time_ms={int(snapshot_server_time_ms)}"
            / f"chunk={pref}"
        )
    safe_symbol(symbol)
    dt = datetime.fromtimestamp(int(min_ms) / 1000, tz=timezone.utc)
    return (
        Path("datasets")
        / kind.value
        / f"symbol={symbol}"
        / f"year={dt.year:04d}"
        / f"month={dt.month:02d}"
        / f"chunk={int(min_ms)}-{int(max_ms)}-{pref}"
    )


def receipt_rel(run_id, sha):
    return Path("imports") / f"run_id={run_id}" / f"source_sha256={sha}" / "import_receipt.json"


def evidence_rel(sha):
    return Path("evidence") / f"sha256={sha}"


def ensure_safe_store_path(root, p):
    p = Path(p)
    if p.is_symlink() or (p.exists() and not (p.is_dir() or p.is_file())):
        raise MarketStoreError("unsafe_store_entry")
