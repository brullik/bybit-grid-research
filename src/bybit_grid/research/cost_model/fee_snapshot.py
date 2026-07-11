from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import Settings

FEE_RATE_ENDPOINT = "/v5/account/fee-rate"


def fee_snapshot_id(category: str) -> str:
    return f"fee_{category}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"


def extract_fee_rows(response: dict[str, Any], snapshot_id: str, category: str, settings: Settings) -> list[dict[str, Any]]:
    result = response.get("result") or {}
    rows = result.get("list") or []
    out = []
    for row in rows:
        out.append({
            "fee_snapshot_id": snapshot_id,
            "snapshot_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "environment": settings.bybit_env,
            "base_url": settings.bybit_api_base_url,
            "category": category,
            "symbol": row.get("symbol"),
            "makerFeeRate": row.get("makerFeeRate"),
            "takerFeeRate": row.get("takerFeeRate"),
            "retCode": response.get("retCode"),
            "retMsg": response.get("retMsg"),
            "source": "account_actual",
        })
    return out


def write_fee_snapshot(rows: list[dict[str, Any]], snapshot_id: str, cost_run_id: str | None = None) -> dict[str, str]:
    root = Path("data/metadata/fee_snapshots") / snapshot_id
    root.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows)
    parquet = root / "fee_rates.parquet"
    js = root / "fee_rates.json"
    df.write_parquet(parquet)
    js.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    report_dir = Path("reports/cost_runs") / (cost_run_id or snapshot_id)
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "fee_snapshot_report.md"
    symbols = sorted({str(r.get("symbol")) for r in rows if r.get("symbol")})
    report.write_text(f"# Fee Snapshot Report\n\nsource: {rows[0].get('source') if rows else 'empty'}\n\nsymbols_with_fee_rates: {len(symbols)}\n", encoding="utf-8")
    return {"parquet": str(parquet), "json": str(js), "report": str(report)}


def fetch_account_fee_rates(category: str, symbols: list[str] | None = None) -> tuple[str, list[dict[str, Any]]]:
    settings = Settings()
    settings.require_private_credentials()
    sid = fee_snapshot_id(category)
    params: dict[str, Any] = {"category": category}
    if symbols and len(symbols) == 1:
        params["symbol"] = symbols[0]
    with BybitClient(settings) as client:
        response = client.private_get(FEE_RATE_ENDPOINT, params)
    return sid, extract_fee_rows(response, sid, category, settings)
