from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl

from bybit_grid.research.outcome_core.grid_crossings import GRID_LEVELS_SERIALIZATION_VERSION, geometric_grid_levels, levels_json
from bybit_grid.research.outcome_store import read_outcomes, write_partitioned_outcomes
from bybit_grid.research.outcome_summary import write_summary

ALLOWED_CHANGED = {"geometric_grid_levels_json", "grid_levels_serialization_version"}


def repaired_levels(low: float, high: float, n: int) -> str:
    return levels_json(geometric_grid_levels(float(low), float(high), int(n)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-run", required=True)
    ap.add_argument("--target-run", required=True)
    args = ap.parse_args()
    base = Path("data/processed/outcome_runs")
    source = base / args.source_run
    target = base / args.target_run
    if source.resolve() == target.resolve():
        raise SystemExit("source and target must differ")
    df = read_outcomes(source)
    if df.is_empty():
        raise SystemExit("source run has no outcome rows")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    old_serial = df["geometric_grid_levels_json"].to_list() if "geometric_grid_levels_json" in df.columns else []
    repaired = [repaired_levels(r["range_low"], r["range_high"], r["grid_cell_number"]) for r in df.select(["range_low", "range_high", "grid_cell_number"]).iter_rows(named=True)]
    out = df.with_columns(
        pl.Series("geometric_grid_levels_json", repaired),
        pl.lit(GRID_LEVELS_SERIALIZATION_VERSION).alias("grid_levels_serialization_version"),
    )
    write_partitioned_outcomes(out, target / "outcomes")
    perf = write_summary(target)
    audit = subprocess.run([sys.executable, "scripts/audit_outcome_semantics.py", "--outcome-run-id", args.target_run], text=True, capture_output=True)
    semantic_audit_ok = audit.returncode == 0
    src_cmp = df.sort("outcome_id")
    tgt_cmp = read_outcomes(target).sort("outcome_id")
    compare_cols = [c for c in src_cmp.columns if c in tgt_cmp.columns and c not in ALLOWED_CHANGED]
    non_grid_drift = 0
    for c in compare_cols:
        if src_cmp[c].to_list() != tgt_cmp[c].to_list():
            non_grid_drift += 1
    report = {
        "source_run": args.source_run,
        "target_run": args.target_run,
        "rows_compared": df.height,
        "non_grid_drift_count": non_grid_drift,
        "outcome_id_drift_count": int(src_cmp["outcome_id"].to_list() != tgt_cmp["outcome_id"].to_list()),
        "outcome_match_key_drift_count": int(src_cmp["outcome_match_key"].to_list() != tgt_cmp["outcome_match_key"].to_list()),
        "serialization_rows_changed": sum(1 for a, b in zip(old_serial, repaired, strict=False) if a != b),
        "semantic_audit_ok": semantic_audit_ok,
        "outcome_rows_total": perf.get("outcome_rows_total"),
    }
    (target / "summary" / "outcome_grid_serialization_repair_report.json").write_text(json.dumps(report, indent=2) + "\n")
    reports = Path("reports/outcome_runs") / args.target_run
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "outcome_grid_serialization_repair_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, separators=(",", ":")))
    if not semantic_audit_ok or non_grid_drift:
        print(audit.stdout, file=sys.stderr)
        print(audit.stderr, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
