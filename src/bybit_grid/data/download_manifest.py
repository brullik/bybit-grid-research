from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

BYTES_PER_ROW_ESTIMATE = 220


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def build_download_manifest(universe: pl.DataFrame, feasible: pl.DataFrame | None, days: int, max_symbols: int, max_gb: float) -> pl.DataFrame:
    pass_symbols: set[str] = set()
    if feasible is not None and not feasible.is_empty() and "feasible_user_5usdt_rule" in feasible.columns:
        pass_symbols = set(feasible.filter(pl.col("feasible_user_5usdt_rule"))["symbol"].unique().to_list())
    status = "validated_5usdt_feasible" if len(pass_symbols) >= 10 else "blocked_by_min_investment"
    chosen = universe.filter(pl.col("symbol").is_in(list(pass_symbols))).sort("turnover24h", descending=True) if status == "validated_5usdt_feasible" else universe.sort("turnover24h", descending=True)
    chosen = chosen.head(max_symbols)
    end_ms = _now_ms()
    requested_start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    rows = []
    for r in chosen.to_dicts():
        launch = int(r.get("launchTime") or 0)
        start_ms = max(requested_start, launch) if launch else requested_start
        minutes = max(0, (end_ms - start_ms) // 60_000 + 1)
        funding_rows = max(1, minutes // (8 * 60))
        rows.append({"symbol": r["symbol"], "trading_feasibility_status": status if r["symbol"] not in pass_symbols else "validated_5usdt_feasible", "start_ms": start_ms, "end_ms": end_ms, "days_requested": days, "estimated_kline_rows": minutes, "estimated_mark_kline_rows": minutes, "estimated_funding_rows": funding_rows, "estimated_total_rows": minutes * 2 + funding_rows, "estimated_bytes": (minutes * 2 + funding_rows) * BYTES_PER_ROW_ESTIMATE, "estimated_gb": ((minutes * 2 + funding_rows) * BYTES_PER_ROW_ESTIMATE) / 1_000_000_000})
    df = pl.DataFrame(rows)
    total_gb = float(df["estimated_gb"].sum()) if not df.is_empty() else 0.0
    if total_gb > max_gb:
        raise ValueError(f"download manifest estimate {total_gb:.3f} GB exceeds cap {max_gb:.3f} GB")
    return df


def write_download_plan(path: Path, manifest: pl.DataFrame, days: int, max_gb: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = float(manifest["estimated_gb"].sum()) if not manifest.is_empty() else 0.0
    lines = ["# Sprint 02 Download Plan", "", f"Days requested: {days}", f"Max GB cap: {max_gb}", f"Estimated GB: {total:.3f}", f"Symbols: {manifest.height}", "", "| symbol | status | est rows | est GB |", "|---|---|---:|---:|"]
    for r in manifest.to_dicts():
        lines.append(f"| {r['symbol']} | {r['trading_feasibility_status']} | {r['estimated_total_rows']} | {r['estimated_gb']:.4f} |")
    path.write_text("\n".join(lines) + "\n")
