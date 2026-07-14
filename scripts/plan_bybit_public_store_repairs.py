#!/usr/bin/env python
from __future__ import annotations
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from pathlib import Path
from bybit_grid.data.market_store.coverage import (
    scan_minute_coverage,
    plan_missing_minute_windows,
)
from bybit_grid.data.market_store.reader import read_dataset
from bybit_grid.data.market_store.models import MarketDatasetKind
from bybit_grid.common.strict_cli import emit, fail, StrictArgumentParser


def main():
    ap = StrictArgumentParser()
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start-ms", required=True, type=int)
    ap.add_argument("--end-ms", required=True, type=int)
    ap.add_argument(
        "--dataset",
        choices=["trade_kline_1m", "mark_kline_1m"],
        default="trade_kline_1m",
    )
    ap.add_argument("--debug", action="store_true")
    ns = ap.parse_args()
    try:
        if not Path(ns.store_root).exists():
            raise FileNotFoundError("store_root_missing")
        rows = read_dataset(
            ns.store_root,
            MarketDatasetKind(ns.dataset),
            symbol=ns.symbol,
            start_ms=ns.start_ms,
            end_ms=ns.end_ms,
        )
        audit = scan_minute_coverage(
            ns.symbol, ns.start_ms, ns.end_ms, [r["open_time_ms"] for r in rows]
        )
        emit(
            {
                "audit": audit,
                "ok": True,
                "repair_windows": plan_missing_minute_windows(audit),
            }
        )
        return 0
    except Exception as e:
        return fail(e, ns.debug)


if __name__ == "__main__":
    sys.exit(main())
