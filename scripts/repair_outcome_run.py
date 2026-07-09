from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_store import dedupe_outcomes
from bybit_grid.research.outcome_summary import write_summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", required=True)
    ap.add_argument("--dedupe", action="store_true")
    ap.add_argument("--rebuild-summary", action="store_true")
    args = ap.parse_args()
    root = Path("data/processed/outcome_runs") / args.outcome_run_id
    files = sorted((root / "outcomes").glob("**/outcomes.parquet"))
    rows_before = rows_after = duplicates_removed = 0
    touched = 0
    for path in files:
        df = pl.read_parquet(path)
        before = df.height
        clean = dedupe_outcomes(df) if args.dedupe else df
        after = clean.height
        rows_before += before
        rows_after += after
        duplicates_removed += before - after
        if args.dedupe and after != before:
            clean.write_parquet(path)
            touched += 1
    perf = write_summary(root) if args.rebuild_summary else {}
    report = {
        "outcome_run_id": args.outcome_run_id,
        "partitions_scanned": len(files),
        "partitions_rewritten": touched,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "duplicates_removed": duplicates_removed,
        "summary_rebuilt": bool(args.rebuild_summary),
        "perf": perf,
    }
    rep = Path("reports/outcome_runs") / args.outcome_run_id
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "outcome_repair_report.md").write_text(
        "# Outcome Repair Report\n\n```json\n" + json.dumps(report, indent=2, default=str) + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
