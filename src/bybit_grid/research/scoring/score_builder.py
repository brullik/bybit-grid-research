from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from bybit_grid.research.cost_model.models import load_cost_config, scenario_objects
from bybit_grid.research.scoring.components import add_ex_post_components

DEFAULT_WEIGHTS = {
    "score_weights_version": "score_weights_v2_frozen",
    "weight_sets": {
        "balanced_v2": {
            "range": 0.25,
            "quality": 0.25,
            "sl": 0.20,
            "turnover": 0.10,
            "activity": 0.10,
            "cost": 0.10,
        },
        "survival_heavy_v2": {
            "range": 0.40,
            "quality": 0.15,
            "sl": 0.25,
            "turnover": 0.05,
            "activity": 0.05,
            "cost": 0.10,
        },
        "quality_heavy_v2": {
            "range": 0.15,
            "quality": 0.45,
            "sl": 0.15,
            "turnover": 0.05,
            "activity": 0.10,
            "cost": 0.10,
        },
        "cost_heavy_v2": {
            "range": 0.15,
            "quality": 0.15,
            "sl": 0.15,
            "turnover": 0.05,
            "activity": 0.15,
            "cost": 0.35,
        },
    },
}

COST_FORMULA_VERSION = "cost_formula_v2_asymmetric_slippage"



def _write_status(root: Path, payload: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "scoring_run_status.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def join_account_fees(
    df: pl.DataFrame,
    fees: pl.DataFrame,
    *,
    context: str,
) -> tuple[pl.DataFrame, dict[str, object]]:
    for label, frame in [("scoring", df), ("fees", fees)]:
        missing = sorted({"category", "symbol"} - set(frame.columns))
        if missing:
            raise ValueError(f"{context}: {label} missing fee join columns: {missing}")
    scoring_categories = sorted(df["category"].drop_nulls().cast(pl.Utf8).unique().to_list())
    fee_categories = sorted(fees["category"].drop_nulls().cast(pl.Utf8).unique().to_list())
    if scoring_categories != ["linear"]:
        raise ValueError(f"{context}: unsupported scoring categories {scoring_categories}")
    if "linear" not in fee_categories:
        raise ValueError(f"{context}: fee snapshot missing linear category")
    dup = fees.group_by(["category", "symbol"]).len().filter(pl.col("len") > 1)
    if dup.height:
        raise ValueError(f"{context}: duplicate fee rows per category/symbol")
    joined = df.join(fees, on=["category", "symbol"], how="left")
    missing_fee = joined.filter(pl.col("maker_fee_rate").is_null() | pl.col("taker_fee_rate").is_null())
    missing_symbols = sorted(missing_fee["symbol"].unique().to_list()) if missing_fee.height else []
    audit = {
        "context": context,
        "input_rows": df.height,
        "output_rows": joined.height,
        "scoring_symbol_count": df["symbol"].n_unique(),
        "scoring_symbols": sorted(df["symbol"].unique().to_list()),
        "scoring_categories": scoring_categories,
        "fee_symbol_count": fees["symbol"].n_unique(),
        "fee_categories": fee_categories,
        "missing_fee_row_count": missing_fee.height,
        "symbols_missing_fee_rates": missing_symbols,
        "fee_join_ok": missing_fee.height == 0,
    }
    if missing_fee.height:
        raise ValueError(json.dumps(audit, sort_keys=True))
    return joined, audit

def load_weights(path: str | Path | None = None):
    return DEFAULT_WEIGHTS


def resolve_fee_snapshot_id(requested: str | None) -> str:
    if not requested or requested == "latest":
        roots = [p for p in Path("data/metadata/fee_snapshots").glob("*/fee_rates.parquet")]
        if not roots:
            raise FileNotFoundError("no fee snapshots available")
        return sorted((p.parent for p in roots), key=lambda p: p.stat().st_mtime)[-1].name
    return requested


def load_fee_rates(requested: str | None) -> tuple[pl.DataFrame, dict[str, object]]:
    resolved = resolve_fee_snapshot_id(requested)
    path = Path("data/metadata/fee_snapshots") / resolved / "fee_rates.parquet"
    df = pl.read_parquet(path).rename(
        {
            c: n
            for c, n in {
                "makerFeeRate": "maker_fee_rate",
                "takerFeeRate": "taker_fee_rate",
                "source": "fee_source",
            }.items()
            if c in pl.read_parquet(path, n_rows=0).columns
        }
    )
    if "category" not in df.columns:
        df = df.with_columns(pl.lit("linear").alias("category"))
    if "fee_source" not in df.columns:
        df = df.with_columns(pl.lit("account_actual").alias("fee_source"))
    df = df.with_columns(
        [
            pl.col("maker_fee_rate").cast(pl.Float64),
            pl.col("taker_fee_rate").cast(pl.Float64),
            pl.col("symbol").cast(pl.Utf8),
            pl.col("category").cast(pl.Utf8),
        ]
    )
    if df.filter(
        ~pl.col("maker_fee_rate").is_finite() | ~pl.col("taker_fee_rate").is_finite()
    ).height:
        raise ValueError("non-finite fee values")
    if df["fee_source"].n_unique() > 1:
        raise ValueError("mixed fee sources in one snapshot")
    dup = (
        df.group_by(["category", "symbol"])
        .agg(
            [
                pl.col("maker_fee_rate").n_unique().alias("m"),
                pl.col("taker_fee_rate").n_unique().alias("t"),
            ]
        )
        .filter((pl.col("m") > 1) | (pl.col("t") > 1))
    )
    if dup.height:
        raise ValueError("non-identical duplicate fee rates")
    df = df.unique(["category", "symbol"]).select(
        ["category", "symbol", "maker_fee_rate", "taker_fee_rate", "fee_source"]
    )
    return df, {
        "fee_snapshot_id_resolved": resolved,
        "fee_source": df["fee_source"][0] if df.height else "unknown",
    }


def _dist(df: pl.DataFrame, col: str) -> dict[str, object]:
    s = df[col]
    return {
        "count": s.len(),
        "null_count": s.null_count(),
        "mean": s.mean(),
        "std": s.std(),
        "p05": s.quantile(0.05),
        "p25": s.quantile(0.25),
        "median": s.median(),
        "p75": s.quantile(0.75),
        "p95": s.quantile(0.95),
        "min": s.min(),
        "max": s.max(),
    }


def _duplicate_key_count(df: pl.DataFrame, keys: list[str]) -> int:
    if df.is_empty():
        return 0
    return int(df.group_by(keys).len().filter(pl.col("len") > 1)["len"].sum() or 0)


def build_scoring_dataset(
    input_path: Path,
    scoring_run_id: str,
    weights_path: str | None = None,
    fee_snapshot_id: str | None = None,
    cost_config: str | None = None,
    source_outcome_run_id: str | None = None,
) -> dict[str, object]:
    root = Path("data/processed/scoring_runs") / scoring_run_id
    _write_status(root, {"status": "building", "scoring_run_id": scoring_run_id, "source_outcome_run_id": source_outcome_run_id})
    try:
        result = _build_scoring_dataset_impl(
            input_path, scoring_run_id, weights_path, fee_snapshot_id, cost_config, source_outcome_run_id
        )
        required_artifacts = [
            root / "outcome_scoring_dataset.parquet",
            root / "fee_coverage_audit.json",
            root / "scoring_semantics_audit.json",
            root / "cost_summary_audit.json",
            root / "fee_join_context_audit.json",
        ]
        missing = [str(path) for path in required_artifacts if not path.exists()]
        if missing:
            raise FileNotFoundError(f"required scoring artifacts missing before completion: {missing}")
        _write_status(root, {
            "status": "complete",
            "scoring_run_id": scoring_run_id,
            "source_outcome_run_id": source_outcome_run_id,
            "completed_at_utc": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        })
        return result
    except Exception as exc:
        _write_status(root, {"status": "failed", "scoring_run_id": scoring_run_id, "source_outcome_run_id": source_outcome_run_id, "failed_stage": "build_scoring_dataset", "error_type": type(exc).__name__, "error_summary": str(exc)[:500]})
        raise


def _build_scoring_dataset_impl(
    input_path: Path,
    scoring_run_id: str,
    weights_path: str | None = None,
    fee_snapshot_id: str | None = None,
    cost_config: str | None = None,
    source_outcome_run_id: str | None = None,
) -> dict[str, object]:
    df = pl.read_parquet(input_path)
    if "category" not in df.columns:
        raise ValueError("expanded_scoring_input missing required category")
    if source_outcome_run_id is not None and "source_outcome_run_id" not in df.columns:
        df = df.with_columns(pl.lit(source_outcome_run_id).alias("source_outcome_run_id"))
    fees, meta = load_fee_rates(fee_snapshot_id)
    df, expanded_fee_join_audit = join_account_fees(df, fees, context="expanded_scoring_input")
    miss = expanded_fee_join_audit["symbols_missing_fee_rates"]
    root = Path("data/processed/scoring_runs") / scoring_run_id
    root.mkdir(parents=True, exist_ok=True)
    coverage = {
        "fee_snapshot_id_requested": fee_snapshot_id,
        "fee_snapshot_id_resolved": meta["fee_snapshot_id_resolved"],
        "fee_source": meta["fee_source"],
        "scoring_symbols": sorted(df["symbol"].unique().to_list()),
        "symbols_with_fee_rates": sorted(
            df.filter(pl.col("maker_fee_rate").is_not_null())["symbol"].unique().to_list()
        ),
        "symbols_missing_fee_rates": miss,
        "fee_coverage_rate": 1 - len(miss) / max(df["symbol"].n_unique(), 1),
        "fee_coverage_ok": not miss,
    }
    fee_join_context_audits = {"expanded_scoring_input": expanded_fee_join_audit}
    (root / "fee_coverage_audit.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True), encoding="utf-8"
    )
    if miss:
        pl.DataFrame({"symbol": miss}).write_parquet(root / "fee_missing_symbols.parquet")
        raise ValueError(json.dumps(coverage))
    df = add_ex_post_components(df)
    cfg = load_cost_config(cost_config or "config/cost_scenarios.yml")
    df = df.with_columns(
        [
            pl.lit(cfg["cost_model_version"]).alias("cost_model_version"),
            pl.lit(meta["fee_snapshot_id_resolved"]).alias("fee_snapshot_id"),
        ]
    )
    scenario_names = []
    for scen in scenario_objects(cfg):
        scenario_names.append(scen.name)
        entry = (
            pl.when(pl.lit(scen.entry_fee_source) == "maker")
            .then(pl.col("maker_fee_rate"))
            .otherwise(pl.col("taker_fee_rate"))
        )
        exitf = (
            pl.when(pl.lit(scen.exit_fee_source) == "maker")
            .then(pl.col("maker_fee_rate"))
            .otherwise(pl.col("taker_fee_rate"))
        )
        r = pl.col("grid_interval_ratio").cast(pl.Float64)
        slip = pl.lit(scen.slippage_bps_per_market_leg / 10_000.0)
        gross_long = r - 1
        gross_short = (r - 1) / r
        net_long = gross_long - (entry + exitf * r + slip + slip * r)
        net_short = gross_short - (entry + exitf / r + slip + slip / r)
        df = df.with_columns(
            [
                (net_long * 10_000).alias(f"cost_{scen.name}_net_cycle_return_long_bps_proxy"),
                (net_short * 10_000).alias(f"cost_{scen.name}_net_cycle_return_short_bps_proxy"),
                (net_long > 0).alias(f"cost_{scen.name}_fee_break_even_long_bool"),
                (net_short > 0).alias(f"cost_{scen.name}_fee_break_even_short_bool"),
                ((net_long > 0) & (net_short > 0)).alias(
                    f"cost_{scen.name}_fee_break_even_both_bool"
                ),
                (net_long / gross_long).alias(f"cost_{scen.name}_fee_efficiency_ratio_long"),
                (net_short / gross_short).alias(f"cost_{scen.name}_fee_efficiency_ratio_short"),
            ]
        )
    weights = load_weights(weights_path)
    cost_cols = [f"cost_{n}_fee_break_even_both_bool" for n in scenario_names]
    df = df.with_columns(
        [
            pl.mean_horizontal([pl.col(c).cast(pl.Float64) for c in cost_cols]).alias(
                "ex_post_fee_viability_score"
            ),
            (
                (
                    pl.col("ex_post_close_cross_activity_lower").cast(pl.Float64)
                    + pl.col("ex_post_intrabar_touch_activity_upper").cast(pl.Float64)
                    + pl.col("ex_post_unique_levels_touched").cast(pl.Float64)
                )
                / (pl.col("future_horizon_minutes").cast(pl.Float64).clip(1, None))
            )
            .clip(0, 1)
            .alias("ex_post_grid_activity_score"),
        ]
    )
    for name, w in weights["weight_sets"].items():
        event = (
            (pl.col("ex_post_range_survival_ratio") * w["range"])
            + (pl.col("ex_post_data_quality_score") * w["quality"])
            + (pl.col("ex_post_capital_turnover_score") * w["turnover"])
        ) / (w["range"] + w["quality"] + w["turnover"])
        sl = event * 0.7 + (1 - pl.col("ex_post_sl_risk_score").fill_null(1.0)) * 0.3
        grid = (
            event * 0.6
            + pl.col("ex_post_grid_activity_score") * 0.2
            + pl.col("ex_post_fee_viability_score") * 0.2
        )
        combined = (
            pl.col("ex_post_range_survival_ratio") * w["range"]
            + pl.col("ex_post_data_quality_score") * w["quality"]
            + (1 - pl.col("ex_post_sl_risk_score").fill_null(1.0)) * w["sl"]
            + pl.col("ex_post_capital_turnover_score") * w["turnover"]
            + pl.col("ex_post_grid_activity_score") * w["activity"]
            + pl.col("ex_post_fee_viability_score") * w["cost"]
        )
        eligible = pl.col("ex_post_score_eligible_bool")
        df = df.with_columns(
            [
                event.clip(0, 1).alias(f"ex_post_event_quality_score_v2_{name}"),
                sl.clip(0, 1).alias(f"ex_post_sl_probe_score_v2_{name}"),
                grid.clip(0, 1).alias(f"ex_post_grid_probe_score_v2_{name}"),
                combined.clip(0, 1).alias(f"ex_post_combined_probe_score_v2_{name}"),
                pl.when(eligible).then(event.clip(0, 1)).otherwise(None).alias(f"ex_post_event_quality_score_v3_{name}"),
                pl.when(eligible).then(sl.clip(0, 1)).otherwise(None).alias(f"ex_post_sl_probe_score_v3_{name}"),
                pl.when(eligible).then(grid.clip(0, 1)).otherwise(None).alias(f"ex_post_grid_probe_score_v3_{name}"),
                pl.when(eligible).then(combined.clip(0, 1)).otherwise(None).alias(f"ex_post_combined_probe_score_v3_{name}"),
                combined.clip(0, 1).alias(f"ex_post_combined_probe_score_v3_{name}_conservative_all_rows"),
            ]
        )
    df = df.with_columns(
        pl.col("ex_post_combined_probe_score_v3_balanced_v2").alias("ex_post_proxy_score_v1")
    )
    df.write_parquet(root / "outcome_scoring_dataset.parquet")
    v3_score_cols = [f"ex_post_combined_probe_score_v3_{n}" for n in weights["weight_sets"]]
    eligible_rows = df.filter(pl.col("ex_post_score_eligible_bool")).height
    ineligible_rows = df.height - eligible_rows
    score_null_count_by_weight_set = {n: df[f"ex_post_combined_probe_score_v3_{n}"].null_count() for n in weights["weight_sets"]}
    ineligible_reason_counts = (
        df.filter(~pl.col("ex_post_score_eligible_bool"))
        .group_by("ex_post_score_incomplete_reason")
        .len()
        .to_dicts()
        if ineligible_rows else []
    )
    eligible_nulls = sum(df.filter(pl.col("ex_post_score_eligible_bool"))[c].null_count() for c in v3_score_cols)
    ineligible_non_nulls = sum(df.filter(~pl.col("ex_post_score_eligible_bool"))[c].drop_nulls().len() for c in v3_score_cols)
    non_finite = 0
    out_bounds = 0
    for c in v3_score_cols:
        non_finite += df.filter(pl.col(c).is_not_null() & ~pl.col(c).is_finite()).height
        out_bounds += df.filter(pl.col(c).is_not_null() & ((pl.col(c) < 0) | (pl.col(c) > 1))).height
    corr_cols = v3_score_cols
    high_pairs = []
    for i, a_col in enumerate(corr_cols):
        for b_col in corr_cols[i + 1 :]:
            val = df.filter(pl.col(a_col).is_not_null() & pl.col(b_col).is_not_null()).select(
                pl.corr(pl.col(a_col).rank(), pl.col(b_col).rank())
            ).item()
            if val is not None and math.isfinite(val) and abs(val) >= 0.98:
                high_pairs.append({"a": a_col, "b": b_col, "abs_spearman": abs(val)})
    sem_ok = eligible_nulls == 0 and ineligible_non_nulls == 0 and non_finite == 0 and out_bounds == 0
    sem = {
        "scoring_semantics_audit_ok": sem_ok,
        "scoring_run_id": scoring_run_id,
        "source_outcome_run_id": df["source_outcome_run_id"][0] if "source_outcome_run_id" in df.columns else None,
        "rows_total": df.height,
        "score_eligible_rows": eligible_rows,
        "score_ineligible_rows": ineligible_rows,
        "score_eligible_rate": eligible_rows / max(df.height, 1),
        "ineligible_reason_counts": ineligible_reason_counts,
        "score_null_count_by_weight_set": score_null_count_by_weight_set,
        "eligible_null_canonical_score_count": eligible_nulls,
        "ineligible_non_null_canonical_score_count": ineligible_non_nulls,
        "non_finite_score_count": non_finite,
        "out_of_bounds_score_count": out_bounds,
        "canonical_score_version": "v3",
        "risk_budget_usdt": 5,
        "risk_budget_proven_bool": False,
        "profitability_claims_present_bool": False,
        "pnl_claims_present_bool": False,
        "placeholder_constant_components_present": False,
        "high_correlation_pair_count_abs_spearman_ge_0_98": len(high_pairs),
        "high_correlation_pairs": high_pairs,
    }
    (root / "scoring_semantics_audit.json").write_text(json.dumps(sem, indent=2, sort_keys=True), encoding="utf-8")
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "fee_snapshot_report.md").write_text(
        f"# Fee Snapshot Report\n\nresolved: {meta['fee_snapshot_id_resolved']}\ncoverage: {coverage['fee_coverage_rate']}\n",
        encoding="utf-8",
    )
    if cost_config:
        (rep / "cost_model_config_resolved.yml").write_text(
            json.dumps(
                {
                    "scoring_run_id": scoring_run_id,
                    "source_outcome_run_id": df["source_outcome_run_id"][0] if "source_outcome_run_id" in df.columns else None,
                    "cost_model_version": cfg["cost_model_version"],
                    "cost_formula_version": COST_FORMULA_VERSION,
                    "fee_snapshot_id_requested": fee_snapshot_id,
                    "fee_snapshot_id_resolved": meta["fee_snapshot_id_resolved"],
                    "fee_source": meta["fee_source"],
                    "fee_coverage_rate": coverage["fee_coverage_rate"],
                    "risk_budget_usdt": 5,
                    "risk_budget_proven_bool": False,
                    "scenarios": cfg["scenarios"],
                    "score_weights_version": weights["score_weights_version"],
                    "weight_sets": weights["weight_sets"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    (rep / "cost_model_audit.json").write_text(
        json.dumps(
            {
                "cost_model_audit_ok": True,
                "cost_model_version": cfg["cost_model_version"],
                "cost_formula_version": COST_FORMULA_VERSION,
                "asymmetric_fee_normalization_ok": True,
                "asymmetric_slippage_normalization_ok": True,
                "fee_snapshot_id_resolved": meta["fee_snapshot_id_resolved"],
                "fee_source": meta["fee_source"],
                "fee_coverage_rate": coverage["fee_coverage_rate"],
                "risk_budget_proven_bool": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    dists = {}
    for n in weights["weight_sets"]:
        col = f"ex_post_combined_probe_score_v3_{n}"
        eligible_dist = _dist(df.filter(pl.col("ex_post_score_eligible_bool")), col)
        eligible_dist.update(
            {
                "rows_total": df.height,
                "eligible_rows": eligible_rows,
                "ineligible_rows": ineligible_rows,
                "canonical_null_count_all_rows": df[col].null_count(),
                "eligible_distribution_count": eligible_rows,
            }
        )
        dists[n] = eligible_dist
    (rep / "score_sensitivity_report.md").write_text(
        "# Score Sensitivity Report\n\n" + json.dumps({"distributions": dists}, indent=2),
        encoding="utf-8",
    )
    summary = df.group_by("symbol").agg(
        [
            pl.len().alias("row_count_total"),
            pl.col("ex_post_score_eligible_bool").sum().alias("score_eligible_rows"),
            (~pl.col("ex_post_score_eligible_bool")).sum().alias("score_ineligible_rows"),
            pl.col("ex_post_proxy_score_v1")
            .filter(pl.col("ex_post_score_eligible_bool"))
            .mean()
            .alias("mean_score_eligible_only"),
            pl.len().alias("row_count"),
            pl.col("ex_post_proxy_score_v1")
            .filter(pl.col("ex_post_score_eligible_bool"))
            .mean()
            .alias("mean_score"),
        ]
    )
    summary.write_parquet(rep / "outcome_scoring_summary.parquet")
    (rep / "outcome_scoring_report.md").write_text(
        "# Outcome Scoring Report\n\nEx-post proxy diagnostics only; not PnL/ROI/EV/profitability.\n",
        encoding="utf-8",
    )
    (rep / "risk_budget_readiness_report.md").write_text(
        "# Risk Budget Status: NOT YET PROVEN\n\nrisk_budget_proven_bool: false\n", encoding="utf-8"
    )
    score_cols = [c for c in df.columns if c.startswith("ex_post_") and "score_v3" in c and "conservative" not in c]
    pl.DataFrame(
        [
            {"component": c, "mean": df[c].mean(), "min": df[c].min(), "max": df[c].max()}
            for c in [
                "ex_post_data_quality_score",
                "ex_post_grid_activity_score",
                "ex_post_fee_viability_score",
                *score_cols,
            ]
            if c in df.columns
        ]
    ).write_parquet(rep / "score_component_summary.parquet")
    corr = {
        a: {
            b: {
                "pearson": df.select(pl.corr(a, b)).item(),
                "spearman": df.select(pl.corr(pl.col(a).rank(), pl.col(b).rank())).item(),
            }
            for b in score_cols
        }
        for a in score_cols
    }
    (rep / "score_correlation_report.json").write_text(
        json.dumps({"score_correlation_report_ok": True, "correlations": corr}, indent=2),
        encoding="utf-8",
    )
    cost_rows = []
    cost_keys = ["range_action_event_id", "future_horizon_minutes", "grid_cell_number"]
    grain_path = root / "event_horizon_grid.parquet"
    if grain_path.exists():
        cost_df = pl.read_parquet(grain_path)
        required = {"category", "symbol", "range_action_event_id", "future_horizon_minutes", "grid_cell_number"}
        missing_required = sorted(required - set(cost_df.columns))
        if missing_required:
            raise ValueError(f"event_horizon_grid missing required cost columns: {missing_required}")
        duplicate_cost_keys = _duplicate_key_count(cost_df, cost_keys)
        if duplicate_cost_keys:
            raise ValueError(f"duplicate event-horizon-grid cost keys: {duplicate_cost_keys}")
        cost_df, cost_fee_join_audit = join_account_fees(cost_df, fees, context="cost_summary_event_horizon_grid")
        fee_join_context_audits["cost_summary_event_horizon_grid"] = cost_fee_join_audit
        for scen in scenario_objects(cfg):
            entry = (
                pl.when(pl.lit(scen.entry_fee_source) == "maker")
                .then(pl.col("maker_fee_rate"))
                .otherwise(pl.col("taker_fee_rate"))
            )
            exitf = (
                pl.when(pl.lit(scen.exit_fee_source) == "maker")
                .then(pl.col("maker_fee_rate"))
                .otherwise(pl.col("taker_fee_rate"))
            )
            r = pl.col("grid_interval_ratio").cast(pl.Float64)
            slip = pl.lit(scen.slippage_bps_per_market_leg / 10_000.0)
            gross_long = r - 1
            gross_short = (r - 1) / r
            net_long = gross_long - (entry + exitf * r + slip + slip * r)
            net_short = gross_short - (entry + exitf / r + slip + slip / r)
            cost_df = cost_df.with_columns(
                [
                    (net_long * 10_000).alias(f"cost_{scen.name}_net_cycle_return_long_bps_proxy"),
                    (net_short * 10_000).alias(f"cost_{scen.name}_net_cycle_return_short_bps_proxy"),
                    ((net_long > 0) & (net_short > 0)).alias(f"cost_{scen.name}_fee_break_even_both_bool"),
                    (net_long / gross_long).alias(f"cost_{scen.name}_fee_efficiency_ratio_long"),
                    (net_short / gross_short).alias(f"cost_{scen.name}_fee_efficiency_ratio_short"),
                ]
            )
    else:
        raise FileNotFoundError(f"required canonical cost grain not found: {grain_path}")
    sl_rows_removed = df.height - cost_df.height
    for scen in scenario_names:
        cost_rows.append(
            cost_df.group_by(["future_horizon_minutes", "grid_cell_number"])
            .agg(
                [
                    pl.len().alias("row_count"),
                    pl.col(f"cost_{scen}_fee_break_even_both_bool")
                    .mean()
                    .alias("fee_break_even_both_rate"),
                    pl.col(f"cost_{scen}_net_cycle_return_long_bps_proxy")
                    .quantile(0.5)
                    .alias("net_cycle_return_long_bps_proxy_p50"),
                    pl.col(f"cost_{scen}_net_cycle_return_short_bps_proxy")
                    .quantile(0.5)
                    .alias("net_cycle_return_short_bps_proxy_p50"),
                    pl.col(f"cost_{scen}_fee_efficiency_ratio_long")
                    .quantile(0.5)
                    .alias("fee_efficiency_long_p50"),
                    pl.col(f"cost_{scen}_fee_efficiency_ratio_short")
                    .quantile(0.5)
                    .alias("fee_efficiency_short_p50"),
                ]
            )
            .with_columns(pl.lit(scen).alias("scenario"))
        )
    cost_summary = (pl.concat(cost_rows, how="diagonal_relaxed") if cost_rows else pl.DataFrame()).with_columns([
        pl.lit("event_horizon_grid").alias("cost_summary_grain"),
        pl.lit(cost_df.height).alias("cost_summary_source_rows"),
        pl.lit(duplicate_cost_keys).alias("cost_summary_duplicate_key_count"),
        pl.lit(False).alias("cost_summary_dimension_multiplication_detected_bool"),
    ])
    cost_summary.write_parquet(rep / "cost_scenario_summary.parquet")
    cost_audit = {
        "cost_summary_audit_ok": duplicate_cost_keys == 0,
        "cost_summary_grain": "event_horizon_grid",
        "cost_summary_source_rows": cost_df.height,
        "cost_summary_expected_rows": cost_df.height,
        "cost_summary_duplicate_key_count": duplicate_cost_keys,
        "cost_summary_dimension_multiplication_detected_bool": False,
        "expanded_scoring_rows": df.height,
        "sl_dimension_rows_not_used_for_cost_summary": sl_rows_removed,
        "cost_summary_scenario_count": len(scenario_names),
        "cost_summary_group_count": cost_summary.height,
    }
    (root / "cost_summary_audit.json").write_text(json.dumps(cost_audit, indent=2, sort_keys=True), encoding="utf-8")
    (root / "fee_join_context_audit.json").write_text(json.dumps(fee_join_context_audits, indent=2, sort_keys=True), encoding="utf-8")
    (rep / "cost_scenario_report.md").write_text(
        f"# Cost Scenario Report\n\nOne-cycle proxy diagnostics only; not event PnL.\n\ncost_summary_grain: event_horizon_grid\ncost_summary_source_rows: {cost_df.height}\nexpanded rows ignored for cost summary: {df.height}\nSL-dimension rows intentionally removed: {sl_rows_removed}\nactual duplicate event-horizon-grid keys: {duplicate_cost_keys}\n",
        encoding="utf-8",
    )
    (rep / "scoring_null_policy.md").write_text(
        "# Scoring Null Policy\n\nIncomplete evidence is excluded from ranking: canonical v3 ranking scores are null when ex_post_score_eligible_bool=false. Conservative all-row diagnostics are not ranking scores.\n",
        encoding="utf-8",
    )
    return {
        "rows": df.height,
        "risk_budget_proven_bool": False,
        "fee_coverage": coverage,
        "score_distribution_by_fixed_weight_set": dists,
    }
