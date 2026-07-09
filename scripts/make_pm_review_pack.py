from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPORTS = [
    "reports/sprint_03_3_profile_summary.md",
    "reports/sprint_03_3_core_benchmark.md",
    "reports/sprint_03_range_candidate_report.md",
    "reports/sprint_03_1_range_event_calibration_report.md",
    "reports/sprint_03_2_density_report.md",
    "reports/sprint_03_3_fast_core_report.md",
]


def allowed(path: Path, run_id: str) -> bool:
    s = path.as_posix()
    if s.startswith(".env") or "/.env" in s:
        return False
    banned = ["data/raw/", f"data/processed/range_runs/{run_id}/raw_candidates/", f"data/processed/range_runs/{run_id}/range_regimes/", f"data/processed/range_runs/{run_id}/actionable_events/", "reports/runs/", "__pycache__/", ".pytest_cache/", ".ruff_cache/"]
    return not any(b in s for b in banned) and not s.endswith(".pyc")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    run_id = args.run_id
    out = Path(f"pm_review_pack_{run_id}.zip")
    members: list[Path] = [Path(r) for r in REPORTS if Path(r).exists()]
    summary = Path("data/processed/range_runs") / run_id / "summary"
    if summary.exists():
        members.extend(sorted(summary.glob("*.json")))
        members.extend(sorted(summary.glob("*.parquet")))
    with ZipFile(out, "w", ZIP_DEFLATED) as zf:
        for p in members:
            if p.is_file() and allowed(p, run_id):
                zf.write(p, p.as_posix())
    print(f"created {out} files={len(ZipFile(out).namelist())}")

if __name__ == "__main__":
    main()
