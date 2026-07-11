from __future__ import annotations

import json
from pathlib import Path
import polars as pl

GRAIN_CONTRACT_VERSION = "grain_contract_v3_whole_row"
GRAIN_KEYS = {
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
KEYS = GRAIN_KEYS
REQUIRED_KEYS = [
    *GRAIN_KEYS["expanded_scoring_input"],
    "outcome_id",
    "outcome_match_key",
    "symbol",
    "signal_time_ms",
]

SL_MARKERS = (
    "sl_atr_buffer",
    "lower_sl_price",
    "upper_sl_price",
    "sl_hit_bool",
    "first_sl_",
    "minutes_to_first_sl",
)
GRID_MARKERS = (
    "grid_cell_number",
    "grid_interval_",
    "geometric_grid_levels_json",
    "future_close_level",
    "future_intrabar_level",
    "future_unique_grid",
    "grid_levels",
)
EVENT_ALLOW_EXACT = set(GRAIN_KEYS["event_horizon"]) | {
    "symbol",
    "category",
    "signal_time_ms",
    "range_regime_id",
    "range_low",
    "range_high",
    "range_mid",
    "range_width",
    "range_width_pct",
    "atr",
    "atr_pct",
    "future_data_complete_bool",
    "future_coverage_minutes",
    "future_rows_available",
    "future_missing_minutes_count",
    "future_bad_ohlc_count",
    "future_zero_volume_count",
    "minutes_to_first_exit",
    "minutes_until_range_exit",
    "first_exit_ambiguous_bool",
    "funding_source_status",
    "funding_rate_sum",
    "funding_rate_abs_sum",
    "funding_rate_mean",
    "mark_price",
    "mark_price_at_signal",
    "outcome_end_ms",
}
SL_ALLOW_EXACT = (
    EVENT_ALLOW_EXACT
    | set(GRAIN_KEYS["event_horizon_sl"])
    | {
        "sl_proxy_valid_bool",
        "lower_sl_price",
        "upper_sl_price",
        "sl_hit_bool",
        "minutes_to_first_sl",
        "first_sl_ambiguous_bool",
        "first_sl_side",
    }
)
GRID_ALLOW_EXACT = (
    EVENT_ALLOW_EXACT
    | set(GRAIN_KEYS["event_horizon_grid"])
    | {
        "grid_interval_ratio",
        "grid_interval_pct",
        "grid_interval_bps",
        "geometric_grid_levels_json",
        "future_close_level_cross_count",
        "future_intrabar_level_touch_count",
        "future_unique_grid_levels_touched_count",
    }
)
CONTRACT_COLUMNS_BY_GRAIN = {
    "event_horizon": sorted(EVENT_ALLOW_EXACT),
    "event_horizon_sl": sorted(SL_ALLOW_EXACT),
    "event_horizon_grid": sorted(GRID_ALLOW_EXACT),
    "expanded_scoring_input": ["*"],
}


def canonical_outcome_files(outcome_run_id: str) -> list[Path]:
    root = Path("data/processed/outcome_runs") / outcome_run_id / "outcomes"
    return [
        Path(p)
        for p in sorted(
            {
                p.resolve()
                for p in root.glob("symbol=*/year=*/month=*/outcomes.parquet")
                if p.is_file()
            }
        )
    ]


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
    null_key_rows = (
        df.height
        if missing_cols
        else df.filter(pl.any_horizontal([pl.col(c).is_null() for c in REQUIRED_KEYS])).height
    )
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


def _forbidden(name: str, columns: list[str]) -> list[str]:
    if name == "event_horizon":
        return [
            c
            for c in columns
            if any(m in c for m in (*SL_MARKERS, *GRID_MARKERS))
            or (c.startswith("future_") and ("grid" in c or "level" in c))
        ]
    if name == "event_horizon_sl":
        return [c for c in columns if any(m in c for m in GRID_MARKERS)]
    if name == "event_horizon_grid":
        return [c for c in columns if any(m in c for m in SL_MARKERS)]
    return []


def _allowed_columns(df: pl.DataFrame, name: str) -> list[str]:
    if name == "expanded_scoring_input":
        return df.columns
    allow = set(CONTRACT_COLUMNS_BY_GRAIN[name])
    return [c for c in df.columns if c in allow]


def whole_row_invariance_violations(
    df: pl.DataFrame, name: str, keys: list[str], columns: list[str]
) -> pl.DataFrame:
    cols = [c for c in columns if c in df.columns]
    non_keys = [c for c in cols if c not in keys]
    if not non_keys:
        return pl.DataFrame({"grain": [], "struct_cardinality": []})
    bad = (
        df.select(cols)
        .group_by(keys)
        .agg(pl.struct(non_keys).n_unique().alias("struct_cardinality"))
        .filter(pl.col("struct_cardinality") > 1)
    )
    return bad.with_columns(pl.lit(name).alias("grain")) if not bad.is_empty() else pl.DataFrame({"grain": [], "struct_cardinality": []})


def null_pattern_violations(
    df: pl.DataFrame, name: str, keys: list[str], columns: list[str]
) -> pl.DataFrame:
    cols = [c for c in columns if c in df.columns]
    non_keys = [c for c in cols if c not in keys]
    if not non_keys:
        return pl.DataFrame({"grain": [], "null_pattern_cardinality": []})
    bad = (
        df.select(cols)
        .with_columns(pl.struct([pl.col(c).is_null().alias(c) for c in non_keys]).alias("__null_pattern"))
        .group_by(keys)
        .agg(pl.col("__null_pattern").n_unique().alias("null_pattern_cardinality"))
        .filter(pl.col("null_pattern_cardinality") > 1)
    )
    return bad.with_columns(pl.lit(name).alias("grain")) if not bad.is_empty() else pl.DataFrame({"grain": [], "null_pattern_cardinality": []})


def invariance_violations(
    df: pl.DataFrame, name: str, keys: list[str], columns: list[str]
) -> pl.DataFrame:
    return whole_row_invariance_violations(df, name, keys, columns)


def unique_grain(
    df: pl.DataFrame, keys: list[str], columns: list[str] | None = None
) -> pl.DataFrame:
    cols = [c for c in (columns or df.columns) if c in df.columns]
    selected = df.select(cols).sort(keys)
    out = selected.unique(keys, keep="first", maintain_order=True)
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
    forbidden = {}
    inv_counts = {}
    null_counts = {}
    inv_frames = []
    grains = {}
    for name, keys in KEYS.items():
        cols = _allowed_columns(df, name)
        forbidden[name] = _forbidden(name, cols)
        inv = (
            pl.DataFrame({"grain": [], "struct_cardinality": []})
            if name == "expanded_scoring_input"
            else whole_row_invariance_violations(df, name, keys, cols)
        )
        null_inv = (
            pl.DataFrame({"grain": [], "null_pattern_cardinality": []})
            if name == "expanded_scoring_input"
            else null_pattern_violations(df, name, keys, cols)
        )
        inv_counts[name] = inv.height
        null_counts[name] = null_inv.height
        if not inv.is_empty():
            inv_frames.append(inv)
        grains[name] = unique_grain(df, keys, cols)
    dupes = {name: duplicate_count(grain, KEYS[name]) for name, grain in grains.items()}
    cart, _ = cartesian_completeness_audit(df)
    bad_forbidden = {k: v for k, v in forbidden.items() if v}
    contract_ok = not bad_forbidden and sum(inv_counts.values()) == 0
    if not contract_ok:
        raise ValueError(
            json.dumps(
                {
                    "grain_contract_audit_ok": False,
                    "forbidden_columns_found_by_grain": bad_forbidden,
                    "invariance_violation_count_by_grain": inv_counts,
                    "whole_row_invariance_violation_count_by_grain": inv_counts,
                    "null_pattern_violation_count_by_grain": null_counts,
                    "synthetic_row_risk_detected_bool": sum(inv_counts.values()) > 0,
                },
                sort_keys=True,
            )
        )
    audit = {
        "rows": {k: v.height for k, v in grains.items()},
        "duplicate_key_counts": dupes,
        "unique_event_horizon_rows": grains["event_horizon"].height,
        "funding_event_horizon_rows": grains["event_horizon"]
        .select(
            KEYS["event_horizon"] + [c for c in grains["event_horizon"].columns if "funding" in c]
        )
        .unique()
        .height
        if [c for c in grains["event_horizon"].columns if "funding" in c]
        else grains["event_horizon"].height,
        "expanded_rows": grains["expanded_scoring_input"].height,
        "grain_audit_ok": not any(dupes.values()),
        "violations": [n for n, c in dupes.items() if c],
        "cartesian_completeness_ok": cart["cartesian_completeness_ok"],
        "grain_contract_version": GRAIN_CONTRACT_VERSION,
        "contract_columns_by_grain": CONTRACT_COLUMNS_BY_GRAIN,
        "forbidden_columns_found_by_grain": forbidden,
        "invariance_violation_count_by_grain": inv_counts,
        "whole_row_invariance_violation_count_by_grain": inv_counts,
        "null_pattern_violation_count_by_grain": null_counts,
        "synthetic_row_risk_detected_bool": sum(inv_counts.values()) > 0,
        "representative_row_selection_version": "whole_row_v1",
        "grain_contract_audit_ok": contract_ok,
    }
    return grains, audit


def write_outcome_grains(outcome_run_id: str, scoring_run_id: str) -> dict[str, object]:
    df = read_canonical_outcome_partitions(outcome_run_id)
    source = _source_audit(outcome_run_id, df)
    if not source["source_audit_ok"]:
        raise ValueError(json.dumps(source))
    root = Path("data/processed/scoring_runs") / scoring_run_id
    root.mkdir(parents=True, exist_ok=True)
    try:
        grains, audit = build_outcome_grains(df)
    except ValueError:
        raise
    cart, incomplete = cartesian_completeness_audit(df)
    for name, frame in grains.items():
        frame.write_parquet(root / f"{name}.parquet")
    for fn, obj in [
        ("outcome_source_audit.json", source),
        ("outcome_grain_audit.json", audit),
        (
            "outcome_grain_contract_audit.json",
            {
                k: audit[k]
                for k in [
                    "grain_contract_version",
                    "contract_columns_by_grain",
                    "forbidden_columns_found_by_grain",
                    "invariance_violation_count_by_grain",
                    "whole_row_invariance_violation_count_by_grain",
                    "null_pattern_violation_count_by_grain",
                    "synthetic_row_risk_detected_bool",
                    "representative_row_selection_version",
                    "grain_contract_audit_ok",
                ]
            },
        ),
        ("outcome_cartesian_completeness_audit.json", cart),
    ]:
        (root / fn).write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    if not incomplete.is_empty():
        incomplete.write_parquet(root / "outcome_cartesian_incomplete_keys.parquet")
        raise ValueError(json.dumps(cart))
    return audit | {"source_audit": source, "cartesian_audit": cart}
