from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import polars as pl


PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
OUTCOME_BOUNDARY_SEMANTICS_VERSION = "persisted-exclusive-outcome-end-v1"
OUTCOME_SEMANTICS_VERSION = "v5_exact_outcome_window_provenance"
OUTCOME_WINDOW_SEMANTICS_VERSION = "exact-minute-outcome-window-v1"
ACTIONABLE_EVENT_SEMANTICS_VERSION = "range-actionable-prefix-invariance-v1"
CANONICAL_OUTCOME_END_COLUMN = "outcome_end_exclusive_ms"
LEGACY_OUTCOME_END_COLUMN = "outcome_end_ms"
MINUTE_MS = 60_000
DAY_MS = 86_400_000

PROFILES = {
    "prototype_90d": {
        "min_train_days": 45,
        "validation_days": 14,
        "test_days": 14,
        "step_days": 14,
        "purge_minutes": 2880,
        "embargo_minutes": 2880,
        "max_outcome_horizon_minutes": 2880,
    },
    "long_history": {
        "min_train_days": 365,
        "validation_days": 90,
        "test_days": 90,
        "step_days": 30,
        "purge_minutes": 2880,
        "embargo_minutes": 2880,
        "max_outcome_horizon_minutes": 2880,
    },
}

REQUIRED_EVENT_COLUMNS = [
    "range_action_event_id",
    "range_regime_id",
    "signal_time_ms",
    "future_horizon_minutes",
    "future_data_complete_bool",
    "future_outcome_eligible_bool",
    "outcome_semantics_version",
    "outcome_window_semantics_version",
    "actionable_event_semantics_version",
    "decision_time_source",
    "causal_provenance_complete_bool",
    "decision_time_ms",
    "entry_time_ms",
    CANONICAL_OUTCOME_END_COLUMN,
]

RECONCILIATION_REASONS = [
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
]


@dataclass(frozen=True)
class SplitProfile:
    min_train_days: int
    validation_days: int
    test_days: int
    step_days: int
    purge_minutes: int
    embargo_minutes: int
    max_outcome_horizon_minutes: int = 2880


def _empty_splits() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "fold_id": pl.String,
            "role": pl.String,
            "range_action_event_id": pl.String,
            "range_regime_id": pl.String,
            "signal_time_ms": pl.Int64,
            "decision_time_ms": pl.Int64,
            "entry_time_ms": pl.Int64,
            CANONICAL_OUTCOME_END_COLUMN: pl.Int64,
            "future_horizon_minutes": pl.Int64,
            "future_data_complete_bool": pl.Boolean,
            "future_outcome_eligible_bool": pl.Boolean,
            "outcome_semantics_version": pl.String,
            "outcome_window_semantics_version": pl.String,
            "actionable_event_semantics_version": pl.String,
            "decision_time_source": pl.String,
            "causal_provenance_complete_bool": pl.Boolean,
            "symbol": pl.String,
            "outcome_boundary_semantics_version": pl.String,
            "train_start_ms": pl.Int64,
            "train_end_ms": pl.Int64,
            "validation_start_ms": pl.Int64,
            "validation_end_ms": pl.Int64,
            "test_start_ms": pl.Int64,
            "test_end_ms": pl.Int64,
            "purge_minutes": pl.Int64,
            "embargo_minutes": pl.Int64,
            "persisted_outcome_end_required_bool": pl.Boolean,
            "derived_outcome_end_count": pl.Int64,
            "legacy_outcome_end_column_allowed_bool": pl.Boolean,
        }
    )


def _empty_disposition_ledger() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "fold_id": pl.String,
            "range_action_event_id": pl.String,
            "range_regime_id": pl.String,
            "role": pl.String,
            "exclusion_or_assignment_reason": pl.String,
            "signal_time_ms": pl.Int64,
            "decision_time_ms": pl.Int64,
            "entry_time_ms": pl.Int64,
            "future_horizon_minutes": pl.Int64,
            "max_outcome_horizon_minutes": pl.Int64,
            CANONICAL_OUTCOME_END_COLUMN: pl.Int64,
            "future_data_complete_bool": pl.Boolean,
            "future_outcome_eligible_bool": pl.Boolean,
            "outcome_semantics_version": pl.String,
            "outcome_window_semantics_version": pl.String,
            "actionable_event_semantics_version": pl.String,
            "decision_time_source": pl.String,
            "causal_provenance_complete_bool": pl.Boolean,
            "symbol": pl.String,
            "train_start_ms": pl.Int64,
            "train_end_ms": pl.Int64,
            "validation_start_ms": pl.Int64,
            "validation_end_ms": pl.Int64,
            "test_start_ms": pl.Int64,
            "test_end_ms": pl.Int64,
            "purge_minutes": pl.Int64,
            "embargo_minutes": pl.Int64,
            "outcome_boundary_semantics_version": pl.String,
            "persisted_outcome_end_required_bool": pl.Boolean,
            "derived_outcome_end_count": pl.Int64,
            "legacy_outcome_end_column_allowed_bool": pl.Boolean,
        }
    )


def _contract_error(kind: str, **details: object) -> ValueError:
    return ValueError(json.dumps({"error": kind, **details}, sort_keys=True))


def _validate_events(events: pl.DataFrame) -> None:
    if LEGACY_OUTCOME_END_COLUMN in events.columns:
        raise _contract_error(
            "legacy_outcome_end_column_forbidden", column=LEGACY_OUTCOME_END_COLUMN
        )
    missing = [c for c in REQUIRED_EVENT_COLUMNS if c not in events.columns]
    if missing:
        raise _contract_error("missing_required_walk_forward_columns", columns=missing)
    if events.is_empty():
        return
    duplicate_count = events.height - events.select(
        ["range_action_event_id", "future_horizon_minutes"]
    ).unique().height
    if duplicate_count:
        raise _contract_error("duplicate_event_horizon_rows", count=duplicate_count)

    invariant_columns = [
        "range_regime_id",
        "signal_time_ms",
        "outcome_semantics_version",
        "outcome_window_semantics_version",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
        "decision_time_ms",
        "entry_time_ms",
    ]
    if "symbol" in events.columns:
        invariant_columns.append("symbol")
    inconsistent = (
        events.group_by("range_action_event_id")
        .agg(pl.struct(invariant_columns).n_unique().alias("variant_count"))
        .filter(pl.col("variant_count") != 1)
    )
    if inconsistent.height:
        raise _contract_error(
            "inconsistent_event_metadata_across_horizons", count=inconsistent.height
        )

    expected_versions = {
        "outcome_semantics_version": OUTCOME_SEMANTICS_VERSION,
        "outcome_window_semantics_version": OUTCOME_WINDOW_SEMANTICS_VERSION,
        "actionable_event_semantics_version": ACTIONABLE_EVENT_SEMANTICS_VERSION,
    }
    for column, expected in expected_versions.items():
        actual = sorted(str(v) for v in events[column].drop_nulls().unique().to_list())
        if actual != [expected] or events[column].null_count():
            raise _contract_error(
                "invalid_outcome_semantics_version",
                column=column,
                expected=expected,
                actual=actual,
                null_count=events[column].null_count(),
            )

    int_columns = [
        "signal_time_ms",
        "decision_time_ms",
        "entry_time_ms",
        "future_horizon_minutes",
        CANONICAL_OUTCOME_END_COLUMN,
    ]
    bool_columns = [
        "causal_provenance_complete_bool",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
    ]
    id_columns = ["range_action_event_id", "range_regime_id"]
    for index, row in enumerate(events.iter_rows(named=True)):
        for column in int_columns:
            if type(row[column]) is not int:
                raise _contract_error(
                    "invalid_integer_value", row=index, column=column
                )
        for column in bool_columns:
            if type(row[column]) is not bool:
                raise _contract_error(
                    "invalid_boolean_value", row=index, column=column
                )
        for column in id_columns:
            if not isinstance(row[column], str) or not row[column]:
                raise _contract_error("invalid_identifier", row=index, column=column)
        signal = row["signal_time_ms"]
        decision = row["decision_time_ms"]
        entry = row["entry_time_ms"]
        horizon = row["future_horizon_minutes"]
        outcome_end = row[CANONICAL_OUTCOME_END_COLUMN]
        if any(row[column] < 0 for column in int_columns[:-2]) or outcome_end < 0:
            raise _contract_error("negative_outcome_timestamp", row=index)
        if horizon <= 0:
            raise _contract_error("non_positive_horizon", row=index)
        if decision != signal:
            raise _contract_error("decision_signal_mismatch", row=index)
        expected_entry = ((decision // MINUTE_MS) + 1) * MINUTE_MS
        if entry != expected_entry:
            raise _contract_error("entry_not_next_minute", row=index)
        if outcome_end != entry + horizon * MINUTE_MS:
            raise _contract_error(
                "persisted_outcome_end_mismatch",
                row=index,
                expected=entry + horizon * MINUTE_MS,
                actual=outcome_end,
            )
        if row["decision_time_source"] != "event_decision_time":
            raise _contract_error("invalid_decision_time_source", row=index)
        if row["causal_provenance_complete_bool"] is not True:
            raise _contract_error("incomplete_causal_provenance", row=index)
        expected_eligible = row["future_data_complete_bool"]
        if row["future_outcome_eligible_bool"] is not expected_eligible:
            raise _contract_error("outcome_eligibility_mismatch", row=index)


def build_splits(events: pl.DataFrame, profile_name: str = "prototype_90d") -> pl.DataFrame:
    cfg = SplitProfile(**PROFILES[profile_name])
    _validate_events(events)
    if events.is_empty():
        out = _empty_splits()
        out.attrs = {
            "fold_summary": [],
            "reason_summary": [],
            "disposition_ledger": [],
            "source_event_count": 0,
            "missing_max_horizon_count": 0,
            "ineligible_max_horizon_count": 0,
            "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
        }
        return out
    source_event_ids = set(events["range_action_event_id"].to_list())
    source_event_count = len(source_event_ids)
    max_rows = events.filter(
        pl.col("future_horizon_minutes") == cfg.max_outcome_horizon_minutes
    )
    max_event_ids = set(max_rows["range_action_event_id"].to_list())
    missing_max_ids = source_event_ids - max_event_ids
    eligible_max = max_rows.filter(
        pl.col("future_data_complete_bool")
        & pl.col("future_outcome_eligible_bool")
    )
    eligible_event_ids = set(eligible_max["range_action_event_id"].to_list())
    ineligible_max_ids = max_event_ids - eligible_event_ids

    selected_columns = [
        "range_action_event_id",
        "range_regime_id",
        "signal_time_ms",
        "future_horizon_minutes",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
        "outcome_semantics_version",
        "outcome_window_semantics_version",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
        "decision_time_ms",
        "entry_time_ms",
        CANONICAL_OUTCOME_END_COLUMN,
    ]
    if "symbol" in eligible_max.columns:
        selected_columns.append("symbol")
    eligible = eligible_max.select(selected_columns).sort("signal_time_ms")
    source_columns = [
        "range_action_event_id",
        "range_regime_id",
        "signal_time_ms",
        "decision_time_ms",
        "entry_time_ms",
        "outcome_semantics_version",
        "outcome_window_semantics_version",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
    ]
    if "symbol" in events.columns:
        source_columns.append("symbol")
    source_events = events.select(source_columns).unique("range_action_event_id").sort(
        "signal_time_ms"
    )
    source_lookup = {
        row["range_action_event_id"]: row for row in source_events.iter_rows(named=True)
    }
    max_lookup = {
        row["range_action_event_id"]: row for row in max_rows.iter_rows(named=True)
    }
    start = int(source_events["signal_time_ms"].min())
    end = int(source_events["signal_time_ms"].max())
    rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    reason_rows: list[dict[str, object]] = []
    fold = 0
    cursor = start + cfg.min_train_days * DAY_MS
    while (
        cursor
        + cfg.purge_minutes * MINUTE_MS
        + (cfg.validation_days + cfg.test_days) * DAY_MS
        + cfg.embargo_minutes * MINUTE_MS
        <= end
    ):
        train_start = start
        train_end = cursor
        validation_start = cursor + cfg.purge_minutes * MINUTE_MS
        validation_end = validation_start + cfg.validation_days * DAY_MS
        test_start = validation_end + cfg.embargo_minutes * MINUTE_MS
        test_end = test_start + cfg.test_days * DAY_MS
        bounds = [
            ("train", train_start, train_end),
            ("validation", validation_start, validation_end),
            ("test", test_start, test_end),
        ]
        categories = {eid: "missing_max_horizon" for eid in missing_max_ids}
        categories.update({eid: "ineligible_max_horizon" for eid in ineligible_max_ids})
        tentative: list[dict[str, object]] = []
        for row in eligible.iter_rows(named=True):
            signal = row["signal_time_ms"]
            event_id = row["range_action_event_id"]
            role: str | None = None
            role_end: int | None = None
            if signal < train_start or signal >= test_end:
                categories[event_id] = "outside_fold_window"
            elif train_end <= signal < validation_start:
                categories[event_id] = "purge_gap"
            elif validation_end <= signal < test_start:
                categories[event_id] = "embargo_gap"
            else:
                for candidate_role, lower, upper in bounds:
                    if lower <= signal < upper:
                        role = candidate_role
                        role_end = upper
                        break
                if role is None or role_end is None:
                    categories[event_id] = "unassigned"
                elif row[CANONICAL_OUTCOME_END_COLUMN] > role_end:
                    categories[event_id] = f"{role}_horizon_boundary"
                else:
                    tentative.append({**row, "role": role})

        regime_roles: dict[object, set[str]] = {}
        for row in tentative:
            regime_roles.setdefault(row["range_regime_id"], set()).add(str(row["role"]))
        cross_regimes = {regime for regime, roles in regime_roles.items() if len(roles) > 1}
        assigned: list[dict[str, object]] = []
        for row in tentative:
            event_id = row["range_action_event_id"]
            if row["range_regime_id"] in cross_regimes:
                categories[event_id] = "cross_role_regime_excluded"
            else:
                categories[event_id] = f"{row['role']}_assigned"
                assigned.append(row)
        for event_id in source_event_ids:
            categories.setdefault(event_id, "unassigned")

        counts = {
            reason: sum(1 for category in categories.values() if category == reason)
            for reason in RECONCILIATION_REASONS
        }
        reconciled_count = sum(counts.values())
        reconciliation_delta = reconciled_count - source_event_count
        reconciliation_ok = reconciliation_delta == 0 and counts["unassigned"] == 0
        fold_id = f"wf_{fold:03d}"
        for reason, count in counts.items():
            reason_rows.append(
                {
                    "fold_id": fold_id,
                    "exclusion_or_assignment_reason": reason,
                    "event_count": count,
                    "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
                }
            )

        common = {
            "train_start_ms": train_start,
            "train_end_ms": train_end,
            "validation_start_ms": validation_start,
            "validation_end_ms": validation_end,
            "test_start_ms": test_start,
            "test_end_ms": test_end,
            "purge_minutes": cfg.purge_minutes,
            "embargo_minutes": cfg.embargo_minutes,
            "purged_event_count": counts["purge_gap"],
            "embargo_excluded_event_count": counts["embargo_gap"],
            "regime_excluded_event_count": counts["cross_role_regime_excluded"],
            "configured_train_days": cfg.min_train_days,
            "actual_train_days": (train_end - train_start) / DAY_MS,
            "purge_gap_minutes": cfg.purge_minutes,
            "validation_days": cfg.validation_days,
            "embargo_gap_minutes": cfg.embargo_minutes,
            "test_days": cfg.test_days,
            "source_event_count": source_event_count,
            "complete_label_event_count": len(eligible_event_ids),
            "missing_max_horizon_count": len(missing_max_ids),
            "ineligible_label_excluded_count": len(ineligible_max_ids),
            "ineligible_max_horizon_count": len(ineligible_max_ids),
            "incomplete_label_excluded_count": len(ineligible_max_ids),
            "incomplete_max_horizon_count": len(ineligible_max_ids),
            "outside_fold_window_count": counts["outside_fold_window"],
            "unassigned_event_count": counts["unassigned"],
            "coverage_reconciliation_ok": reconciliation_ok,
            "coverage_reconciliation_delta": reconciliation_delta,
            "walk_forward_scope": profile_name,
            "sufficient_for_parameter_selection_bool": False,
            "sufficient_for_state_machine_engineering_bool": True,
            "risk_budget_proven_bool": False,
            "live_authorized_bool": False,
            "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
            "persisted_outcome_end_required_bool": True,
            "derived_outcome_end_count": 0,
            "legacy_outcome_end_column_allowed_bool": False,
        }
        for row in assigned:
            rows.append(
                {
                    "fold_id": fold_id,
                    "role": row["role"],
                    "range_action_event_id": row["range_action_event_id"],
                    "range_regime_id": row["range_regime_id"],
                    "signal_time_ms": row["signal_time_ms"],
                    "decision_time_ms": row["decision_time_ms"],
                    "entry_time_ms": row["entry_time_ms"],
                    CANONICAL_OUTCOME_END_COLUMN: row[CANONICAL_OUTCOME_END_COLUMN],
                    "future_horizon_minutes": row["future_horizon_minutes"],
                    "future_data_complete_bool": row["future_data_complete_bool"],
                    "future_outcome_eligible_bool": row["future_outcome_eligible_bool"],
                    "outcome_semantics_version": row["outcome_semantics_version"],
                    "outcome_window_semantics_version": row[
                        "outcome_window_semantics_version"
                    ],
                    "actionable_event_semantics_version": row[
                        "actionable_event_semantics_version"
                    ],
                    "decision_time_source": row["decision_time_source"],
                    "causal_provenance_complete_bool": row[
                        "causal_provenance_complete_bool"
                    ],
                    "symbol": row.get("symbol"),
                    **common,
                }
            )
        for event_id in sorted(source_event_ids):
            source_row = source_lookup[event_id]
            max_row = max_lookup.get(event_id)
            reason = categories[event_id]
            role = reason.removesuffix("_assigned") if reason.endswith("_assigned") else None
            ledger_rows.append(
                {
                    "fold_id": fold_id,
                    "range_action_event_id": event_id,
                    "range_regime_id": source_row["range_regime_id"],
                    "role": role,
                    "exclusion_or_assignment_reason": reason,
                    "signal_time_ms": source_row["signal_time_ms"],
                    "decision_time_ms": source_row["decision_time_ms"],
                    "entry_time_ms": source_row["entry_time_ms"],
                    "future_horizon_minutes": (
                        max_row["future_horizon_minutes"] if max_row is not None else None
                    ),
                    "max_outcome_horizon_minutes": cfg.max_outcome_horizon_minutes,
                    CANONICAL_OUTCOME_END_COLUMN: (
                        max_row[CANONICAL_OUTCOME_END_COLUMN]
                        if max_row is not None
                        else None
                    ),
                    "future_data_complete_bool": (
                        max_row["future_data_complete_bool"] if max_row is not None else None
                    ),
                    "future_outcome_eligible_bool": (
                        max_row["future_outcome_eligible_bool"] if max_row is not None else None
                    ),
                    "outcome_semantics_version": source_row["outcome_semantics_version"],
                    "outcome_window_semantics_version": source_row[
                        "outcome_window_semantics_version"
                    ],
                    "actionable_event_semantics_version": source_row[
                        "actionable_event_semantics_version"
                    ],
                    "decision_time_source": source_row["decision_time_source"],
                    "causal_provenance_complete_bool": source_row[
                        "causal_provenance_complete_bool"
                    ],
                    "symbol": source_row.get("symbol"),
                    "train_start_ms": train_start,
                    "train_end_ms": train_end,
                    "validation_start_ms": validation_start,
                    "validation_end_ms": validation_end,
                    "test_start_ms": test_start,
                    "test_end_ms": test_end,
                    "purge_minutes": cfg.purge_minutes,
                    "embargo_minutes": cfg.embargo_minutes,
                    "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
                    "persisted_outcome_end_required_bool": True,
                    "derived_outcome_end_count": 0,
                    "legacy_outcome_end_column_allowed_bool": False,
                }
            )
        summary_rows.append(
            {
                "fold_id": fold_id,
                "train_events": counts["train_assigned"],
                "validation_events": counts["validation_assigned"],
                "test_events": counts["test_assigned"],
                "purge_gap_event_count": counts["purge_gap"],
                "embargo_gap_event_count": counts["embargo_gap"],
                "cross_role_regime_excluded_event_count": counts[
                    "cross_role_regime_excluded"
                ],
                "train_horizon_boundary_excluded_count": counts[
                    "train_horizon_boundary"
                ],
                "validation_horizon_boundary_excluded_count": counts[
                    "validation_horizon_boundary"
                ],
                "test_horizon_boundary_excluded_count": counts["test_horizon_boundary"],
                **common,
            }
        )
        fold += 1
        cursor += cfg.step_days * DAY_MS

    out = pl.DataFrame(rows) if rows else _empty_splits()
    out.attrs = {
        "fold_summary": summary_rows,
        "reason_summary": reason_rows,
        "disposition_ledger": ledger_rows,
        "source_event_count": source_event_count,
        "missing_max_horizon_count": len(missing_max_ids),
        "ineligible_max_horizon_count": len(ineligible_max_ids),
        "incomplete_max_horizon_count": len(ineligible_max_ids),
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
    }
    return out


def write_splits(scoring_run_id: str, profile: str = "prototype_90d") -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    events = pl.read_parquet(root / "event_horizon.parquet")
    out = build_splits(events, profile)
    out.write_parquet(root / "walk_forward_splits.parquet")
    ledger_rows = out.attrs.get("disposition_ledger", [])
    ledger = pl.DataFrame(ledger_rows) if ledger_rows else _empty_disposition_ledger()
    ledger.write_parquet(root / "walk_forward_event_eligibility.parquet")
    fold_summary = pl.DataFrame(out.attrs.get("fold_summary", []))
    reason_summary = pl.DataFrame(out.attrs.get("reason_summary", []))
    if not fold_summary.is_empty():
        fold_summary.write_parquet(root / "walk_forward_fold_summary.parquet")
        reason_summary.write_parquet(root / "walk_forward_exclusion_reason_summary.parquet")
    report_root = Path("reports/scoring_runs") / scoring_run_id
    report_root.mkdir(parents=True, exist_ok=True)
    report_root.joinpath("walk_forward_design_report.md").write_text(
        "# Walk-Forward Design\n\n"
        f"profile: {profile}\n"
        f"fold_count: {fold_summary.height}\n"
        f"walk_forward_scope: {profile}\n"
        f"outcome_boundary_semantics_version: {OUTCOME_BOUNDARY_SEMANTICS_VERSION}\n"
        "persisted_outcome_end_required_bool: true\n"
        "derived_outcome_end_count: 0\n"
        "legacy_outcome_end_column_allowed_bool: false\n"
        "sufficient_for_parameter_selection_bool: false\n"
        "sufficient_for_state_machine_engineering_bool: true\n"
        "risk_budget_proven_bool: false\n"
        "live_authorized_bool: false\n\n"
        "Every event is reconciled per fold, including missing and ineligible maximum "
        "horizons. Role admission consumes the persisted exclusive outcome end and allows "
        "exact equality with that role's end. No robust parameter selection is claimed.\n",
        encoding="utf-8",
    )
    ledger_duplicate_count = (
        ledger.height
        - ledger.select(["fold_id", "range_action_event_id"]).unique().height
        if not ledger.is_empty()
        else 0
    )
    expected_ledger_rows = (
        int(fold_summary["source_event_count"].sum()) if not fold_summary.is_empty() else 0
    )
    ledger_reconciliation_ok = (
        not ledger.is_empty()
        and ledger_duplicate_count == 0
        and ledger.height == expected_ledger_rows
    )
    coverage_ok = (
        (not fold_summary.is_empty())
        and bool(fold_summary["coverage_reconciliation_ok"].all())
        and ledger_reconciliation_ok
    )
    coverage = {
        "walk_forward_coverage_audit_ok": coverage_ok,
        "fold_count": fold_summary.height,
        "walk_forward_scope": profile,
        "sufficient_for_parameter_selection_bool": False,
        "sufficient_for_state_machine_engineering_bool": True,
        "risk_budget_proven_bool": False,
        "live_authorized_bool": False,
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
        "persisted_outcome_end_required_bool": True,
        "derived_outcome_end_count": 0,
        "legacy_outcome_end_column_allowed_bool": False,
        "incomplete_max_horizon_events_excluded_bool": True,
        "ineligible_max_horizon_events_excluded_bool": True,
        "missing_max_horizon_events_reconciled_bool": True,
        "full_disposition_ledger_bool": True,
        "disposition_ledger_row_count": ledger.height,
        "disposition_ledger_expected_row_count": expected_ledger_rows,
        "disposition_ledger_duplicate_fold_event_count": ledger_duplicate_count,
        "disposition_ledger_reconciliation_ok": ledger_reconciliation_ok,
        "source_event_count": out.attrs.get("source_event_count", 0),
        "missing_max_horizon_count": out.attrs.get("missing_max_horizon_count", 0),
        "ineligible_max_horizon_count": out.attrs.get("ineligible_max_horizon_count", 0),
        "incomplete_max_horizon_count": out.attrs.get("incomplete_max_horizon_count", 0),
        "coverage_reconciliation_ok": coverage_ok,
        "coverage_reconciliation_delta": (
            int(fold_summary["coverage_reconciliation_delta"].sum())
            if not fold_summary.is_empty()
            else None
        ),
        "unassigned_event_count": (
            int(fold_summary["unassigned_event_count"].sum())
            if not fold_summary.is_empty()
            else None
        ),
        "folds": fold_summary.to_dicts() if not fold_summary.is_empty() else [],
    }
    (root / "walk_forward_coverage_audit.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "walk_forward_fold_count": out["fold_id"].n_unique() if not out.is_empty() else 0,
        "rows": out.height,
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
        "persisted_outcome_end_required_bool": True,
        "derived_outcome_end_count": 0,
    }
