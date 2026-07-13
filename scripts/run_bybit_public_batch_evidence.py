#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bybit_grid.data.public_batch.evidence import GUARDRAILS, atomic_write, canonical_json_bytes, write_status
from bybit_grid.data.public_batch.models import PublicBatchError

RUN_ID = "bybit_public_batch_063b_btcusdt_v1"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--kline-row-count", type=int, default=1001)
    parser.add_argument("--funding-lookback-days", type=int, default=100)
    parser.add_argument("--output-root", default="data/processed/public_batch_runs")
    parser.add_argument("--no-network-fixture-mode", action="store_true", help="test-only lifecycle mode")
    args = parser.parse_args(argv)
    run_dir = Path(args.output_root) / args.run_id
    try:
        write_status(run_dir, "building", run_id=args.run_id)
        if not args.no_network_fixture_mode:
            raise PublicBatchError("owner_network_capture_not_run_by_codex")
        summary = {"run_id": args.run_id, "symbol": args.symbol, "kline_row_count": args.kline_row_count, **GUARDRAILS}
        atomic_write(run_dir / "capture_summary.json", canonical_json_bytes(summary))
        write_status(run_dir, "complete", run_id=args.run_id)
        print(json.dumps({"ok": True, "status": "complete", "run_id": args.run_id}, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        write_status(
            run_dir,
            "failed",
            run_id=args.run_id,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        print(json.dumps({"ok": False, "status": "failed", "exception_type": type(exc).__name__, "exception_message": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
