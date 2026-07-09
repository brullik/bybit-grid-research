from __future__ import annotations

import argparse
import json
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
        if bad or missing or any("outcomes.parquet" in n for n in names):
            raise SystemExit(f"bad={bad} missing={missing}")
        perf = json.loads(z.read("outcome_perf.json").decode("utf-8"))
    if perf.get("outcome_rows_total", 0) <= 0:
        raise SystemExit("outcome_rows_total must be > 0")
    if perf.get("unique_outcome_id_count") != perf.get("outcome_rows_total"):
        raise SystemExit("duplicate outcome_id rows detected")
    if perf.get("duplicate_range_action_event_horizon_grid_sl_rows") != 0:
        raise SystemExit("duplicate composite outcome rows detected")
    required = ["funding_files_found_count", "funding_rows_joined_total", "funding_source_status_counts"]
    missing_diag = [k for k in required if k not in perf]
    if missing_diag:
        raise SystemExit(f"missing funding diagnostics: {missing_diag}")
    if perf.get("funding_rows_total", 0) == 0 and perf.get("funding_files_found_count", 0) > 0 and not perf.get("funding_zero_reason"):
        raise SystemExit("funding rows are zero despite files found without explicit reason")
    print(json.dumps({"review_pack_ok": True, "outcome_run_id": args.outcome_run_id}, separators=(",", ":")))


if __name__ == "__main__":
    main()
