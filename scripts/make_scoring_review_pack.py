from __future__ import annotations
import argparse
import json
import zipfile
from pathlib import Path

ALLOW = {
    "fee_snapshot_report.md",
    "cost_model_config.yml",
    "cost_model_audit.json",
    "outcome_grain_audit.json",
    "outcome_scoring_summary.parquet",
    "outcome_scoring_report.md",
    "score_sensitivity_report.md",
    "walk_forward_design_report.md",
    "walk_forward_leakage_audit_summary.json",
    "risk_budget_readiness_report.md",
    "review_pack_manifest.json",
}
p = argparse.ArgumentParser()
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
rep = Path("reports/scoring_runs") / a.scoring_run_id
data = Path("data/processed/scoring_runs") / a.scoring_run_id
rep.mkdir(parents=True, exist_ok=True)
manifest = {"scoring_run_id": a.scoring_run_id, "allowlisted_members": sorted(ALLOW)}
(rep / "review_pack_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
zip_path = Path(f"pm_review_pack_scoring_{a.scoring_run_id}.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for name in sorted(ALLOW):
        src = rep / name
        if not src.exists() and name == "outcome_grain_audit.json":
            src = data / name
        if not src.exists() and name == "outcome_scoring_summary.parquet":
            try:
                import polars as pl

                ds = data / "outcome_scoring_dataset.parquet"
                if ds.exists():
                    pl.read_parquet(ds).head(1000).write_parquet(rep / name)
            except Exception:
                pass
            src = rep / name
        if src.exists():
            z.write(src, arcname=name)
print(json.dumps({"review_pack_zip": str(zip_path), "review_pack_ok": True}))
