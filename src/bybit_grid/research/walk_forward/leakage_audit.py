from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from bybit_grid.research.walk_forward.splits import (
    ACTIONABLE_EVENT_SEMANTICS_VERSION,
    CANONICAL_OUTCOME_END_COLUMN,
    LEGACY_OUTCOME_END_COLUMN,
    MINUTE_MS,
    OUTCOME_BOUNDARY_SEMANTICS_VERSION,
    OUTCOME_SEMANTICS_VERSION,
    OUTCOME_WINDOW_SEMANTICS_VERSION,
)


PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)

REQUIRED_SPLIT_COLUMNS = [
    "fold_id",
    "role",
    "range_action_event_id",
    "range_regime_id",
    "signal_time_ms",
    "decision_time_ms",
    "entry_time_ms",
    "future_horizon_minutes",
    CANONICAL_OUTCOME_END_COLUMN,
    "future_data_complete_bool",
    "future_outcome_eligible_bool",
    "outcome_semantics_version",
    "outcome_window_semantics_version",
    "actionable_event_semantics_version",
    "decision_time_source",
    "causal_provenance_complete_bool",
    "outcome_boundary_semantics_version",
    "persisted_outcome_end_required_bool",
    "derived_outcome_end_count",
    "legacy_outcome_end_column_allowed_bool",
    "train_start_ms",
    "train_end_ms",
    "validation_start_ms",
    "validation_end_ms",
    "test_start_ms",
    "test_end_ms",
    "purge_minutes",
    "embargo_minutes",
]

ROLE_BOUNDS = {
    "train": ("train_start_ms", "train_end_ms"),
    "validation": ("validation_start_ms", "validation_end_ms"),
    "test": ("test_start_ms", "test_end_ms"),
}


def _result(violations: list[dict[str, object]]) -> dict[str, object]:
    return {
        "leakage_violations": len(violations),
        "violations": violations,
        "leakage_audit_ok": not violations,
        "temporal_leakage_audit_ok": not violations,
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
        "persisted_outcome_end_required_bool": True,
        "derived_outcome_end_count": 0,
        "legacy_outcome_end_column_allowed_bool": False,
        "sufficient_for_parameter_selection_bool": False,
        "risk_budget_proven_bool": False,
        "live_authorized_bool": False,
    }


def audit_splits(splits: pl.DataFrame) -> dict[str, object]:
    violations: list[dict[str, object]] = []
    if splits.is_empty():
        violations.append({"type": "empty_splits"})
        return _result(violations)
    if LEGACY_OUTCOME_END_COLUMN in splits.columns:
        violations.append(
            {
                "type": "legacy_outcome_end_column_forbidden",
                "column": LEGACY_OUTCOME_END_COLUMN,
            }
        )
    missing = [c for c in REQUIRED_SPLIT_COLUMNS if c not in splits.columns]
    if missing:
        violations.append({"type": "missing_required_split_columns", "columns": missing})
        return _result(violations)

    duplicate_count = splits.height - splits.select(
        ["fold_id", "range_action_event_id"]
    ).unique().height
    if duplicate_count:
        violations.append({"type": "duplicate_fold_event_rows", "count": duplicate_count})

    allowed_roles = set(ROLE_BOUNDS)
    invalid_roles = sorted(
        str(role)
        for role in splits["role"].drop_nulls().unique().to_list()
        if role not in allowed_roles
    )
    if invalid_roles or splits["role"].null_count():
        violations.append(
            {
                "type": "invalid_roles",
                "roles": invalid_roles,
                "null_count": splits["role"].null_count(),
            }
        )

    for fold_id in splits["fold_id"].unique().to_list():
        fold = splits.filter(pl.col("fold_id") == fold_id)
        for key, kind in [
            ("range_action_event_id", "overlapping_event_ids"),
            ("range_regime_id", "overlapping_regime_ids"),
        ]:
            crossing = (
                fold.group_by(key)
                .agg(pl.col("role").n_unique().alias("role_count"))
                .filter(pl.col("role_count") > 1)
            )
            if crossing.height:
                violations.append(
                    {"fold_id": fold_id, "type": kind, "count": crossing.height}
                )

        invariant_columns = [
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
        inconsistent = [
            column
            for column in invariant_columns
            if fold[column].n_unique() != 1 or fold[column].null_count()
        ]
        if inconsistent:
            violations.append(
                {
                    "fold_id": fold_id,
                    "type": "inconsistent_fold_bounds_or_contract",
                    "columns": inconsistent,
                }
            )
            continue
        values = fold.select(invariant_columns).row(0, named=True)
        bound_columns = invariant_columns[:8]
        if any(type(values[column]) is not int for column in bound_columns):
            violations.append(
                {"fold_id": fold_id, "type": "non_integer_fold_bound_or_gap"}
            )
            continue
        if values["outcome_boundary_semantics_version"] != OUTCOME_BOUNDARY_SEMANTICS_VERSION:
            violations.append(
                {"fold_id": fold_id, "type": "wrong_outcome_boundary_semantics_version"}
            )
        if values["persisted_outcome_end_required_bool"] is not True:
            violations.append(
                {"fold_id": fold_id, "type": "persisted_outcome_end_not_required"}
            )
        if type(values["derived_outcome_end_count"]) is not int or values[
            "derived_outcome_end_count"
        ] != 0:
            violations.append(
                {"fold_id": fold_id, "type": "derived_outcome_end_detected"}
            )
        if values["legacy_outcome_end_column_allowed_bool"] is not False:
            violations.append(
                {"fold_id": fold_id, "type": "legacy_outcome_end_column_allowed"}
            )
        if not (
            values["train_start_ms"] < values["train_end_ms"]
            <= values["validation_start_ms"]
            < values["validation_end_ms"]
            <= values["test_start_ms"]
            < values["test_end_ms"]
        ):
            violations.append({"fold_id": fold_id, "type": "invalid_fold_bound_order"})
        if (
            values["validation_start_ms"] - values["train_end_ms"]
            != values["purge_minutes"] * MINUTE_MS
        ):
            violations.append({"fold_id": fold_id, "type": "purge_bound_mismatch"})
        if (
            values["test_start_ms"] - values["validation_end_ms"]
            != values["embargo_minutes"] * MINUTE_MS
        ):
            violations.append({"fold_id": fold_id, "type": "embargo_bound_mismatch"})
        if values["purge_minutes"] < 2880 or values["embargo_minutes"] < 2880:
            violations.append({"fold_id": fold_id, "type": "gap_too_small"})

        for index, row in enumerate(fold.iter_rows(named=True)):
            role = row["role"]
            if role not in ROLE_BOUNDS:
                continue
            for column in [
                "signal_time_ms",
                "decision_time_ms",
                "entry_time_ms",
                "future_horizon_minutes",
                CANONICAL_OUTCOME_END_COLUMN,
            ]:
                if type(row[column]) is not int:
                    violations.append(
                        {
                            "fold_id": fold_id,
                            "type": "invalid_integer_value",
                            "row": index,
                            "column": column,
                        }
                    )
            if any(
                type(row[column]) is not int
                for column in [
                    "signal_time_ms",
                    "decision_time_ms",
                    "entry_time_ms",
                    "future_horizon_minutes",
                    CANONICAL_OUTCOME_END_COLUMN,
                ]
            ):
                continue
            signal = row["signal_time_ms"]
            decision = row["decision_time_ms"]
            entry = row["entry_time_ms"]
            horizon = row["future_horizon_minutes"]
            outcome_end = row[CANONICAL_OUTCOME_END_COLUMN]
            start_column, end_column = ROLE_BOUNDS[role]
            role_start = values[start_column]
            role_end = values[end_column]
            if not role_start <= signal < role_end:
                violations.append(
                    {
                        "fold_id": fold_id,
                        "type": f"{role}_signal_outside_role",
                        "event_id": row["range_action_event_id"],
                    }
                )
            bool_columns = [
                "future_data_complete_bool",
                "future_outcome_eligible_bool",
                "causal_provenance_complete_bool",
            ]
            if any(type(row[column]) is not bool for column in bool_columns):
                violations.append(
                    {
                        "fold_id": fold_id,
                        "type": "invalid_boolean_value",
                        "event_id": row["range_action_event_id"],
                    }
                )
                continue
            expected_entry = ((decision // MINUTE_MS) + 1) * MINUTE_MS
            expected_eligible = row["future_data_complete_bool"]
            invalid_window_contract = (
                signal < 0
                or decision < 0
                or entry < 0
                or outcome_end < 0
                or decision != signal
                or entry != expected_entry
                or horizon <= 0
                or outcome_end != entry + horizon * MINUTE_MS
                or row["outcome_semantics_version"] != OUTCOME_SEMANTICS_VERSION
                or row["outcome_window_semantics_version"]
                != OUTCOME_WINDOW_SEMANTICS_VERSION
                or row["actionable_event_semantics_version"]
                != ACTIONABLE_EVENT_SEMANTICS_VERSION
                or row["decision_time_source"] != "event_decision_time"
                or row["causal_provenance_complete_bool"] is not True
                or row["future_outcome_eligible_bool"] is not expected_eligible
                or row["future_outcome_eligible_bool"] is not True
            )
            if invalid_window_contract:
                violations.append(
                    {
                        "fold_id": fold_id,
                        "type": "invalid_persisted_outcome_window",
                        "event_id": row["range_action_event_id"],
                    }
                )
            if outcome_end > role_end:
                violations.append(
                    {
                        "fold_id": fold_id,
                        "type": f"{role}_outcome_crosses_role_end",
                        "event_id": row["range_action_event_id"],
                    }
                )
    return _result(violations)


def write_leakage_audit(scoring_run_id: str) -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    result = audit_splits(pl.read_parquet(root / "walk_forward_splits.parquet"))
    parquet_row = {k: v for k, v in result.items() if k != "violations"}
    parquet_row["violations_json"] = json.dumps(result["violations"], sort_keys=True)
    pl.DataFrame([parquet_row]).write_parquet(root / "walk_forward_leakage_audit.parquet")
    (root / "walk_forward_temporal_leakage_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "walk_forward_leakage_audit_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    report_root = Path("reports/scoring_runs") / scoring_run_id
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "walk_forward_leakage_audit_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    if result["leakage_violations"]:
        raise ValueError(json.dumps(result, sort_keys=True))
    return result
