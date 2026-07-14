from __future__ import annotations
from pathlib import Path
from .models import MarketStoreAudit
from .reader import _read_chunk


def audit_market_store(root):
    root = Path(root)
    failures = []
    chunks = 0
    receipts = (
        len(list((root / "imports").glob("**/import_receipt.json")))
        if (root / "imports").exists()
        else 0
    )
    if not root.exists():
        failures.append("store_root_missing")
    missing_version = not (root / "store_version.json").exists()
    allowed = {"store_version.json", "datasets", "imports", "evidence", ".building"}
    for p in root.iterdir() if root.exists() else []:
        if p.name not in allowed:
            failures.append(f"unexpected_root_entry:{p.name}")
        if p.is_symlink():
            failures.append(f"unsafe_symlink:{p.relative_to(root).as_posix()}")
        if p.name == ".building" and any(p.iterdir()):
            failures.append("stale_building_entry")
    for p in root.rglob("*") if root.exists() else []:
        if p.is_symlink():
            failures.append(f"unsafe_symlink:{p.relative_to(root).as_posix()}")
    for d in (root / "datasets").glob("**/chunk=*") if (root / "datasets").exists() else []:
        chunks += 1
        try:
            _read_chunk(d, d.parts[d.parts.index("datasets") + 1])
        except Exception as e:
            failures.append(str(e))
    if chunks == 0:
        failures.append("no_committed_chunks")
        if missing_version:
            failures.append("store_version_missing")
    if receipts == 0 and chunks == 0:
        failures.append("no_import_receipts")
    return MarketStoreAudit(not failures, tuple(failures), chunks, receipts)
