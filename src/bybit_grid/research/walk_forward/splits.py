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
    e = (
        events.select(
            [
                c
                for c in ["range_action_event_id", "range_regime_id", time_col, "symbol"]
                if c in events.columns
            ]
        )
        .unique()
        .sort(time_col)
    )
    e = e.with_columns(
        (pl.col(time_col) + cfg.max_outcome_horizon_minutes * 60_000).alias("outcome_end_ms")
    )
    start = e[time_col].min()
    end = e[time_col].max()
    day = 86_400_000
    rows = []
    fold = 0
    cursor = start + cfg.min_train_days * day
    while cursor + (cfg.validation_days + cfg.test_days) * day <= end:
        val_start = cursor
        val_end = val_start + cfg.validation_days * day
        test_start = val_end + cfg.embargo_minutes * 60_000
        test_end = test_start + cfg.test_days * day
        train_end = val_start - cfg.purge_minutes * 60_000
        bounds = [
            ("train", start, train_end, train_end),
            ("validation", val_start, val_end, val_end),
            ("test", test_start, test_end, test_end),
        ]
        assigned = set()
        regime_excl = 0
        purged = e.filter((pl.col(time_col) >= train_end) & (pl.col(time_col) < val_start)).height
        emb = e.filter((pl.col(time_col) >= val_end) & (pl.col(time_col) < test_start)).height
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
                    }
                )
        fold += 1
        cursor += cfg.step_days * day
    return pl.DataFrame(rows)


def write_splits(scoring_run_id: str, profile: str = "prototype_90d") -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    df = pl.read_parquet(root / "event_horizon.parquet")
    out = build_splits(df, profile)
    out.write_parquet(root / "walk_forward_splits.parquet")
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
            ]
        ).write_parquet(root / "walk_forward_fold_summary.parquet")
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    rep.joinpath("walk_forward_design_report.md").write_text(
        f"# Walk-Forward Design\n\nprofile: {profile}\nfold_count: {out['fold_id'].n_unique() if not out.is_empty() else 0}\nNo parameter selection is performed.\n",
        encoding="utf-8",
    )
    return {
        "walk_forward_fold_count": out["fold_id"].n_unique() if not out.is_empty() else 0,
        "rows": out.height,
    }
