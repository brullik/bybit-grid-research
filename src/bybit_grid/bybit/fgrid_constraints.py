from __future__ import annotations

import json
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import polars as pl

from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload
from bybit_grid.logging import redact

STRICT_API_RESPONSE_ENVELOPE_CONTRACT = "strict-envelope-v1"
_INT64_MIN = -(2**63)
_INT64_MAX = (2**63) - 1

RANGE_WIDTH_PCT = [
    Decimal("0.02"),
    Decimal("0.05"),
    Decimal("0.10"),
    Decimal("0.15"),
    Decimal("0.20"),
]
CELL_NUMBER = [2, 5, 10, 20, 30]
LEVERAGE = [1, 2, 3, 5, 10]
INIT_MARGIN_PROBE = [
    Decimal("5"),
    Decimal("10"),
    Decimal("25"),
    Decimal("50"),
    Decimal("100"),
]
STOP_LOSS_MULT_BELOW_MIN = [Decimal("0.98"), Decimal("0.95"), Decimal("0.90")]
STAGE_A_RANGE_WIDTH_PCT = [
    Decimal("0.02"),
    Decimal("0.05"),
    Decimal("0.10"),
    Decimal("0.20"),
]
STAGE_A_CELL_NUMBER = [2, 5, 10, 20]
STAGE_A_LEVERAGE = [1, 3, 10]
STAGE_A_INIT_MARGIN_PROBE = [
    Decimal("5"),
    Decimal("10"),
    Decimal("25"),
    Decimal("50"),
    Decimal("100"),
]
STAGE_A_STOP_LOSS_MULT_BELOW_MIN = [Decimal("0.90"), Decimal("0.95")]
CANDIDATE_KEY_COLUMNS = [
    "symbol",
    "range_width_pct",
    "cell_number_requested",
    "leverage_requested",
    "init_margin_requested",
    "stop_loss_mult",
    "min_price",
    "max_price",
]


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


def _exact_int64(value: object) -> bool:
    return type(value) is int and _INT64_MIN <= value <= _INT64_MAX


def _native_marker_state(response: dict[str, Any]) -> tuple[bool, bool]:
    if ("retMsg" in response and type(response["retMsg"]) is not str) or (
        "debug_msg" in response and type(response["debug_msg"]) is not str
    ):
        return False, False
    result = response.get("result")
    if (
        type(result) is dict
        and "debug_msg" in result
        and type(result["debug_msg"]) is not str
    ):
        return False, False
    has_ret_code = "retCode" in response
    has_status_code = "status_code" in response
    if not has_ret_code and not has_status_code:
        return False, False
    ret_code = response.get("retCode")
    status_code = response.get("status_code")
    if (has_ret_code and not _exact_int64(ret_code)) or (
        has_status_code and not _exact_int64(status_code)
    ):
        return False, False
    ret_success = ret_code == 0 if has_ret_code else None
    status_success = status_code == 200 if has_status_code else None
    if has_ret_code and has_status_code and ret_success is not status_success:
        return False, False
    return True, bool(ret_success if has_ret_code else status_success)


def _redacted_message(value: object, label: str) -> str | None:
    if type(value) is not str:
        return None
    if value == "":
        return ""
    safe = redact({label: value})
    if type(safe) is dict:
        candidate = safe.get(label)
        if type(candidate) is str and candidate != value:
            return candidate
    return "***REDACTED***"


def _effective_debug_message(
    result: dict[str, Any], payload: dict[str, Any]
) -> str | None:
    result_value = result.get("debug_msg")
    payload_value = payload.get("debug_msg")
    if type(result_value) is str and result_value:
        return result_value
    if type(payload_value) is str:
        return payload_value
    if type(result_value) is str:
        return result_value
    return None


def parse_validate_response(
    meta: dict[str, Any],
    response: dict[str, Any] | object,
    status_code: int | None = None,
    raw_path: str | None = None,
) -> dict[str, Any]:
    payload = response if type(response) is dict else {}
    result_value = payload.get("result")
    result = result_value if type(result_value) is dict else payload
    raw_ret_code = payload.get("retCode")
    raw_native_status_code = payload.get("status_code")
    ret_code = raw_ret_code if _exact_int64(raw_ret_code) else None
    native_status_code = (
        raw_native_status_code if _exact_int64(raw_native_status_code) else None
    )
    http_status_code = status_code if _exact_int64(status_code) else None
    raw_ret_msg = payload.get("retMsg")
    semantic_debug_msg = _effective_debug_message(result, payload)
    envelope_valid, marker_success = _native_marker_state(payload)
    row = {
        **meta,
        "retCode": ret_code,
        "retMsg": _redacted_message(raw_ret_msg, "retMsg"),
        "status_code": native_status_code,
        "http_status_code": http_status_code,
        "check_code": result.get("check_code"),
        "debug_msg": _redacted_message(semantic_debug_msg, "debug_msg"),
        "raw_response_path_redacted": raw_path,
    }
    for name, col in [
        ("investment", "investment"),
        ("cell_number", "cell_number"),
        ("leverage", "leverage"),
        ("min_price", "min_price"),
        ("max_price", "max_price"),
        ("entry_price", "entry_price"),
        ("stop_loss_price", "stop_loss_price"),
        ("take_profit_price", "take_profit_price"),
        ("profit", "profit"),
    ]:
        row[
            f"{col}_from"
            if col not in {"investment", "cell_number", "leverage"}
            else f"{col}_min"
        ] = (
            float(_field(result, name, "from"))
            if _field(result, name, "from") is not None
            else None
        )
        row[
            f"{col}_to"
            if col not in {"investment", "cell_number", "leverage"}
            else f"{col}_max"
        ] = (
            float(_field(result, name, "to"))
            if _field(result, name, "to") is not None
            else None
        )
    validate_ok = (
        envelope_valid
        and marker_success
        and semantic_debug_msg not in ("param error", "schema error")
    )
    bybit = (
        validate_ok
        and _inside(
            meta["cell_number_requested"],
            _dec(row["cell_number_min"]),
            _dec(row["cell_number_max"]),
        )
        and _inside(
            meta["leverage_requested"],
            _dec(row["leverage_min"]),
            _dec(row["leverage_max"]),
        )
    )
    target_init_margin = Decimal("5")
    investment_min_dec = _dec(row["investment_min"])
    investment_max_dec = _dec(row["investment_max"])
    if not envelope_valid:
        feasible5 = False
        blocker = "response_envelope_invalid"
    elif row["investment_min"] is None:
        feasible5 = False
        blocker = "investment_min_missing"
    else:
        feasible5 = bool(
            bybit
            and investment_min_dec is not None
            and investment_min_dec <= target_init_margin
        )
        blocker = (
            None
            if feasible5
            else ("min_investment_gt_5usdt" if bybit else "bybit_not_feasible")
        )
    last_price = _dec(meta.get("lastPrice"))
    req_min = _dec(meta.get("min_price"))
    req_max = _dec(meta.get("max_price"))
    req_sl = _dec(meta.get("stop_loss_price"))
    long_liq = _field(result, "long_liq_price", "from") or _dec(
        result.get("long_liq_price")
    )
    short_liq = _field(result, "short_liq_price", "from") or _dec(
        result.get("short_liq_price")
    )

    def pct(num: Decimal | None, den: Decimal | None) -> float | None:
        if num is None or den in (None, Decimal("0")):
            return None
        return float((num / den) * Decimal("100"))

    row.update(
        {
            "envelope_valid": bool(envelope_valid),
            "validate_ok": bool(validate_ok),
            "schema_or_param_rejected": bool(
                semantic_debug_msg in ("param error", "schema error")
                or ret_code == 10001
            ),
            "feasible_bybit": bool(bybit),
            "min_investment_feasible_at_5usdt": feasible5,
            "feasible_user_5usdt_rule": feasible5,
            "target_init_margin_usdt": float(target_init_margin),
            "target_init_margin_inside_validate_range": bool(
                envelope_valid
                and marker_success
                and investment_min_dec is not None
                and investment_max_dec is not None
                and investment_min_dec <= target_init_margin <= investment_max_dec
            ),
            "long_liq_price": float(long_liq) if long_liq is not None else None,
            "short_liq_price": float(short_liq) if short_liq is not None else None,
            "requested_range_width_pct": pct(
                (req_max - req_min)
                if req_max is not None and req_min is not None
                else None,
                req_min,
            ),
            "requested_stop_loss_distance_from_min_pct": pct(
                (req_min - req_sl)
                if req_min is not None and req_sl is not None
                else None,
                req_min,
            ),
            "requested_stop_loss_distance_from_last_pct": pct(
                (last_price - req_sl)
                if last_price is not None and req_sl is not None
                else None,
                last_price,
            ),
            "long_liq_distance_from_last_pct": pct(
                (last_price - long_liq)
                if last_price is not None and long_liq is not None
                else None,
                last_price,
            ),
            "short_liq_distance_from_last_pct": pct(
                (short_liq - last_price)
                if last_price is not None and short_liq is not None
                else None,
                last_price,
            ),
            "blocker_reason": blocker,
        }
    )
    return row


def candidate_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(c) for c in CANDIDATE_KEY_COLUMNS)


def build_candidate_payloads(
    symbol: str,
    last_price: Any,
    tick_size: Any,
    max_configs: int | None = None,
    stage: str = "fast",
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    if stage == "fast":
        dimensions = (
            STAGE_A_RANGE_WIDTH_PCT,
            STAGE_A_CELL_NUMBER,
            STAGE_A_LEVERAGE,
            STAGE_A_INIT_MARGIN_PROBE,
            STAGE_A_STOP_LOSS_MULT_BELOW_MIN,
        )
    elif stage == "full":
        dimensions = (
            RANGE_WIDTH_PCT,
            CELL_NUMBER,
            LEVERAGE,
            INIT_MARGIN_PROBE,
            STOP_LOSS_MULT_BELOW_MIN,
        )
    else:
        raise ValueError(f"unknown candidate stage: {stage}")
    for width, cells, lev, margin, sl_mult in product(*dimensions):
        lower = Decimal("1") - (width / 2)
        upper = Decimal("1") + (width / 2)
        sl = lower * sl_mult
        payload = build_fgrid_validate_payload(
            symbol,
            Decimal(str(last_price)),
            Decimal(str(tick_size)),
            leverage=lev,
            cell_number=cells,
            init_margin=margin,
            lower_mult=lower,
            upper_mult=upper,
            stop_loss_mult=sl,
        )
        meta = {
            "symbol": symbol,
            "lastPrice": float(last_price),
            "tickSize": str(tick_size),
            "range_width_pct": float(width),
            "min_price": float(payload["min_price"]),
            "max_price": float(payload["max_price"]),
            "stop_loss_price": float(payload["stop_loss_price"]),
            "cell_number_requested": cells,
            "leverage_requested": lev,
            "init_margin_requested": float(margin),
            "stop_loss_mult": float(sl_mult),
        }
        out.append((payload, meta))
        if max_configs and len(out) >= max_configs:
            break
    return out


def existing_keys(path: Path) -> set[tuple[Any, ...]]:
    if not path.exists():
        return set()
    df = pl.read_parquet(path)
    cols = [c for c in CANDIDATE_KEY_COLUMNS if c in df.columns]
    return {
        tuple(r.get(c) for c in CANDIDATE_KEY_COLUMNS)
        for r in df.select(cols).to_dicts()
    }


def append_constraints(path: Path, rows: list[dict[str, Any]]) -> pl.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows) if rows else pl.DataFrame()
    if path.exists() and not df.is_empty():
        df = pl.concat([pl.read_parquet(path), df], how="diagonal_relaxed")
    if not df.is_empty():
        for col in CANDIDATE_KEY_COLUMNS:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))
        df = df.unique(CANDIDATE_KEY_COLUMNS, keep="last")
        df.write_parquet(path)
    return df


def write_redacted_response(path: Path, response: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact(response), indent=2, sort_keys=True), encoding="utf-8"
    )
# Mandatory RED probe: native grid validate result contract intentionally unavailable.
