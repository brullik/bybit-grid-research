from __future__ import annotations

import argparse
import glob
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from threading import Lock
from typing import Any

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.rate_limit import TokenBucketRateLimiter
from bybit_grid.config import load_settings
from bybit_grid.data.funding import download_funding_history
from bybit_grid.data.klines import download_kline_range
from bybit_grid.data.mark_klines import download_mark_kline_range
from bybit_grid.data.quality import detect_1m_gaps, detect_bad_ohlc, detect_duplicate_candles

VALIDATED = "validated_5usdt_feasible"
SOURCES = ("klines", "mark_klines", "funding")


def _source_glob(data_dir: Path, source: str, symbol: str) -> str:
    if source == "funding":
        return str(data_dir / "raw" / "funding" / f"symbol={symbol}" / "year=*" / "part.parquet")
    return str(data_dir / "raw" / source / f"symbol={symbol}" / "year=*" / "month=*" / "part.parquet")


def existing_ok(data_dir: Path, source: str, symbol: str, start_ms: int, end_ms: int) -> bool:
    files = [Path(p) for p in glob.glob(_source_glob(data_dir, source, symbol))]
    if not files:
        return False
    df = pl.concat([pl.read_parquet(p) for p in files], how="diagonal_relaxed")
    if df.is_empty():
        return False
    ts_col = "funding_rate_timestamp_ms" if source == "funding" else "open_time_ms"
    df = df.filter((pl.col(ts_col) >= start_ms) & (pl.col(ts_col) <= end_ms))
    if df.is_empty():
        return False
    if source == "funding":
        expected = max(1, (end_ms - start_ms) // (8 * 60 * 60_000))
        return df.height >= expected and df.unique(["symbol", ts_col]).height == df.height
    expected = max(1, (end_ms - start_ms) // 60_000 + 1)
    return (
        df.height >= expected
        and detect_1m_gaps(df).height == 0
        and detect_duplicate_candles(df).height == 0
        and detect_bad_ohlc(df).height == 0
    )


def _download_symbol(row: dict[str, Any], limiter: TokenBucketRateLimiter, skip_existing_ok: bool) -> dict[str, Any]:
    settings = load_settings()
    symbol = row["symbol"]
    start_ms = int(row["start_ms"])
    end_ms = int(row["end_ms"])
    stats = {"symbol": symbol, "downloaded": 0, "skipped_existing_ok": 0, "failed": 0, "rows_written": 0}
    with BybitClient(settings, rate_limiter=limiter) as client:
        for source, downloader in (
            ("klines", download_kline_range),
            ("mark_klines", download_mark_kline_range),
            ("funding", download_funding_history),
        ):
            try:
                if skip_existing_ok and existing_ok(settings.data_dir, source, symbol, start_ms, end_ms):
                    stats["skipped_existing_ok"] += 1
                    continue
                df = downloader(client, symbol, start_ms, end_ms)
                stats["downloaded"] += 1
                stats["rows_written"] += df.height if hasattr(df, "height") else 0
            except Exception as exc:  # continue per symbol/source
                stats["failed"] += 1
                stats.setdefault("errors", []).append(f"{source}: {exc}")
    return stats


def _write_perf_report(metrics: dict[str, Any]) -> None:
    Path("reports").mkdir(exist_ok=True)
    Path("reports/sprint_02_download_performance_report.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = ["# Sprint 02 Download Performance Report", ""]
    for key, value in metrics.items():
        if key != "symbol_results":
            lines.append(f"- {key}: {value}")
    Path("reports/sprint_02_download_performance_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/processed/download_manifest.parquet")
    parser.add_argument("--sleep-sec", type=float, default=0.0, help="deprecated; use --max-requests-per-second")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-blocked", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-requests-per-second", type=float, default=8.0)
    parser.add_argument("--skip-existing-ok", action="store_true")
    parser.add_argument("--symbols-limit", type=int)
    parser.add_argument("--days-override", type=int)
    args = parser.parse_args()

    start = time.monotonic()
    manifest = pl.read_parquet(args.manifest)
    total = manifest.height
    if args.days_override and not manifest.is_empty():
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - args.days_override * 24 * 60 * 60 * 1000
        manifest = manifest.with_columns(pl.lit(start_ms).alias("start_ms"), pl.lit(end_ms).alias("end_ms"))
    blocked = manifest.filter(pl.col("trading_feasibility_status") != VALIDATED) if "trading_feasibility_status" in manifest.columns else pl.DataFrame()
    downloadable = manifest if args.include_blocked else manifest.filter(pl.col("trading_feasibility_status") == VALIDATED)
    if args.symbols_limit:
        downloadable = downloadable.head(args.symbols_limit)
    metrics: dict[str, Any] = {
        "manifest_rows_total": total,
        "downloadable_rows": downloadable.height,
        "skipped_blocked_by_min_investment": blocked.height if not args.include_blocked else 0,
        "download_blocked_by_policy": False,
        "include_blocked": args.include_blocked,
    }
    print(downloadable)
    if downloadable.is_empty() and not args.include_blocked:
        metrics["download_blocked_by_policy"] = True
        metrics["blocker"] = "download blocked by policy: no validated_5usdt_feasible symbols"
        metrics["total_seconds"] = round(time.monotonic() - start, 3)
        _write_perf_report(metrics)
        print(metrics["blocker"])
        return
    if args.dry_run:
        metrics["total_seconds"] = round(time.monotonic() - start, 3)
        _write_perf_report(metrics)
        return

    limiter = TokenBucketRateLimiter(args.max_requests_per_second)
    results = []
    lock = Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_download_symbol, row, limiter, args.skip_existing_ok) for row in downloadable.to_dicts()]
        for fut in as_completed(futures):
            res = fut.result()
            with lock:
                results.append(res)
            print(res)
    elapsed = time.monotonic() - start
    metrics.update({
        "total_seconds": round(elapsed, 3),
        "api_requests_count": limiter.wait_count,
        "rows_written": sum(r.get("rows_written", 0) for r in results),
        "seconds_per_symbol": round(elapsed / max(1, downloadable.height), 3),
        "requests_per_second_effective": round(limiter.wait_count / elapsed, 3) if elapsed else 0,
        "skipped_existing_ok": sum(r.get("skipped_existing_ok", 0) for r in results),
        "downloaded": sum(r.get("downloaded", 0) for r in results),
        "failures": sum(r.get("failed", 0) for r in results),
        "symbol_results": results,
    })
    _write_perf_report(metrics)


if __name__ == "__main__":
    main()
