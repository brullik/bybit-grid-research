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
    for p in root.rglob("*"):
        if p.is_symlink():
            failures.append(f"unsafe_symlink:{p.relative_to(root).as_posix()}")
    for d in (root / "datasets").glob("**/chunk=*") if (root / "datasets").exists() else []:
        chunks += 1
        try:
            _read_chunk(d, d.parts[d.parts.index("datasets") + 1])
        except Exception as e:
            failures.append(str(e))
    return MarketStoreAudit(not failures, tuple(failures), chunks, receipts)
