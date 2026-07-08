from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

BYTES_PER_ROW_ESTIMATE = 220
ONE_MINUTE_MS = 60_000


def last_closed_minute_ms(now_ms: int | None = None) -> int:
    now = int(datetime.now(timezone.utc).timestamp() * 1000) if now_ms is None else int(now_ms)
    return (now // ONE_MINUTE_MS) * ONE_MINUTE_MS - ONE_MINUTE_MS


def start_for_days_ms(end_ms: int, days: int) -> int:
    return int(end_ms) - int(days) * 24 * 60 * ONE_MINUTE_MS + ONE_MINUTE_MS


def estimate_rows(start_ms: int, end_ms: int, days: int | None = None) -> dict[str, int]:
    minutes = max(0, (int(end_ms) - int(start_ms)) // ONE_MINUTE_MS + 1)
    funding_rows = max(1, int(days) * 3) if days is not None else max(1, minutes // (8 * 60))
    return {
        "estimated_kline_rows": minutes,
        "estimated_mark_kline_rows": minutes,
        "estimated_funding_rows": funding_rows,
        "estimated_total_rows": minutes * 2 + funding_rows,
    }


def build_download_manifest(
    universe: pl.DataFrame,
    feasible: pl.DataFrame | None,
    days: int,
    max_symbols: int,
    max_gb: float,
) -> pl.DataFrame:
    pass_symbols: set[str] = set()
    if universe.is_empty():
        return pl.DataFrame({
            "symbol": [],
            "trading_feasibility_status": [],
            "start_ms": [],
            "end_ms": [],
            "days_requested": [],
            "estimated_kline_rows": [],
            "estimated_mark_kline_rows": [],
            "estimated_funding_rows": [],
            "estimated_total_rows": [],
            "estimated_bytes": [],
            "estimated_gb": [],
        })
    if feasible is not None and not feasible.is_empty():
        if "min_investment_feasible_at_5usdt" in feasible.columns:
            pass_symbols = set(
                feasible.filter(pl.col("min_investment_feasible_at_5usdt"))["symbol"].unique().to_list()
            )
        elif "feasible_user_5usdt_rule" in feasible.columns:
            pass_symbols = set(
                feasible.filter(pl.col("feasible_user_5usdt_rule"))["symbol"].unique().to_list()
            )
        else:
            pass_symbols = set(feasible["symbol"].unique().to_list()) if "symbol" in feasible.columns else set()
    status = "validated_5usdt_feasible" if len(pass_symbols) >= 1 else "blocked_by_min_investment"
    if status == "validated_5usdt_feasible":
        chosen = universe.filter(pl.col("symbol").is_in(list(pass_symbols))).sort(
            "turnover24h", descending=True
        )
    else:
        chosen = universe.sort("turnover24h", descending=True)
    chosen = chosen.head(max_symbols)
    end_ms = last_closed_minute_ms()
    requested_start = start_for_days_ms(end_ms, days)
    rows = []
    for r in chosen.to_dicts():
        launch = int(r.get("launchTime") or 0)
        start_ms = max(requested_start, launch) if launch else requested_start
        start_ms = (start_ms // ONE_MINUTE_MS) * ONE_MINUTE_MS
        estimates = estimate_rows(start_ms, end_ms, days)
        total_rows = estimates["estimated_total_rows"]
        rows.append(
            {
                "symbol": r["symbol"],
                "trading_feasibility_status": status
                if r["symbol"] not in pass_symbols
                else "validated_5usdt_feasible",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "days_requested": days,
                **estimates,
                "estimated_bytes": total_rows * BYTES_PER_ROW_ESTIMATE,
                "estimated_gb": (total_rows * BYTES_PER_ROW_ESTIMATE) / 1_000_000_000,
            }
        )
    df = pl.DataFrame(rows)
    total_gb = float(df["estimated_gb"].sum()) if not df.is_empty() else 0.0
    if total_gb > max_gb:
        raise ValueError(
            f"download manifest estimate {total_gb:.3f} GB exceeds cap {max_gb:.3f} GB"
        )
    return df


def write_download_plan(path: Path, manifest: pl.DataFrame, days: int, max_gb: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = float(manifest["estimated_gb"].sum()) if not manifest.is_empty() else 0.0
    downloadable = (
        manifest.filter(pl.col("trading_feasibility_status") == "validated_5usdt_feasible").height
        if not manifest.is_empty()
        else 0
    )
    lines = [
        "# Sprint 02 Download Plan",
        "",
        f"Days requested: {days}",
        f"Max GB cap: {max_gb}",
        f"Estimated GB: {total:.3f}",
        f"Symbols: {manifest.height}",
        f"Downloadable rows: {downloadable}",
        f"Skipped blocked by min investment: {manifest.height - downloadable}",
        f"Download blocked by policy: {bool(manifest.height and downloadable == 0)}",
        "",
        "| symbol | status | est rows | est GB |",
        "|---|---|---:|---:|",
    ]
    for r in manifest.to_dicts():
        lines.append(
            f"| {r['symbol']} | {r['trading_feasibility_status']} | {r['estimated_total_rows']} | {r['estimated_gb']:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
