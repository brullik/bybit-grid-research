from __future__ import annotations
import hashlib
from pathlib import Path
from .models import StoreFileInventoryEntry, MarketStoreError


def snapshot_tree(root: Path) -> tuple[StoreFileInventoryEntry, ...]:
    root = Path(root)
    if not root.exists():
        return ()
    out=[]
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root).as_posix()
        st=p.lstat()
        if p.is_symlink():
            raise MarketStoreError(f"unsafe_store_entry:{rel}")
        if p.is_dir():
            out.append(StoreFileInventoryEntry(rel,'directory',0,None,st.st_mtime_ns))
        elif p.is_file():
            out.append(StoreFileInventoryEntry(rel,'file',st.st_size,hashlib.sha256(p.read_bytes()).hexdigest(),st.st_mtime_ns))
        else:
            raise MarketStoreError(f"unsafe_store_entry:{rel}")
    return tuple(out)
