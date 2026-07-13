#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

from bybit_grid.data.public_batch.evidence import (
    CANONICAL_MEMBERS,
    build_manifest,
    canonical_json_bytes,
    read_json,
    validate_review_pack,
)
from bybit_grid.data.public_batch.reconstruct import validate_run_directory


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--input-root", default="data/processed/public_batch_runs")
    args = parser.parse_args(argv)
    tmp = None
    try:
        run_dir = Path(args.input_root) / args.run_id
        validate_run_directory(run_dir, args.run_id)
        status = read_json(run_dir / "public_batch_run_status.json")
        if status.get("status") != "complete":
            raise ValueError("run_not_complete")
        member_bytes = {}
        for name in CANONICAL_MEMBERS:
            if name != "review_pack_manifest.json":
                member_bytes[name] = (run_dir / name).read_bytes()
        summary = read_json(run_dir / "capture_summary.json")
        manifest = canonical_json_bytes(
            build_manifest(
                member_bytes, run_id=args.run_id, symbol=summary.get("symbol", "BTCUSDT")
            )
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(args.output).with_suffix(Path(args.output).suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in CANONICAL_MEMBERS:
                zf.writestr(
                    name, manifest if name == "review_pack_manifest.json" else member_bytes[name]
                )
        validate_review_pack(tmp, args.run_id)
        os.replace(tmp, args.output)
        print(
            json.dumps({"ok": True, "output": args.output}, sort_keys=True, separators=(",", ":"))
        )
        return 0
    except Exception as exc:
        if tmp is not None and tmp.exists():
            tmp.unlink()
        print(
            json.dumps(
                {"ok": False, "exception_type": type(exc).__name__, "exception_message": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
