from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def allowed(path: Path, run_id: str) -> bool:
    s = path.as_posix()
    banned = [
        "data/raw/",
        f"data/processed/range_runs/{run_id}/raw_candidates/",
        f"data/processed/range_runs/{run_id}/event_candidates/",
        f"data/processed/range_runs/{run_id}/range_regimes/",
        f"data/processed/range_runs/{run_id}/actionable_events/",
        ".env",
        "reports/runs/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
    ]
    return not any(b in s for b in banned) and not s.endswith(".pyc")


def _run_report(script: str, run_id: str) -> None:
    subprocess.run([sys.executable, script, "--run-id", run_id], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    run_id = args.run_id
    # Regenerate run-isolated markdown reports so the pack never falls back to stale globals.
    _run_report("scripts/report_range_candidates.py", run_id)
    _run_report("scripts/report_range_candidate_density.py", run_id)

    out = Path(f"pm_review_pack_{run_id}.zip")
    members: list[Path] = []
    report_dir = Path("reports/range_runs") / run_id
    for name in ["range_candidate_report.md", "range_candidate_density_report.md", "profile_summary.md"]:
        p = report_dir / name
        if p.exists():
            members.append(p)
    summary = Path("data/processed/range_runs") / run_id / "summary"
    for name in [
        "range_candidate_perf.json",
        "range_candidate_summary.parquet",
        "range_density_summary.parquet",
        "range_rejection_summary.parquet",
        "actionable_density_calibration.parquet",
    ]:
        p = summary / name
        if p.exists():
            members.append(p)
    with ZipFile(out, "w", ZIP_DEFLATED) as zf:
        for p in members:
            if p.is_file() and allowed(p, run_id):
                zf.write(p, p.as_posix())
    print(f"created {out} files={len(ZipFile(out).namelist())}")

if __name__ == "__main__":
    main()
