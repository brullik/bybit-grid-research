from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_core.models import (
    DEFAULT_GRID_COUNTS,
    DEFAULT_HORIZONS_MINUTES,
    DEFAULT_SL_ATR_BUFFERS,
    OutcomePlan,
)
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes
from bybit_grid.research.outcome_store import write_partitioned_outcomes
from bybit_grid.research.outcome_summary import write_summary


def parse_ints(value: str) -> list[int]:
    return [int(x) for x in str(value).split(",") if x != ""]


def parse_floats(value: str) -> list[float]:
    return [float(x) for x in str(value).split(",") if x != ""]


def scan_events(range_run_id: str) -> pl.DataFrame:
    root = Path("data/processed/range_runs") / range_run_id / "actionable_events"
    files = list(root.glob("**/*.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.scan_parquet([str(p) for p in files]).collect()


def read_symbol_frame(base: Path, symbol: str) -> pl.DataFrame:
    files = list(base.glob(f"**/{symbol}*.parquet")) + list(
        base.glob(f"**/symbol={symbol}/**/*.parquet")
    )
    if not files:
        return pl.DataFrame()
    return pl.scan_parquet([str(p) for p in files]).collect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range-run-id", default="action_density_v2_123x90")
    ap.add_argument("--outcome-run-id", default="outcomes_action_density_v2_123x90_v1")
    ap.add_argument("--future-horizons-minutes", default=",".join(map(str, DEFAULT_HORIZONS_MINUTES)))
    ap.add_argument("--grid-counts", default=",".join(map(str, DEFAULT_GRID_COUNTS)))
    ap.add_argument("--sl-atr-buffers", default=",".join(map(str, DEFAULT_SL_ATR_BUFFERS)))
    ap.add_argument("--symbols-limit", type=int)
    ap.add_argument("--days-limit", type=int)
    ap.add_argument("--fast-max", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run-plan", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-existing-ok", action="store_true")
    ap.add_argument("--confirm-large-run", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    events = scan_events(args.range_run_id)
    if args.symbols_limit and not events.is_empty():
        syms = events["symbol"].unique().sort().head(args.symbols_limit).to_list()
        events = events.filter(pl.col("symbol").is_in(syms))
    if args.days_limit and not events.is_empty():
        mn = int(events["signal_time_ms"].min())
        events = events.filter(pl.col("signal_time_ms") < mn + args.days_limit * 86_400_000)
    horizons = parse_ints(args.future_horizons_minutes)
    grids = parse_ints(args.grid_counts)
    sls = parse_floats(args.sl_atr_buffers)
    plan = OutcomePlan(args.range_run_id, args.outcome_run_id, events.height, horizons, grids, sls)
    print(json.dumps(plan.__dict__ | {"planned_rows": plan.planned_rows, "workers": args.workers}, indent=2))
    if args.dry_run_plan:
        return
    if plan.planned_rows > 200_000 and not args.confirm_large_run:
        raise SystemExit("planned runtime/rows may be large; rerun with --confirm-large-run")
    if events.is_empty():
        raise SystemExit("no actionable events found")
    outroot = Path("data/processed/outcome_runs") / args.outcome_run_id
    rows = []
    symbols = events["symbol"].unique().to_list()
    done = 0

    def work(sym: str) -> list[dict]:
        evs = events.filter(pl.col("symbol") == sym).to_dicts()
        klines = read_symbol_frame(Path("data/raw/klines"), sym)
        marks = read_symbol_frame(Path("data/raw/mark_klines"), sym)
        funding = read_symbol_frame(Path("data/raw/funding"), sym)
        result = []
        for ev in evs:
            result.extend(compute_event_outcomes(ev, klines, marks, funding, horizons, grids, sls))
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, symbol): symbol for symbol in symbols}
        for fut in as_completed(futs):
            rows.extend(fut.result())
            done += 1
            elapsed = time.time() - t0
            eta = elapsed / done * (len(symbols) - done) if done else 0
            print(f"progress symbols={done}/{len(symbols)} rows={len(rows)} eta_sec={eta:.1f}")
    write_partitioned_outcomes(pl.DataFrame(rows), outroot / "outcomes", args.skip_existing_ok)
    perf = write_summary(outroot)
    Path("data/processed/outcome_runs").mkdir(parents=True, exist_ok=True)
    Path("data/processed/outcome_runs/latest_outcome_run.txt").write_text(args.outcome_run_id + "\n")
    print(json.dumps(perf, indent=2, default=str))


if __name__ == "__main__":
    main()
