from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from io import BytesIO

import polars as pl

REQUIRED = {
    "review_pack_manifest.json",
    "fee_snapshot_report.md",
    "fee_coverage_audit.json",
    "cost_model_config_resolved.yml",
    "cost_model_audit.json",
    "cost_scenario_summary.parquet",
    "cost_summary_audit.json",
    "scoring_run_status.json",
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
    "walk_forward_exclusion_reason_summary.parquet",
    "walk_forward_leakage_audit_summary.json",
    "walk_forward_temporal_leakage_audit.json",
    "outcome_category_normalization_audit.json",
    "fee_join_context_audit.json",
}
BOOLS = [
    ("outcome_source_audit.json", "source_audit_ok", True),
    ("outcome_grain_audit.json", "grain_audit_ok", True),
    ("outcome_cartesian_completeness_audit.json", "cartesian_completeness_ok", True),
    ("outcome_grain_contract_audit.json", "grain_contract_audit_ok", True),
    ("outcome_grain_contract_audit.json", "synthetic_row_risk_detected_bool", False),
    ("fee_coverage_audit.json", "fee_coverage_ok", True),
    ("cost_model_audit.json", "cost_model_audit_ok", True),
    ("cost_summary_audit.json", "cost_summary_audit_ok", True),
    ("cost_summary_audit.json", "cost_summary_dimension_multiplication_detected_bool", False),
    ("scoring_semantics_audit.json", "scoring_semantics_audit_ok", True),
    ("walk_forward_coverage_audit.json", "walk_forward_coverage_audit_ok", True),
    ("walk_forward_coverage_audit.json", "coverage_reconciliation_ok", True),
    ("walk_forward_coverage_audit.json", "sufficient_for_parameter_selection_bool", False),
    ("walk_forward_leakage_audit_summary.json", "leakage_audit_ok", True),
    ("walk_forward_temporal_leakage_audit.json", "temporal_leakage_audit_ok", True),
    ("scoring_semantics_audit.json", "risk_budget_proven_bool", False),
    ("cost_model_audit.json", "risk_budget_proven_bool", False),
    ("outcome_category_normalization_audit.json", "category_normalization_ok", True),
]


def _json(z, name):
    return json.loads(z.read(name).decode())


def _parquet(z, name):
    return pl.read_parquet(BytesIO(z.read(name)))


def check_zip(zip_path: str, scoring_run_id: str) -> dict[str, object]:
    if not Path(zip_path).exists():
        return {
            "review_pack_ok": False,
            "error": "zip_not_found",
            "zip": zip_path,
            "scoring_run_id": scoring_run_id,
        }
    with zipfile.ZipFile(zip_path) as z:
        raw_names = z.namelist()
        names = set(raw_names)
        missing = sorted(REQUIRED - names)
        extra = sorted(names - REQUIRED)
        duplicate_members = sorted({n for n in raw_names if raw_names.count(n) > 1})
        forbidden_paths = sorted(n for n in names if n.startswith("/") or ".." in n.split("/"))
        manifest = (
            _json(z, "review_pack_manifest.json") if "review_pack_manifest.json" in names else {}
        )
        manifest_ok = bool(
            manifest
            and set(manifest.get("members", [])) == names
            and manifest.get("scoring_run_id") == scoring_run_id
        )
        hash_bad = []
        expected_hash_keys = REQUIRED - {"review_pack_manifest.json"}
        sha = manifest.get("sha256", {}) if manifest else {}
        if set(sha) != expected_hash_keys:
            manifest_ok = False
            hash_bad.append(
                {
                    "hash_key_mismatch": {
                        "missing": sorted(expected_hash_keys - set(sha)),
                        "unexpected": sorted(set(sha) - expected_hash_keys),
                    }
                }
            )
        for n, h in sha.items():
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
            fee, cost, sem, grain = (
                _json(z, n)
                for n in [
                    "fee_coverage_audit.json",
                    "cost_model_audit.json",
                    "scoring_semantics_audit.json",
                    "outcome_grain_contract_audit.json",
                ]
            )

            if (
                manifest.get("review_pack_schema_version")
                != "scoring_review_pack_v4_audit_complete"
            ):
                consistency.append("review_pack_schema_version")
            if manifest.get("manifest_hash_policy") != "self_excluded_v1":
                consistency.append("manifest_hash_policy")
            for k, exp in {
                "review_phase": "state_machine_engineering_ready",
                "parameter_selection_authorized_bool": False,
                "live_authorized_bool": False,
            }.items():
                if manifest.get(k) != exp:
                    consistency.append(k)
            cat = _json(z, "outcome_category_normalization_audit.json")
            if cat.get("rows_before") != cat.get("rows_after"):
                consistency.append("category_rows_before_after")
            if (
                cat.get("normalized_categories") != ["linear"]
                or cat.get("default_category") != "linear"
            ):
                consistency.append("category_normalized_values")
            if cat.get("category_source") not in {"project_scope_default", "source_column"}:
                consistency.append("category_source")
            if cat.get("category_source") == "source_column":
                src = [
                    str(x).strip().lower()
                    for x in cat.get("source_categories", cat.get("raw_categories", []))
                ]
                if src and set(src) != {"linear"}:
                    consistency.append("category_source_column_normalization")
            for grain_name in [
                "event_horizon",
                "event_horizon_sl",
                "event_horizon_grid",
                "expanded_scoring_input",
            ]:
                if grain.get("category_present_by_grain", {}).get(grain_name) is not True:
                    consistency.append(f"category_present_{grain_name}")
                if grain.get("category_values_by_grain", {}).get(grain_name) != ["linear"]:
                    consistency.append(f"category_values_{grain_name}")
                if (
                    grain.get("null_required_column_counts_by_grain", {})
                    .get(grain_name, {})
                    .get("category")
                    != 0
                ):
                    consistency.append(f"category_nulls_{grain_name}")
            joins = _json(z, "fee_join_context_audit.json")
            if set(joins) != {"expanded_scoring_input", "cost_summary_event_horizon_grid"}:
                consistency.append("fee_join_contexts")
            grain_audit = _json(z, "outcome_grain_audit.json")
            cost_summary = _json(z, "cost_summary_audit.json")
            expected_rows = {
                "expanded_scoring_input": grain_audit.get("rows", {}).get("expanded_scoring_input"),
                "cost_summary_event_horizon_grid": cost_summary.get("cost_summary_source_rows"),
            }
            for ctx, audit in joins.items():
                for k, exp in {
                    "fee_join_ok": True,
                    "scoring_categories": ["linear"],
                    "missing_fee_row_count": 0,
                    "symbols_missing_fee_rates": [],
                }.items():
                    if audit.get(k) != exp:
                        consistency.append(f"fee_join_{ctx}_{k}")
                if audit.get("input_rows") != audit.get("output_rows"):
                    consistency.append(f"fee_join_{ctx}_rows")
                if audit.get("scoring_symbol_count", 0) <= 0 or audit.get(
                    "fee_symbol_count", 0
                ) < audit.get("scoring_symbol_count", 0):
                    consistency.append(f"fee_join_{ctx}_symbol_counts")
                if (
                    expected_rows.get(ctx) is not None
                    and audit.get("input_rows") != expected_rows[ctx]
                ):
                    consistency.append(f"fee_join_{ctx}_expected_rows")
            if fee.get("fee_coverage_ok") is not True or fee.get("fee_coverage_rate") != 1.0:
                consistency.append("fee_coverage")
            if sem.get("risk_budget_proven_bool") is not False:
                consistency.append("risk_budget_proven_bool")
            status = _json(z, "scoring_run_status.json")
            if status.get("status") != "complete" or status.get("scoring_run_id") != scoring_run_id:
                consistency.append("scoring_run_status")
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
            if cost_summary.get("cost_summary_grain") != "event_horizon_grid":
                consistency.append("cost_summary_grain")
            if cost_summary.get("cost_summary_duplicate_key_count") != 0:
                consistency.append("cost_summary_duplicate_key_count")
            wf = _parquet(z, "walk_forward_fold_summary.parquet")
            if wf.is_empty():
                consistency.append("walk_forward_fold_summary_empty")
            else:
                bad_wf = wf.filter(
                    (pl.col("coverage_reconciliation_ok") != True)  # noqa: E712
                    | (pl.col("coverage_reconciliation_delta") != 0)
                    | (pl.col("unassigned_event_count") != 0)
                    | (
                        (
                            pl.col("train_events")
                            + pl.col("validation_events")
                            + pl.col("test_events")
                        )
                        <= 0
                    )
                    | (pl.col("actual_train_days") < pl.col("configured_train_days"))
                    | (pl.col("purge_gap_minutes") < 2880)
                    | (pl.col("embargo_gap_minutes") < 2880)
                    | (pl.col("sufficient_for_parameter_selection_bool") != False)  # noqa: E712
                    | (pl.col("sufficient_for_state_machine_engineering_bool") != True)  # noqa: E712
                )
                if bad_wf.height:
                    consistency.append("walk_forward_fold_summary_invariants")
        ok = (
            not missing
            and not extra
            and not duplicate_members
            and not forbidden_paths
            and manifest_ok
            and not bad
            and not hash_bad
            and not consistency
        )
        return {
            "review_pack_ok": ok,
            "members": sorted(names),
            "missing_members": missing,
            "extra_members": extra,
            "duplicate_members": duplicate_members,
            "forbidden_paths": forbidden_paths,
            "manifest_ok": manifest_ok,
            "bad_audit_values": bad,
            "hash_mismatches": hash_bad,
            "consistency_errors": consistency,
            "scoring_run_id": scoring_run_id,
        }


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
