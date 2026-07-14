#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from dataclasses import asdict
from pathlib import Path
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.common.strict_cli import emit, fail, StrictArgumentParser


def main():
    ap = StrictArgumentParser()
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    try:
        if not Path(ns.store_root).exists():
            raise FileNotFoundError("store_root_missing")
        a = audit_market_store(ns.store_root)
        emit({"audit": asdict(a), "ok": a.ok})
        return 0 if a.ok else 1
    except Exception as e:
        return fail(e, ns.debug)


if __name__ == "__main__":
    sys.exit(main())
