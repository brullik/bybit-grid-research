from __future__ import annotations
import argparse
import json
import sys
import zipfile

REQUIRED = {
    "review_pack_manifest.json",
    "fee_snapshot_report.md",
    "fee_coverage_audit.json",
    "cost_model_config_resolved.yml",
    "cost_model_audit.json",
    "cost_scenario_summary.parquet",
    "cost_scenario_report.md",
    "outcome_source_audit.json",
    "outcome_grain_audit.json",
    "outcome_cartesian_completeness_audit.json",
    "outcome_grain_contract_audit.json",
    "scoring_semantics_audit.json",
    "scoring_null_policy.md",
    "score_component_summary.parquet",
    "score_correlation_report.json",
    "outcome_scoring_summary.parquet",
    "outcome_scoring_report.md",
    "score_sensitivity_report.md",
    "risk_budget_readiness_report.md",
    "walk_forward_design_report.md",
    "walk_forward_fold_summary.parquet",
    "walk_forward_coverage_audit.json",
    "walk_forward_leakage_audit_summary.json",
    "walk_forward_temporal_leakage_audit.json",
}
BOOLS = [
    ("outcome_source_audit.json", "source_audit_ok", True),
    ("outcome_grain_audit.json", "grain_audit_ok", True),
    ("outcome_cartesian_completeness_audit.json", "cartesian_completeness_ok", True),
    ("outcome_grain_contract_audit.json", "grain_contract_audit_ok", True),
    ("fee_coverage_audit.json", "fee_coverage_ok", True),
    ("cost_model_audit.json", "cost_model_audit_ok", True),
    ("scoring_semantics_audit.json", "scoring_semantics_audit_ok", True),
    ("walk_forward_coverage_audit.json", "walk_forward_coverage_audit_ok", True),
    ("walk_forward_leakage_audit_summary.json", "leakage_audit_ok", True),
    ("walk_forward_temporal_leakage_audit.json", "temporal_leakage_audit_ok", True),
    ("scoring_semantics_audit.json", "risk_budget_proven_bool", False),
]
p = argparse.ArgumentParser()
p.add_argument("--zip", required=True)
p.add_argument("--scoring-run-id", required=True)
a = p.parse_args()
with zipfile.ZipFile(a.zip) as z:
    raw_names = z.namelist()
    names = set(raw_names)
    missing = sorted(REQUIRED - names)
    extra = sorted(names - REQUIRED)
    duplicate_members = sorted({n for n in raw_names if raw_names.count(n) > 1})
    forbidden_paths = sorted(n for n in names if n.startswith("/") or ".." in n.split("/"))
    manifest = (
        json.loads(z.read("review_pack_manifest.json"))
        if "review_pack_manifest.json" in names
        else {}
    )
    manifest_ok = bool(
        manifest
        and set(manifest.get("members", [])) == names
        and manifest.get("scoring_run_id") == a.scoring_run_id
    )
    bad = []
    for fn, key, exp in BOOLS:
        if fn in names:
            val = json.loads(z.read(fn).decode()).get(key)
            if val is not exp:
                bad.append({"file": fn, "key": key, "value": val, "expected": exp})
res = {
    "review_pack_ok": not missing
    and not extra
    and not duplicate_members
    and not forbidden_paths
    and manifest_ok
    and not bad,
    "members": sorted(names),
    "missing_members": missing,
    "extra_members": extra,
    "duplicate_members": duplicate_members,
    "forbidden_paths": forbidden_paths,
    "manifest_ok": manifest_ok,
    "bad_audit_values": bad,
    "scoring_run_id": a.scoring_run_id,
}
print(json.dumps(res, sort_keys=True))
sys.exit(0 if res["review_pack_ok"] else 1)
