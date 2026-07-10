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
    args = ap.parse_args()
    results = []
    for core in ["reference", "numpy_fast_v2"]:
        run_id = f"benchmark_{core}_{int(time.time())}"
        cmd = [
            sys.executable,
            "scripts/build_candidate_outcomes.py",
            "--range-run-id", args.range_run_id,
            "--outcome-run-id", run_id,
            "--symbols-limit", str(args.symbols_limit),
            "--days-limit", str(args.days_limit),
            "--grid-counts", args.grid_counts,
            "--sl-atr-buffers", args.sl_atr_buffers,
            "--core", core,
            "--executor", "auto",
            "--workers", "auto",
            "--fast-max",
        ]
        started = time.time()
        proc = subprocess.run(cmd, text=True, capture_output=True)
        runtime = time.time() - started
        perf_path = Path("data/processed/outcome_runs") / run_id / "summary/outcome_perf.json"
        perf = json.loads(perf_path.read_text()) if perf_path.exists() else {}
        results.append({"core": core, "run_id": run_id, "returncode": proc.returncode, "runtime_seconds": runtime, "rows": perf.get("outcome_rows_total"), "stdout_tail": proc.stdout[-1000:], "stderr_tail": proc.stderr[-1000:]})
    ref = next((r for r in results if r["core"] == "reference"), {})
    fast = next((r for r in results if r["core"] == "numpy_fast_v2"), {})
    speedup = (ref.get("runtime_seconds") or 0) / fast["runtime_seconds"] if fast.get("runtime_seconds") else None
    summary = {"benchmark_ok": all(r["returncode"] == 0 for r in results), "results": results, "speedup": speedup}
    Path("outcome_core_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["benchmark_ok"] else 1)


if __name__ == "__main__":
    main()
