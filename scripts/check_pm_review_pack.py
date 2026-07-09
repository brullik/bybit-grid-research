from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile

BANNED_PARTS = ["data/raw/", "/raw_candidates/", "/event_candidates/", "/range_regimes/", "/actionable_events/", "reports/runs/", "__pycache__/", ".pytest_cache/", ".ruff_cache/"]
GLOBAL_REPORT_PREFIXES = ("reports/sprint_",)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    names = ZipFile(args.zip).namelist()
    run_prefix = f"reports/range_runs/{args.run_id}/"
    required = {run_prefix + "range_candidate_report.md", run_prefix + "range_candidate_density_report.md"}
    missing = sorted(required - set(names))
    banned = [n for n in names if any(part in n for part in BANNED_PARTS) or n == ".env" or "/.env" in n]
    globals_ = [n for n in names if n.startswith(GLOBAL_REPORT_PREFIXES)]
    if missing or banned or globals_:
        raise SystemExit(f"pm review pack check failed missing={missing} banned={banned} stale_global_reports={globals_}")
    print(f"pm review pack ok zip={Path(args.zip).name} files={len(names)}")

if __name__ == "__main__":
    main()
