from __future__ import annotations
import json
from pathlib import Path
import polars as pl
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
    # Sprint 05 intentionally uses fixed built-in weights when no explicit JSON-like
    # file is supplied; this is not a search or optimization routine.
    return DEFAULT_WEIGHTS


def build_scoring_dataset(
    input_path: Path, scoring_run_id: str, weights_path: str | None = None
) -> dict[str, object]:
    df = pl.read_parquet(input_path)
    df = add_ex_post_components(df)
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
    root = Path("data/processed/scoring_runs") / scoring_run_id
    root.mkdir(parents=True, exist_ok=True)
    df.write_parquet(root / "outcome_scoring_dataset.parquet")
    rep = Path("reports/scoring_runs") / scoring_run_id
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "outcome_scoring_report.md").write_text(
        "# Outcome Scoring Report\n\nHistorical ex_post proxy diagnostics only. Not PnL, ROI, EV, Profit Factor, Sharpe, or profitability.\n\n## Risk Budget Status: NOT YET PROVEN\nNext required model: native neutral-grid position/exposure simulator\n",
        encoding="utf-8",
    )
    sens = {
        name: df.select(pl.col(f"ex_post_proxy_score_v1_{name}").mean()).item()
        for name in weights["weight_sets"]
    }
    (rep / "score_sensitivity_report.md").write_text(
        "# Score Sensitivity Report\n\nFixed, not optimized.\n" + json.dumps(sens, indent=2),
        encoding="utf-8",
    )
    (rep / "risk_budget_readiness_report.md").write_text(
        "# Risk Budget Status: NOT YET PROVEN\n\nNext required model: native neutral-grid position/exposure simulator\n\nNeutral-grid net exposure varies as orders execute, so actual maximum loss is not proven.\n",
        encoding="utf-8",
    )
    return {
        "rows": df.height,
        "risk_budget_proven_bool": False,
        "score_distribution_by_fixed_weight_set": sens,
    }
