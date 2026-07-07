from __future__ import annotations

import json
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import polars as pl

from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload
from bybit_grid.logging import redact

RANGE_WIDTH_PCT = [Decimal("0.02"), Decimal("0.05"), Decimal("0.10"), Decimal("0.15"), Decimal("0.20")]
CELL_NUMBER = [2, 5, 10, 20, 30]
LEVERAGE = [1, 2, 3, 5, 10]
INIT_MARGIN_PROBE = [Decimal("5"), Decimal("10"), Decimal("25"), Decimal("50"), Decimal("100")]
STOP_LOSS_MULT_BELOW_MIN = [Decimal("0.98"), Decimal("0.95"), Decimal("0.90")]


def _dec(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _field(result: dict[str, Any], name: str, bound: str) -> Decimal | None:
    val = result.get(name)
    if isinstance(val, dict):
        return _dec(val.get(bound))
    for key in (f"{name}_{bound}", f"{name}.{bound}"):
        if key in result:
            return _dec(result.get(key))
    return None


def _inside(value: Any, low: Decimal | None, high: Decimal | None) -> bool:
    v = _dec(value)
    if v is None:
        return False
    return (low is None or v >= low) and (high is None or v <= high)


def parse_validate_response(meta: dict[str, Any], response: dict[str, Any], status_code: int | None = None, raw_path: str | None = None) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    ret_code = response.get("retCode")
    status = response.get("status_code", status_code)
    row = {**meta, "retCode": ret_code, "retMsg": response.get("retMsg"), "status_code": status, "check_code": result.get("check_code"), "debug_msg": result.get("debug_msg") or response.get("debug_msg"), "raw_response_path_redacted": raw_path}
    for name, col in [("investment", "investment"), ("cell_number", "cell_number"), ("leverage", "leverage"), ("min_price", "min_price"), ("max_price", "max_price"), ("stop_loss_price", "stop_loss_price"), ("profit", "profit")]:
        row[f"{col}_from" if col not in {"investment", "cell_number", "leverage"} else f"{col}_min"] = float(_field(result, name, "from")) if _field(result, name, "from") is not None else None
        row[f"{col}_to" if col not in {"investment", "cell_number", "leverage"} else f"{col}_max"] = float(_field(result, name, "to")) if _field(result, name, "to") is not None else None
    validate_ok = ret_code in (0, "0", None) and status in (None, 200, "200") and row["debug_msg"] not in ("param error", "schema error")
    bybit = validate_ok and _inside(meta["cell_number_requested"], _dec(row["cell_number_min"]), _dec(row["cell_number_max"])) and _inside(meta["leverage_requested"], _dec(row["leverage_min"]), _dec(row["leverage_max"]))
    if row["investment_min"] is None:
        feasible5 = False
        blocker = "investment_min_missing"
    else:
        feasible5 = bool(bybit and Decimal(str(row["investment_min"])) <= Decimal("5"))
        blocker = None if feasible5 else ("min_investment_gt_5usdt" if bybit else "bybit_not_feasible")
    row.update({"validate_ok": bool(validate_ok), "schema_or_param_rejected": bool(row["debug_msg"] in ("param error", "schema error") or ret_code in (10001, "10001")), "feasible_bybit": bool(bybit), "feasible_user_5usdt_rule": feasible5, "blocker_reason": blocker})
    return row


def build_candidate_payloads(symbol: str, last_price: Any, tick_size: Any, max_configs: int | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for width, cells, lev, margin, sl_mult in product(RANGE_WIDTH_PCT, CELL_NUMBER, LEVERAGE, INIT_MARGIN_PROBE, STOP_LOSS_MULT_BELOW_MIN):
        lower = Decimal("1") - (width / 2)
        upper = Decimal("1") + (width / 2)
        sl = lower * sl_mult
        payload = build_fgrid_validate_payload(symbol, Decimal(str(last_price)), Decimal(str(tick_size)), leverage=lev, cell_number=cells, init_margin=margin, lower_mult=lower, upper_mult=upper, stop_loss_mult=sl)
        meta = {"symbol": symbol, "lastPrice": float(last_price), "tickSize": str(tick_size), "range_width_pct": float(width), "min_price": float(payload["min_price"]), "max_price": float(payload["max_price"]), "stop_loss_price": float(payload["stop_loss_price"]), "cell_number_requested": cells, "leverage_requested": lev, "init_margin_requested": float(margin)}
        out.append((payload, meta))
        if max_configs and len(out) >= max_configs:
            break
    return out


def existing_keys(path: Path) -> set[tuple[Any, ...]]:
    if not path.exists():
        return set()
    cols = ["symbol", "range_width_pct", "cell_number_requested", "leverage_requested", "init_margin_requested"]
    return {tuple(r[c] for c in cols) for r in pl.read_parquet(path).select(cols).to_dicts()}


def append_constraints(path: Path, rows: list[dict[str, Any]]) -> pl.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows) if rows else pl.DataFrame()
    if path.exists() and not df.is_empty():
        df = pl.concat([pl.read_parquet(path), df], how="diagonal_relaxed").unique(["symbol", "range_width_pct", "cell_number_requested", "leverage_requested", "init_margin_requested"], keep="last")
    if not df.is_empty():
        df.write_parquet(path)
    return df


def write_redacted_response(path: Path, response: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(response), indent=2, sort_keys=True))
