#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bybit_grid.data.public_batch.capture import run_capture_plans
from bybit_grid.data.public_batch.evidence import (
    atomic_write,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    write_status,
)
from bybit_grid.data.public_batch.recording import RecordingPublicClient
from bybit_grid.data.public_batch.reconstruct import (
    artifact_bytes,
    records_from_jsonl,
    reconstruct_from_records,
    validate_run_directory,
)

RUN_ID = "bybit_public_batch_063b_btcusdt_v1"


def _run(args, *, client=None):
    run_dir = Path(args.output_root) / args.run_id
    write_status(run_dir, "building", run_id=args.run_id)
    client = client or RecordingPublicClient()
    run_capture_plans(
        client,
        symbol=args.symbol,
        kline_row_count=args.kline_row_count,
        funding_lookback_days=args.funding_lookback_days,
    )
    raw = canonical_jsonl_bytes(client.records)
    atomic_write(run_dir / "recorded_public_responses.jsonl", raw)
    records = records_from_jsonl((run_dir / "recorded_public_responses.jsonl").read_bytes())
    evidence = reconstruct_from_records(
        records,
        symbol=args.symbol,
        kline_row_count=args.kline_row_count,
        funding_lookback_days=args.funding_lookback_days,
    )
    members = artifact_bytes(evidence, run_id=args.run_id, symbol=args.symbol)
    for name, data in members.items():
        atomic_write(run_dir / name, data)
    validate_run_directory(run_dir, args.run_id)
    complete = {
        "run_id": args.run_id,
        "status": "complete",
        "evidence_validation_ok": True,
        "non_status_artifact_count": 17,
    }
    atomic_write(run_dir / "public_batch_run_status.json", canonical_json_bytes(complete))
    return {"ok": True, "status": "complete", "run_id": args.run_id}


def main(argv=None, *, client=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--kline-row-count", type=int, default=1001)
    parser.add_argument("--funding-lookback-days", type=int, default=100)
    parser.add_argument("--output-root", default="data/processed/public_batch_runs")
    args = parser.parse_args(argv)
    run_dir = Path(args.output_root) / args.run_id
    try:
        out = _run(args, client=client)
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        write_status(
            run_dir,
            "failed",
            run_id=args.run_id,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "failed",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
