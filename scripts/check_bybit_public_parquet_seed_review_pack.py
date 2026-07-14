#!/usr/bin/env python
from __future__ import annotations
import argparse
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from pathlib import Path
from bybit_grid.data.market_store.evidence import check_seed_review_pack
from _cli_common import emit, fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-pack", required=True)
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    try:
        if not Path(ns.review_pack).exists():
            raise FileNotFoundError("review_pack_missing")
        emit(check_seed_review_pack(ns.review_pack))
        return 0
    except Exception as e:
        return fail(e, ns.debug)


if __name__ == "__main__":
    sys.exit(main())
