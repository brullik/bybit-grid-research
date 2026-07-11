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
    },
    "long_history": {
        "min_train_days": 365,
        "validation_days": 90,
        "test_days": 90,
        "step_days": 30,
        "purge_minutes": 2880,
        "embargo_minutes": 2880,
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
                for c in [
                    "range_action_event_id",
                    "range_regime_id",
                    time_col,
                    "symbol",
                    "future_horizon_minutes",
                ]
                if c in events.columns
            ]
        )
        .unique()
        .sort(time_col)
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
        test_start = val_end
        test_end = test_start + cfg.test_days * day
        train_end = val_start - (cfg.purge_minutes + cfg.embargo_minutes) * 60_000
        bounds = [
            ("train", start, train_end),
            ("validation", val_start, val_end),
            ("test", test_start, test_end),
        ]
        assigned_regimes = set()
        for role, lo, hi in bounds:
            part = e.filter((pl.col(time_col) >= lo) & (pl.col(time_col) < hi))
            for r in part.iter_rows(named=True):
                reg = r.get("range_regime_id")
                if reg in assigned_regimes:
                    continue
                assigned_regimes.add(reg)
                rows.append(
                    {
                        "fold_id": f"wf_{fold:03d}",
                        "role": role,
                        "range_action_event_id": r["range_action_event_id"],
                        "range_regime_id": reg,
                        "signal_time_ms": r[time_col],
                        "symbol": r.get("symbol"),
                        "validation_start_ms": val_start,
                        "test_start_ms": test_start,
                        "test_end_ms": test_end,
                        "purge_minutes": cfg.purge_minutes,
                        "embargo_minutes": cfg.embargo_minutes,
                    }
                )
        fold += 1
        cursor += cfg.step_days * day
    return pl.DataFrame(rows)


def write_splits(scoring_run_id: str, profile: str = "prototype_90d") -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    src = root / "event_horizon.parquet"
    df = pl.read_parquet(src)
    out = build_splits(df, profile)
    out.write_parquet(root / "walk_forward_splits.parquet")
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
