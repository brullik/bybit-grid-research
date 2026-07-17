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
from bybit_grid.research.range_detector import DetectionConfig
from bybit_grid.research.range_core import FUNNEL_KEYS, arrays_from_frame, detect_ranges_core_with_funnel
from bybit_grid.research.range_event_coalescer import CoalesceConfig, coalesce_range_events
from bybit_grid.research.range_actionable_events import ActionableEventConfig, build_actionable_events
from bybit_grid.research.range_features import DEFAULT_LOOKBACKS
from bybit_grid.research.range_profiles import RANGE_PROFILES, resolve_profiles

RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"

REJECTION_KEYS = FUNNEL_KEYS


def default_workers() -> int:
    return min(32, os.cpu_count() or 8)


def _detection_config_from_args(args_dict: dict) -> DetectionConfig:
    return DetectionConfig(
        lookbacks=tuple(int(value) for value in args_dict["lookbacks"].split(",")),
        max_zero_volume_window_pct=args_dict["max_zero_volume_window_pct"],
    )


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
    cfg = _detection_config_from_args(args_dict)
    end_ms = int(row.get("end_ms") or 0) or None
    start_ms = int(row.get("start_ms") or 0) or None
    if args_dict.get("days_limit") and end_ms:
        start_ms = max(start_ms or 0, end_ms - int(args_dict["days_limit"]) * 86_400_000 + 60_000)
    raw_base = Path(args_dict["raw_output_dir"])
    event_base = Path(args_dict["event_output_dir"])
    regime_base = Path(args_dict["regime_output_dir"])
    actionable_base = Path(args_dict["actionable_output_dir"])
    layers = set(str(args_dict["output_layer"]).replace(",", " ").split())
    if "both" in layers:
        layers = {"raw", "event"}
    if args_dict.get("skip_existing_ok") and all(
        _existing(base, symbol) for base in [raw_base if "raw" in layers else event_base, event_base if "event" in layers else raw_base]
    ):
        return {
            "symbol": symbol,
            "skipped_existing_ok": True,
            "candles_scanned": 0,
            "raw_candidate_rows": 0,
            "event_candidate_rows": 0,
            "max_zero_volume_window_pct": cfg.max_zero_volume_window_pct,
        }
    df = _read_symbol(args_dict["data_dir"], symbol, start_ms, end_ms)
    arrays = arrays_from_frame(df) if not df.is_empty() else None
    core_start = time.monotonic()
    raw_parts = []
    counters = {k: 0 for k in REJECTION_KEYS}
    if arrays is not None:
        for prof in resolve_profiles(args_dict["profile"]):
            part, funnel = detect_ranges_core_with_funnel(
                arrays,
                symbol,
                prof,
                cfg.lookbacks,
                core=args_dict.get("core", "numpy_fast"),
                config=cfg,
            )
            raw_parts.append(part)
            for k in REJECTION_KEYS:
                counters[k] += int(funnel.get(k, 0))
    core_detect_seconds = time.monotonic() - core_start
    raw = pl.concat([x for x in raw_parts if not x.is_empty()], how="diagonal_relaxed") if any(not x.is_empty() for x in raw_parts) else pl.DataFrame()
    coalesce_start = time.monotonic()
    events = coalesce_range_events(raw, CoalesceConfig(cooldown_mode=args_dict["cooldown_mode"], cooldown_minutes=args_dict.get("cooldown_minutes"), range_cluster_bps=float(args_dict["range_cluster_bps"]))) if not raw.is_empty() and "event" in layers else pl.DataFrame()
    regimes, actionable = build_actionable_events(raw, event_cfg=ActionableEventConfig(allow_reentry_events=bool(args_dict.get("allow_reentry_events")), max_events_per_regime=int(args_dict.get("max_events_per_regime") or 1))) if not raw.is_empty() and ("actionable" in layers or "range_regimes" in layers) else (pl.DataFrame(), pl.DataFrame())
    coalesce_seconds = time.monotonic() - coalesce_start
    write_start = time.monotonic()
    if "raw" in layers and not raw.is_empty():
        write_partitioned_candidates(raw, raw_base)
    if "event" in layers and not events.is_empty():
        write_partitioned_candidates(events, event_base)
    if "range_regimes" in layers and not regimes.is_empty():
        write_partitioned_candidates(regimes.rename({"first_seen_time_ms": "signal_time_ms"}), regime_base)
    if "actionable" in layers and not actionable.is_empty():
        write_partitioned_candidates(actionable, actionable_base)
    write_seconds = time.monotonic() - write_start
    return {
        "symbol": symbol,
        "skipped_existing_ok": False,
        "candles_scanned": df.height,
        "raw_candidate_rows": raw.height,
        "event_candidate_rows": events.height,
        "range_regime_rows": regimes.height,
        "actionable_event_rows": actionable.height,
        "core_detect_seconds": core_detect_seconds,
        "coalesce_seconds": coalesce_seconds,
        "write_seconds": write_seconds,
        "max_zero_volume_window_pct": cfg.max_zero_volume_window_pct,
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
    p.add_argument("--run-id", default="auto")
    p.add_argument("--output-dir", default="")
    p.add_argument("--raw-output-dir", default="")
    p.add_argument("--event-output-dir", default="")
    p.add_argument("--regime-output-dir", default="")
    p.add_argument("--actionable-output-dir", default="")
    p.add_argument("--workers", type=int, default=default_workers())
    p.add_argument("--symbols-limit", type=int)
    p.add_argument("--days-limit", type=int)
    p.add_argument("--dry-run-plan", action="store_true")
    p.add_argument("--fast-max", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--skip-existing-ok", action="store_true")
    p.add_argument("--confirm-large-run", action="store_true")
    p.add_argument("--profile", choices=[*RANGE_PROFILES.keys(), "all"], default="actionable_research")
    p.add_argument("--core", choices=["python_reference", "numpy_fast", "numba_optional"], default="numpy_fast")
    p.add_argument("--output-layer", default="actionable")
    p.add_argument("--coalesce-events", action="store_true", default=True)
    p.add_argument("--cooldown-mode", choices=["lookback_fraction", "fixed", "none"], default="lookback_fraction")
    p.add_argument("--cooldown-minutes", type=int)
    p.add_argument("--range-cluster-bps", type=float, default=25.0)
    p.add_argument("--allow-reentry-events", action="store_true")
    p.add_argument("--min-minutes-outside-midzone-before-reentry", type=int, default=30)
    p.add_argument("--max-events-per-regime", type=int, default=1)
    p.add_argument("--max-event-candidates-per-symbol-day", type=int, default=300)
    p.add_argument("--materialize-rejection-counters", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-density-smoke-pass")
    p.add_argument("--override-density-fail", action="store_true")
    p.add_argument("--lookbacks", default=",".join(str(x) for x in DEFAULT_LOOKBACKS))
    p.add_argument("--max-zero-volume-window-pct", type=float, default=0.05)
    p.add_argument("--debug-write-all-features", action="store_true")
    args = p.parse_args()
    requested_config = _detection_config_from_args(vars(args))
    if args.run_id == "auto":
        args.run_id = time.strftime("range_%Y%m%d_%H%M%S")
    run_root = Path("data/processed/range_runs") / args.run_id
    args.raw_output_dir = args.raw_output_dir or str(run_root / "raw_candidates")
    args.event_output_dir = args.event_output_dir or str(run_root / "event_candidates")
    args.regime_output_dir = args.regime_output_dir or str(run_root / "range_regimes")
    args.actionable_output_dir = args.actionable_output_dir or str(run_root / "actionable_events")
    start = time.monotonic()
    manifest = load_manifest(Path(args.manifest))
    if "symbol" not in manifest.columns:
        raise SystemExit("manifest missing symbol column")
    work = manifest.sort("symbol")
    if args.symbols_limit:
        work = work.head(args.symbols_limit)
    est_rows, est_source = estimate_rows(work, args.days_limit)
    profiles = ",".join(p.name for p in resolve_profiles(args.profile))
    plan = {"run_id": args.run_id, "symbols": work.height, "workers": args.workers, "estimated_kline_rows": est_rows, "estimated_source": est_source, "profiles": profiles, "lookbacks": args.lookbacks, "max_zero_volume_window_pct": requested_config.max_zero_volume_window_pct, "output_layer": args.output_layer, "core_name": args.core}
    print("dry_run_plan " + " ".join(f"{k}={v}" for k, v in plan.items()))
    if args.dry_run_plan:
        return
    if not args.confirm_large_run and est_rows > 5_000_000:
        raise SystemExit("large run guard: pass --confirm-large-run")
    if args.require_density_smoke_pass and not args.override_density_fail:
        cal = Path("data/processed/range_runs") / args.require_density_smoke_pass / "summary" / "actionable_density_calibration.parquet"
        if not cal.exists():
            raise SystemExit(f"density smoke guard: calibration summary not found: {cal}")
        cal_df = pl.read_parquet(cal)
        if cal_df.is_empty() or not (cal_df["acceptance_density_status"] == "pass").any():
            raise SystemExit("density smoke guard: no passing calibration profile; use --override-density-fail with PM approval")
    results = []
    rows = work.to_dicts()
    args_dict = vars(args)
    for base in [Path(args.raw_output_dir), Path(args.event_output_dir), Path(args.regime_output_dir), Path(args.actionable_output_dir), run_root / "summary"]:
        base.mkdir(parents=True, exist_ok=True)
    if args.workers <= 1:
        for done, row in enumerate(rows, start=1):
            res = _worker(row, args_dict)
            results.append(res)
            eta = ((time.monotonic() - start) / done) * (len(rows) - done) if done else 0
            print(
                f"progress {done}/{len(rows)} symbol={res['symbol']} raw={res['raw_candidate_rows']} "
                f"event={res['event_candidate_rows']} actionable={res.get('actionable_event_rows',0)} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
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
                    f"event={res['event_candidate_rows']} actionable={res.get('actionable_event_rows',0)} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
                )
    runtime = time.monotonic() - start
    summary = pl.DataFrame(results)
    (run_root / "summary").mkdir(parents=True, exist_ok=True)
    summary.write_parquet(run_root / "summary" / "range_candidate_summary.parquet")
    summary.write_parquet(run_root / "summary" / "range_rejection_summary.parquet")
    latest = Path("data/processed/range_runs/latest_run.txt")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(args.run_id, encoding="utf-8")
    perf = {
        "symbols_processed": len(rows),
        "candles_scanned": int(summary["candles_scanned"].sum()) if summary.height else 0,
        "raw_candidate_rows_written": int(summary["raw_candidate_rows"].sum()) if summary.height else 0,
        "event_candidate_rows_written": int(summary["event_candidate_rows"].sum()) if summary.height else 0,
        "range_regime_rows_written": int(summary["range_regime_rows"].sum()) if summary.height and "range_regime_rows" in summary.columns else 0,
        "actionable_event_rows_written": int(summary["actionable_event_rows"].sum()) if summary.height and "actionable_event_rows" in summary.columns else 0,
        "runtime_seconds": runtime,
        "workers_used": args.workers,
        "core_name": args.core,
        "core_detect_seconds": float(summary["core_detect_seconds"].sum()) if summary.height and "core_detect_seconds" in summary.columns else 0.0,
        "coalesce_seconds": float(summary["coalesce_seconds"].sum()) if summary.height and "coalesce_seconds" in summary.columns else 0.0,
        "write_seconds": float(summary["write_seconds"].sum()) if summary.height and "write_seconds" in summary.columns else 0.0,
        **{k: int(summary[k].sum()) if summary.height and k in summary.columns else 0 for k in REJECTION_KEYS},
    }
    perf["candidate_rows_written"] = perf["raw_candidate_rows_written"]
    perf["rows_per_sec_by_core"] = perf["candles_scanned"] / perf["core_detect_seconds"] if perf["core_detect_seconds"] else 0
    perf["raw_candidates_per_sec"] = perf["raw_candidate_rows_written"] / runtime if runtime else 0
    perf["actionable_events_per_sec"] = perf["actionable_event_rows_written"] / runtime if runtime else 0
    candles = perf["candles_scanned"]
    perf["candidates_per_10k_candles"] = perf["raw_candidate_rows_written"] / candles * 10_000 if candles else 0
    Path("reports").mkdir(exist_ok=True)
    (run_root / "summary" / "range_candidate_perf.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    Path(f"reports/sprint_03_2_range_actionable_report_{args.run_id}.md").write_text("# Sprint 03.2 Range Actionable Report\n\n" + "\n".join(f"- {k}: {v}" for k, v in perf.items()) + "\n", encoding="utf-8")
    print("completed " + " ".join(f"{k}={v}" for k, v in perf.items()))


if __name__ == "__main__":
    main()
