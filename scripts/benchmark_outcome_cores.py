from __future__ import annotations
import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.outcome_store import read_outcomes

EXCLUDED = {"outcome_run_id", "created_at", "created_at_utc"}


def median_rep(reps):
    ok = [r for r in reps if r["returncode"] == 0]
    arr = ok or reps
    return sorted(arr, key=lambda r: r["runtime_seconds"])[len(arr) // 2] if arr else {}


def compare_runs(ref_id, fast_id):
    ref = read_outcomes(Path("data/processed/outcome_runs") / ref_id)
    fast = read_outcomes(Path("data/processed/outcome_runs") / fast_id)
    report = {
        "equivalence_ok": False,
        "reference_run_id": ref_id,
        "fast_run_id": fast_id,
        "reference_rows": ref.height,
        "fast_rows": fast.height,
        "joined_rows": 0,
        "missing_in_reference": 0,
        "missing_in_fast": 0,
        "columns_compared": [],
        "columns_excluded": [],
        "mismatch_count_total": 0,
        "mismatch_count_by_column": {},
        "first_mismatches": [],
    }
    if (
        "outcome_match_key" not in ref.columns
        or "outcome_match_key" not in fast.columns
    ):
        return report
    rkeys = set(ref["outcome_match_key"].to_list())
    fkeys = set(fast["outcome_match_key"].to_list())
    report["missing_in_reference"] = len(fkeys - rkeys)
    report["missing_in_fast"] = len(rkeys - fkeys)
    common = sorted(
        (set(ref.columns) & set(fast.columns)) - EXCLUDED - {"outcome_match_key"}
    )
    excluded = sorted(
        (set(ref.columns) | set(fast.columns)) - set(common) - {"outcome_match_key"}
    )
    report["columns_compared"] = common
    report["columns_excluded"] = excluded
    joined = ref.join(fast, on="outcome_match_key", how="inner", suffix="__fast")
    report["joined_rows"] = joined.height
    mism = {}
    first = []
    for c in common:
        a = joined[c].to_list()
        b = joined[f"{c}__fast"].to_list()
        cnt = 0
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            ok = x is None and y is None
            if not ok and x is not None and y is not None:
                if isinstance(x, float) or isinstance(y, float):
                    try:
                        ok = math.isclose(
                            float(x), float(y), rel_tol=1e-10, abs_tol=1e-12
                        ) or (math.isnan(float(x)) and math.isnan(float(y)))
                    except Exception:
                        ok = False
                else:
                    ok = x == y
            if not ok:
                cnt += 1
                if len(first) < 20:
                    first.append(
                        {
                            "outcome_match_key": joined["outcome_match_key"][i],
                            "column": c,
                            "reference": x,
                            "fast": y,
                        }
                    )
        if cnt:
            mism[c] = cnt
    report["mismatch_count_by_column"] = mism
    report["mismatch_count_total"] = sum(mism.values())
    report["first_mismatches"] = first
    report["equivalence_ok"] = (
        report["missing_in_reference"] == 0
        and report["missing_in_fast"] == 0
        and report["mismatch_count_total"] == 0
        and report["reference_rows"] == report["fast_rows"] == report["joined_rows"]
    )
    return report


def main():
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
            st = time.time()
            proc = subprocess.run(cmd, text=True, capture_output=True)
            runtime = time.time() - st
            perf_path = (
                Path("data/processed/outcome_runs")
                / run_id
                / "summary/outcome_perf.json"
            )
            perf = json.loads(perf_path.read_text()) if perf_path.exists() else {}
            reps.append(
                {
                    "core": core,
                    "run_id": run_id,
                    "returncode": proc.returncode,
                    "runtime_seconds": runtime,
                    "compute_seconds": runtime
                    - float(
                        perf.get("write_wall_seconds", perf.get("write_seconds", 0))
                        or 0
                    ),
                    "write_wall_seconds": perf.get(
                        "write_wall_seconds", perf.get("write_seconds")
                    ),
                    "rows": perf.get("outcome_rows_total"),
                    "stdout_tail": proc.stdout[-1000:],
                    "stderr_tail": proc.stderr[-1000:],
                }
            )
        m = median_rep(reps)
        results.append(
            {
                "core": core,
                "median_runtime_seconds": m.get("runtime_seconds"),
                "median_compute_seconds": m.get("compute_seconds"),
                "median_run_id": m.get("run_id"),
                "repetitions": reps,
            }
        )
    ref = next(r for r in results if r["core"] == "reference")
    fast = next(r for r in results if r["core"] == "numpy_fast_v3")
    summary = {
        "benchmark_ok": all(
            rep["returncode"] == 0 for r in results for rep in r["repetitions"]
        ),
        "results": results,
        "speedup": (
            (ref.get("median_runtime_seconds") or 0) / fast["median_runtime_seconds"]
            if fast.get("median_runtime_seconds")
            else None
        ),
        "compute_only_speedup": (
            (ref.get("median_compute_seconds") or 0) / fast["median_compute_seconds"]
            if fast.get("median_compute_seconds")
            else None
        ),
    }
    if args.verify_equivalence:
        eq = compare_runs(ref.get("median_run_id"), fast.get("median_run_id"))
        Path("outcome_core_equivalence_report.json").write_text(
            json.dumps(eq, indent=2, default=str) + "\n"
        )
        summary["equivalence_report"] = "outcome_core_equivalence_report.json"
        summary["equivalence_ok"] = eq["equivalence_ok"]
        summary["benchmark_ok"] = summary["benchmark_ok"] and eq["equivalence_ok"]
    Path("outcome_core_benchmark_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n"
    )
    print(json.dumps(summary, indent=2, default=str))
    raise SystemExit(0 if summary["benchmark_ok"] else 1)


if __name__ == "__main__":
    main()
