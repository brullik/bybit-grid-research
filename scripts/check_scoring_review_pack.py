from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile

REQUIRED = {
    "review_pack_manifest.json", "fee_snapshot_report.md", "fee_coverage_audit.json",
    "cost_model_config_resolved.yml", "cost_model_audit.json", "cost_scenario_summary.parquet",
    "cost_scenario_report.md", "outcome_source_audit.json", "outcome_grain_audit.json",
    "outcome_cartesian_completeness_audit.json", "outcome_grain_contract_audit.json",
    "scoring_semantics_audit.json", "scoring_null_policy.md", "score_component_summary.parquet",
    "score_correlation_report.json", "outcome_scoring_summary.parquet", "outcome_scoring_report.md",
    "score_sensitivity_report.md", "risk_budget_readiness_report.md", "walk_forward_design_report.md",
    "walk_forward_fold_summary.parquet", "walk_forward_coverage_audit.json",
    "walk_forward_leakage_audit_summary.json", "walk_forward_temporal_leakage_audit.json",
}
BOOLS = [
    ("outcome_source_audit.json", "source_audit_ok", True),
    ("outcome_grain_audit.json", "grain_audit_ok", True),
    ("outcome_cartesian_completeness_audit.json", "cartesian_completeness_ok", True),
    ("outcome_grain_contract_audit.json", "grain_contract_audit_ok", True),
    ("outcome_grain_contract_audit.json", "synthetic_row_risk_detected_bool", False),
    ("fee_coverage_audit.json", "fee_coverage_ok", True),
    ("cost_model_audit.json", "cost_model_audit_ok", True),
    ("scoring_semantics_audit.json", "scoring_semantics_audit_ok", True),
    ("walk_forward_coverage_audit.json", "walk_forward_coverage_audit_ok", True),
    ("walk_forward_coverage_audit.json", "coverage_reconciliation_ok", True),
    ("walk_forward_coverage_audit.json", "sufficient_for_parameter_selection_bool", False),
    ("walk_forward_leakage_audit_summary.json", "leakage_audit_ok", True),
    ("walk_forward_temporal_leakage_audit.json", "temporal_leakage_audit_ok", True),
    ("scoring_semantics_audit.json", "risk_budget_proven_bool", False),
    ("cost_model_audit.json", "risk_budget_proven_bool", False),
]

def _json(z, name):
    return json.loads(z.read(name).decode())

def check_zip(zip_path: str, scoring_run_id: str) -> dict[str, object]:
    with zipfile.ZipFile(zip_path) as z:
        raw_names = z.namelist()
        names = set(raw_names)
        missing = sorted(REQUIRED - names)
        extra = sorted(names - REQUIRED)
        duplicate_members = sorted({n for n in raw_names if raw_names.count(n) > 1})
        forbidden_paths = sorted(n for n in names if n.startswith("/") or ".." in n.split("/"))
        manifest = _json(z, "review_pack_manifest.json") if "review_pack_manifest.json" in names else {}
        manifest_ok = bool(manifest and set(manifest.get("members", [])) == names and manifest.get("scoring_run_id") == scoring_run_id)
        hash_bad = []
        if manifest and "sha256" in manifest:
            for n, h in manifest["sha256"].items():
                if n == "review_pack_manifest.json":
                    continue
                if n in names and hashlib.sha256(z.read(n)).hexdigest() != h:
                    hash_bad.append(n)
        bad = []
        for fn, key, exp in BOOLS:
            if fn in names:
                val = _json(z, fn).get(key)
                if val is not exp:
                    bad.append({"file": fn, "key": key, "value": val, "expected": exp})
        consistency = []
        if not missing:
            fee, cost, sem, grain = (_json(z, n) for n in ["fee_coverage_audit.json","cost_model_audit.json","scoring_semantics_audit.json","outcome_grain_contract_audit.json"])
            cfg = z.read("cost_model_config_resolved.yml").decode()
            if "REQUIRED_FOR_ACCOUNT_ACTUAL" in cfg or "manual_scenario" in cfg:
                consistency.append("unresolved_fee_provenance")
            if cost.get("fee_snapshot_id_resolved") != fee.get("fee_snapshot_id_resolved"):
                consistency.append("fee_snapshot_mismatch")
            if cost.get("fee_source") != fee.get("fee_source"):
                consistency.append("fee_source_mismatch")
            if grain.get("grain_contract_version") != "grain_contract_v3_whole_row":
                consistency.append("grain_contract_version")
            if sem.get("canonical_score_version") != "v3":
                consistency.append("canonical_score_version")
        ok = not missing and not extra and not duplicate_members and not forbidden_paths and manifest_ok and not bad and not hash_bad and not consistency
        return {"review_pack_ok": ok, "members": sorted(names), "missing_members": missing, "extra_members": extra, "duplicate_members": duplicate_members, "forbidden_paths": forbidden_paths, "manifest_ok": manifest_ok, "bad_audit_values": bad, "hash_mismatches": hash_bad, "consistency_errors": consistency, "scoring_run_id": scoring_run_id}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", required=True)
    p.add_argument("--scoring-run-id", required=True)
    a = p.parse_args()
    res = check_zip(a.zip, a.scoring_run_id)
    print(json.dumps(res, sort_keys=True))
    sys.exit(0 if res["review_pack_ok"] else 1)


if __name__ == "__main__":
    main()
