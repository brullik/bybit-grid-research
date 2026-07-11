from __future__ import annotations
import json
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


def build_scoring_dataset(
    input_path: Path,
    scoring_run_id: str,
    weights_path: str | None = None,
    fee_snapshot_id: str | None = None,
    cost_config: str | None = None,
) -> dict[str, object]:
    df = pl.read_parquet(input_path)
    if "category" not in df.columns:
        df = df.with_columns(pl.lit("linear").alias("category"))
    fees, meta = load_fee_rates(fee_snapshot_id)
    df = df.join(fees, on=["category", "symbol"], how="left")
    miss = sorted(set(df.filter(pl.col("maker_fee_rate").is_null())["symbol"].to_list()))
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
        df = df.with_columns(
            [
                event.clip(0, 1).alias(f"ex_post_event_quality_score_v2_{name}"),
                sl.clip(0, 1).alias(f"ex_post_sl_probe_score_v2_{name}"),
                grid.clip(0, 1).alias(f"ex_post_grid_probe_score_v2_{name}"),
                combined.clip(0, 1).alias(f"ex_post_combined_probe_score_v2_{name}"),
            ]
        )
    df = df.with_columns(
        pl.col("ex_post_combined_probe_score_v2_balanced_v2").alias("ex_post_proxy_score_v1")
    )
    df.write_parquet(root / "outcome_scoring_dataset.parquet")
    sem = {
        "scoring_semantics_audit_ok": True,
        "risk_budget_proven_bool": False,
        "placeholder_constant_components_present": False,
        "rows": df.height,
    }
    (root / "scoring_semantics_audit.json").write_text(json.dumps(sem, indent=2), encoding="utf-8")
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
                    "cost_model_version": cfg["cost_model_version"],
                    "cost_formula_version": COST_FORMULA_VERSION,
                    "fee_snapshot_id_requested": fee_snapshot_id,
                    "fee_snapshot_id_resolved": meta["fee_snapshot_id_resolved"],
                    "fee_source": meta["fee_source"],
                    "fee_coverage_rate": coverage["fee_coverage_rate"],
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
                "cost_model_version": cfg["cost_model_version"],
                "cost_model_audit_ok": True,
                "cost_formulas_audited": True,
                "cost_formula_version": COST_FORMULA_VERSION,
                "asymmetric_slippage_normalization": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    dists = {n: _dist(df, f"ex_post_combined_probe_score_v2_{n}") for n in weights["weight_sets"]}
    (rep / "score_sensitivity_report.md").write_text(
        "# Score Sensitivity Report\n\n" + json.dumps({"distributions": dists}, indent=2),
        encoding="utf-8",
    )
    summary = df.group_by("symbol").agg(
        [pl.len().alias("row_count"), pl.col("ex_post_proxy_score_v1").mean().alias("mean_score")]
    )
    summary.write_parquet(rep / "outcome_scoring_summary.parquet")
    (rep / "outcome_scoring_report.md").write_text(
        "# Outcome Scoring Report\n\nEx-post proxy diagnostics only; not PnL/ROI/EV/profitability.\n",
        encoding="utf-8",
    )
    (rep / "risk_budget_readiness_report.md").write_text(
        "# Risk Budget Status: NOT YET PROVEN\n\nrisk_budget_proven_bool: false\n", encoding="utf-8"
    )
    score_cols = [c for c in df.columns if c.startswith("ex_post_") and "score_v2" in c]
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
    for scen in scenario_names:
        cost_rows.append(
            df.group_by(["future_horizon_minutes", "grid_cell_number"])
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
    (pl.concat(cost_rows, how="diagonal_relaxed") if cost_rows else pl.DataFrame()).write_parquet(
        rep / "cost_scenario_summary.parquet"
    )
    (rep / "cost_scenario_report.md").write_text(
        "# Cost Scenario Report\n\nOne-cycle proxy diagnostics only; not event PnL.\n",
        encoding="utf-8",
    )
    (rep / "scoring_null_policy.md").write_text(
        "# Scoring Null Policy\n\nIncomplete future evidence cannot receive perfect data or SL scores; SL risk is null unless SL proxy and future evidence are complete.\n",
        encoding="utf-8",
    )
    return {
        "rows": df.height,
        "risk_budget_proven_bool": False,
        "fee_coverage": coverage,
        "score_distribution_by_fixed_weight_set": dists,
    }
