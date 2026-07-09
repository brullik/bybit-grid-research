from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.outcome_summary import write_summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", default="latest")
    args = ap.parse_args()
    if args.outcome_run_id == "latest":
        rid = Path("data/processed/outcome_runs/latest_outcome_run.txt").read_text().strip()
    else:
        rid = args.outcome_run_id
    root = Path("data/processed/outcome_runs") / rid
    perf = write_summary(root)
    rep = Path("reports/outcome_runs") / rid
    rep.mkdir(parents=True, exist_ok=True)
    lines = ["# Candidate Outcome Report", ""] + [f"- {k}: {v}" for k, v in perf.items()]
    (rep / "outcome_report.md").write_text("\n".join(lines) + "\n")
    (rep / "outcome_quality_report.md").write_text(
        "# Outcome Quality Report\n\n" + "\n".join(lines[2:]) + "\n"
    )
    print(json.dumps(perf, indent=2, default=str))


if __name__ == "__main__":
    main()
