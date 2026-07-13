#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from bybit_grid.data.public_batch.capture import run_capture_plans
from bybit_grid.data.public_batch.evidence import (
    CANONICAL_MEMBERS,
    NON_STATUS_ARTIFACT_COUNT,
    DirectoryEvidenceReader,
    atomic_write,
    build_manifest,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    parse_canonical_json_bytes,
    validate_persisted_public_batch_evidence,
    write_status,
)
from bybit_grid.data.public_batch.models import PublicBatchError
from bybit_grid.data.public_batch.recording import RecordingPublicClient
from bybit_grid.data.public_batch.reconstruct import (
    artifact_bytes,
    build_capture_plan,
    records_from_jsonl,
    reconstruct_from_records,
)

RUN_ID = "bybit_public_batch_063b_btcusdt_v1"


def _validate_args(args):
    if args.run_id != RUN_ID:
        raise PublicBatchError("run_id_not_canonical")
    if args.symbol != "BTCUSDT":
        raise PublicBatchError("symbol_not_canonical")
    if args.kline_row_count != 1001:
        raise PublicBatchError("kline_row_count_not_canonical")
    if args.funding_lookback_days != 100:
        raise PublicBatchError("funding_lookback_days_not_canonical")
    if type(args.timeout_seconds) is not int or not (1 <= args.timeout_seconds <= 120):
        raise PublicBatchError("timeout_seconds_invalid")


def _run(args, *, client=None, fail_at=None):
    _validate_args(args)
    root = Path(args.output_root)
    final_dir = root / args.run_id
    if final_dir.exists():
        raise PublicBatchError("final_run_dir_exists")
    root.mkdir(parents=True, exist_ok=True)
    tmp_dir = root / f".{args.run_id}.building.{os.getpid()}.{uuid.uuid4().hex}"
    tmp_dir.mkdir(mode=0o700)
    try:
        write_status(tmp_dir, "building", run_id=args.run_id)
        plan = build_capture_plan(run_id=args.run_id, symbol=args.symbol, base_url=args.base_url, timeout_seconds=args.timeout_seconds)
        atomic_write(tmp_dir / "capture_plan.json", canonical_json_bytes(plan))
        if fail_at == "early":
            raise PublicBatchError("injected_early_failure")
        client = client or RecordingPublicClient(base_url=args.base_url, timeout_seconds=args.timeout_seconds)
        run_capture_plans(client, symbol=args.symbol, kline_row_count=args.kline_row_count, funding_lookback_days=args.funding_lookback_days)
        raw = canonical_jsonl_bytes(client.records)
        atomic_write(tmp_dir / "recorded_public_responses.jsonl", raw)
        persisted_plan = parse_canonical_json_bytes("capture_plan.json", (tmp_dir / "capture_plan.json").read_bytes())
        records = records_from_jsonl((tmp_dir / "recorded_public_responses.jsonl").read_bytes(), capture_plan=persisted_plan)
        if fail_at == "mid":
            raise PublicBatchError("injected_mid_failure")
        evidence = reconstruct_from_records(records, symbol=args.symbol, kline_row_count=args.kline_row_count, funding_lookback_days=args.funding_lookback_days)
        members = artifact_bytes(evidence, run_id=args.run_id, symbol=args.symbol, base_url=args.base_url, timeout_seconds=args.timeout_seconds)
        for name, data in members.items():
            if name not in {"capture_plan.json", "recorded_public_responses.jsonl"}:
                atomic_write(tmp_dir / name, data)
        complete = {"run_id": args.run_id, "status": "complete", "evidence_validation_ok": True, "non_status_artifact_count": NON_STATUS_ARTIFACT_COUNT}
        atomic_write(tmp_dir / "public_batch_run_status.json", canonical_json_bytes(complete))
        member_bytes = {name: (tmp_dir / name).read_bytes() for name in CANONICAL_MEMBERS if name != "review_pack_manifest.json"}
        atomic_write(tmp_dir / "review_pack_manifest.json", canonical_json_bytes(build_manifest(member_bytes, run_id=args.run_id, symbol=args.symbol)))
        if fail_at == "late":
            raise PublicBatchError("injected_late_failure")
        validate_persisted_public_batch_evidence(DirectoryEvidenceReader(tmp_dir), expected_run_id=args.run_id, require_complete_status=True)
        os.replace(tmp_dir, final_dir)
        return {"ok": True, "status": "complete", "run_id": args.run_id}
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def main(argv=None, *, client=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--kline-row-count", type=int, default=1001)
    parser.add_argument("--funding-lookback-days", type=int, default=100)
    parser.add_argument("--output-root", default="data/processed/public_batch_runs")
    parser.add_argument("--base-url", default="https://api.bybit.com", choices=["https://api.bybit.com", "https://api.bytick.com"])
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        out = _run(args, client=client)
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "failed", "exception_type": type(exc).__name__, "exception_message": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
