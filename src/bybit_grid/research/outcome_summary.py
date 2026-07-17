from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from bybit_grid.research.outcome_store import read_outcomes
from bybit_grid.research.outcome_semantics import (
    ACTIONABLE_EVENT_SEMANTICS_VERSION,
    OUTCOME_SEMANTICS_VERSION,
    OUTCOME_WINDOW_SEMANTICS_VERSION,
    validate_outcome_window_semantics,
)


OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)


def _distribution(df: pl.DataFrame, column: str) -> list[dict]:
    if df.is_empty() or column not in df.columns:
        return []
    return df[column].value_counts().to_dicts()


def build_summaries(root: Path) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    df = read_outcomes(root)
    if df.is_empty():
        perf = {
            "outcome_rows_total": 0,
            "future_outcome_eligible_rows": 0,
            "future_outcome_ineligible_rows": 0,
            "future_outcome_eligible_rate": 0.0,
        }
        summary = pl.DataFrame(
            {
                "metric": list(perf),
                "value": [str(value) for value in perf.values()],
            }
        )
        quality = pl.DataFrame(
            {
                "metric": ["future_data_complete_rate", "future_outcome_eligible_rate"],
                "value": [0.0, 0.0],
            }
        )
        return summary, quality, perf

    required = {
        "outcome_semantics_version",
        "outcome_window_semantics_version",
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
        "actionable_event_semantics_version",
        "decision_time_source",
        "causal_provenance_complete_bool",
        "range_profile_name",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError("outcome summary missing v5 eligibility columns: " + ",".join(missing))
    versions = set(df["outcome_semantics_version"].unique().to_list())
    if versions != {OUTCOME_SEMANTICS_VERSION}:
        raise ValueError("outcome summary requires one uniform v5 semantic version")
    window_versions = set(df["outcome_window_semantics_version"].unique().to_list())
    if window_versions != {OUTCOME_WINDOW_SEMANTICS_VERSION}:
        raise ValueError("outcome summary requires one exact-minute window version")
    for column in ("future_data_complete_bool", "future_outcome_eligible_bool"):
        if df.schema[column] != pl.Boolean or df[column].null_count():
            raise ValueError("outcome summary eligibility fields must be non-null bool")
    if df.filter(
        pl.col("future_data_complete_bool") != pl.col("future_outcome_eligible_bool")
    ).height:
        raise ValueError("outcome summary completeness and eligibility disagree")
    invalid_provenance = df.filter(
        (pl.col("actionable_event_semantics_version") != ACTIONABLE_EVENT_SEMANTICS_VERSION)
        | (pl.col("decision_time_source") != "event_decision_time")
        | (pl.col("causal_provenance_complete_bool") != True)  # noqa: E712
        | pl.col("range_profile_name").is_null()
        | (pl.col("range_profile_name").str.strip_chars() == "")
    ).height
    invalid_provenance += sum(
        df[column].null_count()
        for column in (
            "actionable_event_semantics_version",
            "decision_time_source",
            "causal_provenance_complete_bool",
        )
    )
    if invalid_provenance:
        raise ValueError("outcome summary requires authoritative event/range provenance")
    semantic_validation = validate_outcome_window_semantics(df)
    if semantic_validation["outcome_window_semantic_audit_ok"] is not True:
        raise ValueError(
            "outcome summary semantic validation failed: "
            + "; ".join(str(value) for value in semantic_validation["failures"])
        )
    event_horizon_invariance = (
        df.group_by(["range_action_event_id", "future_horizon_minutes"])
        .agg(
            pl.col("future_data_complete_bool").n_unique().alias("complete_variants"),
            pl.col("future_outcome_eligible_bool").n_unique().alias("eligible_variants"),
        )
        .filter((pl.col("complete_variants") != 1) | (pl.col("eligible_variants") != 1))
        .height
    )
    if event_horizon_invariance:
        raise ValueError("outcome summary event-horizon eligibility is not invariant")

    eligible = df.filter(pl.col("future_outcome_eligible_bool") == True)  # noqa: E712
    dup = (
        df.height
        - df.select(
            [
                "range_action_event_id",
                "future_horizon_minutes",
                "grid_count",
                "sl_atr_buffer",
            ]
        ).unique().height
    )
    statuses = (
        df["funding_source_status"].value_counts().to_dicts()
        if "funding_source_status" in df.columns
        else []
    )
    status_counts = {
        str(row.get("funding_source_status")): int(row.get("count", row.get("len", 0)))
        for row in statuses
    }
    funding_rows_total = (
        int(df["funding_rows_in_horizon"].sum())
        if "funding_rows_in_horizon" in df.columns
        else 0
    )
    unique_eh = df.unique(
        subset=["range_action_event_id", "future_horizon_minutes"],
        keep="first",
        maintain_order=True,
    )
    eligible_eh = unique_eh.filter(pl.col("future_outcome_eligible_bool") == True)  # noqa: E712
    funding_rows_unique = (
        int(unique_eh["funding_rows_in_horizon"].sum())
        if "funding_rows_in_horizon" in unique_eh.columns
        else 0
    )
    unique_status_counts = {}
    if "funding_source_status" in unique_eh.columns:
        unique_status_counts = {
            str(row.get("funding_source_status")): int(row.get("count", row.get("len", 0)))
            for row in unique_eh["funding_source_status"].value_counts().to_dicts()
        }
    symbols = df["symbol"].unique().sort().to_list() if "symbol" in df.columns else []
    symbols_with_ok = (
        df.filter(pl.col("funding_source_status") == "ok")["symbol"]
        .unique()
        .sort()
        .to_list()
        if "funding_source_status" in df.columns and "symbol" in df.columns
        else []
    )
    grid_col = (
        "future_close_level_cross_count"
        if "future_close_level_cross_count" in df.columns
        else "future_grid_level_cross_count"
    )
    sl_probe = eligible.unique(
        subset=["range_action_event_id", "future_horizon_minutes", "sl_atr_buffer"],
        keep="first",
        maintain_order=True,
    )
    sl_summary = []
    if not sl_probe.is_empty() and "sl_hit_bool" in sl_probe.columns:
        sl_summary = (
            sl_probe.group_by(["future_horizon_minutes", "sl_atr_buffer"])
            .agg(
                pl.col("sl_hit_bool").mean().alias("sl_hit_rate"),
                pl.col("first_sl_ambiguous_bool").mean().alias("sl_ambiguous_rate")
                if "first_sl_ambiguous_bool" in sl_probe.columns
                else pl.lit(None).alias("sl_ambiguous_rate"),
                (~pl.col("sl_proxy_valid_bool")).mean().alias("sl_proxy_invalid_rate")
                if "sl_proxy_valid_bool" in sl_probe.columns
                else pl.lit(None).alias("sl_proxy_invalid_rate"),
                pl.col("minutes_to_first_sl").median().alias("median_minutes_to_first_sl"),
            )
            .to_dicts()
        )
    grid_probe = eligible.unique(
        subset=["range_action_event_id", "future_horizon_minutes", "grid_count"],
        keep="first",
        maintain_order=True,
    )
    grid_summary = []
    if not grid_probe.is_empty() and grid_col in grid_probe.columns:
        grid_summary = (
            grid_probe.group_by(["future_horizon_minutes", "grid_count"])
            .agg(
                pl.col("fill_activity_lower_bound_proxy").min().alias("lower_min")
                if "fill_activity_lower_bound_proxy" in grid_probe.columns
                else pl.col(grid_col).min().alias("lower_min"),
                pl.col("fill_activity_lower_bound_proxy").median().alias("lower_median")
                if "fill_activity_lower_bound_proxy" in grid_probe.columns
                else pl.col(grid_col).median().alias("lower_median"),
                pl.col("fill_activity_upper_bound_proxy").median().alias("upper_median")
                if "fill_activity_upper_bound_proxy" in grid_probe.columns
                else pl.col(grid_col).median().alias("upper_median"),
                pl.col("fill_activity_upper_bound_proxy").max().alias("upper_max")
                if "fill_activity_upper_bound_proxy" in grid_probe.columns
                else pl.col(grid_col).max().alias("upper_max"),
            )
            .to_dicts()
        )
    grid_distribution = {"min": None, "median": None, "max": None}
    if not eligible.is_empty() and grid_col in eligible.columns:
        grid_distribution = eligible.select(
            pl.col(grid_col).min().alias("min"),
            pl.col(grid_col).median().alias("median"),
            pl.col(grid_col).max().alias("max"),
        ).to_dicts()[0]

    eligible_rows = eligible.height
    eligible_eh_rows = eligible_eh.height
    perf = {
        "outcome_rows_total": df.height,
        "unique_outcome_id_count": df["outcome_id"].n_unique(),
        "duplicate_range_action_event_horizon_grid_sl_rows": dup,
        "future_data_complete_rate": float(df["future_data_complete_bool"].mean()),
        "future_outcome_eligible_rows": eligible_rows,
        "future_outcome_ineligible_rows": df.height - eligible_rows,
        "future_outcome_eligible_rate": eligible_rows / df.height,
        "expanded_row_metrics_note": (
            "claim metrics use only v5 exact-window eligible rows; funding diagnostics use all rows"
        ),
        "unique_event_horizon_rows": unique_eh.height,
        "future_data_complete_rate_unique_event_horizon": float(
            unique_eh["future_data_complete_bool"].mean()
        ),
        "future_outcome_eligible_unique_event_horizon_rows": eligible_eh_rows,
        "future_outcome_ineligible_unique_event_horizon_rows": unique_eh.height
        - eligible_eh_rows,
        "future_outcome_eligible_rate_unique_event_horizon": eligible_eh_rows
        / unique_eh.height,
        "first_exit_side_distribution_unique_event_horizon": _distribution(
            eligible_eh, "first_exit_side"
        ),
        "first_exit_ambiguous_rate_unique_event_horizon": float(
            eligible_eh["first_exit_ambiguous_bool"].mean()
        )
        if not eligible_eh.is_empty() and "first_exit_ambiguous_bool" in eligible_eh.columns
        else None,
        "first_exit_side_distribution": _distribution(eligible, "first_exit_side"),
        "sl_hit_distribution": _distribution(eligible, "sl_hit_bool"),
        "grid_crossing_distribution": grid_distribution,
        "activity_proxy_note": "grid activity metrics are proxies, not actual native-grid fills",
        "sl_probe_summary": sl_summary,
        "grid_activity_summary": grid_summary,
        "funding_rows_total": funding_rows_total,
        "funding_files_found_count": len(symbols_with_ok),
        "funding_symbols_with_files": symbols_with_ok,
        "funding_rows_scanned_total": funding_rows_total,
        "funding_rows_joined_total": funding_rows_total,
        "funding_joined_instances_expanded_rows": funding_rows_total,
        "funding_joined_unique_event_horizon": funding_rows_unique,
        "funding_coverage_rate_unique_event_horizon": float(
            (unique_eh["funding_rows_in_horizon"] > 0).mean()
        )
        if "funding_rows_in_horizon" in unique_eh.columns
        else 0.0,
        "funding_join_coverage_rate": float((df["funding_rows_in_horizon"] > 0).mean())
        if "funding_rows_in_horizon" in df.columns
        else 0.0,
        "funding_missing_symbols": sorted(set(symbols) - set(symbols_with_ok)),
        "funding_source_status_counts": status_counts,
        "funding_source_status_counts_unique_event_horizon": unique_status_counts,
        "funding_zero_reason": (
            "no overlapping local funding timestamps"
            if funding_rows_total == 0 and status_counts.get("no_overlap", 0) > 0
            else (
                "local funding files missing or unreadable"
                if funding_rows_total == 0
                else ""
            )
        ),
    }
    summary = pl.DataFrame(
        {
            "metric": list(perf),
            "value": [
                json.dumps(value) if isinstance(value, (list, dict)) else str(value)
                for value in perf.values()
            ],
        }
    )
    quality = pl.DataFrame(
        {
            "metric": [
                "future_data_complete_rate",
                "future_outcome_eligible_rate",
                "duplicate_rows",
            ],
            "value": [
                perf["future_data_complete_rate"],
                perf["future_outcome_eligible_rate"],
                float(dup),
            ],
        }
    )
    return summary, quality, perf


def write_summary(root: Path) -> dict:
    summary, quality, perf = build_summaries(root)
    out = root / "summary"
    out.mkdir(parents=True, exist_ok=True)
    summary.write_parquet(out / "outcome_summary.parquet")
    quality.write_parquet(out / "outcome_quality_summary.parquet")
    (out / "outcome_perf.json").write_text(
        json.dumps(perf, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    return perf
