from __future__ import annotations
import argparse
import json
import zipfile
import shutil
from pathlib import Path

REQUIRED = [
    "review_pack_manifest.json",
    "fee_snapshot_report.md",
    "fee_coverage_audit.json",
    "cost_model_config_resolved.yml",
    "cost_model_audit.json",
    "outcome_source_audit.json",
    "outcome_grain_audit.json",
    "outcome_cartesian_completeness_audit.json",
    "scoring_semantics_audit.json",
    "outcome_scoring_summary.parquet",
    "outcome_scoring_report.md",
    "score_sensitivity_report.md",
    "risk_budget_readiness_report.md",
    "walk_forward_design_report.md",
    "walk_forward_fold_summary.parquet",
    "walk_forward_leakage_audit_summary.json",
    "walk_forward_temporal_leakage_audit.json",
]
p = argparse.ArgumentParser()
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
rep = Path("reports/scoring_runs") / a.scoring_run_id
data = Path("data/processed/scoring_runs") / a.scoring_run_id
rep.mkdir(parents=True, exist_ok=True)
for name in REQUIRED:
    if name == "review_pack_manifest.json":
        continue
    if not (rep / name).exists() and (data / name).exists():
        shutil.copyfile(data / name, rep / name)
missing = [n for n in REQUIRED if n != "review_pack_manifest.json" and not (rep / n).exists()]
if missing:
    raise SystemExit(json.dumps({"review_pack_ok": False, "missing_members": missing}))
manifest = {"scoring_run_id": a.scoring_run_id, "members": REQUIRED}
(rep / "review_pack_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
zip_path = Path(f"pm_review_pack_scoring_{a.scoring_run_id}.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for name in REQUIRED:
        z.write(rep / name, arcname=name)
print(json.dumps({"review_pack_zip": str(zip_path), "review_pack_ok": True, "members": REQUIRED}))
