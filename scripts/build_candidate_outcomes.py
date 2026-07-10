from __future__ import annotations

import argparse
import json
import sys
import time
import os
try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from bybit_grid.research.outcome_core.models import (
    DEFAULT_GRID_COUNTS,
    DEFAULT_HORIZONS_MINUTES,
    DEFAULT_SL_ATR_BUFFERS,
    OutcomePlan,
)
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes as compute_reference_outcomes
from bybit_grid.research.outcome_core.outcome_fast import compute_event_outcomes as compute_fast_outcomes
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
    files = list(base.glob(f"**/{symbol}*.parquet")) + list(base.glob(f"symbol={symbol}/**/*.parquet")) + list(
        base.glob(f"**/symbol={symbol}/**/*.parquet")
    )
    if not files:
        return pl.DataFrame()
    return pl.scan_parquet([str(p) for p in files]).collect()



def work_symbol(payload: tuple) -> list[dict]:
    sym, events_dicts, horizons, grids, sls, range_run_id, outcome_run_id, core = payload
    core_func = compute_fast_outcomes if core == "numpy_fast_v2" else compute_reference_outcomes
    klines = read_symbol_frame(Path("data/raw/klines"), sym)
    marks = read_symbol_frame(Path("data/raw/mark_klines"), sym)
    funding = read_symbol_frame(Path("data/raw/funding"), sym)
    result: list[dict] = []
    for ev in events_dicts:
        result.extend(core_func(ev, klines, marks, funding, horizons, grids, sls, range_run_id=range_run_id, outcome_run_id=outcome_run_id))
    return result

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
    ap.add_argument("--core", choices=["reference", "numpy_fast_v2"], default="numpy_fast_v2")
    ap.add_argument("--executor", choices=["auto", "thread", "process"], default="auto")
    ap.add_argument("--workers", default="auto")
    ap.add_argument("--profile-core", action="store_true")
    ap.add_argument("--dry-run-plan", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-existing-ok", action="store_true")
    ap.add_argument("--confirm-large-run", action="store_true")
    ap.add_argument("--funding-debug", action="store_true")
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
    symbols = events["symbol"].unique().to_list() if not events.is_empty() else []
    workers = min(len(symbols) or 1, max(1, (os.cpu_count() or 4) - 1), 16) if args.workers == "auto" else int(args.workers)
    executor_name = "thread" if args.executor == "auto" else args.executor
    print(json.dumps(plan.__dict__ | {"planned_rows": plan.planned_rows, "workers": workers, "core": args.core, "executor": executor_name}, indent=2))
    if args.dry_run_plan:
        return
    if plan.planned_rows > 200_000 and not args.confirm_large_run:
        raise SystemExit("planned runtime/rows may be large; rerun with --confirm-large-run")
    if events.is_empty():
        raise SystemExit("no actionable events found")
    outroot = Path("data/processed/outcome_runs") / args.outcome_run_id
    done = 0
    rows_written = 0
    events_done = 0
    symbol_payloads = {
        symbol: (symbol, events.filter(pl.col("symbol") == symbol).to_dicts(), horizons, grids, sls, args.range_run_id, args.outcome_run_id, args.core)
        for symbol in symbols
    }

    executor_cls = ThreadPoolExecutor if executor_name == "thread" else ProcessPoolExecutor
    write_seconds = 0.0
    with executor_cls(max_workers=workers) as ex:
        futs = {ex.submit(work_symbol, symbol_payloads[symbol]): symbol for symbol in symbols}
        for fut in as_completed(futs):
            sym_rows = fut.result()
            tw = time.time()
            write_partitioned_outcomes(pl.DataFrame(sym_rows), outroot / "outcomes", args.skip_existing_ok)
            write_seconds += time.time() - tw
            done += 1
            rows_written += len(sym_rows)
            events_done += events.filter(pl.col("symbol") == futs[fut]).height
            elapsed = time.time() - t0
            eps = events_done / elapsed if elapsed else 0.0
            rps = rows_written / elapsed if elapsed else 0.0
            eta = elapsed / done * (len(symbols) - done) if done else 0
            print(f"progress symbols_done={done} symbols_total={len(symbols)} events_done={events_done} rows_written={rows_written} events_per_sec={eps:.2f} rows_per_sec={rps:.2f} eta_sec={eta:.1f}")
    perf = write_summary(outroot)
    Path("data/processed/outcome_runs").mkdir(parents=True, exist_ok=True)
    Path("data/processed/outcome_runs/latest_outcome_run.txt").write_text(args.outcome_run_id + "\n")
    runtime = time.time() - t0
    perf.update({"core_name": args.core, "executor_name": executor_name, "workers_used": workers, "symbols_processed": len(symbols), "events_processed": events_done, "outcome_rows_total": rows_written, "total_runtime_seconds": runtime, "market_data_load_seconds": None, "array_prepare_seconds": None, "base_grain_seconds": None, "sl_grain_seconds": None, "grid_grain_seconds": None, "materialization_seconds": None, "write_seconds": write_seconds, "events_per_second": events_done / runtime if runtime else 0.0, "rows_per_second": rows_written / runtime if runtime else 0.0, "peak_memory_mb": (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 if resource is not None else None)})
    (outroot / "summary" / "outcome_perf.json").write_text(json.dumps(perf, indent=2, default=str) + "\n")
    print(json.dumps(perf, indent=2, default=str))


if __name__ == "__main__":
    main()
