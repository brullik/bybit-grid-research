from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.fgrid_constraints import (
    append_constraints,
    build_candidate_payloads,
    candidate_key,
    existing_keys,
    parse_validate_response,
    write_redacted_response,
)
from bybit_grid.config import load_settings


def report(df: pl.DataFrame) -> None:
    Path("reports").mkdir(exist_ok=True)
    if df.is_empty():
        text = "# Sprint 02 FGrid Constraints Report\n\nNo validation rows.\n"
    else:
        total = df["symbol"].unique().len()
        bybit_symbols = df.filter(pl.col("feasible_bybit"))["symbol"].unique().len()
        five_usdt_symbols = df.filter(pl.col("feasible_user_5usdt_rule"))["symbol"].unique().len()
        text = (
            "# Sprint 02 FGrid Constraints Report\n\n"
            f"- symbols tested: {total}\n"
            f"- percent with any Bybit-feasible config: "
            f"{bybit_symbols / total * 100 if total else 0:.1f}%\n"
            f"- percent satisfying 5 USDT rule: "
            f"{five_usdt_symbols / total * 100 if total else 0:.1f}%\n\n"
        )
        if five_usdt_symbols == 0:
            text += (
                "**PM BLOCKER:** no tested symbol/config satisfied the 5 USDT native grid "
                "minimum-investment rule.\n"
            )
    Path("reports/sprint_02_fgrid_constraints_report.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="data/processed/universe_selected.parquet")
    parser.add_argument("--max-symbols", type=int, default=30)
    parser.add_argument("--max-configs-per-symbol", type=int, default=20)
    parser.add_argument("--sleep-sec", type=float, default=0.5)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--user-threshold", type=float, default=5.0)
    parser.add_argument("--expansion-multiplier", type=float, default=5.0)
    args = parser.parse_args()

    output = Path("data/processed/fgrid_validate_constraints.parquet")
    raw_dir = Path("data/processed/fgrid_validate_raw_redacted")
    done = existing_keys(output) if args.resume else set()
    rows = []
    settings = load_settings()
    universe = pl.read_parquet(args.universe).head(args.max_symbols)

    with BybitClient(settings) as client:
        for symbol_row in universe.to_dicts():
            symbol_rows = []
            for stage in ("fast", "full"):
                candidates = build_candidate_payloads(
                    symbol_row["symbol"],
                    symbol_row["lastPrice"],
                    symbol_row["tickSize"],
                    args.max_configs_per_symbol if stage == "full" else min(args.max_configs_per_symbol, 27),
                    stage=stage,
                )
                if stage == "full":
                    mins = [r.get("investment_min") for r in symbol_rows if r.get("investment_min") is not None]
                    if not mins or min(mins) > args.user_threshold * args.expansion_multiplier:
                        break
                for payload, meta in candidates:
                    key = candidate_key(meta)
                    if key in done:
                        continue
                    try:
                        response = client.validate_grid_bot(payload)
                        status_code = None
                    except Exception as exc:
                        response = getattr(exc, "payload", {}) or {
                            "retCode": getattr(exc, "ret_code", None),
                            "retMsg": str(exc),
                            "debug_msg": getattr(exc, "debug_msg", None),
                        }
                        status_code = getattr(exc, "status_code", None)
                    raw_path = raw_dir / f"{meta['symbol']}_{len(rows):06d}.json"
                    write_redacted_response(raw_path, response)
                    parsed = parse_validate_response(meta, response, status_code, str(raw_path))
                    rows.append(parsed)
                    symbol_rows.append(parsed)
                    time.sleep(args.sleep_sec)

    df = append_constraints(output, rows)
    feasible = df.filter(pl.col("feasible_user_5usdt_rule")) if not df.is_empty() else df
    feasible.write_parquet("data/processed/fgrid_feasible_configs.parquet")
    report(df)
    print(f"rows={df.height}")


if __name__ == "__main__":
    main()
