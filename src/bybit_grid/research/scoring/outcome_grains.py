from __future__ import annotations

import json
from pathlib import Path
import polars as pl

PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
GRAIN_CONTRACT_VERSION = "grain_contract_v4_persisted_exclusive_outcome_end"
OUTCOME_BOUNDARY_SEMANTICS_VERSION = "persisted-exclusive-outcome-end-v1"
OUTCOME_SEMANTICS_VERSION = "v5_exact_outcome_window_provenance"
OUTCOME_WINDOW_SEMANTICS_VERSION = "exact-minute-outcome-window-v1"
ACTIONABLE_EVENT_SEMANTICS_VERSION = "range-actionable-prefix-invariance-v1"
CANONICAL_OUTCOME_END_COLUMN = "outcome_end_exclusive_ms"
LEGACY_OUTCOME_END_COLUMN = "outcome_end_ms"
MINUTE_MS = 60_000

PERSISTED_OUTCOME_COLUMNS = [
    "outcome_semantics_version",
    "outcome_window_semantics_version",
    "actionable_event_semantics_version",
    "decision_time_source",
    "causal_provenance_complete_bool",
    "decision_time_ms",
    "entry_time_ms",
    CANONICAL_OUTCOME_END_COLUMN,
    "future_data_complete_bool",
    "future_outcome_eligible_bool",
]
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
REQUIRED_COLUMNS_BY_GRAIN = {
    "event_horizon": [
        "range_action_event_id",
        "future_horizon_minutes",
        "symbol",
        "category",
        *PERSISTED_OUTCOME_COLUMNS,
    ],
    "event_horizon_sl": [
        "range_action_event_id",
        "future_horizon_minutes",
        "sl_atr_buffer",
        "symbol",
        "category",
        *PERSISTED_OUTCOME_COLUMNS,
    ],
    "event_horizon_grid": [
        "range_action_event_id",
        "future_horizon_minutes",
        "grid_cell_number",
        "symbol",
        "category",
        *PERSISTED_OUTCOME_COLUMNS,
    ],
    "expanded_scoring_input": [
        "range_action_event_id",
        "future_horizon_minutes",
        "grid_cell_number",
        "sl_atr_buffer",
        "symbol",
        "category",
        *PERSISTED_OUTCOME_COLUMNS,
    ],
}
REQUIRED_KEYS = [
    *GRAIN_KEYS["expanded_scoring_input"],
    "outcome_id",
    "outcome_match_key",
    "symbol",
    "signal_time_ms",
    *PERSISTED_OUTCOME_COLUMNS,
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
    *PERSISTED_OUTCOME_COLUMNS,
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


def _persisted_outcome_contract_violations(df: pl.DataFrame) -> list[dict[str, object]]:
    """Return fail-closed violations for the canonical persisted outcome window."""
    violations: list[dict[str, object]] = []
    if LEGACY_OUTCOME_END_COLUMN in df.columns:
        violations.append(
            {
                "type": "legacy_outcome_end_column_forbidden",
                "column": LEGACY_OUTCOME_END_COLUMN,
            }
        )
    missing = [c for c in PERSISTED_OUTCOME_COLUMNS if c not in df.columns]
    if missing:
        violations.append({"type": "missing_persisted_outcome_columns", "columns": missing})
        return violations

    expected_versions = {
        "outcome_semantics_version": OUTCOME_SEMANTICS_VERSION,
        "outcome_window_semantics_version": OUTCOME_WINDOW_SEMANTICS_VERSION,
        "actionable_event_semantics_version": ACTIONABLE_EVENT_SEMANTICS_VERSION,
    }
    for column, expected in expected_versions.items():
        actual = sorted(str(v) for v in df[column].drop_nulls().unique().to_list())
        if actual != [expected] or df[column].null_count():
            violations.append(
                {
                    "type": "invalid_semantics_version",
                    "column": column,
                    "expected": expected,
                    "actual": actual,
                    "null_count": df[column].null_count(),
                }
            )

    typed_columns = [
        "signal_time_ms",
        "decision_time_ms",
        "entry_time_ms",
        CANONICAL_OUTCOME_END_COLUMN,
        "future_horizon_minutes",
    ]
    bool_columns = [
        "causal_provenance_complete_bool",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
    ]
    if any(c not in df.columns for c in typed_columns):
        return violations

    for index, row in enumerate(df.iter_rows(named=True)):
        for column in typed_columns:
            if type(row[column]) is not int:  # bool and float are intentionally rejected
                violations.append(
                    {
                        "type": "invalid_integer_value",
                        "row": index,
                        "column": column,
                    }
                )
        for column in bool_columns:
            if type(row[column]) is not bool:
                violations.append(
                    {
                        "type": "invalid_boolean_value",
                        "row": index,
                        "column": column,
                    }
                )
        if any(type(row[c]) is not int for c in typed_columns):
            continue
        signal = row["signal_time_ms"]
        decision = row["decision_time_ms"]
        entry = row["entry_time_ms"]
        outcome_end = row[CANONICAL_OUTCOME_END_COLUMN]
        horizon = row["future_horizon_minutes"]
        if any(row[column] < 0 for column in typed_columns[:-1]):
            violations.append({"type": "negative_outcome_timestamp", "row": index})
        if horizon <= 0:
            violations.append({"type": "non_positive_horizon", "row": index})
        if decision != signal:
            violations.append({"type": "decision_signal_mismatch", "row": index})
        expected_entry = ((decision // MINUTE_MS) + 1) * MINUTE_MS
        if entry != expected_entry:
            violations.append({"type": "entry_not_next_minute", "row": index})
        if outcome_end != entry + horizon * MINUTE_MS:
            violations.append(
                {
                    "type": "persisted_outcome_end_mismatch",
                    "row": index,
                    "expected": entry + horizon * MINUTE_MS,
                    "actual": outcome_end,
                }
            )
        if row["causal_provenance_complete_bool"] is not True:
            violations.append({"type": "incomplete_causal_provenance", "row": index})
        if row["decision_time_source"] != "event_decision_time":
            violations.append({"type": "invalid_decision_time_source", "row": index})
        expected_eligible = row["future_data_complete_bool"] is True
        if row["future_outcome_eligible_bool"] is not expected_eligible:
            violations.append({"type": "outcome_eligibility_mismatch", "row": index})
    return violations



def normalize_outcome_category(
    df: pl.DataFrame,
    *,
    default_category: str = "linear",
) -> tuple[pl.DataFrame, dict[str, object]]:
    rows_before = df.height
    present = "category" in df.columns
    source_categories = (
        sorted(str(x) for x in df["category"].drop_nulls().unique().to_list()) if present else []
    )
    if present:
        out = df.with_columns(
            pl.col("category").cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("category")
        )
        category_source = "source_column"
    else:
        out = df.with_columns(pl.lit(default_category).alias("category"))
        category_source = "project_scope_default"
    empty_count = out.filter(pl.col("category").is_null() | (pl.col("category") == "")).height
    normalized_categories = sorted(out["category"].drop_nulls().unique().to_list())
    ok = empty_count == 0 and normalized_categories == [default_category]
    audit = {
        "category_normalization_ok": ok,
        "category_source": category_source,
        "category_column_present_in_source": present,
        "source_categories": source_categories,
        "normalized_categories": normalized_categories,
        "rows_before": rows_before,
        "rows_after": out.height,
        "default_category": default_category,
    }
    if not ok:
        raise ValueError(json.dumps(audit, sort_keys=True))
    return out, audit

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
    unique_match_keys = (
        df["outcome_match_key"].n_unique() if "outcome_match_key" in df.columns else 0
    )
    contract_violations = _persisted_outcome_contract_violations(df)
    duplicate_outcome_id_count = max(df.height - unique_ids, 0)
    duplicate_outcome_match_key_count = max(df.height - unique_match_keys, 0)
    audit = {
        "source_outcome_run_id": outcome_run_id,
        "physical_files_found": len(physical),
        "unique_physical_files": len(set(map(str, physical))),
        "summary_files_excluded": len(summary),
        "rows_loaded": df.height,
        "null_key_rows": null_key_rows,
        "unique_outcome_id_count": unique_ids,
        "duplicate_outcome_id_count": duplicate_outcome_id_count,
        "duplicate_outcome_match_key_count": duplicate_outcome_match_key_count,
        "persisted_outcome_contract_violations": contract_violations,
        "source_audit_ok": bool(physical)
        and not missing_cols
        and null_key_rows == 0
        and duplicate_outcome_id_count == 0
        and duplicate_outcome_match_key_count == 0
        and not contract_violations,
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
    if "category" not in df.columns:
        df, _ = normalize_outcome_category(df)
    missing = [c for c in REQUIRED_KEYS if c in df.columns and df[c].null_count() > 0]
    absent = [c for c in REQUIRED_KEYS if c not in df.columns]
    if missing or absent:
        raise ValueError(f"null/missing required outcome keys: null={missing}, missing={absent}")
    source_duplicate_counts = {
        "expanded_composite_key": duplicate_count(
            df, GRAIN_KEYS["expanded_scoring_input"]
        ),
        "outcome_id": df.height - df.select("outcome_id").unique().height,
        "outcome_match_key": df.height - df.select("outcome_match_key").unique().height,
    }
    if any(source_duplicate_counts.values()):
        raise ValueError(
            json.dumps(
                {
                    "grain_contract_audit_ok": False,
                    "duplicate_source_key_counts": source_duplicate_counts,
                },
                sort_keys=True,
            )
        )
    persisted_contract_violations = _persisted_outcome_contract_violations(df)
    if persisted_contract_violations:
        raise ValueError(
            json.dumps(
                {
                    "grain_contract_audit_ok": False,
                    "persisted_outcome_contract_violations": persisted_contract_violations,
                },
                sort_keys=True,
            )
        )
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
    actual_columns = {name: frame.columns for name, frame in grains.items()}
    missing_required = {
        name: [c for c in REQUIRED_COLUMNS_BY_GRAIN[name] if c not in frame.columns]
        for name, frame in grains.items()
    }
    null_required = {
        name: {c: int(frame[c].null_count()) for c in REQUIRED_COLUMNS_BY_GRAIN[name] if c in frame.columns}
        for name, frame in grains.items()
    }
    category_present = {name: "category" in frame.columns for name, frame in grains.items()}
    category_values = {
        name: sorted(frame["category"].drop_nulls().unique().to_list()) if "category" in frame.columns else []
        for name, frame in grains.items()
    }
    cart, _ = cartesian_completeness_audit(df)
    bad_forbidden = {k: v for k, v in forbidden.items() if v}
    required_ok = (
        not any(missing_required.values())
        and all(all(v == 0 for v in counts.values()) for counts in null_required.values())
        and all(vals == ["linear"] for vals in category_values.values())
    )
    contract_ok = not bad_forbidden and sum(inv_counts.values()) == 0 and required_ok
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
                    "actual_columns_by_grain": actual_columns,
                    "missing_required_columns_by_grain": missing_required,
                    "null_required_column_counts_by_grain": null_required,
                    "category_present_by_grain": category_present,
                    "category_values_by_grain": category_values,
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
        "outcome_boundary_semantics_version": OUTCOME_BOUNDARY_SEMANTICS_VERSION,
        "persisted_outcome_end_required_bool": True,
        "derived_outcome_end_count": 0,
        "legacy_outcome_end_column_allowed_bool": False,
        "contract_columns_by_grain": CONTRACT_COLUMNS_BY_GRAIN,
        "forbidden_columns_found_by_grain": forbidden,
        "invariance_violation_count_by_grain": inv_counts,
        "whole_row_invariance_violation_count_by_grain": inv_counts,
        "null_pattern_violation_count_by_grain": null_counts,
        "synthetic_row_risk_detected_bool": sum(inv_counts.values()) > 0,
        "representative_row_selection_version": "whole_row_v1",
        "required_columns_by_grain": REQUIRED_COLUMNS_BY_GRAIN,
        "actual_columns_by_grain": actual_columns,
        "missing_required_columns_by_grain": missing_required,
        "null_required_column_counts_by_grain": null_required,
        "category_present_by_grain": category_present,
        "category_values_by_grain": category_values,
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
    df, category_audit = normalize_outcome_category(df)
    try:
        grains, audit = build_outcome_grains(df)
    except ValueError:
        raise
    cart, incomplete = cartesian_completeness_audit(df)
    for name, frame in grains.items():
        frame.write_parquet(root / f"{name}.parquet")
    for fn, obj in [
        ("outcome_source_audit.json", source),
        ("outcome_category_normalization_audit.json", category_audit),
        ("outcome_grain_audit.json", audit),
        (
            "outcome_grain_contract_audit.json",
            {
                k: audit[k]
                for k in [
                    "grain_contract_version",
                    "outcome_boundary_semantics_version",
                    "persisted_outcome_end_required_bool",
                    "derived_outcome_end_count",
                    "legacy_outcome_end_column_allowed_bool",
                    "contract_columns_by_grain",
                    "forbidden_columns_found_by_grain",
                    "invariance_violation_count_by_grain",
                    "whole_row_invariance_violation_count_by_grain",
                    "null_pattern_violation_count_by_grain",
                    "synthetic_row_risk_detected_bool",
                    "representative_row_selection_version",
                    "required_columns_by_grain",
                    "actual_columns_by_grain",
                    "missing_required_columns_by_grain",
                    "null_required_column_counts_by_grain",
                    "category_present_by_grain",
                    "category_values_by_grain",
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
