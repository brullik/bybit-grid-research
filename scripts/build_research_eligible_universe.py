from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

UNSPECIFIED = "FGRID_CHECK_CODE_UNSPECIFIED"


def build(selected: pl.DataFrame, constraints: pl.DataFrame, target: float, min_turnover: float) -> pl.DataFrame:
    if selected.is_empty() or constraints.is_empty():
        return pl.DataFrame()
    c = constraints
    if "min_investment_feasible_at_5usdt" not in c.columns and "feasible_user_5usdt_rule" in c.columns:
        c = c.with_columns(pl.col("feasible_user_5usdt_rule").alias("min_investment_feasible_at_5usdt"))
    eligible = c.filter(
        pl.col("validate_ok")
        & pl.col("feasible_bybit")
        & pl.col("min_investment_feasible_at_5usdt")
        & pl.col("target_init_margin_inside_validate_range")
        & (pl.col("check_code").is_null() | (pl.col("check_code") == UNSPECIFIED))
    )
    best = eligible.sort(["symbol", "investment_min"]).unique("symbol", keep="first")
    joined = selected.join(best, on="symbol", how="inner", suffix="_validate")
    if "turnover24h" in joined.columns:
        joined = joined.filter(pl.col("turnover24h") >= min_turnover)
    if "isPreListing" in joined.columns:
        joined = joined.filter(~pl.col("isPreListing"))
    if "age_days" in joined.columns:
        joined = joined.filter(pl.col("age_days").is_null() | (pl.col("age_days") >= 1))
    return joined.sort(["turnover24h", "investment_min"], descending=[True, False])


def write_report(path: Path, df: pl.DataFrame, target: float) -> None:
    path.parent.mkdir(exist_ok=True)
    lines=["# Sprint 02 Research Eligible Universe Report", "", f"target_init_margin_usdt: {target}", f"eligible_symbols_count: {df.height}", "", "| symbol | turnover24h | investment_min | investment_max |", "|---|---:|---:|---:|"]
    for r in df.head(100).to_dicts():
        lines.append(f"| {r.get('symbol')} | {r.get('turnover24h')} | {r.get('investment_min')} | {r.get('investment_max')} |")
    path.write_text("\n".join(lines)+"\n", encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--selected', default='data/processed/universe_selected.parquet')
    ap.add_argument('--constraints', default='data/processed/fgrid_validate_constraints.parquet')
    ap.add_argument('--target-init-margin', type=float, default=5)
    ap.add_argument('--min-turnover', type=float, default=1_000_000)
    args=ap.parse_args()
    selected=pl.read_parquet(args.selected) if Path(args.selected).exists() else pl.DataFrame()
    constraints=pl.read_parquet(args.constraints) if Path(args.constraints).exists() else pl.DataFrame()
    df=build(selected,constraints,args.target_init_margin,args.min_turnover)
    Path('data/processed').mkdir(parents=True, exist_ok=True)
    df.write_parquet('data/processed/research_eligible_universe.parquet')
    write_report(Path('reports/sprint_02_research_eligible_universe_report.md'), df, args.target_init_margin)
    print(f"eligible_symbols_count={df.height}")
if __name__ == '__main__':
    main()
