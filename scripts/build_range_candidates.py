from __future__ import annotations

import argparse
import glob
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.research.range_candidate_store import write_partitioned_candidates
from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_event_coalescer import CoalesceConfig, coalesce_range_events
from bybit_grid.research.range_features import DEFAULT_LOOKBACKS
from bybit_grid.research.range_profiles import resolve_profiles

REJECTION_KEYS = (
    "missing_window_rejection_count",
    "bad_ohlc_window_rejection_count",
    "zero_volume_window_rejection_count",
    "insufficient_history_rejection_count",
    "range_height_rejection_count",
    "middle_zone_rejection_count",
    "lower_upper_entry_rejection_count",
    "slope_rejection_count",
    "boring_range_rejection_count",
)


def default_workers() -> int:
    return min(32, os.cpu_count() or 8)


def _read_symbol(data_dir: str, symbol: str, start_ms: int | None, end_ms: int | None) -> pl.DataFrame:
    files = glob.glob(
        str(Path(data_dir) / "raw" / "klines" / f"symbol={symbol}" / "year=*" / "month=*" / "part.parquet")
    )
    if not files:
        return pl.DataFrame()
    lf = pl.scan_parquet(files)
    if start_ms is not None:
        lf = lf.filter(pl.col("open_time_ms") >= start_ms)
    if end_ms is not None:
        lf = lf.filter(pl.col("open_time_ms") <= end_ms)
    return lf.collect()


def _existing(base: Path, symbol: str) -> bool:
    return bool(list((base / f"symbol={symbol}").glob("year=*/month=*/candidates.parquet")))


def _worker(row: dict, args_dict: dict) -> dict:
    symbol = row["symbol"]
    end_ms = int(row.get("end_ms") or 0) or None
    start_ms = int(row.get("start_ms") or 0) or None
    if args_dict.get("days_limit") and end_ms:
        start_ms = max(start_ms or 0, end_ms - int(args_dict["days_limit"]) * 86_400_000 + 60_000)
    raw_base = Path(args_dict["raw_output_dir"])
    event_base = Path(args_dict["event_output_dir"])
    layers = set(str(args_dict["output_layer"]).replace(",", " ").split())
    if "both" in layers:
        layers = {"raw", "event"}
    if args_dict.get("skip_existing_ok") and all(
        _existing(base, symbol) for base in [raw_base if "raw" in layers else event_base, event_base if "event" in layers else raw_base]
    ):
        return {"symbol": symbol, "skipped_existing_ok": True, "candles_scanned": 0, "raw_candidate_rows": 0, "event_candidate_rows": 0}
    df = _read_symbol(args_dict["data_dir"], symbol, start_ms, end_ms)
    cfg = DetectionConfig(lookbacks=tuple(int(x) for x in args_dict["lookbacks"].split(",")))
    raw_parts = [detect_range_candidates(df, symbol, cfg, prof) for prof in resolve_profiles(args_dict["profile"])]
    raw = pl.concat([x for x in raw_parts if not x.is_empty()], how="diagonal_relaxed") if any(not x.is_empty() for x in raw_parts) else pl.DataFrame()
    events = coalesce_range_events(raw, CoalesceConfig(cooldown_mode=args_dict["cooldown_mode"], cooldown_minutes=args_dict.get("cooldown_minutes"), range_cluster_bps=float(args_dict["range_cluster_bps"]))) if not raw.is_empty() else pl.DataFrame()
    if "raw" in layers and not raw.is_empty():
        write_partitioned_candidates(raw, raw_base)
    if "event" in layers and not events.is_empty():
        write_partitioned_candidates(events, event_base)
    counters = {k: 0 for k in REJECTION_KEYS}
    counters["insufficient_history_rejection_count"] = sum(max(0, int(lb) - df.height) for lb in cfg.lookbacks)
    return {
        "symbol": symbol,
        "skipped_existing_ok": False,
        "candles_scanned": df.height,
        "raw_candidate_rows": raw.height,
        "event_candidate_rows": events.height,
        **counters,
    }


def load_manifest(path: Path) -> pl.DataFrame:
    return pl.read_parquet(path) if path.exists() else pl.DataFrame({"symbol": []})


def estimate_rows(work: pl.DataFrame, days_limit: int | None) -> tuple[int, str]:
    if days_limit and "symbol" in work.columns:
        return int(work.height * days_limit * 1440), "manifest/time_bounds"
    if "estimated_kline_rows" in work.columns:
        return int(work["estimated_kline_rows"].sum()), "manifest/estimated_kline_rows"
    return 0, "unknown"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="data/processed/research_download_manifest.parquet")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--output-dir", default="data/processed/range_raw_candidates")
    p.add_argument("--raw-output-dir", default="data/processed/range_raw_candidates")
    p.add_argument("--event-output-dir", default="data/processed/range_event_candidates")
    p.add_argument("--workers", type=int, default=default_workers())
    p.add_argument("--symbols-limit", type=int)
    p.add_argument("--days-limit", type=int)
    p.add_argument("--dry-run-plan", action="store_true")
    p.add_argument("--fast-max", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--skip-existing-ok", action="store_true")
    p.add_argument("--confirm-large-run", action="store_true")
    p.add_argument("--profile", choices=["broad_diagnostic", "balanced_research", "strict_research", "all"], default="balanced_research")
    p.add_argument("--output-layer", default="both")
    p.add_argument("--coalesce-events", action="store_true", default=True)
    p.add_argument("--cooldown-mode", choices=["lookback_fraction", "fixed", "none"], default="lookback_fraction")
    p.add_argument("--cooldown-minutes", type=int)
    p.add_argument("--range-cluster-bps", type=float, default=5.0)
    p.add_argument("--max-event-candidates-per-symbol-day", type=int, default=300)
    p.add_argument("--materialize-rejection-counters", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--lookbacks", default=",".join(str(x) for x in DEFAULT_LOOKBACKS))
    p.add_argument("--max-zero-volume-window-pct", type=float, default=0.05)
    p.add_argument("--debug-write-all-features", action="store_true")
    args = p.parse_args()
    args.raw_output_dir = args.output_dir if args.output_dir != "data/processed/range_raw_candidates" else args.raw_output_dir
    start = time.monotonic()
    manifest = load_manifest(Path(args.manifest))
    if "symbol" not in manifest.columns:
        raise SystemExit("manifest missing symbol column")
    work = manifest.sort("symbol")
    if args.symbols_limit:
        work = work.head(args.symbols_limit)
    est_rows, est_source = estimate_rows(work, args.days_limit)
    profiles = ",".join(p.name for p in resolve_profiles(args.profile))
    plan = {"symbols": work.height, "workers": args.workers, "estimated_kline_rows": est_rows, "estimated_source": est_source, "profiles": profiles, "lookbacks": args.lookbacks, "output_layer": args.output_layer}
    print("dry_run_plan " + " ".join(f"{k}={v}" for k, v in plan.items()))
    if args.dry_run_plan:
        return
    if not args.confirm_large_run and est_rows > 5_000_000:
        raise SystemExit("large run guard: pass --confirm-large-run")
    results = []
    rows = work.to_dicts()
    args_dict = vars(args)
    for base in [Path(args.raw_output_dir), Path(args.event_output_dir)]:
        base.mkdir(parents=True, exist_ok=True)
    if args.workers <= 1:
        for done, row in enumerate(rows, start=1):
            res = _worker(row, args_dict)
            results.append(res)
            eta = ((time.monotonic() - start) / done) * (len(rows) - done) if done else 0
            print(
                f"progress {done}/{len(rows)} symbol={res['symbol']} raw={res['raw_candidate_rows']} "
                f"event={res['event_candidate_rows']} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
            )
    else:
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(_worker, r, args_dict) for r in rows]
            for done, fut in enumerate(as_completed(futs), start=1):
                res = fut.result()
                results.append(res)
                eta = ((time.monotonic() - start) / done) * (len(rows) - done) if done else 0
                print(
                    f"progress {done}/{len(rows)} symbol={res['symbol']} raw={res['raw_candidate_rows']} "
                    f"event={res['event_candidate_rows']} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
                )
    runtime = time.monotonic() - start
    summary = pl.DataFrame(results)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    summary.write_parquet("data/processed/range_candidate_summary.parquet")
    perf = {
        "symbols_processed": len(rows),
        "candles_scanned": int(summary["candles_scanned"].sum()) if summary.height else 0,
        "raw_candidate_rows_written": int(summary["raw_candidate_rows"].sum()) if summary.height else 0,
        "event_candidate_rows_written": int(summary["event_candidate_rows"].sum()) if summary.height else 0,
        "runtime_seconds": runtime,
        "workers_used": args.workers,
        **{k: int(summary[k].sum()) if summary.height and k in summary.columns else 0 for k in REJECTION_KEYS},
    }
    perf["candidate_rows_written"] = perf["raw_candidate_rows_written"]
    candles = perf["candles_scanned"]
    perf["candidates_per_10k_candles"] = perf["raw_candidate_rows_written"] / candles * 10_000 if candles else 0
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_03_1_range_candidate_perf.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    Path("reports/sprint_03_range_candidate_perf.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    print("completed " + " ".join(f"{k}={v}" for k, v in perf.items()))


if __name__ == "__main__":
    main()
