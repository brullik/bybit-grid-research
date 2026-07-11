from __future__ import annotations

import json
from pathlib import Path
import polars as pl

KEYS = {
    "event_horizon": ["range_action_event_id", "future_horizon_minutes"],
    "event_horizon_sl": ["range_action_event_id", "future_horizon_minutes", "sl_atr_buffer"],
    "event_horizon_grid": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number"],
    "expanded_scoring_input": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number", "sl_atr_buffer"],
}


def read_outcomes(outcome_run_id: str) -> pl.DataFrame:
    root = Path("data/processed/outcome_runs") / outcome_run_id
    files = list(root.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet outcomes found under {root}")
    return pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")


def duplicate_count(df: pl.DataFrame, keys: list[str]) -> int:
    return df.height - df.select(keys).unique().height


def unique_grain(df: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    non_keys = [c for c in df.columns if c not in keys]
    exprs = [pl.col(c).drop_nulls().first().alias(c) for c in non_keys]
    out = df.group_by(keys).agg(exprs) if exprs else df.select(keys).unique()
    return out.select(keys + [c for c in out.columns if c not in keys])


def build_outcome_grains(df: pl.DataFrame) -> tuple[dict[str, pl.DataFrame], dict[str, object]]:
    grains = {name: unique_grain(df, keys) for name, keys in KEYS.items()}
    dupes = {name: duplicate_count(grain, KEYS[name]) for name, grain in grains.items()}
    violations = [name for name, count in dupes.items() if count]
    # Funding context must be sourced once per event-horizon: audit expected multiplication.
    eh = grains["event_horizon"]
    exp = grains["expanded_scoring_input"]
    funding_cols = [c for c in eh.columns if "funding" in c]
    funding_unique_rows = eh.select(KEYS["event_horizon"] + funding_cols).unique().height if funding_cols else eh.height
    audit = {
        "rows": {k: v.height for k, v in grains.items()},
        "duplicate_key_counts": dupes,
        "unique_event_horizon_rows": eh.height,
        "funding_event_horizon_rows": funding_unique_rows,
        "expanded_rows": exp.height,
        "grain_audit_ok": not violations,
        "violations": violations,
    }
    return grains, audit


def write_outcome_grains(outcome_run_id: str, scoring_run_id: str) -> dict[str, object]:
    grains, audit = build_outcome_grains(read_outcomes(outcome_run_id))
    root = Path("data/processed/scoring_runs") / scoring_run_id
    root.mkdir(parents=True, exist_ok=True)
    for name, frame in grains.items():
        frame.write_parquet(root / f"{name}.parquet")
    (root / "outcome_grain_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    return audit
