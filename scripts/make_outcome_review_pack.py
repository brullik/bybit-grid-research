from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcome-run-id", required=True)
    args = ap.parse_args()
    rid = args.outcome_run_id
    out = Path(f"pm_review_pack_{rid}.zip")
    files = [
        Path("reports/outcome_runs") / rid / "outcome_report.md",
        Path("reports/outcome_runs") / rid / "outcome_quality_report.md",
        Path("data/processed/outcome_runs") / rid / "summary/outcome_summary.parquet",
        Path("data/processed/outcome_runs") / rid / "summary/outcome_quality_summary.parquet",
        Path("data/processed/outcome_runs") / rid / "summary/outcome_perf.json",
    ]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for file in files:
            if file.exists():
                z.write(file, file.name)
    print(out)


if __name__ == "__main__":
    main()
