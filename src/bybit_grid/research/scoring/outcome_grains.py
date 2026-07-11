from __future__ import annotations

import json
from pathlib import Path
import polars as pl

REQUIRED_KEYS = [
    "range_action_event_id",
    "future_horizon_minutes",
    "grid_cell_number",
    "sl_atr_buffer",
    "outcome_id",
    "outcome_match_key",
    "symbol",
    "signal_time_ms",
]
KEYS = {
    "event_horizon": ["range_action_event_id", "future_horizon_minutes"],
    "event_horizon_sl": ["range_action_event_id", "future_horizon_minutes", "sl_atr_buffer"],
    "event_horizon_grid": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number"],
    "expanded_scoring_input": [
        "range_action_event_id",
        "future_horizon_minutes",
        "grid_cell_number",
        "sl_atr_buffer",
    ],
}


def canonical_outcome_files(outcome_run_id: str) -> list[Path]:
    root = Path("data/processed/outcome_runs") / outcome_run_id / "outcomes"
    files = sorted(
        {p.resolve() for p in root.glob("symbol=*/year=*/month=*/outcomes.parquet") if p.is_file()}
    )
    return [Path(p) for p in files]


def read_canonical_outcome_partitions(outcome_run_id: str) -> pl.DataFrame:
    files = canonical_outcome_files(outcome_run_id)
    if not files:
        raise FileNotFoundError(f"no canonical outcome partitions found for {outcome_run_id}")
    return pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")


def _source_audit(outcome_run_id: str, df: pl.DataFrame) -> dict[str, object]:
    root = Path("data/processed/outcome_runs") / outcome_run_id
    physical = canonical_outcome_files(outcome_run_id)
    summary = list((root / "summary").glob("*.parquet")) if (root / "summary").exists() else []
    missing_cols = [c for c in REQUIRED_KEYS if c not in df.columns]
    if missing_cols:
        null_key_rows = df.height
    else:
        null_key_rows = df.filter(
            pl.any_horizontal([pl.col(c).is_null() for c in REQUIRED_KEYS])
        ).height
    unique_ids = df["outcome_id"].n_unique() if "outcome_id" in df.columns else 0
    audit = {
        "source_outcome_run_id": outcome_run_id,
        "physical_files_found": len(physical),
        "unique_physical_files": len(set(map(str, physical))),
        "summary_files_excluded": len(summary),
        "rows_loaded": df.height,
        "null_key_rows": null_key_rows,
        "unique_outcome_id_count": unique_ids,
        "duplicate_outcome_id_count": max(df.height - unique_ids, 0),
        "source_audit_ok": bool(physical) and not missing_cols and null_key_rows == 0,
    }
    if missing_cols:
        audit["missing_required_key_columns"] = missing_cols
    return audit


def duplicate_count(df: pl.DataFrame, keys: list[str]) -> int:
    return df.height - df.select(keys).unique().height


def unique_grain(df: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    non_keys = [c for c in df.columns if c not in keys]
    exprs = [pl.col(c).drop_nulls().first().alias(c) for c in non_keys]
    out = df.group_by(keys).agg(exprs) if exprs else df.select(keys).unique()
    return out.select(keys + [c for c in out.columns if c not in keys])


def cartesian_completeness_audit(df: pl.DataFrame) -> tuple[dict[str, object], pl.DataFrame]:
    grid_set = (
        sorted(df["grid_cell_number"].drop_nulls().unique().to_list())
        if "grid_cell_number" in df.columns
        else []
    )
    sl_set = (
        sorted(df["sl_atr_buffer"].drop_nulls().unique().to_list())
        if "sl_atr_buffer" in df.columns
        else []
    )
    eh = df.select(KEYS["event_horizon"]).unique()
    actual_grid = df.select(KEYS["event_horizon_grid"]).unique().height
    actual_sl = df.select(KEYS["event_horizon_sl"]).unique().height
    actual_exp = df.select(KEYS["expanded_scoring_input"]).unique().height
    counts = df.group_by(KEYS["event_horizon"]).agg(
        [
            pl.col("grid_cell_number").n_unique().alias("unique_grid_count"),
            pl.col("sl_atr_buffer").n_unique().alias("unique_sl_count"),
            pl.struct(["grid_cell_number", "sl_atr_buffer"])
            .n_unique()
            .alias("expanded_combination_count"),
        ]
    )
    incomplete = counts.filter(
        (pl.col("unique_grid_count") != len(grid_set))
        | (pl.col("unique_sl_count") != len(sl_set))
        | (pl.col("expanded_combination_count") != len(grid_set) * len(sl_set))
    )
    audit = {
        "grid_cell_numbers": grid_set,
        "sl_atr_buffers": sl_set,
        "event_horizon_rows": eh.height,
        "expected_event_horizon_grid_rows": eh.height * len(grid_set),
        "actual_event_horizon_grid_rows": actual_grid,
        "expected_event_horizon_sl_rows": eh.height * len(sl_set),
        "actual_event_horizon_sl_rows": actual_sl,
        "expected_expanded_rows": eh.height * len(grid_set) * len(sl_set),
        "actual_expanded_rows": actual_exp,
        "incomplete_event_horizon_count": incomplete.height,
        "unexpected_grid_values": [],
        "unexpected_sl_values": [],
        "cartesian_completeness_ok": incomplete.height == 0
        and actual_exp == eh.height * len(grid_set) * len(sl_set),
    }
    return audit, incomplete


def build_outcome_grains(df: pl.DataFrame) -> tuple[dict[str, pl.DataFrame], dict[str, object]]:
    missing = [c for c in REQUIRED_KEYS if c in df.columns and df[c].null_count() > 0]
    absent = [c for c in REQUIRED_KEYS if c not in df.columns]
    if missing or absent:
        raise ValueError(f"null/missing required outcome keys: null={missing}, missing={absent}")
    grains = {name: unique_grain(df, keys) for name, keys in KEYS.items()}
    dupes = {name: duplicate_count(grain, KEYS[name]) for name, grain in grains.items()}
    cart, _ = cartesian_completeness_audit(df)
    violations = [name for name, count in dupes.items() if count]
    eh = grains["event_horizon"]
    exp = grains["expanded_scoring_input"]
    audit = {
        "rows": {k: v.height for k, v in grains.items()},
        "duplicate_key_counts": dupes,
        "unique_event_horizon_rows": eh.height,
        "funding_event_horizon_rows": (
            eh.select(KEYS["event_horizon"] + [c for c in eh.columns if "funding" in c])
            .unique()
            .height
            if [c for c in eh.columns if "funding" in c]
            else eh.height
        ),
        "expanded_rows": exp.height,
        "grain_audit_ok": not violations,
        "violations": violations,
    }
    audit.update({"cartesian_completeness_ok": cart["cartesian_completeness_ok"]})
    return grains, audit


def write_outcome_grains(outcome_run_id: str, scoring_run_id: str) -> dict[str, object]:
    df = read_canonical_outcome_partitions(outcome_run_id)
    source = _source_audit(outcome_run_id, df)
    if not source["source_audit_ok"]:
        raise ValueError(json.dumps(source))
    grains, audit = build_outcome_grains(df)
    cart, incomplete = cartesian_completeness_audit(df)
    root = Path("data/processed/scoring_runs") / scoring_run_id
    root.mkdir(parents=True, exist_ok=True)
    for name, frame in grains.items():
        frame.write_parquet(root / f"{name}.parquet")
    (root / "outcome_source_audit.json").write_text(
        json.dumps(source, indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "outcome_grain_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8"
    )
    (root / "outcome_cartesian_completeness_audit.json").write_text(
        json.dumps(cart, indent=2, sort_keys=True), encoding="utf-8"
    )
    if not incomplete.is_empty():
        incomplete.write_parquet(root / "outcome_cartesian_incomplete_keys.parquet")
        raise ValueError(json.dumps(cart))
    return audit | {"source_audit": source, "cartesian_audit": cart}
