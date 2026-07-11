from __future__ import annotations
import argparse
import json
import zipfile
import sys

REQUIRED = {
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
}
BOOLS = [
    ("outcome_source_audit.json", "source_audit_ok", True),
    ("outcome_grain_audit.json", "grain_audit_ok", True),
    ("outcome_cartesian_completeness_audit.json", "cartesian_completeness_ok", True),
    ("fee_coverage_audit.json", "fee_coverage_ok", True),
    ("scoring_semantics_audit.json", "scoring_semantics_audit_ok", True),
    ("walk_forward_leakage_audit_summary.json", "leakage_audit_ok", True),
    ("walk_forward_temporal_leakage_audit.json", "temporal_leakage_audit_ok", True),
    ("scoring_semantics_audit.json", "risk_budget_proven_bool", False),
]
p = argparse.ArgumentParser()
p.add_argument("--zip", required=True)
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
with zipfile.ZipFile(a.zip) as z:
    names = set(z.namelist())
    missing = sorted(REQUIRED - names)
    extra = sorted(names - REQUIRED)
    manifest = (
        json.loads(z.read("review_pack_manifest.json"))
        if "review_pack_manifest.json" in names
        else {}
    )
    manifest_ok = set(manifest.get("members", [])) == names if manifest else False
    bad = []
    for fn, key, exp in BOOLS:
        if fn in names:
            val = json.loads(z.read(fn).decode()).get(key)
            if val is not exp:
                bad.append({"file": fn, "key": key, "value": val, "expected": exp})
res = {
    "review_pack_ok": not missing and not extra and manifest_ok and not bad,
    "members": sorted(names),
    "missing_members": missing,
    "extra_members": extra,
    "manifest_ok": manifest_ok,
    "bad_audit_values": bad,
    "scoring_run_id": a.scoring_run_id,
}
print(json.dumps(res, sort_keys=True))
sys.exit(0 if res["review_pack_ok"] else 1)
