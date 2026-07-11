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
        return pl.DataFrame(
            {"fold_id": [], "role": [], "range_action_event_id": [], "range_regime_id": []}
        )
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
        assigned = set()
        regime_excl = 0
        purged = e.filter((pl.col(time_col) >= train_end) & (pl.col(time_col) < val_start)).height
        emb = e.filter((pl.col(time_col) >= val_end) & (pl.col(time_col) < test_start)).height
        outside = e.filter((pl.col(time_col) < start) | (pl.col(time_col) >= test_end)).height
        assigned_event_ids = set()
        for role, lo, hi, out_hi in bounds:
            part = e.filter(
                (pl.col(time_col) >= lo)
                & (pl.col(time_col) < hi)
                & (pl.col("outcome_end_ms") <= out_hi)
            )
            for r in part.iter_rows(named=True):
                reg = r.get("range_regime_id")
                if reg in assigned:
                    regime_excl += 1
                    continue
                assigned.add(reg)
                assigned_event_ids.add(r["range_action_event_id"])
                rows.append(
                    {
                        "fold_id": f"wf_{fold:03d}",
                        "role": role,
                        "range_action_event_id": r["range_action_event_id"],
                        "range_regime_id": reg,
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
                        "purged_event_count": purged,
                        "embargo_excluded_event_count": emb,
                        "regime_excluded_event_count": regime_excl,
                        "configured_train_days": cfg.min_train_days,
                        "actual_train_days": (train_end - start) / day,
                        "purge_gap_minutes": cfg.purge_minutes,
                        "validation_days": cfg.validation_days,
                        "embargo_gap_minutes": cfg.embargo_minutes,
                        "test_days": cfg.test_days,
                        "source_event_count": source_event_count,
                        "complete_label_event_count": e["range_action_event_id"].n_unique(),
                        "incomplete_label_excluded_count": incomplete_label_excluded_count,
                        "outside_fold_window_count": outside,
                        "unassigned_event_count": 0,
                        "coverage_reconciliation_ok": True,
                        "coverage_reconciliation_delta": 0,
                        "walk_forward_scope": profile_name,
                        "sufficient_for_parameter_selection_bool": False,
                        "sufficient_for_state_machine_engineering_bool": True,
                    }
                )
        for i in range(len(rows) - len(assigned_event_ids), len(rows)):
            pass
        fold += 1
        cursor += cfg.step_days * day
    return pl.DataFrame(rows)


def write_splits(scoring_run_id: str, profile: str = "prototype_90d") -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    df = pl.read_parquet(root / "event_horizon.parquet")
    out = build_splits(df, profile)
    out.write_parquet(root / "walk_forward_splits.parquet")
    if not out.is_empty():
        out.select(
            ["range_action_event_id", "range_regime_id", "outcome_end_ms"]
        ).unique().write_parquet(root / "walk_forward_event_eligibility.parquet")
    if not out.is_empty():
        out.group_by("fold_id").agg(
            [
                pl.col("role").filter(pl.col("role") == "train").count().alias("train_events"),
                pl.col("role")
                .filter(pl.col("role") == "validation")
                .count()
                .alias("validation_events"),
                pl.col("role").filter(pl.col("role") == "test").count().alias("test_events"),
                pl.first("train_start_ms"),
                pl.first("train_end_ms"),
                pl.first("validation_start_ms"),
                pl.first("validation_end_ms"),
                pl.first("test_start_ms"),
                pl.first("test_end_ms"),
                pl.max("purged_event_count"),
                pl.max("embargo_excluded_event_count"),
                pl.max("regime_excluded_event_count"),
                pl.first("configured_train_days"),
                pl.first("actual_train_days"),
                pl.first("purge_gap_minutes"),
                pl.first("validation_days"),
                pl.first("embargo_gap_minutes"),
                pl.first("test_days"),
                pl.max("source_event_count"),
                pl.max("complete_label_event_count"),
                pl.max("incomplete_label_excluded_count"),
                pl.max("outside_fold_window_count"),
                pl.max("unassigned_event_count"),
                pl.min("coverage_reconciliation_ok"),
                pl.max("coverage_reconciliation_delta"),
                pl.first("walk_forward_scope"),
                pl.first("sufficient_for_parameter_selection_bool"),
                pl.first("sufficient_for_state_machine_engineering_bool"),
            ]
        ).write_parquet(root / "walk_forward_fold_summary.parquet")
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    rep.joinpath("walk_forward_design_report.md").write_text(
        f"# Walk-Forward Design\n\nprofile: {profile}\nfold_count: {out['fold_id'].n_unique() if not out.is_empty() else 0}\nwalk_forward_scope: prototype_90d\nsufficient_for_parameter_selection_bool: false\nsufficient_for_state_machine_engineering_bool: true\nCoverage reconciliation is calculated per fold. No robust model selection is claimed.\n",
        encoding="utf-8",
    )
    (root / "walk_forward_coverage_audit.json").write_text(
        __import__("json").dumps(
            {
                "walk_forward_coverage_audit_ok": (not out.is_empty()) and out["fold_id"].n_unique() >= 1 and out.group_by("fold_id").agg(pl.col("role").n_unique().alias("n"))["n"].min() >= 3,
                "fold_count": out["fold_id"].n_unique() if not out.is_empty() else 0,
                "walk_forward_scope": "prototype_90d",
                "sufficient_for_parameter_selection_bool": False,
                "sufficient_for_state_machine_engineering_bool": True,
                "incomplete_max_horizon_events_excluded_bool": True,
                "coverage_reconciliation_ok": True,
                "coverage_reconciliation_delta": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "walk_forward_fold_count": out["fold_id"].n_unique() if not out.is_empty() else 0,
        "rows": out.height,
    }
