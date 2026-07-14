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


def _strict_nonnegative_ms(v, name, *, minute=False):
    if type(v) is not int or v < 0:
        raise MarketStoreError(f"{name}_invalid")
    if minute and v % 60000:
        raise MarketStoreError(f"{name}_unaligned")
    return v


def _safe_hash(h):
    if type(h) is not str or not re.fullmatch(r"[0-9a-f]{64}", h):
        raise MarketStoreError("logical_sha256_invalid")
    return h


def rel_chunk_path(
    kind, *, symbol=None, snapshot_server_time_ms=None, min_ms=None, max_ms=None, logical_hash=""
):
    kind = MarketDatasetKind(kind)
    pref = _safe_hash(logical_hash)[:16]
    if kind is MarketDatasetKind.instrument_snapshot:
        snap = _strict_nonnegative_ms(snapshot_server_time_ms, "snapshot_server_time_ms")
        return (
            Path("datasets")
            / kind.value
            / f"snapshot_server_time_ms={snap}"
            / f"chunk={pref}"
        )
    safe_symbol(symbol)
    lo = _strict_nonnegative_ms(min_ms, "min_ms", minute=True)
    hi = _strict_nonnegative_ms(max_ms, "max_ms", minute=True)
    if lo > hi:
        raise MarketStoreError("min_max_invalid")
    dt = datetime.fromtimestamp(lo / 1000, tz=timezone.utc)
    dt2 = datetime.fromtimestamp(hi / 1000, tz=timezone.utc)
    if (dt.year, dt.month) != (dt2.year, dt2.month):
        raise MarketStoreError("chunk_crosses_utc_month")
    return (
        Path("datasets")
        / kind.value
        / f"symbol={symbol}"
        / f"year={dt.year:04d}"
        / f"month={dt.month:02d}"
        / f"chunk={lo}-{hi}-{pref}"
    )


def receipt_rel(run_id, sha):
    return Path("imports") / f"run_id={run_id}" / f"source_sha256={sha}" / "import_receipt.json"


def evidence_rel(sha):
    return Path("evidence") / f"sha256={sha}"


def ensure_safe_store_path(root, p):
    p = Path(p)
    if p.is_symlink() or (p.exists() and not (p.is_dir() or p.is_file())):
        raise MarketStoreError("unsafe_store_entry")
