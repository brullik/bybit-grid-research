from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.research.range_actionable_events import build_actionable_events
from bybit_grid.research.range_core import arrays_from_frame, detect_ranges_core_with_funnel
from bybit_grid.research.range_profiles import RANGE_PROFILES


def sample(symbol: str, days: int):
    n = days * 1440
    idx = list(range(n))
    t = [i * 60_000 for i in idx]
    # Simple deterministic oscillation without requiring NumPy in minimal test environments.
    close = [100.0 + ((i % 24) - 12) * 0.04 + ((i % 288) - 144) * 0.0005 for i in idx]
    high = [x + 0.8 for x in close]
    low = [x - 0.8 for x in close]
    df = pl.DataFrame({"open_time_ms": t, "open": close, "high": high, "low": low, "close": close, "volume": [1.0] * n, "turnover": [1000.0] * n})
    return arrays_from_frame(df)


def run(args: argparse.Namespace) -> dict[str, object]:
    profile = RANGE_PROFILES[args.profile]
    timings: dict[str, float] = {}
    rows_in = args.symbols_limit * args.days_limit * 1440
    t0 = time.monotonic()
    symbols = [f"S{i:03d}USDT" for i in range(args.symbols_limit)]
    timings["load_parquet_seconds"] = time.monotonic() - t0

    try:
        import numpy  # noqa: F401

        lookbacks = (30, 60, 120)
        sample_days = args.days_limit
    except ModuleNotFoundError:
        lookbacks = (30,)
        sample_days = 1
        symbols = symbols[:1]

    raw_parts = []
    funnels = []
    t0 = time.monotonic()
    for sym in symbols:
        raw, funnel = detect_ranges_core_with_funnel(
            sample(sym, sample_days), sym, profile, lookbacks, core=args.core
        )
        raw_parts.append(raw)
        funnels.append(funnel)
    timings["detect_raw_candidates_seconds"] = time.monotonic() - t0
    raw = (
        pl.concat([x for x in raw_parts if not x.is_empty()], how="diagonal_relaxed")
        if any(not x.is_empty() for x in raw_parts)
        else pl.DataFrame()
    )

    t0 = time.monotonic()
    regimes, actionable = build_actionable_events(raw) if not raw.is_empty() else (pl.DataFrame(), pl.DataFrame())
    timings["coalesce_regimes_seconds"] = time.monotonic() - t0
    timings["build_actionable_events_seconds"] = timings["coalesce_regimes_seconds"]

    t0 = time.monotonic()
    Path("reports").mkdir(exist_ok=True)
    raw.head(10).write_parquet("reports/sprint_03_3_core_benchmark_sample.parquet")
    timings["write_outputs_seconds"] = time.monotonic() - t0
    current, peak = tracemalloc.get_traced_memory()
    del current
    stats = {
        "core_name": args.core,
        "symbols": len(symbols),
        "days": sample_days,
        "input_rows": rows_in,
        "raw_candidates": raw.height,
        "range_regimes": regimes.height,
        "actionable_events": actionable.height,
        "stage_seconds": timings,
        "rows_per_sec_by_stage": {
            k.replace("seconds", "rows_per_sec"): (rows_in / v if v else 0) for k, v in timings.items()
        },
        "peak_memory_bytes": peak,
        "funnel": {k: sum(int(f.get(k, 0)) for f in funnels) for k in (funnels[0].keys() if funnels else [])},
    }
    return stats


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols-limit", type=int, default=3)
    ap.add_argument("--days-limit", type=int, default=7)
    ap.add_argument("--core", choices=["python_reference","numpy_fast","numba_optional"], default="numpy_fast")
    ap.add_argument("--profile", default="actionable_fast_strict")
    args=ap.parse_args()
    tracemalloc.start()
    prof=cProfile.Profile()
    stats=prof.runcall(run,args)
    s=io.StringIO()
    pstats.Stats(prof, stream=s).sort_stats("cumtime").print_stats(25)
    stats["cprofile_top"] = s.getvalue().splitlines()[:35]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_03_3_profile_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    lines=["# Sprint 03.3 Range Core Profile", "", *[f"- {k}: {v}" for k,v in stats.items() if k not in {"cprofile_top", "stage_seconds", "rows_per_sec_by_stage", "funnel"}], "", "## Stage Timers", *[f"- {k}: {v:.6f}" for k,v in stats["stage_seconds"].items()], "", "## Rows/sec", *[f"- {k}: {v:.2f}" for k,v in stats["rows_per_sec_by_stage"].items()], "", "## cProfile Top", "```", *stats["cprofile_top"], "```"]
    Path("reports/sprint_03_3_profile_summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    Path("reports/sprint_03_3_core_benchmark.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("profile_complete " + " ".join(f"{k}={v}" for k,v in stats.items() if isinstance(v,(int,float,str))))

if __name__ == "__main__":
    main()
