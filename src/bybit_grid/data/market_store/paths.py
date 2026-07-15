from __future__ import annotations
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat
from .models import MarketDatasetKind, MarketStoreError

SYM = re.compile(r"[A-Z0-9]{2,32}")
_MAX_INT64 = (1 << 63) - 1


def _safe_dataset_kind(value):
    if type(value) is MarketDatasetKind:
        return value
    if type(value) is not str:
        raise MarketStoreError("dataset_invalid")
    try:
        return MarketDatasetKind(value)
    except (TypeError, ValueError) as exc:
        raise MarketStoreError("dataset_invalid") from exc


def safe_symbol(s):
    if type(s) is not str or SYM.fullmatch(s) is None:
        raise MarketStoreError("unsafe_symbol")
    return s


def _strict_nonnegative_ms(v, name, *, minute=False):
    if type(v) is not int or v < 0 or v > _MAX_INT64:
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
    kind = _safe_dataset_kind(kind)
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
    try:
        dt = datetime.fromtimestamp(lo / 1000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise MarketStoreError("min_ms_invalid") from exc
    try:
        dt2 = datetime.fromtimestamp(hi / 1000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise MarketStoreError("max_ms_invalid") from exc
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


def safe_posix_relative_text(value, name="relative_path"):
    has_control = type(value) is str and any(
        ord(char) < 32
        or 127 <= ord(char) <= 159
        or 0xD800 <= ord(char) <= 0xDFFF
        for char in value
    )
    if (
        type(value) is not str
        or not value
        or value.startswith("/")
        or "\\" in value
        or ":" in value
        or has_control
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise MarketStoreError(f"{name}_invalid")
    return value


def _absolute_lexical_path(value):
    try:
        return Path(os.path.abspath(os.fspath(value)))
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("unsafe_store_entry") from exc


def ensure_safe_store_path(root, p):
    root_abs = _absolute_lexical_path(root)
    path_abs = _absolute_lexical_path(p)
    if path_abs != root_abs and root_abs not in path_abs.parents:
        raise MarketStoreError("unsafe_store_entry")

    paths = [root_abs]
    current = root_abs
    for part in path_abs.relative_to(root_abs).parts:
        current /= part
        paths.append(current)

    seen = set()
    for entry in paths:
        if entry in seen:
            continue
        seen.add(entry)
        try:
            mode = entry.lstat().st_mode
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise MarketStoreError("unsafe_store_entry") from exc
        if stat.S_ISLNK(mode):
            raise MarketStoreError("unsafe_store_entry")
        is_final = entry == path_abs
        if not stat.S_ISDIR(mode) and not (is_final and stat.S_ISREG(mode)):
            raise MarketStoreError("unsafe_store_entry")
    if path_abs == root_abs:
        try:
            if root_abs.exists() and not root_abs.is_dir():
                raise MarketStoreError("unsafe_store_entry")
        except (OSError, ValueError) as exc:
            raise MarketStoreError("unsafe_store_entry") from exc
