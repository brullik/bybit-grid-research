from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from bybit_grid.data.download_manifest import build_download_manifest, write_download_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="data/processed/universe_selected.parquet")
    parser.add_argument("--feasible", default="data/processed/fgrid_feasible_configs.parquet")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--max-symbols", type=int, default=50)
    parser.add_argument("--max-gb", type=float, default=25)
    args = parser.parse_args()
    universe = pl.read_parquet(args.universe)
    feasible = pl.read_parquet(args.feasible) if Path(args.feasible).exists() else pl.DataFrame()
    manifest = build_download_manifest(
        universe, feasible, args.days, args.max_symbols, args.max_gb
    )
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    manifest.write_parquet("data/processed/download_manifest.parquet")
    write_download_plan(Path("reports/sprint_02_download_plan.md"), manifest, args.days, args.max_gb)
    estimated_gb = manifest["estimated_gb"].sum() if not manifest.is_empty() else 0
    print(f"rows={manifest.height} est_gb={estimated_gb:.3f}")


if __name__ == "__main__":
    main()
