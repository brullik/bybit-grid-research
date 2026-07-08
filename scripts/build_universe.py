from __future__ import annotations

# ruff: noqa: E402

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.universe.builder import (
    fetch_linear_instruments,
    fetch_linear_tickers,
    filter_universe,
    normalize_universe,
    write_universe_report,
)


def build_universe(min_turnover: float = 5_000_000, max_symbols: int = 100) -> dict[str, int]:
    settings = load_settings()
    with BybitClient(settings) as client:
        df = normalize_universe(fetch_linear_instruments(client), fetch_linear_tickers(client))
    candidates, selected, counts = filter_universe(df, min_turnover, max_symbols)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    candidates.write_parquet("data/processed/universe_candidates.parquet")
    selected.write_parquet("data/processed/universe_selected.parquet")
    write_universe_report(
        Path("reports/sprint_02_universe_report.md"), counts, selected, min_turnover
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-turnover", type=float, default=5_000_000)
    parser.add_argument("--max-symbols", type=int, default=100)
    args = parser.parse_args()
    print(build_universe(args.min_turnover, args.max_symbols))


if __name__ == "__main__":
    main()
