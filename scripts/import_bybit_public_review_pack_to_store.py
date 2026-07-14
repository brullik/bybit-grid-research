#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from pathlib import Path
from bybit_grid.data.market_store.import_public_batch import (
    load_validated_public_replay_batch_from_review_pack,
    import_validated_public_batch_to_store,
)
from bybit_grid.common.strict_cli import emit, fail, StrictArgumentParser


def main():
    ap = StrictArgumentParser()
    ap.add_argument("--review-pack", required=True)
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--expected-run-id", required=True)
    ap.add_argument("--expected-sha256")
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    try:
        if not Path(ns.review_pack).exists():
            raise FileNotFoundError("review_pack_missing")
        ev = load_validated_public_replay_batch_from_review_pack(
            Path(ns.review_pack),
            expected_run_id=ns.expected_run_id,
            expected_sha256=ns.expected_sha256,
        )
        rec = import_validated_public_batch_to_store(ev, ns.store_root)
        emit({"ok": True, "receipt": rec})
        return 0
    except Exception as e:
        return fail(e, ns.debug)


if __name__ == "__main__":
    sys.exit(main())
