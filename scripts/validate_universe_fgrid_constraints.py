from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
import sys
from threading import Lock
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.fgrid_constraints import (
    append_strict_constraints as append_constraints,
    build_strict_validate_error_evidence,
    candidate_key,
    parse_strict_validate_response,
    prepare_strict_constraints,
    strict_constraint_records,
    strict_existing_keys,
    strict_feasible_constraints,
    write_redacted_response,
)
from bybit_grid.bybit.fgrid_min_sweep import (
    build_min_sweep_candidates,
    progress_line,
    should_stop_symbol,
)
from bybit_grid.bybit.rate_limit import TokenBucketRateLimiter
from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.bybit.validate_only import (
    ValidateOnlyBoundaryError,
    enforce_validate_only_settings as _enforce_validate_only_settings,
)
from bybit_grid.config import Settings, load_settings
from scripts.build_universe import build_universe


STRICT_NATIVE_GRID_VALIDATE_SWEEP_CONTRACT = "native-grid-validate-result-v1"


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
        remove_expr = remove_expr | (
            pl.col("blocker_reason") == "investment_min_missing"
        )
    if skipped_paths and "raw_response_path_redacted" in df.columns:
        remove_expr = remove_expr | pl.col("raw_response_path_redacted").is_in(
            list(skipped_paths)
        )
    null_cols = [
        c for c in ("investment_min", "retCode", "status_code") if c in df.columns
    ]
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


def _strict_attempt_rows(df: pl.DataFrame) -> pl.DataFrame:
    return strict_constraint_records(df)


def _strict_feasible_rows(
    rows: list[dict[str, Any]], *, require_5usdt: bool
) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    return strict_feasible_constraints(pl.DataFrame(rows), require_5usdt=require_5usdt)


def report(df: pl.DataFrame) -> None:
    Path("reports").mkdir(exist_ok=True)
    attempts = _strict_attempt_rows(df)
    if attempts.is_empty():
        text = "# Sprint 02 FGrid Constraints Report\n\nNo validation rows.\n"
    else:
        bybit = strict_feasible_constraints(attempts, require_5usdt=False)
        five_usdt = strict_feasible_constraints(attempts, require_5usdt=True)
        total = attempts["symbol"].unique().len()
        bybit_symbols = bybit["symbol"].unique().len()
        five_usdt_symbols = five_usdt["symbol"].unique().len()
        text = f"# Sprint 02 FGrid Constraints Report\n\n- symbols tested: {total}\n- percent with any Bybit-feasible config: {bybit_symbols / total * 100 if total else 0:.1f}%\n- percent satisfying 5 USDT rule: {five_usdt_symbols / total * 100 if total else 0:.1f}%\n\n"
        if five_usdt_symbols == 0:
            text += "**PM BLOCKER:** no tested symbol/config satisfied the 5 USDT native grid minimum-investment rule.\n"
    Path("reports/sprint_02_fgrid_constraints_report.md").write_text(
        text, encoding="utf-8"
    )


def finalize_outputs(
    df: pl.DataFrame,
    feasible_path: Path = Path("data/processed/fgrid_feasible_configs.parquet"),
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    attempts = _strict_attempt_rows(df)
    bybit_feasible = strict_feasible_constraints(attempts, require_5usdt=False)
    feasible = strict_feasible_constraints(attempts, require_5usdt=True)
    feasible_path.parent.mkdir(parents=True, exist_ok=True)
    if feasible.width:
        feasible.write_parquet(feasible_path)
    elif feasible_path.exists():
        feasible_path.unlink()
    report(df)
    return attempts, bybit_feasible, feasible


def reset_strict_derived_outputs(
    feasible_path: Path = Path("data/processed/fgrid_feasible_configs.parquet"),
    report_path: Path = Path("reports/sprint_02_fgrid_constraints_report.md"),
) -> None:
    for path in (feasible_path, report_path):
        if path.exists():
            path.unlink()


def _max_lev(row: dict[str, Any]) -> Any:
    return row.get("maxLeverage") or row.get("max_leverage") or 1


def _plan(
    universe: pl.DataFrame, max_profiles: int, absolute_max: int
) -> tuple[
    list[
        tuple[
            dict[str, Any],
            list[tuple[dict[str, Any], dict[str, Any]]],
        ]
    ],
    int,
]:
    work: list[
        tuple[
            dict[str, Any],
            list[tuple[dict[str, Any], dict[str, Any]]],
        ]
    ] = []
    total = 0
    for row in universe.to_dicts():
        candidates = build_min_sweep_candidates(
            row["symbol"],
            row["lastPrice"],
            row["tickSize"],
            _max_lev(row),
            max_profiles,
            absolute_max,
        )
        work.append((row, candidates))
        total += len(candidates)
    return work, total


def _validate_symbol(
    row: dict[str, Any],
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    settings: Settings,
    args: argparse.Namespace,
    limiter: TokenBucketRateLimiter,
    done: set[tuple[Any, ...]],
    done_lock: Lock,
    raw_dir: Path,
) -> tuple[list[dict[str, Any]], int, int, dict[str, int | None]]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    errors = 0
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
                error_evidence = None
            except ValidateOnlyBoundaryError:
                raise
            except BybitAPIError as exc:
                errors += 1
                error_evidence = build_strict_validate_error_evidence(exc)
                response_data = error_evidence.get("response_data")
                response = response_data if type(response_data) is dict else {}
                status_code = exc.status_code
            except Exception as exc:
                errors += 1
                error_evidence = build_strict_validate_error_evidence(exc)
                response = {}
                status_code = None
            raw_path = raw_dir / f"{meta['symbol']}_{time.time_ns()}.json"
            write_redacted_response(raw_path, response)
            parsed = parse_strict_validate_response(
                meta,
                response,
                status_code,
                str(raw_path),
                error_evidence=error_evidence,
            )
            rows.append(parsed)
            if args.stop_after_first_5usdt_feasible:
                strict_five = _strict_feasible_rows(rows, require_5usdt=True)
                if should_stop_symbol(
                    strict_five.to_dicts(),
                    Decimal(str(args.user_threshold)),
                    args.exhaustive,
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
    parser.add_argument(
        "--universe", default="data/processed/universe_selected.parquet"
    )
    parser.add_argument(
        "--mode",
        choices=["default", "min-investment-sweep"],
        default="min-investment-sweep",
    )
    parser.add_argument("--max-symbols", type=int, default=150)
    parser.add_argument(
        "--max-configs-per-symbol", type=int, default=20, help="legacy alias"
    )
    parser.add_argument("--max-profiles-per-symbol", type=int, default=12)
    parser.add_argument("--absolute-max-profiles-per-symbol", type=int, default=24)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--max-requests-per-second", type=float, default=9.5)
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=0.0,
        help="deprecated; use --max-requests-per-second",
    )
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument(
        "--stop-after-first-5usdt-feasible", action="store_true", default=True
    )
    parser.add_argument("--exhaustive", action="store_true")
    parser.add_argument("--dry-run-plan", action="store_true")
    parser.add_argument("--confirm-large-sweep", action="store_true")
    parser.add_argument("--fast-max", action="store_true")
    parser.add_argument("--user-threshold", type=float, default=5.0)
    parser.add_argument("--purge-skipped-constraints", action="store_true")
    parser.add_argument("--auto-build-universe", action="store_true")
    parser.add_argument("--min-turnover", type=float, default=5_000_000)
    parser.add_argument("--universe-max-symbols", type=int, default=150)
    args = parser.parse_args()
    settings = load_settings()
    _enforce_validate_only_settings(settings=settings)
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

    if not args.dry_run_plan:
        if settings.grid_validate_enabled is False:
            raise SystemExit(
                "GRID_VALIDATE_ENABLED=false. This command would not call Bybit validate. "
                "Set GRID_VALIDATE_ENABLED=true for real min-investment sweep, "
                "or use --dry-run-plan."
            )
        settings.require_private_credentials()

    output = Path("data/processed/fgrid_validate_constraints.parquet")
    raw_dir = Path("data/processed/fgrid_validate_raw_redacted")
    universe_path = Path(args.universe)
    if not universe_path.exists():
        if not args.auto_build_universe:
            print(f"missing_universe={args.universe}")
            print(
                "Run: python scripts/build_universe.py --min-turnover 5000000 --max-symbols 150"
            )
            print("Or rerun this command with --auto-build-universe.")
            raise SystemExit(2)
        counts = build_universe(args.min_turnover, args.universe_max_symbols)
        print(
            f"step=build_universe status=ok selected_count={counts.get('selected', counts.get('selected_count', 0))}"
        )
    universe = pl.read_parquet(universe_path).head(args.max_symbols)
    symbol_work, planned = _plan(
        universe, args.max_profiles_per_symbol, args.absolute_max_profiles_per_symbol
    )
    est = (
        int(planned / args.max_requests_per_second)
        if args.max_requests_per_second
        else 0
    )
    print(
        f"symbols={len(symbol_work)} profiles_per_symbol_max={args.max_profiles_per_symbol} "
        f"planned_requests<={planned} "
        f"estimated_seconds_at_{args.max_requests_per_second}rps={est}"
    )
    if args.dry_run_plan:
        return
    if planned > 5000 and not args.confirm_large_sweep:
        raise SystemExit("planned requests > 5000; pass --confirm-large-sweep")
    if est > 600:
        print(
            f"warning: estimated runtime exceeds 10 minutes planned_requests={planned} estimated_seconds={est}"
        )

    reset_strict_derived_outputs()
    prepare_strict_constraints(output)
    done = strict_existing_keys(output) if args.resume else set()
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
                pool.submit(
                    _validate_symbol,
                    row,
                    candidates,
                    settings,
                    args,
                    limiter,
                    done,
                    done_lock,
                    raw_dir,
                )
                for row, candidates in symbol_work
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
                strict_five = _strict_feasible_rows(all_rows, require_5usdt=True)
                best5 = (
                    strict_five["symbol"].unique().len()
                    if "symbol" in strict_five.columns
                    else 0
                )
                line = progress_line(
                    completed, planned, start, best5, errors, skipped, api_calls
                )
                print(line)
                api_rps_now = api_calls / max(time.monotonic() - start, 1e-9)
                if api_rps_now > 15:
                    print(
                        "warning: api_rps exceeds endpoint limit; check whether rows are real API responses or skipped/resumed rows"
                    )
    except KeyboardInterrupt:
        if pending:
            append_constraints(output, pending)
        interrupted_df = pl.read_parquet(output) if output.exists() else pl.DataFrame()
        finalize_outputs(interrupted_df)
        print(
            f"interrupted; flushed_rows={len(pending)} resume_command=python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols {args.max_symbols} --fast-max"
        )
        raise
    if pending:
        append_constraints(output, pending)
    df = pl.read_parquet(output) if output.exists() else pl.DataFrame()
    attempts, bybit_feasible, _ = finalize_outputs(df)
    best_min = (
        bybit_feasible["investment_min"].drop_nulls().min()
        if (
            not bybit_feasible.is_empty() and "investment_min" in bybit_feasible.columns
        )
        else None
    )
    elapsed = max(time.monotonic() - start, 1e-9)
    symbols_tested = (
        attempts["symbol"].unique().len()
        if not attempts.is_empty() and "symbol" in attempts.columns
        else 0
    )
    configs_tested = attempts.height
    investment_non_null = (
        attempts["investment_min"].drop_nulls().len()
        if not attempts.is_empty() and "investment_min" in attempts.columns
        else 0
    )
    print(
        f"rows={attempts.height} symbols_tested={symbols_tested} "
        f"configs_tested={configs_tested} "
        f"investment_min_non_null_rows={investment_non_null} best_global_min_investment={best_min}"
    )
    print(
        f"api_calls_attempted={api_calls} api_calls_succeeded={api_succeeded} "
        f"api_calls_failed={api_failed} max_observed_endpoint_limit={max_observed_endpoint_limit} "
        f"min_observed_limit_status={min_observed_limit_status} "
        f"rate_limit_10006_count={rate_limit_10006_count} effective_api_rps={api_calls / elapsed:.2f}"
    )


if __name__ == "__main__":
    main()
