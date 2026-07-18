from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from io import BytesIO

import polars as pl

PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
REVIEW_PACK_SCHEMA_VERSION = "scoring_review_pack_v5_persisted_outcome_boundary"
GRAIN_CONTRACT_VERSION = "grain_contract_v4_persisted_exclusive_outcome_end"
OUTCOME_BOUNDARY_SEMANTICS_VERSION = "persisted-exclusive-outcome-end-v1"
OUTCOME_SEMANTICS_VERSION = "v5_exact_outcome_window_provenance"
OUTCOME_WINDOW_SEMANTICS_VERSION = "exact-minute-outcome-window-v1"
ACTIONABLE_EVENT_SEMANTICS_VERSION = "range-actionable-prefix-invariance-v1"
MINUTE_MS = 60_000
BOUNDARY_AUDIT_MEMBERS = [
    "walk_forward_coverage_audit.json",
    "walk_forward_leakage_audit_summary.json",
    "walk_forward_temporal_leakage_audit.json",
]
DISPOSITION_REASONS = {
    "missing_max_horizon",
    "ineligible_max_horizon",
    "outside_fold_window",
    "purge_gap",
    "embargo_gap",
    "train_horizon_boundary",
    "validation_horizon_boundary",
    "test_horizon_boundary",
    "cross_role_regime_excluded",
    "train_assigned",
    "validation_assigned",
    "test_assigned",
    "unassigned",
}

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
    "walk_forward_event_eligibility.parquet",
    "walk_forward_splits.parquet",
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
    ("outcome_grain_contract_audit.json", "persisted_outcome_end_required_bool", True),
    ("outcome_grain_contract_audit.json", "legacy_outcome_end_column_allowed_bool", False),
    ("fee_coverage_audit.json", "fee_coverage_ok", True),
    ("cost_model_audit.json", "cost_model_audit_ok", True),
    ("cost_summary_audit.json", "cost_summary_audit_ok", True),
    ("cost_summary_audit.json", "cost_summary_dimension_multiplication_detected_bool", False),
    ("scoring_semantics_audit.json", "scoring_semantics_audit_ok", True),
    ("walk_forward_coverage_audit.json", "walk_forward_coverage_audit_ok", True),
    ("walk_forward_coverage_audit.json", "coverage_reconciliation_ok", True),
    ("walk_forward_coverage_audit.json", "sufficient_for_parameter_selection_bool", False),
    ("walk_forward_coverage_audit.json", "persisted_outcome_end_required_bool", True),
    ("walk_forward_coverage_audit.json", "legacy_outcome_end_column_allowed_bool", False),
    ("walk_forward_coverage_audit.json", "risk_budget_proven_bool", False),
    ("walk_forward_coverage_audit.json", "live_authorized_bool", False),
    ("walk_forward_coverage_audit.json", "full_disposition_ledger_bool", True),
    ("walk_forward_coverage_audit.json", "disposition_ledger_reconciliation_ok", True),
    ("walk_forward_leakage_audit_summary.json", "leakage_audit_ok", True),
    ("walk_forward_leakage_audit_summary.json", "persisted_outcome_end_required_bool", True),
    ("walk_forward_leakage_audit_summary.json", "legacy_outcome_end_column_allowed_bool", False),
    ("walk_forward_temporal_leakage_audit.json", "temporal_leakage_audit_ok", True),
    ("walk_forward_temporal_leakage_audit.json", "persisted_outcome_end_required_bool", True),
    ("walk_forward_temporal_leakage_audit.json", "legacy_outcome_end_column_allowed_bool", False),
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

            manifest_contract = {
                "review_pack_schema_version": REVIEW_PACK_SCHEMA_VERSION,
                "manifest_hash_policy": "self_excluded_v1",
                "review_phase": "state_machine_engineering_ready",
                "parameter_selection_authorized_bool": False,
                "live_authorized_bool": False,
                "risk_budget_proven_bool": False,
                "canonical_score_version": "v3",
                "grain_contract_version": GRAIN_CONTRACT_VERSION,
                "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
                "scoring_run_id": scoring_run_id,
            }
            manifest_error_names = {
                "risk_budget_proven_bool": "manifest_risk_budget_proven_bool",
                "canonical_score_version": "manifest_canonical_score_version",
                "grain_contract_version": "manifest_grain_contract_version",
                "outcome_boundary_semantics_version": (
                    "manifest_outcome_boundary_semantics_version"
                ),
            }
            for k, exp in manifest_contract.items():
                if manifest.get(k) != exp:
                    consistency.append(manifest_error_names.get(k, k))
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

            outcome_source = _json(z, "outcome_source_audit.json")
            source_outcome_values = [
                manifest.get("source_outcome_run_id"),
                outcome_source.get("source_outcome_run_id"),
                status.get("source_outcome_run_id"),
                sem.get("source_outcome_run_id"),
            ]
            if not all(isinstance(v, str) and v for v in source_outcome_values) or len(
                set(source_outcome_values)
            ) != 1:
                consistency.append("manifest_source_outcome_run_id")

            fee_snapshot_values = [
                manifest.get("fee_snapshot_id_resolved"),
                fee.get("fee_snapshot_id_resolved"),
                cost.get("fee_snapshot_id_resolved"),
            ]
            if not all(isinstance(v, str) and v for v in fee_snapshot_values) or len(
                set(fee_snapshot_values)
            ) != 1:
                consistency.append("manifest_fee_snapshot_id_resolved")
            if cost.get("fee_source") != fee.get("fee_source"):
                consistency.append("fee_source_mismatch")

            if [
                manifest.get("cost_formula_version"),
                cost.get("cost_formula_version"),
            ] != ["cost_formula_v2_asymmetric_slippage"] * 2:
                consistency.append("manifest_cost_formula_version")
            if [
                manifest.get("grain_contract_version"),
                grain.get("grain_contract_version"),
            ] != [GRAIN_CONTRACT_VERSION] * 2:
                consistency.append("manifest_grain_contract_version")
            if type(grain.get("derived_outcome_end_count")) is not int or grain.get(
                "derived_outcome_end_count"
            ) != 0:
                consistency.append("grain_contract_derived_outcome_end_count")
            if (
                grain.get("outcome_boundary_semantics_version")
                != OUTCOME_BOUNDARY_SEMANTICS_VERSION
            ):
                consistency.append("grain_contract_outcome_boundary_semantics_version")
            boundary_versions = [manifest.get("outcome_boundary_semantics_version")]
            for member in BOUNDARY_AUDIT_MEMBERS:
                boundary_audit = _json(z, member)
                boundary_versions.append(
                    boundary_audit.get("outcome_boundary_semantics_version")
                )
                if boundary_audit.get("persisted_outcome_end_required_bool") is not True:
                    consistency.append(f"{member}_persisted_outcome_end_required_bool")
                derived = boundary_audit.get("derived_outcome_end_count")
                if type(derived) is not int or derived != 0:
                    consistency.append(f"{member}_derived_outcome_end_count")
                if boundary_audit.get("legacy_outcome_end_column_allowed_bool") is not False:
                    consistency.append(f"{member}_legacy_outcome_end_column_allowed_bool")
            if boundary_versions != [OUTCOME_BOUNDARY_SEMANTICS_VERSION] * len(
                boundary_versions
            ):
                consistency.append("outcome_boundary_semantics_version_mismatch")
            if [manifest.get("canonical_score_version"), sem.get("canonical_score_version")] != [
                "v3"
            ] * 2:
                consistency.append("manifest_canonical_score_version")
            if (
                manifest.get("risk_budget_proven_bool") is not False
                or cost.get("risk_budget_proven_bool") is not False
                or sem.get("risk_budget_proven_bool") is not False
            ):
                consistency.append("manifest_risk_budget_proven_bool")
            if cost_summary.get("cost_summary_grain") != "event_horizon_grid":
                consistency.append("cost_summary_grain")
            if cost_summary.get("cost_summary_duplicate_key_count") != 0:
                consistency.append("cost_summary_duplicate_key_count")
            wf = _parquet(z, "walk_forward_fold_summary.parquet")
            if wf.is_empty():
                consistency.append("walk_forward_fold_summary_empty")
            else:
                required_wf_columns = {
                    "coverage_reconciliation_ok",
                    "coverage_reconciliation_delta",
                    "unassigned_event_count",
                    "train_events",
                    "validation_events",
                    "test_events",
                    "actual_train_days",
                    "configured_train_days",
                    "purge_gap_minutes",
                    "embargo_gap_minutes",
                    "sufficient_for_parameter_selection_bool",
                    "sufficient_for_state_machine_engineering_bool",
                    "outcome_boundary_semantics_version",
                    "persisted_outcome_end_required_bool",
                    "derived_outcome_end_count",
                    "legacy_outcome_end_column_allowed_bool",
                    "source_event_count",
                    "missing_max_horizon_count",
                    "ineligible_max_horizon_count",
                    "outside_fold_window_count",
                    "purge_gap_event_count",
                    "embargo_gap_event_count",
                    "cross_role_regime_excluded_event_count",
                    "train_horizon_boundary_excluded_count",
                    "validation_horizon_boundary_excluded_count",
                    "test_horizon_boundary_excluded_count",
                }
                if not required_wf_columns.issubset(wf.columns):
                    consistency.append("walk_forward_fold_summary_missing_boundary_contract")
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
                        | (
                            pl.col("outcome_boundary_semantics_version")
                            != OUTCOME_BOUNDARY_SEMANTICS_VERSION
                        )
                        | (pl.col("persisted_outcome_end_required_bool") != True)  # noqa: E712
                        | (pl.col("derived_outcome_end_count") != 0)
                        | (pl.col("legacy_outcome_end_column_allowed_bool") != False)  # noqa: E712
                    )
                    if bad_wf.height:
                        consistency.append("walk_forward_fold_summary_invariants")

            ledger = _parquet(z, "walk_forward_event_eligibility.parquet")
            reason_summary = _parquet(z, "walk_forward_exclusion_reason_summary.parquet")
            required_ledger_columns = {
                "fold_id",
                "range_action_event_id",
                "range_regime_id",
                "role",
                "exclusion_or_assignment_reason",
                "signal_time_ms",
                "decision_time_ms",
                "entry_time_ms",
                "future_horizon_minutes",
                "max_outcome_horizon_minutes",
                "outcome_end_exclusive_ms",
                "future_data_complete_bool",
                "future_outcome_eligible_bool",
                "outcome_semantics_version",
                "outcome_window_semantics_version",
                "actionable_event_semantics_version",
                "decision_time_source",
                "causal_provenance_complete_bool",
                "train_start_ms",
                "train_end_ms",
                "validation_start_ms",
                "validation_end_ms",
                "test_start_ms",
                "test_end_ms",
                "purge_minutes",
                "embargo_minutes",
                "outcome_boundary_semantics_version",
                "persisted_outcome_end_required_bool",
                "derived_outcome_end_count",
                "legacy_outcome_end_column_allowed_bool",
            }
            required_reason_columns = {
                "fold_id",
                "exclusion_or_assignment_reason",
                "event_count",
                "outcome_boundary_semantics_version",
            }
            if "outcome_end_ms" in ledger.columns:
                consistency.append(
                    "walk_forward_disposition_ledger_legacy_outcome_end_column"
                )
            if ledger.is_empty() or not required_ledger_columns.issubset(ledger.columns):
                consistency.append("walk_forward_disposition_ledger_contract")
            elif not required_reason_columns.issubset(reason_summary.columns):
                consistency.append("walk_forward_reason_summary_contract")
            elif wf.is_empty() or not required_wf_columns.issubset(wf.columns):
                consistency.append("walk_forward_ledger_fold_summary_contract")
            else:
                duplicate_ledger_rows = ledger.height - ledger.select(
                    ["fold_id", "range_action_event_id"]
                ).unique().height
                if duplicate_ledger_rows:
                    consistency.append("walk_forward_disposition_ledger_duplicate_fold_event")
                if set(ledger["exclusion_or_assignment_reason"].to_list()) - DISPOSITION_REASONS:
                    consistency.append("walk_forward_disposition_ledger_unknown_reason")
                fold_ids = set(wf["fold_id"].to_list())
                if (
                    set(ledger["fold_id"].to_list()) != fold_ids
                    or set(reason_summary["fold_id"].to_list()) != fold_ids
                ):
                    consistency.append("walk_forward_disposition_ledger_fold_sets")

                ledger_counts: dict[tuple[object, object], int] = {}
                for row in ledger.group_by(
                    ["fold_id", "exclusion_or_assignment_reason"]
                ).len().iter_rows(named=True):
                    ledger_counts[
                        (row["fold_id"], row["exclusion_or_assignment_reason"])
                    ] = row["len"]
                reason_keys: set[tuple[object, object]] = set()
                for row in reason_summary.iter_rows(named=True):
                    key = (row["fold_id"], row["exclusion_or_assignment_reason"])
                    reason_keys.add(key)
                    if (
                        row["outcome_boundary_semantics_version"]
                        != OUTCOME_BOUNDARY_SEMANTICS_VERSION
                        or type(row["event_count"]) is not int
                        or row["event_count"] != ledger_counts.get(key, 0)
                    ):
                        consistency.append("walk_forward_reason_summary_ledger_counts")
                        break
                expected_reason_keys = {
                    (fold_id, reason) for fold_id in fold_ids for reason in DISPOSITION_REASONS
                }
                if reason_keys != expected_reason_keys:
                    consistency.append("walk_forward_reason_summary_reason_sets")
                if reason_summary.height != reason_summary.select(
                    ["fold_id", "exclusion_or_assignment_reason"]
                ).unique().height:
                    consistency.append("walk_forward_reason_summary_duplicate_reason")

                count_fields = {
                    "missing_max_horizon": "missing_max_horizon_count",
                    "ineligible_max_horizon": "ineligible_max_horizon_count",
                    "outside_fold_window": "outside_fold_window_count",
                    "purge_gap": "purge_gap_event_count",
                    "embargo_gap": "embargo_gap_event_count",
                    "cross_role_regime_excluded": "cross_role_regime_excluded_event_count",
                    "train_horizon_boundary": "train_horizon_boundary_excluded_count",
                    "validation_horizon_boundary": (
                        "validation_horizon_boundary_excluded_count"
                    ),
                    "test_horizon_boundary": "test_horizon_boundary_excluded_count",
                    "train_assigned": "train_events",
                    "validation_assigned": "validation_events",
                    "test_assigned": "test_events",
                    "unassigned": "unassigned_event_count",
                }
                fold_rows = {row["fold_id"]: row for row in wf.iter_rows(named=True)}
                bound_columns = [
                    "train_start_ms",
                    "train_end_ms",
                    "validation_start_ms",
                    "validation_end_ms",
                    "test_start_ms",
                    "test_end_ms",
                    "purge_minutes",
                    "embargo_minutes",
                ]
                for fold_id, fold_row in fold_rows.items():
                    fold_ledger = ledger.filter(pl.col("fold_id") == fold_id)
                    if fold_ledger.height != fold_row["source_event_count"]:
                        consistency.append("walk_forward_disposition_ledger_source_count")
                    if any(
                        ledger_counts.get((fold_id, reason), 0) != fold_row[field]
                        for reason, field in count_fields.items()
                    ):
                        consistency.append("walk_forward_disposition_ledger_fold_counts")
                    for column in bound_columns:
                        if (
                            fold_ledger[column].n_unique() != 1
                            or fold_ledger[column].item(0) != fold_row[column]
                        ):
                            consistency.append("walk_forward_disposition_ledger_fold_bounds")
                            break

                for row in ledger.iter_rows(named=True):
                    reason = row["exclusion_or_assignment_reason"]
                    assigned_role = (
                        reason.removesuffix("_assigned")
                        if reason.endswith("_assigned")
                        else None
                    )
                    if row["role"] != assigned_role:
                        consistency.append("walk_forward_disposition_ledger_role_reason")
                        break
                    if (
                        row["outcome_boundary_semantics_version"]
                        != OUTCOME_BOUNDARY_SEMANTICS_VERSION
                        or row["persisted_outcome_end_required_bool"] is not True
                        or type(row["derived_outcome_end_count"]) is not int
                        or row["derived_outcome_end_count"] != 0
                        or row["legacy_outcome_end_column_allowed_bool"] is not False
                        or row["outcome_semantics_version"] != OUTCOME_SEMANTICS_VERSION
                        or row["outcome_window_semantics_version"]
                        != OUTCOME_WINDOW_SEMANTICS_VERSION
                        or row["actionable_event_semantics_version"]
                        != ACTIONABLE_EVENT_SEMANTICS_VERSION
                        or row["decision_time_source"] != "event_decision_time"
                        or row["causal_provenance_complete_bool"] is not True
                    ):
                        consistency.append("walk_forward_disposition_ledger_semantics")
                        break
                    if (
                        type(row["signal_time_ms"]) is not int
                        or type(row["decision_time_ms"]) is not int
                        or type(row["entry_time_ms"]) is not int
                    ):
                        consistency.append("walk_forward_disposition_ledger_times")
                        break
                    expected_entry = (
                        (row["decision_time_ms"] // MINUTE_MS) + 1
                    ) * MINUTE_MS
                    if (
                        row["decision_time_ms"] != row["signal_time_ms"]
                        or row["entry_time_ms"] != expected_entry
                        or min(
                            row["signal_time_ms"],
                            row["decision_time_ms"],
                            row["entry_time_ms"],
                        )
                        < 0
                    ):
                        consistency.append("walk_forward_disposition_ledger_times")
                        break
                    if reason == "missing_max_horizon":
                        if any(
                            row[column] is not None
                            for column in [
                                "future_horizon_minutes",
                                "outcome_end_exclusive_ms",
                                "future_data_complete_bool",
                                "future_outcome_eligible_bool",
                            ]
                        ):
                            consistency.append("walk_forward_missing_max_horizon_ledger")
                            break
                    else:
                        if (
                            type(row["future_horizon_minutes"]) is not int
                            or type(row["max_outcome_horizon_minutes"]) is not int
                            or row["future_horizon_minutes"]
                            != row["max_outcome_horizon_minutes"]
                            or type(row["outcome_end_exclusive_ms"]) is not int
                            or row["outcome_end_exclusive_ms"]
                            != row["entry_time_ms"]
                            + row["future_horizon_minutes"] * MINUTE_MS
                            or type(row["future_data_complete_bool"]) is not bool
                            or type(row["future_outcome_eligible_bool"]) is not bool
                            or row["future_outcome_eligible_bool"]
                            is not row["future_data_complete_bool"]
                            or (
                                reason == "ineligible_max_horizon"
                                and row["future_outcome_eligible_bool"] is not False
                            )
                            or (
                                reason != "ineligible_max_horizon"
                                and row["future_outcome_eligible_bool"] is not True
                            )
                        ):
                            consistency.append("walk_forward_persisted_outcome_end_ledger")
                            break

                try:
                    event_sets = [
                        set(
                            ledger.filter(pl.col("fold_id") == fold_id)[
                                "range_action_event_id"
                            ].to_list()
                        )
                        for fold_id in sorted(fold_ids)
                    ]
                    if event_sets and any(events != event_sets[0] for events in event_sets[1:]):
                        consistency.append("walk_forward_disposition_ledger_event_sets")
                    recomputed: dict[tuple[object, object], tuple[str, str | None]] = {}
                    for fold_id in fold_ids:
                        fold_ledger_rows = ledger.filter(
                            pl.col("fold_id") == fold_id
                        ).iter_rows(named=True)
                        direct: dict[tuple[object, object], tuple[str, str | None]] = {}
                        tentative: dict[tuple[object, object], tuple[str, object]] = {}
                        fold_signals: list[int] = []
                        for row in fold_ledger_rows:
                            key = (fold_id, row["range_action_event_id"])
                            signal = row["signal_time_ms"]
                            fold_signals.append(signal)
                            if row["future_horizon_minutes"] is None:
                                direct[key] = ("missing_max_horizon", None)
                                continue
                            if (
                                row["future_data_complete_bool"] is not True
                                or row["future_outcome_eligible_bool"] is not True
                            ):
                                direct[key] = ("ineligible_max_horizon", None)
                                continue
                            role = None
                            role_end = None
                            if signal < row["train_start_ms"] or signal >= row["test_end_ms"]:
                                direct[key] = ("outside_fold_window", None)
                                continue
                            if row["train_end_ms"] <= signal < row["validation_start_ms"]:
                                direct[key] = ("purge_gap", None)
                                continue
                            if row["validation_end_ms"] <= signal < row["test_start_ms"]:
                                direct[key] = ("embargo_gap", None)
                                continue
                            for candidate, start_column, end_column in [
                                ("train", "train_start_ms", "train_end_ms"),
                                (
                                    "validation",
                                    "validation_start_ms",
                                    "validation_end_ms",
                                ),
                                ("test", "test_start_ms", "test_end_ms"),
                            ]:
                                if row[start_column] <= signal < row[end_column]:
                                    role = candidate
                                    role_end = row[end_column]
                                    break
                            if role is None:
                                direct[key] = ("unassigned", None)
                            elif row["outcome_end_exclusive_ms"] > role_end:
                                direct[key] = (f"{role}_horizon_boundary", None)
                            else:
                                tentative[key] = (role, row["range_regime_id"])
                        if fold_signals and min(fold_signals) != next(
                            row["train_start_ms"]
                            for row in ledger.filter(pl.col("fold_id") == fold_id).iter_rows(
                                named=True
                            )
                        ):
                            consistency.append("walk_forward_fold_universe_start")
                        regime_roles: dict[object, set[str]] = {}
                        for role, regime in tentative.values():
                            regime_roles.setdefault(regime, set()).add(role)
                        cross_regimes = {
                            regime for regime, roles in regime_roles.items() if len(roles) > 1
                        }
                        recomputed.update(direct)
                        for key, (role, regime) in tentative.items():
                            recomputed[key] = (
                                ("cross_role_regime_excluded", None)
                                if regime in cross_regimes
                                else (f"{role}_assigned", role)
                            )
                    declared = {
                        (row["fold_id"], row["range_action_event_id"]): (
                            row["exclusion_or_assignment_reason"],
                            row["role"],
                        )
                        for row in ledger.iter_rows(named=True)
                    }
                    if recomputed != declared:
                        consistency.append("walk_forward_disposition_reason_recomputation")
                except (KeyError, TypeError, ValueError, StopIteration):
                    consistency.append("walk_forward_disposition_reason_recomputation")

                split_rows = _parquet(z, "walk_forward_splits.parquet")
                split_required_columns = required_ledger_columns - {
                    "exclusion_or_assignment_reason",
                    "max_outcome_horizon_minutes",
                }
                if (
                    "outcome_end_ms" in split_rows.columns
                    or not split_required_columns.issubset(split_rows.columns)
                ):
                    consistency.append("walk_forward_splits_boundary_contract")
                else:
                    split_duplicate_count = split_rows.height - split_rows.select(
                        ["fold_id", "range_action_event_id"]
                    ).unique().height
                    if split_duplicate_count:
                        consistency.append("walk_forward_splits_duplicate_fold_event")
                    assigned_ledger = ledger.filter(pl.col("role").is_not_null())
                    comparison_columns = [
                        "fold_id",
                        "range_action_event_id",
                        "range_regime_id",
                        "role",
                        "signal_time_ms",
                        "decision_time_ms",
                        "entry_time_ms",
                        "future_horizon_minutes",
                        "outcome_end_exclusive_ms",
                        "future_data_complete_bool",
                        "future_outcome_eligible_bool",
                        "outcome_semantics_version",
                        "outcome_window_semantics_version",
                        "actionable_event_semantics_version",
                        "decision_time_source",
                        "causal_provenance_complete_bool",
                        "train_start_ms",
                        "train_end_ms",
                        "validation_start_ms",
                        "validation_end_ms",
                        "test_start_ms",
                        "test_end_ms",
                        "purge_minutes",
                        "embargo_minutes",
                        "outcome_boundary_semantics_version",
                        "persisted_outcome_end_required_bool",
                        "derived_outcome_end_count",
                        "legacy_outcome_end_column_allowed_bool",
                    ]
                    assigned_records = {
                        (row["fold_id"], row["range_action_event_id"]): row
                        for row in assigned_ledger.select(comparison_columns).iter_rows(
                            named=True
                        )
                    }
                    split_records = {
                        (row["fold_id"], row["range_action_event_id"]): row
                        for row in split_rows.select(comparison_columns).iter_rows(named=True)
                    }
                    if assigned_records != split_records:
                        consistency.append("walk_forward_assigned_ledger_split_mismatch")
                coverage = _json(z, "walk_forward_coverage_audit.json")
                expected_ledger_rows = int(wf["source_event_count"].sum())
                if (
                    coverage.get("disposition_ledger_row_count") != ledger.height
                    or coverage.get("disposition_ledger_expected_row_count")
                    != expected_ledger_rows
                ):
                    consistency.append("walk_forward_coverage_ledger_counts")
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
