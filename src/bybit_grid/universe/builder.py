from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from bybit_grid.bybit.client import BybitClient

TEST_MARKERS = ("TEST", "PRE", "PERPTEST")
FIELDS = [
    "symbol","baseCoin","quoteCoin","status","contractType","launchTime","age_days",
    "tickSize","qtyStep","minOrderQty","minNotionalValue","maxLeverage","fundingInterval",
    "turnover24h","volume24h","lastPrice","liquidity_rank","eligible_liquidity_1m",
    "eligible_liquidity_5m","eligible_liquidity_10m","eligible_liquidity_25m",
]


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch_linear_instruments(client: BybitClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        result = client.public_get("/v5/market/instruments-info", params).get("result", {})
        rows.extend(result.get("list", []))
        cursor = result.get("nextPageCursor") or ""
        if not cursor:
            return rows


def fetch_linear_tickers(client: BybitClient) -> list[dict[str, Any]]:
    return client.public_get("/v5/market/tickers", {"category": "linear"}).get("result", {}).get("list", [])


def normalize_universe(instruments: list[dict[str, Any]], tickers: list[dict[str, Any]]) -> pl.DataFrame:
    ticker_by_symbol = {r.get("symbol"): r for r in tickers}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rows = []
    for inst in instruments:
        sym = inst.get("symbol", "")
        lot = inst.get("lotSizeFilter") or {}
        price = inst.get("priceFilter") or {}
        lev = inst.get("leverageFilter") or {}
        tick = ticker_by_symbol.get(sym, {})
        launch = int(_num(inst.get("launchTime"), 0))
        rows.append({
            "symbol": sym,
            "baseCoin": inst.get("baseCoin"),
            "quoteCoin": inst.get("quoteCoin"),
            "status": inst.get("status"),
            "contractType": inst.get("contractType"),
            "isPreListing": str(inst.get("isPreListing", "false")).lower() == "true",
            "launchTime": launch,
            "age_days": max(0.0, (now_ms - launch) / 86_400_000) if launch else None,
            "tickSize": price.get("tickSize"),
            "qtyStep": lot.get("qtyStep"),
            "minOrderQty": lot.get("minOrderQty"),
            "minNotionalValue": lot.get("minNotionalValue"),
            "maxLeverage": lev.get("maxLeverage"),
            "fundingInterval": inst.get("fundingInterval"),
            "turnover24h": _num(tick.get("turnover24h")),
            "volume24h": _num(tick.get("volume24h")),
            "lastPrice": _num(tick.get("lastPrice"), None),
        })
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).with_columns(
        pl.col("turnover24h").rank("ordinal", descending=True).cast(pl.Int64).alias("liquidity_rank"),
        (pl.col("turnover24h") >= 1_000_000).alias("eligible_liquidity_1m"),
        (pl.col("turnover24h") >= 5_000_000).alias("eligible_liquidity_5m"),
        (pl.col("turnover24h") >= 10_000_000).alias("eligible_liquidity_10m"),
        (pl.col("turnover24h") >= 25_000_000).alias("eligible_liquidity_25m"),
    )


def filter_universe(df: pl.DataFrame, min_turnover: float, max_symbols: int | None = None) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, int]]:
    if df.is_empty():
        return df, df, {"total_linear_instruments": 0, "trading_usdt_perpetual_count": 0, "excluded_prelaunch_count": 0, "excluded_low_liquidity_count": 0, "selected_count": 0}
    base = df.filter(
        (pl.col("quoteCoin") == "USDT")
        & ((pl.col("contractType") == "LinearPerpetual") | pl.col("contractType").is_null())
        & (pl.col("status") == "Trading")
    )
    pre = base.filter(pl.col("isPreListing") | pl.col("symbol").str.contains("|".join(TEST_MARKERS)))
    candidates = base.filter(~(pl.col("isPreListing") | pl.col("symbol").str.contains("|".join(TEST_MARKERS)))).select(FIELDS)
    selected = candidates.filter(pl.col("turnover24h") >= min_turnover).sort("turnover24h", descending=True)
    low = candidates.height - selected.height
    if max_symbols:
        selected = selected.head(max_symbols)
    counts = {"total_linear_instruments": df.height, "trading_usdt_perpetual_count": base.height, "excluded_prelaunch_count": pre.height, "excluded_low_liquidity_count": low, "selected_count": selected.height}
    return candidates.sort("turnover24h", descending=True), selected, counts


def write_universe_report(path: Path, counts: dict[str, int], selected: pl.DataFrame, min_turnover: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Sprint 02 Universe Report", "", f"Turnover threshold used: {min_turnover:,.0f}", ""]
    for k, v in counts.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Top 20 selected symbols by turnover", "", "| rank | symbol | turnover24h | lastPrice |", "|---:|---|---:|---:|"]
    for r in selected.head(20).to_dicts():
        lines.append(f"| {r['liquidity_rank']} | {r['symbol']} | {r['turnover24h']:.2f} | {r.get('lastPrice')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
