from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LIMIT_ENV = {
    "POLARS_MAX_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range-run-id", required=True)
    ap.add_argument("--symbols-limit", type=int, default=3)
    ap.add_argument("--days-limit", type=int, default=7)
    ap.add_argument("--grid-counts", default="5,10,20")
    ap.add_argument("--sl-atr-buffers", default="0,0.5,1.0")
    args = ap.parse_args()
    profiles = [("thread", w) for w in ["1", "4", "8", "auto"]] + [
        ("process", w) for w in ["1", "2", "4", "auto"]
    ]
    results = []
    for ex, workers in profiles:
        run_id = f"executor_bench_{ex}_{workers}_{int(time.time())}"
        cmd = [
            sys.executable,
            "scripts/build_candidate_outcomes.py",
            "--range-run-id",
            args.range_run_id,
            "--outcome-run-id",
            run_id,
            "--symbols-limit",
            str(args.symbols_limit),
            "--days-limit",
            str(args.days_limit),
            "--grid-counts",
            args.grid_counts,
            "--sl-atr-buffers",
            args.sl_atr_buffers,
            "--core",
            "numpy_fast_v3",
            "--executor",
            ex,
            "--workers",
            workers,
            "--fast-max",
        ]
        env = os.environ.copy() | LIMIT_ENV
        started = time.time()
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env, check=False)
        runtime = time.time() - started
        results.append(
            {
                "executor": ex,
                "workers": workers,
                "returncode": proc.returncode,
                "runtime_seconds": runtime,
                "stdout_tail": proc.stdout[-500:],
                "stderr_tail": proc.stderr[-500:],
            }
        )
    valid = [r for r in results if r["returncode"] == 0]
    rec = (
        min(valid, key=lambda r: r["runtime_seconds"])
        if valid
        else {"executor": "thread", "workers": "1"}
    )
    summary = {
        "benchmark_ok": bool(valid),
        "results": results,
        "recommendation": {"executor": rec["executor"], "workers": rec["workers"]},
    }
    Path("outcome_executor_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if valid else 1)


if __name__ == "__main__":
    main()
