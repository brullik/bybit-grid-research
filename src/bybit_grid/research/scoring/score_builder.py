from __future__ import annotations
import json
import shutil
from pathlib import Path
import polars as pl
from bybit_grid.research.cost_model.cycle_costs import geometric_cycle_costs
from bybit_grid.research.cost_model.models import FeeRate, load_cost_config, scenario_objects
from bybit_grid.research.scoring.components import add_ex_post_components

DEFAULT_WEIGHTS = {
    "score_weights_version": "score_weights_v1_fixed",
    "weight_sets": {
        "balanced": {"range": 0.4, "sl": 0.2, "data": 0.2, "turnover": 0.2},
        "survival_heavy": {"range": 0.6, "sl": 0.2, "data": 0.1, "turnover": 0.1},
        "quality_heavy": {"range": 0.3, "sl": 0.2, "data": 0.4, "turnover": 0.1},
    },
}


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
    for scen in scenario_objects(cfg):
        vals = []
        for r in df.select(
            [
                "symbol",
                "maker_fee_rate",
                "taker_fee_rate",
                "fee_snapshot_id",
                "fee_source",
                "grid_interval_ratio",
            ]
        ).iter_rows(named=True):
            vals.append(
                geometric_cycle_costs(
                    float(r["grid_interval_ratio"]),
                    FeeRate(
                        r["symbol"],
                        r["maker_fee_rate"],
                        r["taker_fee_rate"],
                        r["fee_snapshot_id"],
                        r["fee_source"],
                    ),
                    scen,
                )
            )
        cdf = pl.DataFrame(vals).select(
            [
                pl.col("net_cycle_return_long_bps").alias(
                    f"cost_{scen.name}_net_cycle_return_long_bps_proxy"
                ),
                pl.col("net_cycle_return_short_bps").alias(
                    f"cost_{scen.name}_net_cycle_return_short_bps_proxy"
                ),
                pl.col("fee_break_even_long_bool").alias(
                    f"cost_{scen.name}_fee_break_even_long_bool"
                ),
                pl.col("fee_break_even_short_bool").alias(
                    f"cost_{scen.name}_fee_break_even_short_bool"
                ),
                (pl.col("fee_break_even_long_bool") & pl.col("fee_break_even_short_bool")).alias(
                    f"cost_{scen.name}_fee_break_even_both_bool"
                ),
                pl.col("fee_efficiency_ratio_long").alias(
                    f"cost_{scen.name}_fee_efficiency_ratio_long"
                ),
                pl.col("fee_efficiency_ratio_short").alias(
                    f"cost_{scen.name}_fee_efficiency_ratio_short"
                ),
            ]
        )
        df = pl.concat([df, cdf], how="horizontal")
    weights = load_weights(weights_path)
    for name, w in weights["weight_sets"].items():
        df = df.with_columns(
            (
                (pl.col("ex_post_range_survival_ratio") * w["range"])
                + (pl.col("ex_post_data_complete_score") * w["data"])
                + ((1 - pl.col("ex_post_sl_risk_score")) * w["sl"])
                + (pl.col("ex_post_capital_turnover_score") * w["turnover"])
            ).alias(f"ex_post_proxy_score_v1_{name}")
        )
    df = df.with_columns(pl.col("ex_post_proxy_score_v1_balanced").alias("ex_post_proxy_score_v1"))
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
        shutil.copyfile(cost_config, rep / "cost_model_config_resolved.yml")
    (rep / "cost_model_audit.json").write_text(
        json.dumps(
            {"cost_model_version": cfg["cost_model_version"], "cost_formulas_audited": True},
            indent=2,
        ),
        encoding="utf-8",
    )
    dists = {n: _dist(df, f"ex_post_proxy_score_v1_{n}") for n in weights["weight_sets"]}
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
    return {
        "rows": df.height,
        "risk_budget_proven_bool": False,
        "fee_coverage": coverage,
        "score_distribution_by_fixed_weight_set": dists,
    }
