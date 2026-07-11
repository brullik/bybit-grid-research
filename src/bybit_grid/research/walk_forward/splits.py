from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import polars as pl

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


@dataclass(frozen=True)
class SplitProfile:
    min_train_days: int
    validation_days: int
    test_days: int
    step_days: int
    purge_minutes: int
    embargo_minutes: int
    max_outcome_horizon_minutes: int = 2880


def build_splits(events: pl.DataFrame, profile_name: str = "prototype_90d") -> pl.DataFrame:
    cfg = SplitProfile(**PROFILES[profile_name])
    if events.is_empty():
        out = pl.DataFrame(
            {"fold_id": [], "role": [], "range_action_event_id": [], "range_regime_id": []}
        )
        out.attrs = {"fold_summary": [], "reason_summary": []}
        return out
    time_col = "signal_time_ms" if "signal_time_ms" in events.columns else "event_time_ms"
    source_event_count = events["range_action_event_id"].n_unique()
    max_rows = events.filter(pl.col("future_horizon_minutes") == cfg.max_outcome_horizon_minutes) if "future_horizon_minutes" in events.columns else events
    if "future_data_complete_bool" not in max_rows.columns:
        max_rows = max_rows.with_columns(pl.lit(True).alias("future_data_complete_bool"))
    if "outcome_end_ms" not in max_rows.columns:
        max_rows = max_rows.with_columns((pl.col(time_col) + cfg.max_outcome_horizon_minutes * 60_000).alias("outcome_end_ms"))
    e_all = max_rows.select([c for c in ["range_action_event_id", "range_regime_id", time_col, "symbol", "future_data_complete_bool", "outcome_end_ms"] if c in max_rows.columns]).unique().sort(time_col)
    e = e_all.filter(
        pl.col("future_data_complete_bool")
        & pl.col("range_action_event_id").is_not_null()
        & pl.col("range_regime_id").is_not_null()
        & pl.col(time_col).is_not_null()
    )
    incomplete_label_excluded_count = source_event_count - e["range_action_event_id"].n_unique()
    start = e[time_col].min()
    end = e[time_col].max()
    day = 86_400_000
    rows = []
    summary_rows = []
    reason_rows = []
    fold = 0
    cursor = start + cfg.min_train_days * day
    while (
        cursor
        + cfg.purge_minutes * 60_000
        + (cfg.validation_days + cfg.test_days) * day
        + cfg.embargo_minutes * 60_000
        <= end
    ):
        val_start = cursor + cfg.purge_minutes * 60_000
        val_end = val_start + cfg.validation_days * day
        test_start = val_end + cfg.embargo_minutes * 60_000
        test_end = test_start + cfg.test_days * day
        train_end = cursor
        bounds = [
            ("train", start, train_end, train_end),
            ("validation", val_start, val_end, val_end),
            ("test", test_start, test_end, test_end),
        ]
        categories = {r["range_action_event_id"]: "incomplete_max_horizon" for r in e_all.filter(~pl.col("future_data_complete_bool")).iter_rows(named=True)}
        tentative: list[dict[str, object]] = []
        boundary_counts = {"train": 0, "validation": 0, "test": 0}
        for r in e.iter_rows(named=True):
            t = r[time_col]
            eid = r["range_action_event_id"]
            role = None
            role_end = None
            if t < start or t >= test_end:
                categories[eid] = "outside_fold_window"
            elif train_end <= t < val_start:
                categories[eid] = "purge_gap"
            elif val_end <= t < test_start:
                categories[eid] = "embargo_gap"
            else:
                for b_role, lo, hi, out_hi in bounds:
                    if lo <= t < hi:
                        role = b_role
                        role_end = out_hi
                        break
                if role is None:
                    categories[eid] = "unassigned"
                elif r["outcome_end_ms"] > role_end:
                    categories[eid] = f"{role}_horizon_boundary"
                    boundary_counts[role] += 1
                else:
                    tentative.append({**r, "role": role})
        regime_roles: dict[object, set[str]] = {}
        for r in tentative:
            regime_roles.setdefault(r["range_regime_id"], set()).add(str(r["role"]))
        cross_regimes = {reg for reg, roles in regime_roles.items() if len(roles) > 1}
        for r in tentative:
            eid = r["range_action_event_id"]
            if r["range_regime_id"] in cross_regimes:
                categories[eid] = "cross_role_regime_excluded"
            else:
                categories[eid] = f"{r['role']}_assigned"
                rows.append(
                    {
                        "fold_id": f"wf_{fold:03d}",
                        "role": r["role"],
                        "range_action_event_id": eid,
                        "range_regime_id": r["range_regime_id"],
                        "signal_time_ms": r[time_col],
                        "outcome_end_ms": r["outcome_end_ms"],
                        "symbol": r.get("symbol"),
                        "train_start_ms": start,
                        "train_end_ms": train_end,
                        "validation_start_ms": val_start,
                        "validation_end_ms": val_end,
                        "test_start_ms": test_start,
                        "test_end_ms": test_end,
                        "purge_minutes": cfg.purge_minutes,
                        "embargo_minutes": cfg.embargo_minutes,
                        "purged_event_count": 0,
                        "embargo_excluded_event_count": 0,
                        "regime_excluded_event_count": 0,
                        "configured_train_days": cfg.min_train_days,
                        "actual_train_days": (train_end - start) / day,
                        "purge_gap_minutes": cfg.purge_minutes,
                        "validation_days": cfg.validation_days,
                        "embargo_gap_minutes": cfg.embargo_minutes,
                        "test_days": cfg.test_days,
                        "source_event_count": source_event_count,
                        "complete_label_event_count": e["range_action_event_id"].n_unique(),
                        "incomplete_label_excluded_count": incomplete_label_excluded_count,
                        "outside_fold_window_count": 0,
                        "unassigned_event_count": 0,
                        "coverage_reconciliation_ok": True,
                        "coverage_reconciliation_delta": 0,
                        "walk_forward_scope": profile_name,
                        "sufficient_for_parameter_selection_bool": False,
                        "sufficient_for_state_machine_engineering_bool": True,
                    }
                )
        for r in e.iter_rows(named=True):
            categories.setdefault(r["range_action_event_id"], "unassigned")
        counts = {name: sum(1 for c in categories.values() if c == name) for name in [
            "incomplete_max_horizon", "outside_fold_window", "purge_gap", "embargo_gap",
            "train_horizon_boundary", "validation_horizon_boundary", "test_horizon_boundary",
            "cross_role_regime_excluded", "train_assigned", "validation_assigned", "test_assigned", "unassigned"
        ]}
        rhs = sum(counts.values())
        delta = rhs - source_event_count
        ok = delta == 0 and counts["unassigned"] == 0
        fold_id = f"wf_{fold:03d}"
        for reason, count in counts.items():
            reason_rows.append({"fold_id": fold_id, "exclusion_or_assignment_reason": reason, "event_count": count})
        summary_rows.append({
            "fold_id": fold_id,
            "train_events": counts["train_assigned"],
            "validation_events": counts["validation_assigned"],
            "test_events": counts["test_assigned"],
            "train_start_ms": start,
            "train_end_ms": train_end,
            "validation_start_ms": val_start,
            "validation_end_ms": val_end,
            "test_start_ms": test_start,
            "test_end_ms": test_end,
            "purged_event_count": counts["purge_gap"],
            "purge_gap_event_count": counts["purge_gap"],
            "embargo_excluded_event_count": counts["embargo_gap"],
            "embargo_gap_event_count": counts["embargo_gap"],
            "regime_excluded_event_count": counts["cross_role_regime_excluded"],
            "cross_role_regime_excluded_event_count": counts["cross_role_regime_excluded"],
            "train_horizon_boundary_excluded_count": counts["train_horizon_boundary"],
            "validation_horizon_boundary_excluded_count": counts["validation_horizon_boundary"],
            "test_horizon_boundary_excluded_count": counts["test_horizon_boundary"],
            "configured_train_days": cfg.min_train_days,
            "actual_train_days": (train_end - start) / day,
            "purge_gap_minutes": cfg.purge_minutes,
            "validation_days": cfg.validation_days,
            "embargo_gap_minutes": cfg.embargo_minutes,
            "test_days": cfg.test_days,
            "source_event_count": source_event_count,
            "complete_label_event_count": e["range_action_event_id"].n_unique(),
            "incomplete_label_excluded_count": incomplete_label_excluded_count,
            "incomplete_max_horizon_count": counts["incomplete_max_horizon"],
            "outside_fold_window_count": counts["outside_fold_window"],
            "unassigned_event_count": counts["unassigned"],
            "coverage_reconciliation_ok": ok,
            "coverage_reconciliation_delta": delta,
            "walk_forward_scope": profile_name,
            "sufficient_for_parameter_selection_bool": False,
            "sufficient_for_state_machine_engineering_bool": True,
        })
        fold += 1
        cursor += cfg.step_days * day
    out = pl.DataFrame(rows)
    out.attrs = {"fold_summary": summary_rows, "reason_summary": reason_rows}
    return out


def write_splits(scoring_run_id: str, profile: str = "prototype_90d") -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    df = pl.read_parquet(root / "event_horizon.parquet")
    out = build_splits(df, profile)
    out.write_parquet(root / "walk_forward_splits.parquet")
    if not out.is_empty():
        out.select(
            ["range_action_event_id", "range_regime_id", "outcome_end_ms"]
        ).unique().write_parquet(root / "walk_forward_event_eligibility.parquet")
    fold_summary = pl.DataFrame(out.attrs.get("fold_summary", []))
    reason_summary = pl.DataFrame(out.attrs.get("reason_summary", []))
    if not fold_summary.is_empty():
        fold_summary.write_parquet(root / "walk_forward_fold_summary.parquet")
        reason_summary.write_parquet(root / "walk_forward_exclusion_reason_summary.parquet")
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    rep.joinpath("walk_forward_design_report.md").write_text(
        f"# Walk-Forward Design\n\nprofile: {profile}\nfold_count: {fold_summary.height}\nwalk_forward_scope: prototype_90d\nsufficient_for_parameter_selection_bool: false\nsufficient_for_state_machine_engineering_bool: true\nCoverage reconciliation is calculated per fold from disjoint event categories, including horizon-boundary and cross-role regime exclusions. No robust model selection is claimed.\n",
        encoding="utf-8",
    )
    (root / "walk_forward_coverage_audit.json").write_text(
        __import__("json").dumps(
            {
                "walk_forward_coverage_audit_ok": (not fold_summary.is_empty()) and bool(fold_summary["coverage_reconciliation_ok"].all()),
                "fold_count": fold_summary.height,
                "walk_forward_scope": "prototype_90d",
                "sufficient_for_parameter_selection_bool": False,
                "sufficient_for_state_machine_engineering_bool": True,
                "incomplete_max_horizon_events_excluded_bool": True,
                "coverage_reconciliation_ok": (not fold_summary.is_empty()) and bool(fold_summary["coverage_reconciliation_ok"].all()),
                "coverage_reconciliation_delta": int(fold_summary["coverage_reconciliation_delta"].sum()) if not fold_summary.is_empty() else None,
                "unassigned_event_count": int(fold_summary["unassigned_event_count"].sum()) if not fold_summary.is_empty() else None,
                "folds": fold_summary.to_dicts() if not fold_summary.is_empty() else [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "walk_forward_fold_count": out["fold_id"].n_unique() if not out.is_empty() else 0,
        "rows": out.height,
    }
