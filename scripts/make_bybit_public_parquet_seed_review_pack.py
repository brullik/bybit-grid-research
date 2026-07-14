#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from pathlib import Path
from bybit_grid.data.market_store.evidence import make_seed_review_pack
from bybit_grid.common.strict_cli import emit, fail, StrictArgumentParser


def main():
    ap = StrictArgumentParser()
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    try:
        if not Path(ns.store_root).exists():
            raise FileNotFoundError("store_root_missing")
        out = make_seed_review_pack(ns.store_root, ns.output)
        emit({"ok": True, "review_pack": str(out)})
        return 0
    except Exception as e:
        return fail(e, ns.debug)


if __name__ == "__main__":
    sys.exit(main())
