from __future__ import annotations
import argparse
import json
import zipfile

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
DENY = (".env", "API", "signature", "data/raw", "outcome partitions", "account value", "cache")
p = argparse.ArgumentParser()
p.add_argument("--zip", required=True)
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
with zipfile.ZipFile(a.zip) as z:
    names = set(z.namelist())
bad = sorted(n for n in names if n not in ALLOW or any(d in n for d in DENY))
res = {
    "review_pack_ok": not bad,
    "members": sorted(names),
    "bad_members": bad,
    "scoring_run_id": a.scoring_run_id,
}
print(json.dumps(res, sort_keys=True))
raise SystemExit(0 if res["review_pack_ok"] else 1)
