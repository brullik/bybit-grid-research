from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import polars as pl

PROFILES = ["actionable_density_v2", "actionable_density_v3", "strict_actionable_v2", "actionable_fast_strict"]
TARGETS = {"compression": 10.0, "p50": 50.0, "p90": 100.0, "p99": 200.0, "symbols": 8}


def blockers(row: dict[str, object]) -> list[str]:
    out: list[str] = []
    if not row.get("actionable_event_rows_written"):
        out.append("actionable_event_rows_written=0")
    if (row.get("raw_to_actionable_compression_ratio") or 0) < TARGETS["compression"]:
        out.append(f"compression<{TARGETS['compression']}")
    if (row.get("actionable_events_per_symbol_day_p50") or 0) > TARGETS["p50"]:
        out.append(f"p50>{TARGETS['p50']}")
    if (row.get("actionable_events_per_symbol_day_p90") or 0) > TARGETS["p90"]:
        out.append(f"p90>{TARGETS['p90']}")
    if (row.get("actionable_events_per_symbol_day_p99") or 0) > TARGETS["p99"]:
        out.append(f"p99>{TARGETS['p99']}")
    if (row.get("symbols_with_actionable_events") or 0) < TARGETS["symbols"]:
        out.append(f"symbols_with_actionable_events<{TARGETS['symbols']}")
    if row.get("duplicate_action_event_id_count"):
        out.append("duplicate_action_event_id_count!=0")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-limit", type=int, default=10)
    ap.add_argument("--days-limit", type=int, default=30)
    ap.add_argument("--fast-max", action="store_true")
    ap.add_argument("--run-id", default="auto")
    args = ap.parse_args()
    run_id = args.run_id if args.run_id != "auto" else time.strftime("density_calibration_%Y%m%d_%H%M%S")
    rows: list[dict[str, object]] = []
    for profile in PROFILES:
        child = f"{run_id}_{profile}"
        cmd = [sys.executable, "scripts/build_range_candidates.py", "--symbols-limit", str(args.symbols_limit), "--days-limit", str(args.days_limit), "--profile", profile, "--output-layer", "actionable", "--core", "numpy_fast", "--run-id", child]
        if args.fast_max:
            cmd.append("--fast-max")
        t0 = time.monotonic()
        subprocess.run(cmd, check=True)
        subprocess.run([sys.executable, "scripts/report_range_candidate_density.py", "--run-id", child], check=True)
        dens = pl.read_parquet(Path("data/processed/range_runs") / child / "summary" / "range_density_summary.parquet").to_dicts()[0]
        row = {"profile_name": profile, **dens, "runtime_seconds": float(dens.get("runtime_seconds") or (time.monotonic() - t0))}
        # Prefer perf-json-derived runtime if density report lacks it.
        import json
        perf_json = json.loads((Path("data/processed/range_runs") / child / "summary" / "range_candidate_perf.json").read_text())
        row["runtime_seconds"] = float(perf_json.get("runtime_seconds") or row["runtime_seconds"])
        row["raw_candidate_rows_written"] = int(dens["raw_candidates_total"])
        row["actionable_event_rows_written"] = int(dens["actionable_events_total"])
        row["blockers"] = ",".join(blockers(row))
        row["acceptance_density_status"] = "pass" if not row["blockers"] else "fail"
        rows.append(row)
    out_root = Path("data/processed/range_runs") / run_id / "summary"
    out_root.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows)
    df.write_parquet(out_root / "actionable_density_calibration.parquet")
    passing = df.filter(pl.col("acceptance_density_status") == "pass").sort("runtime_seconds")
    rec = None if passing.is_empty() else passing["profile_name"][0]
    Path("reports").mkdir(exist_ok=True)
    lines = [f"# Actionable Density Calibration {run_id}", "", f"- recommended_profile: {rec or 'NONE'}", "", "## Results"]
    lines += ["- " + " ".join(f"{k}={v}" for k, v in row.items() if k in {"profile_name","acceptance_density_status","blockers","runtime_seconds","raw_to_actionable_compression_ratio","actionable_events_per_symbol_day_p50","actionable_events_per_symbol_day_p90","actionable_events_per_symbol_day_p99","symbols_with_actionable_events"}) for row in rows]
    Path(f"reports/range_density_calibration_{run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"recommended_profile={rec or 'NONE'} run_id={run_id}")
    if rec is None:
        print("blockers " + "; ".join(f"{r['profile_name']}:{r['blockers']}" for r in rows))

if __name__ == "__main__":
    main()
