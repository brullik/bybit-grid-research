from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range-run-id", required=True)
    ap.add_argument("--symbols-limit", type=int, default=10)
    ap.add_argument("--days-limit", type=int, default=30)
    ap.add_argument("--grid-counts", default="5,10,20")
    ap.add_argument("--sl-atr-buffers", default="0,0.5,1.0")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--verify-equivalence", action="store_true")
    args = ap.parse_args()
    results = []
    for core in ["reference", "numpy_fast_v3"]:
        reps = []
        for rep in range(max(1, args.repetitions)):
            run_id = f"benchmark_{core}_{rep}_{int(time.time())}"
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
                core,
                "--executor",
                "auto",
                "--workers",
                "auto",
                "--fast-max",
            ]
            started = time.time()
            proc = subprocess.run(cmd, text=True, capture_output=True)
            runtime = time.time() - started
            perf_path = Path("data/processed/outcome_runs") / run_id / "summary/outcome_perf.json"
            perf = json.loads(perf_path.read_text()) if perf_path.exists() else {}
            reps.append(
                {
                    "core": core,
                    "run_id": run_id,
                    "returncode": proc.returncode,
                    "runtime_seconds": runtime,
                    "compute_seconds": runtime - float(perf.get("write_seconds", 0) or 0),
                    "write_seconds": perf.get("write_seconds"),
                    "rows": perf.get("outcome_rows_total"),
                    "stdout_tail": proc.stdout[-1000:],
                    "stderr_tail": proc.stderr[-1000:],
                }
            )
        reps_sorted = sorted(reps, key=lambda r: r["runtime_seconds"])
        median = reps_sorted[len(reps_sorted) // 2] if reps_sorted else {}
        results.append(
            {
                "core": core,
                "median_runtime_seconds": median.get("runtime_seconds"),
                "median_compute_seconds": median.get("compute_seconds"),
                "repetitions": reps,
            }
        )
    ref = next((r for r in results if r["core"] == "reference"), {})
    fast = next((r for r in results if r["core"] == "numpy_fast_v3"), {})
    speedup = (
        (ref.get("median_runtime_seconds") or 0) / fast["median_runtime_seconds"]
        if fast.get("median_runtime_seconds")
        else None
    )
    compute_speedup = (
        (ref.get("median_compute_seconds") or 0) / fast["median_compute_seconds"]
        if fast.get("median_compute_seconds")
        else None
    )
    summary = {
        "benchmark_ok": all(rep["returncode"] == 0 for r in results for rep in r["repetitions"]),
        "results": results,
        "speedup": speedup,
        "compute_only_speedup": compute_speedup,
    }
    Path("outcome_core_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["benchmark_ok"] else 1)


if __name__ == "__main__":
    main()
