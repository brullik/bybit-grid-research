from __future__ import annotations

# ruff: noqa: E402

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bybit_grid.bybit.fgrid_feasibility import summarize_min_investment
from bybit_grid.config import load_settings
from scripts.build_universe import build_universe
from scripts.validate_universe_fgrid_constraints import purge_skipped_constraints


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout


def _parse_int(text: str, key: str) -> int:
    m = re.search(rf"{re.escape(key)}[=<=]+([0-9]+)", text)
    return int(m.group(1)) if m else 0


def _parse_float(text: str, key: str) -> float:
    m = re.search(rf"{re.escape(key)}=([0-9.]+)", text)
    return float(m.group(1)) if m else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-symbols", type=int, default=150)
    parser.add_argument("--min-turnover", type=float, default=5_000_000)
    parser.add_argument("--fast-max", action="store_true")
    parser.add_argument("--refresh-universe", action="store_true")
    parser.add_argument("--purge-skipped", action="store_true")
    parser.add_argument("--confirm-large-sweep", action="store_true")
    parser.add_argument("--dry-run-only", action="store_true")
    args = parser.parse_args()

    universe = Path("data/processed/universe_selected.parquet")
    if args.refresh_universe or not universe.exists():
        counts = build_universe(args.min_turnover, args.max_symbols)
        selected_count = counts.get("selected_count", 0)
    else:
        selected_count = pl.read_parquet(universe).height
    print(f"step=build_universe status=ok selected_count={selected_count}")

    if args.purge_skipped:
        purge_skipped_constraints()

    validate_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "validate_universe_fgrid_constraints.py"),
        "--mode",
        "min-investment-sweep",
        "--max-symbols",
        str(args.max_symbols),
        "--dry-run-plan",
    ]
    if args.fast_max:
        validate_cmd.append("--fast-max")
    plan_out = _run(validate_cmd)
    planned = _parse_int(plan_out, "planned_requests")
    estimated = _parse_int(plan_out, "estimated_seconds_at_9.5rps") or int(planned / 9.5)
    print(f"step=dry_run_plan planned_requests={planned} estimated_seconds={estimated}")
    if args.dry_run_only:
        return
    if planned > 5000 and not args.confirm_large_sweep:
        raise SystemExit("planned requests > 5000; pass --confirm-large-sweep")
    if not load_settings().grid_validate_enabled:
        raise SystemExit(
            "GRID_VALIDATE_ENABLED=false. Set it true for real sweep. Dry-run only is available with --dry-run-only."
        )

    real_cmd = [x for x in validate_cmd if x != "--dry-run-plan"]
    if args.confirm_large_sweep:
        real_cmd.append("--confirm-large-sweep")
    sweep_out = _run(real_cmd)
    print(
        "step=validate_sweep "
        f"api_calls_attempted={_parse_int(sweep_out, 'api_calls_attempted')} "
        f"api_calls_succeeded={_parse_int(sweep_out, 'api_calls_succeeded')} "
        f"api_calls_failed={_parse_int(sweep_out, 'api_calls_failed')} "
        f"effective_api_rps={_parse_float(sweep_out, 'effective_api_rps'):.2f}"
    )

    _run([sys.executable, str(ROOT / "scripts" / "analyze_fgrid_min_investment.py")])
    df = pl.read_parquet("data/processed/fgrid_validate_constraints.parquet")
    _, aggregate = summarize_min_investment(df)
    parts = [
        f"step=analyze symbols_tested={aggregate.get('symbols_tested', 0)}",
        f"configs_tested={aggregate.get('configs_tested', 0)}",
    ]
    for threshold in (5, 10, 25, 50, 100, 250, 500):
        parts.append(f"symbols_feasible_at_{threshold}={aggregate.get(f'symbols_feasible_at_{threshold}', 0)}")
    print(" ".join(parts))
    print("final_report=reports/sprint_02_native_grid_feasibility_report.md")


if __name__ == "__main__":
    os.environ.setdefault("LIVE_TRADING_ENABLED", "false")
    os.environ.setdefault("ALLOW_LIVE_TRADING", "NO")
    main()
