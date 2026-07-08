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

from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_candidate_store import write_partitioned_candidates


def default_workers() -> int:
    return min(32, os.cpu_count() or 8)


def _read_symbol(
    data_dir: str, symbol: str, start_ms: int | None, end_ms: int | None
) -> pl.DataFrame:
    files = glob.glob(
        str(
            Path(data_dir)
            / "raw"
            / "klines"
            / f"symbol={symbol}"
            / "year=*"
            / "month=*"
            / "part.parquet"
        )
    )
    if not files:
        return pl.DataFrame()
    lf = pl.scan_parquet(files)
    if start_ms is not None:
        lf = lf.filter(pl.col("open_time_ms") >= start_ms)
    if end_ms is not None:
        lf = lf.filter(pl.col("open_time_ms") <= end_ms)
    return lf.collect()


def _worker(row: dict, args_dict: dict) -> dict:
    symbol = row["symbol"]
    end_ms = int(row.get("end_ms") or 0) or None
    start_ms = int(row.get("start_ms") or 0) or None
    if args_dict.get("days_limit") and end_ms:
        start_ms = max(
            start_ms or 0, end_ms - int(args_dict["days_limit"]) * 24 * 60 * 60_000 + 60_000
        )
    out_base = Path(args_dict["output_dir"])
    if args_dict.get("skip_existing_ok") and list(
        (out_base / f"symbol={symbol}").glob("year=*/month=*/candidates.parquet")
    ):
        return {
            "symbol": symbol,
            "skipped_existing_ok": True,
            "candles_scanned": 0,
            "candidate_rows": 0,
        }
    df = _read_symbol(args_dict["data_dir"], symbol, start_ms, end_ms)
    cfg = DetectionConfig(max_zero_volume_window_pct=float(args_dict["max_zero_volume_window_pct"]))
    cand = detect_range_candidates(df, symbol, cfg)
    paths = [] if cand.is_empty() else write_partitioned_candidates(cand, out_base)
    return {
        "symbol": symbol,
        "skipped_existing_ok": False,
        "candles_scanned": df.height,
        "candidate_rows": cand.height,
        "paths": [str(p) for p in paths],
    }


def load_manifest(path: Path) -> pl.DataFrame:
    return pl.read_parquet(path) if path.exists() else pl.DataFrame({"symbol": []})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="data/processed/research_download_manifest.parquet")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--output-dir", default="data/processed/range_candidates")
    p.add_argument("--workers", type=int, default=default_workers())
    p.add_argument("--symbols-limit", type=int)
    p.add_argument("--days-limit", type=int)
    p.add_argument("--dry-run-plan", action="store_true")
    p.add_argument("--fast-max", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--skip-existing-ok", action="store_true")
    p.add_argument("--confirm-large-run", action="store_true")
    p.add_argument("--max-zero-volume-window-pct", type=float, default=0.05)
    p.add_argument("--debug-write-all-features", action="store_true")
    args = p.parse_args()
    if args.fast_max and args.workers == default_workers():
        args.workers = default_workers()
    start = time.monotonic()
    manifest = load_manifest(Path(args.manifest))
    if "symbol" not in manifest.columns:
        raise SystemExit("manifest missing symbol column")
    work = manifest.sort("symbol")
    if args.symbols_limit:
        work = work.head(args.symbols_limit)
    est_rows = (
        int(work["estimated_kline_rows"].sum()) if "estimated_kline_rows" in work.columns else 0
    )
    plan = {
        "symbols": work.height,
        "workers": args.workers,
        "estimated_kline_rows": est_rows,
        "output_dir": args.output_dir,
        "resume": args.resume,
        "skip_existing_ok": args.skip_existing_ok,
        "max_zero_volume_window_pct": args.max_zero_volume_window_pct,
    }
    print("dry_run_plan " + " ".join(f"{k}={v}" for k, v in plan.items()))
    if args.dry_run_plan:
        return
    if not args.confirm_large_run and not args.symbols_limit and est_rows > 10_000_000:
        raise SystemExit("estimated runtime may exceed 10 minutes; pass --confirm-large-run")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    results = []
    done = 0
    total = work.height
    args_dict = vars(args)
    rows = work.to_dicts()
    if args.workers <= 1:
        for r in rows:
            res = _worker(r, args_dict)
            results.append(res)
            done += 1
            elapsed = time.monotonic() - start
            eta = (elapsed / done) * (total - done) if done else 0
            print(
                f"progress {done}/{total} symbol={res['symbol']} candidates={res['candidate_rows']} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
            )
    else:
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(_worker, r, args_dict) for r in rows]
            for fut in as_completed(futs):
                res = fut.result()
                results.append(res)
                done += 1
                elapsed = time.monotonic() - start
                eta = (elapsed / done) * (total - done) if done else 0
                print(
                    f"progress {done}/{total} symbol={res['symbol']} candidates={res['candidate_rows']} skipped_existing_ok={res.get('skipped_existing_ok')} eta_sec={eta:.1f}"
                )
    runtime = time.monotonic() - start
    cand_rows = sum(int(r["candidate_rows"]) for r in results)
    candles = sum(int(r["candles_scanned"]) for r in results)
    summary = pl.DataFrame(results)
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    summary.write_parquet("data/processed/range_candidate_summary.parquet")
    output_bytes = sum(
        output_file.stat().st_size
        for output_file in Path(args.output_dir).glob("symbol=*/year=*/month=*/candidates.parquet")
    )
    perf = {
        "symbols_processed": total,
        "candles_scanned": candles,
        "candidate_rows_written": cand_rows,
        "candidates_per_10k_candles": (cand_rows / candles * 10_000) if candles else 0,
        "runtime_seconds": runtime,
        "rows_per_sec": candles / runtime if runtime else 0,
        "workers_used": args.workers,
        "output_size_mb": output_bytes / 1_000_000,
        "missing_window_rejection_count": "not_materialized_fast_first",
        "bad_ohlc_window_rejection_count": "not_materialized_fast_first",
        "zero_volume_window_rejection_count": "not_materialized_fast_first",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_03_range_candidate_perf.json").write_text(
        json.dumps(perf, indent=2), encoding="utf-8"
    )
    print("completed " + " ".join(f"{k}={v}" for k, v in perf.items()))


if __name__ == "__main__":
    main()
