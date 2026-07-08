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
    summary, aggregate = summarize_min_investment(df)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    summary.write_parquet("data/processed/fgrid_min_investment_by_symbol.parquet")
    write_report(Path("reports/sprint_02_native_grid_feasibility_report.md"), summary, aggregate)
    print(
        f"symbols_tested={aggregate.get('symbols_tested', 0)} configs_tested={aggregate.get('configs_tested', 0)}"
    )


if __name__ == "__main__":
    main()
