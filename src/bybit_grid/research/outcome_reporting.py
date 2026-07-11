from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from bybit_grid.research.outcome_summary import write_summary


def generate_outcome_reports(outcome_run_id: str) -> dict:
    root = Path("data/processed/outcome_runs") / outcome_run_id
    perf = write_summary(root)
    rep = Path("reports/outcome_runs") / outcome_run_id
    rep.mkdir(parents=True, exist_ok=True)
    lines = ["# Candidate Outcome Report", ""] + [f"- {k}: {v}" for k, v in perf.items()]
    (rep / "outcome_report.md").write_text("\n".join(lines) + "\n")
    (rep / "outcome_quality_report.md").write_text(
        "# Outcome Quality Report\n\n" + "\n".join(lines[2:]) + "\n"
    )
    return perf


def generate_outcome_semantic_audit(outcome_run_id: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_outcome_semantics.py", "--outcome-run-id", outcome_run_id],
        text=True,
        capture_output=True,
        check=False,
    )
    audit_path = (
        Path("data/processed/outcome_runs") / outcome_run_id / "summary/outcome_semantic_audit.json"
    )
    if audit_path.exists():
        result = json.loads(audit_path.read_text())
    else:
        result = {"semantic_audit_ok": False, "stdout": proc.stdout, "stderr": proc.stderr}
    if proc.returncode != 0:
        raise RuntimeError(
            f"semantic audit failed for {outcome_run_id}: {proc.stdout}{proc.stderr}"
        )
    return result
