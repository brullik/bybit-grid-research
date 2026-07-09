from __future__ import annotations

import argparse
import zipfile

ALLOW = {
    "outcome_report.md",
    "outcome_quality_report.md",
    "outcome_summary.parquet",
    "outcome_quality_summary.parquet",
    "outcome_perf.json",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--outcome-run-id", required=True)
    args = ap.parse_args()
    with zipfile.ZipFile(args.zip) as z:
        names = set(z.namelist())
    bad = names - ALLOW
    missing = ALLOW - names
    if bad or missing:
        raise SystemExit(f"bad={bad} missing={missing}")
    print("review_pack_ok")


if __name__ == "__main__":
    main()
