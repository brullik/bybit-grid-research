from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
import sys
from threading import Lock
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.fgrid_constraints import (
    append_constraints,
    candidate_key,
    existing_keys,
    parse_validate_response,
    write_redacted_response,
)
from bybit_grid.bybit.fgrid_min_sweep import (
    build_min_sweep_candidates,
    progress_line,
    should_stop_symbol,
)
from bybit_grid.bybit.rate_limit import TokenBucketRateLimiter
from bybit_grid.config import load_settings


def _is_skipped_raw(path_value: Any) -> bool:
    if not path_value:
        return False
    path = Path(str(path_value))
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("skipped") is True


def purge_skipped_constraints(
    output: Path = Path("data/processed/fgrid_validate_constraints.parquet"),
) -> None:
    if not output.exists():
        print("removed_rows=0 remaining_rows=0 removed_raw_files=0")
        return
    df = pl.read_parquet(output)
    if df.is_empty():
        print("removed_rows=0 remaining_rows=0 removed_raw_files=0")
        return
    skipped_paths = set()
    if "raw_response_path_redacted" in df.columns:
        skipped_paths = {
            str(path)
            for path in df["raw_response_path_redacted"].drop_nulls().to_list()
            if _is_skipped_raw(path)
        }
    remove_expr = pl.lit(False)
    if "blocker_reason" in df.columns:
        remove_expr = remove_expr | (pl.col("blocker_reason") == "investment_min_missing")
    if skipped_paths and "raw_response_path_redacted" in df.columns:
        remove_expr = remove_expr | pl.col("raw_response_path_redacted").is_in(list(skipped_paths))
    null_cols = [c for c in ("investment_min", "retCode", "status_code") if c in df.columns]
    if len(null_cols) == 3:
        remove_expr = remove_expr | (
            pl.col("investment_min").is_null()
            & pl.col("retCode").is_null()
            & pl.col("status_code").is_null()
        )
    remove_expr = remove_expr.fill_null(False)
    remaining = df.filter(~remove_expr)
    removed_rows = df.height - remaining.height
    if remaining.is_empty():
        output.unlink()
    else:
        remaining.write_parquet(output)
    removed_raw_files = 0
    for path_text in skipped_paths:
        path = Path(path_text)
        if path.exists() and _is_skipped_raw(path):
            path.unlink()
            removed_raw_files += 1
    print(
        f"removed_rows={removed_rows} remaining_rows={remaining.height} "
        f"removed_raw_files={removed_raw_files}"
    )


def report(df: pl.DataFrame) -> None:
    Path("reports").mkdir(exist_ok=True)
    if df.is_empty():
        text = "# Sprint 02 FGrid Constraints Report\n\nNo validation rows.\n"
    else:
        total = df["symbol"].unique().len()
        bybit_symbols = df.filter(pl.col("feasible_bybit"))["symbol"].unique().len()
        five_usdt_symbols = df.filter(pl.col("feasible_user_5usdt_rule"))["symbol"].unique().len()
        text = f"# Sprint 02 FGrid Constraints Report\n\n- symbols tested: {total}\n- percent with any Bybit-feasible config: {bybit_symbols / total * 100 if total else 0:.1f}%\n- percent satisfying 5 USDT rule: {five_usdt_symbols / total * 100 if total else 0:.1f}%\n\n"
        if five_usdt_symbols == 0:
            text += "**PM BLOCKER:** no tested symbol/config satisfied the 5 USDT native grid minimum-investment rule.\n"
    Path("reports/sprint_02_fgrid_constraints_report.md").write_text(text, encoding="utf-8")


def _max_lev(row: dict[str, Any]) -> Any:
    return row.get("maxLeverage") or row.get("max_leverage") or 1


def _plan(
    universe: pl.DataFrame, max_profiles: int, absolute_max: int
) -> tuple[list[dict[str, Any]], int]:
    rows = universe.to_dicts()
    total = 0
    for r in rows:
        total += len(
            build_min_sweep_candidates(
                r["symbol"], r["lastPrice"], r["tickSize"], _max_lev(r), max_profiles, absolute_max
            )
        )
    return rows, total


def _validate_symbol(
    row: dict[str, Any],
    args: argparse.Namespace,
    limiter: TokenBucketRateLimiter,
    done: set[tuple[Any, ...]],
    done_lock: Lock,
    raw_dir: Path,
) -> tuple[list[dict[str, Any]], int, int, dict[str, int | None]]:
    settings = load_settings()
    rows: list[dict[str, Any]] = []
    skipped = 0
    errors = 0
    candidates = build_min_sweep_candidates(
        row["symbol"],
        row["lastPrice"],
        row["tickSize"],
        _max_lev(row),
        args.max_profiles_per_symbol,
        args.absolute_max_profiles_per_symbol,
    )
    stats: dict[str, int | None] = {
        "api_calls_attempted": 0,
        "api_calls_succeeded": 0,
        "api_calls_failed": 0,
        "max_observed_endpoint_limit": None,
        "min_observed_limit_status": None,
        "rate_limit_10006_count": 0,
    }
    with BybitClient(settings, rate_limiter=limiter) as client:
        for payload, meta in candidates:
            key = candidate_key(meta)
            with done_lock:
                if key in done:
                    skipped += 1
                    continue
                done.add(key)
            try:
                response = client.validate_grid_bot(payload)
                status_code = None
            except Exception as exc:
                errors += 1
                response = getattr(exc, "payload", {}) or {
                    "retCode": getattr(exc, "ret_code", None),
                    "retMsg": str(exc),
                    "debug_msg": getattr(exc, "debug_msg", None),
                }
                status_code = getattr(exc, "status_code", None)
            raw_path = raw_dir / f"{meta['symbol']}_{time.time_ns()}.json"
            write_redacted_response(raw_path, response)
            parsed = parse_validate_response(meta, response, status_code, str(raw_path))
            rows.append(parsed)
            if args.stop_after_first_5usdt_feasible and should_stop_symbol(
                rows, Decimal(str(args.user_threshold)), args.exhaustive
            ):
                break
        stats = {
            "api_calls_attempted": client.stats.api_calls_attempted,
            "api_calls_succeeded": client.stats.api_calls_succeeded,
            "api_calls_failed": client.stats.api_calls_failed,
            "max_observed_endpoint_limit": client.stats.max_observed_endpoint_limit,
            "min_observed_limit_status": client.stats.min_observed_limit_status,
            "rate_limit_10006_count": client.stats.rate_limit_10006_count,
        }
    return rows, skipped, errors, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="data/processed/universe_selected.parquet")
    parser.add_argument(
        "--mode", choices=["default", "min-investment-sweep"], default="min-investment-sweep"
    )
    parser.add_argument("--max-symbols", type=int, default=150)
    parser.add_argument("--max-configs-per-symbol", type=int, default=20, help="legacy alias")
    parser.add_argument("--max-profiles-per-symbol", type=int, default=12)
    parser.add_argument("--absolute-max-profiles-per-symbol", type=int, default=24)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--max-requests-per-second", type=float, default=9.5)
    parser.add_argument(
        "--sleep-sec", type=float, default=0.0, help="deprecated; use --max-requests-per-second"
    )
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--stop-after-first-5usdt-feasible", action="store_true", default=True)
    parser.add_argument("--exhaustive", action="store_true")
    parser.add_argument("--dry-run-plan", action="store_true")
    parser.add_argument("--confirm-large-sweep", action="store_true")
    parser.add_argument("--fast-max", action="store_true")
    parser.add_argument("--user-threshold", type=float, default=5.0)
    parser.add_argument("--purge-skipped-constraints", action="store_true")
    args = parser.parse_args()
    if args.purge_skipped_constraints:
        purge_skipped_constraints()
        return
    if args.fast_max:
        (
            args.workers,
            args.max_requests_per_second,
            args.sleep_sec,
            args.resume,
            args.progress_every,
        ) = 10, 9.5, 0.0, True, 50
    if args.sleep_sec and args.max_requests_per_second:
        print("warning: --sleep-sec is deprecated; using shared rate limiter")

    settings = load_settings()
    if not args.dry_run_plan and not settings.grid_validate_enabled:
        raise SystemExit(
            "GRID_VALIDATE_ENABLED=false. This command would not call Bybit validate. "
            "Set GRID_VALIDATE_ENABLED=true for real min-investment sweep, or use --dry-run-plan."
        )
    if not args.dry_run_plan:
        settings.require_private_credentials()

    output = Path("data/processed/fgrid_validate_constraints.parquet")
    raw_dir = Path("data/processed/fgrid_validate_raw_redacted")
    universe = pl.read_parquet(args.universe).head(args.max_symbols)
    symbol_rows, planned = _plan(
        universe, args.max_profiles_per_symbol, args.absolute_max_profiles_per_symbol
    )
    est = int(planned / args.max_requests_per_second) if args.max_requests_per_second else 0
    print(
        f"symbols={len(symbol_rows)} profiles_per_symbol_max={args.max_profiles_per_symbol} planned_requests<={planned} estimated_seconds_at_{args.max_requests_per_second}rps={est}"
    )
    if args.dry_run_plan:
        return
    if planned > 5000 and not args.confirm_large_sweep:
        raise SystemExit("planned requests > 5000; pass --confirm-large-sweep")
    if est > 600:
        print(
            f"warning: estimated runtime exceeds 10 minutes planned_requests={planned} estimated_seconds={est}"
        )

    done = existing_keys(output) if args.resume else set()
    done_lock = Lock()
    limiter = TokenBucketRateLimiter(args.max_requests_per_second)
    pending: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    start = time.monotonic()
    completed = skipped = errors = 0
    api_calls = api_succeeded = api_failed = rate_limit_10006_count = 0
    max_observed_endpoint_limit = None
    min_observed_limit_status = None
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(_validate_symbol, r, args, limiter, done, done_lock, raw_dir)
                for r in symbol_rows
            ]
            for fut in as_completed(futures):
                rows, sk, er, stats = fut.result()
                pending.extend(rows)
                all_rows.extend(rows)
                completed += len(rows)
                skipped += sk
                errors += er
                api_calls += int(stats.get("api_calls_attempted") or 0)
                api_succeeded += int(stats.get("api_calls_succeeded") or 0)
                api_failed += int(stats.get("api_calls_failed") or 0)
                rate_limit_10006_count += int(stats.get("rate_limit_10006_count") or 0)
                endpoint_limit = stats.get("max_observed_endpoint_limit")
                if endpoint_limit is not None:
                    max_observed_endpoint_limit = (
                        endpoint_limit
                        if max_observed_endpoint_limit is None
                        else max(max_observed_endpoint_limit, endpoint_limit)
                    )
                limit_status = stats.get("min_observed_limit_status")
                if limit_status is not None:
                    min_observed_limit_status = (
                        limit_status
                        if min_observed_limit_status is None
                        else min(min_observed_limit_status, limit_status)
                    )
                if len(pending) >= args.progress_every:
                    append_constraints(output, pending)
                    pending.clear()
                best5 = len({r["symbol"] for r in all_rows if r.get("feasible_user_5usdt_rule")})
                print(progress_line(completed, planned, start, best5, errors, skipped, api_calls))
    except KeyboardInterrupt:
        if pending:
            append_constraints(output, pending)
        print(
            f"interrupted; flushed_rows={len(pending)} resume_command=python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols {args.max_symbols} --fast-max"
        )
        raise
    if pending:
        append_constraints(output, pending)
    df = pl.read_parquet(output) if output.exists() else pl.DataFrame()
    feasible = df.filter(pl.col("feasible_user_5usdt_rule")) if not df.is_empty() else df
    feasible.write_parquet("data/processed/fgrid_feasible_configs.parquet")
    report(df)
    best_min = (
        df["investment_min"].drop_nulls().min()
        if (not df.is_empty() and "investment_min" in df.columns)
        else None
    )
    elapsed = max(time.monotonic() - start, 1e-9)
    print(
        f"rows={df.height} symbols_tested={df['symbol'].unique().len() if not df.is_empty() else 0} best_global_min_investment={best_min}"
    )
    print(
        f"api_calls_attempted={api_calls} api_calls_succeeded={api_succeeded} "
        f"api_calls_failed={api_failed} max_observed_endpoint_limit={max_observed_endpoint_limit} "
        f"min_observed_limit_status={min_observed_limit_status} "
        f"rate_limit_10006_count={rate_limit_10006_count} effective_api_rps={api_calls / elapsed:.2f}"
    )


if __name__ == "__main__":
    main()
