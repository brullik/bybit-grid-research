from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.bybit.fgrid_feasibility import summarize_min_investment, write_report


def main() -> None:
    inp = Path("data/processed/fgrid_validate_constraints.parquet")
    df = pl.read_parquet(inp) if inp.exists() else pl.DataFrame()
    if df.is_empty():
        print("No constraints available. Run validate_universe_fgrid_constraints.py first.")
        return
    has_real_investment = "investment_min" in df.columns and df["investment_min"].drop_nulls().len() > 0
    if not has_real_investment:
        message = (
            "No real investment_min values found. Check GRID_VALIDATE_ENABLED and purge skipped constraints."
        )
        Path("reports").mkdir(exist_ok=True)
        Path("reports/sprint_02_native_grid_feasibility_report.md").write_text(
            f"# Sprint 02 Native Grid Feasibility Report\n\n{message}\n", encoding="utf-8"
        )
        print(message)
        raise SystemExit(1)
    summary, aggregate = summarize_min_investment(df)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    summary.write_parquet("data/processed/fgrid_min_investment_by_symbol.parquet")
    write_report(Path("reports/sprint_02_native_grid_feasibility_report.md"), summary, aggregate)
    parts = [
        f"symbols_tested={aggregate.get('symbols_tested', 0)}",
        f"configs_tested={aggregate.get('configs_tested', 0)}",
        f"investment_min_non_null_rows={df['investment_min'].drop_nulls().len() if 'investment_min' in df.columns else 0}",
        f"min_investment_min_global_bybit_feasible_only={aggregate.get('min_investment_min_global_bybit_feasible_only')}",
    ]
    for threshold in (5, 10, 25, 50, 100, 250, 500):
        parts.append(f"symbols_min_investment_feasible_at_{threshold}={aggregate.get(f'symbols_min_investment_feasible_at_{threshold}', 0)}")
        parts.append(f"symbols_feasible_at_{threshold}={aggregate.get(f'symbols_feasible_at_{threshold}', 0)}")
    print(" ".join(parts))


if __name__ == "__main__":
    main()
