from __future__ import annotations

import json
import math
import re
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import polars as pl

from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload
from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.logging import redact

STRICT_API_RESPONSE_ENVELOPE_CONTRACT = "strict-envelope-v1"
NATIVE_GRID_VALIDATE_RESULT_CONTRACT = "native-grid-validate-result-v1"
NATIVE_GRID_VALIDATE_SUCCESS_STATUS_CODE = 200
NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE = "FGRID_CHECK_CODE_UNSPECIFIED"
_INT64_MIN = -(2**63)
_INT64_MAX = (2**63) - 1

_STRICT_DECIMAL_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_STRICT_RANGE_FIELDS = (
    ("investment", "investment_min", "investment_max", "positive"),
    ("cell_number", "cell_number_min", "cell_number_max", "positive_int"),
    ("leverage", "leverage_min", "leverage_max", "positive"),
    ("min_price", "min_price_from", "min_price_to", "positive"),
    ("max_price", "max_price_from", "max_price_to", "positive"),
    ("entry_price", "entry_price_from", "entry_price_to", "positive"),
    (
        "stop_loss_price",
        "stop_loss_price_from",
        "stop_loss_price_to",
        "positive",
    ),
    (
        "take_profit_price",
        "take_profit_price_from",
        "take_profit_price_to",
        "positive",
    ),
    ("profit", "profit_from", "profit_to", "nonnegative"),
)
_STRICT_MEMBERSHIP_FIELDS = (
    (
        "init_margin_requested",
        "investment",
        "requested_init_margin_inside_validate_range",
    ),
    (
        "cell_number_requested",
        "cell_number",
        "requested_cell_number_inside_validate_range",
    ),
    (
        "leverage_requested",
        "leverage",
        "requested_leverage_inside_validate_range",
    ),
    ("min_price", "min_price", "requested_min_price_inside_validate_range"),
    ("max_price", "max_price", "requested_max_price_inside_validate_range"),
    (
        "stop_loss_price",
        "stop_loss_price",
        "requested_stop_loss_price_inside_validate_range",
    ),
)
_STRICT_ERROR_REASON_CODES = frozenset(
    {
        "api_error",
        "http_status_error",
        "response_body_empty",
        "response_json_duplicate_key",
        "response_json_invalid",
        "response_json_nonfinite",
        "response_marker_alias_forbidden",
        "response_marker_conflict",
        "response_marker_missing",
        "response_marker_type_invalid",
        "response_message_type_invalid",
        "response_root_not_object",
        "response_utf8_invalid",
    }
)
_STRICT_SELECTOR_BOOL_COLUMNS = (
    "strict_parser_applied",
    "envelope_valid",
    "result_schema_valid",
    "validate_ok",
    "feasible_bybit",
    "requested_init_margin_inside_validate_range",
    "requested_cell_number_inside_validate_range",
    "requested_leverage_inside_validate_range",
    "requested_min_price_inside_validate_range",
    "requested_max_price_inside_validate_range",
    "requested_stop_loss_price_inside_validate_range",
    "requested_values_inside_validate_ranges",
)

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


def _strict_decimal_string(value: object) -> Decimal | None:
    if type(value) is not str or not _STRICT_DECIMAL_RE.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
        as_float = float(parsed)
    except (ArithmeticError, ValueError):
        return None
    if not parsed.is_finite() or not math.isfinite(as_float):
        return None
    if parsed != 0 and as_float == 0:
        return None
    return parsed


def _strict_meta_decimal(value: object) -> Decimal | None:
    if type(value) not in {str, int, float, Decimal}:
        return None
    if type(value) is str and not _STRICT_DECIMAL_RE.fullmatch(value):
        return None
    try:
        parsed = Decimal(str(value))
        as_float = float(parsed)
    except (ArithmeticError, ValueError):
        return None
    if not parsed.is_finite() or not math.isfinite(as_float):
        return None
    if parsed != 0 and as_float == 0:
        return None
    return parsed


def _strict_range(
    result: dict[str, Any], name: str, domain: str
) -> tuple[Decimal | None, Decimal | None, bool]:
    has_flattened_alias = any(
        alias in result
        for alias in (
            f"{name}_from",
            f"{name}_to",
            f"{name}.from",
            f"{name}.to",
        )
    )
    value = result.get(name)
    if type(value) is not dict or set(value) != {"from", "to"}:
        return None, None, False
    low = _strict_decimal_string(value.get("from"))
    high = _strict_decimal_string(value.get("to"))
    if low is None or high is None or low > high:
        return low, high, False
    if domain == "positive_int":
        valid = (
            low > 0
            and high > 0
            and low == low.to_integral_value()
            and high == high.to_integral_value()
        )
    elif domain == "positive":
        valid = low > 0 and high > 0
    else:
        valid = low >= 0 and high >= 0
    return low, high, valid and not has_flattened_alias


def _strict_result_ranges(
    result: dict[str, Any],
) -> tuple[dict[str, tuple[Decimal | None, Decimal | None]], dict[str, Any], bool]:
    ranges: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    columns: dict[str, Any] = {}
    all_valid = True
    for name, low_col, high_col, domain in _STRICT_RANGE_FIELDS:
        low, high, valid = _strict_range(result, name, domain)
        ranges[name] = (low, high)
        columns[low_col] = float(low) if low is not None else None
        columns[high_col] = float(high) if high is not None else None
        all_valid = all_valid and valid
    return ranges, columns, all_valid


def _strict_requested_values(
    meta: dict[str, Any],
) -> tuple[dict[str, Decimal | None], bool]:
    names = {field for field, _, _ in _STRICT_MEMBERSHIP_FIELDS}
    values = {name: _strict_meta_decimal(meta.get(name)) for name in names}
    init_margin = values["init_margin_requested"]
    cells = values["cell_number_requested"]
    leverage = values["leverage_requested"]
    min_price = values["min_price"]
    max_price = values["max_price"]
    stop_loss = values["stop_loss_price"]
    valid = (
        all(value is not None for value in values.values())
        and init_margin is not None
        and cells is not None
        and cells == cells.to_integral_value()
        and leverage is not None
        and min_price is not None
        and max_price is not None
        and stop_loss is not None
        and stop_loss < min_price < max_price
    )
    return values, valid


def _strict_safe_check_code(value: object) -> str | None:
    if type(value) is str and value == NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE:
        return NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE
    if type(value) is str:
        return "" if value == "" else "***REDACTED***"
    return None


def _strict_safe_error_check_code(value: object) -> str | None:
    if type(value) is not str:
        return None
    if value in {
        NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE,
        "FGRID_CHECK_CODE_REJECTED",
    }:
        return value
    return "" if value == "" else "***REDACTED***"


def _strict_safe_reason_code(value: object) -> str:
    return (
        value
        if type(value) is str and value in _STRICT_ERROR_REASON_CODES
        else "api_error"
    )


def _strict_project_response_data(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        return {}
    projected: dict[str, Any] = {}
    if _exact_int64(value.get("retCode")):
        projected["retCode"] = value["retCode"]
    if _exact_int64(value.get("status_code")):
        projected["status_code"] = value["status_code"]
    if type(value.get("retMsg")) is str:
        projected["retMsg"] = _redacted_message(value["retMsg"], "retMsg")
    result = value.get("result")
    if type(result) is dict:
        projected_result: dict[str, Any] = {}
        if _exact_int64(result.get("status_code")):
            projected_result["status_code"] = result["status_code"]
        if type(result.get("check_code")) is str:
            projected_result["check_code"] = _strict_safe_error_check_code(
                result["check_code"]
            )
        if type(result.get("debug_msg")) is str:
            projected_result["debug_msg"] = _redacted_message(
                result["debug_msg"], "debug_msg"
            )
        if projected_result:
            projected["result"] = projected_result
    return projected


def build_strict_validate_error_evidence(exc: BaseException) -> dict[str, Any]:
    attributes = (
        object.__getattribute__(exc, "__dict__")
        if isinstance(exc, BybitAPIError)
        else {}
    )
    response_data = _strict_project_response_data(attributes.get("response_data"))
    raw_ret_code = response_data.get("retCode", attributes.get("ret_code"))
    raw_ret_msg = response_data.get("retMsg", attributes.get("ret_msg"))
    nested = response_data.get("result")
    raw_debug_msg = (
        nested.get("debug_msg")
        if type(nested) is dict and "debug_msg" in nested
        else attributes.get("debug_msg")
    )
    evidence = {
        "reason_code": _strict_safe_reason_code(attributes.get("reason_code")),
        "http_status_code": (
            attributes.get("status_code")
            if _exact_int64(attributes.get("status_code"))
            else None
        ),
        "retCode": raw_ret_code if _exact_int64(raw_ret_code) else None,
        "retMsg": _redacted_message(raw_ret_msg, "retMsg"),
        "debug_msg": _redacted_message(raw_debug_msg, "debug_msg"),
        "response_data": response_data,
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 1024:
        evidence["response_data"] = {}
    return evidence


def _strict_error_columns(value: object) -> dict[str, Any]:
    evidence = value if type(value) is dict else {}
    safe_evidence = {
        "reason_code": _strict_safe_reason_code(evidence.get("reason_code")),
        "http_status_code": (
            evidence.get("http_status_code")
            if _exact_int64(evidence.get("http_status_code"))
            else None
        ),
        "retCode": (
            evidence.get("retCode") if _exact_int64(evidence.get("retCode")) else None
        ),
        "retMsg": _redacted_message(evidence.get("retMsg"), "retMsg"),
        "debug_msg": _redacted_message(evidence.get("debug_msg"), "debug_msg"),
        "response_data": _strict_project_response_data(evidence.get("response_data")),
    }
    has_evidence = type(value) is dict
    return {
        "error_reason_code": safe_evidence["reason_code"] if has_evidence else None,
        "error_http_status_code": safe_evidence["http_status_code"],
        "error_ret_code": safe_evidence["retCode"],
        "error_ret_msg": safe_evidence["retMsg"],
        "error_debug_msg": safe_evidence["debug_msg"],
        "error_evidence_json": (
            json.dumps(safe_evidence, sort_keys=True, separators=(",", ":"))
            if has_evidence
            else None
        ),
    }


def parse_strict_validate_response(
    meta: dict[str, Any],
    response: dict[str, Any] | object,
    status_code: int | None = None,
    raw_path: str | None = None,
    error_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = response if type(response) is dict else {}
    has_error_evidence = error_evidence is not None
    http_status_valid = status_code is None or (
        _exact_int64(status_code) and status_code == 200
    )
    result_value = payload.get("result")
    result = result_value if type(result_value) is dict else {}
    outer_payload = {key: value for key, value in payload.items() if key != "result"}
    envelope_valid, envelope_success = _native_marker_state(outer_payload)
    envelope_valid = (
        envelope_valid
        and envelope_success
        and _exact_int64(payload.get("retCode"))
        and payload.get("retCode") == 0
        and http_status_valid
        and not has_error_evidence
    )
    result_status = result.get("status_code")
    check_code = result.get("check_code")
    debug_msg = result.get("debug_msg")
    marker_schema_valid = (
        _exact_int64(result_status)
        and type(check_code) is str
        and type(debug_msg) is str
    )
    top_level_debug_valid = "debug_msg" not in payload or (
        type(payload.get("debug_msg")) is str and payload.get("debug_msg") == ""
    )
    ranges, range_columns, ranges_valid = _strict_result_ranges(result)
    result_schema_valid = (
        type(result_value) is dict and marker_schema_valid and ranges_valid
    )
    native_check_success = (
        _exact_int64(result_status)
        and result_status == NATIVE_GRID_VALIDATE_SUCCESS_STATUS_CODE
        and type(check_code) is str
        and check_code == NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE
        and type(debug_msg) is str
        and debug_msg == ""
        and top_level_debug_valid
    )
    validate_ok = envelope_valid and result_schema_valid and native_check_success
    requested, requested_meta_valid = _strict_requested_values(meta)
    membership: dict[str, bool] = {}
    for meta_name, range_name, flag_name in _STRICT_MEMBERSHIP_FIELDS:
        low, high = ranges[range_name]
        value = requested[meta_name]
        membership[flag_name] = bool(
            validate_ok
            and requested_meta_valid
            and value is not None
            and low is not None
            and high is not None
            and low <= value <= high
        )
    requested_inside = all(membership.values())
    target_init_margin = Decimal("5")
    investment_low, investment_high = ranges["investment"]
    target_inside = bool(
        validate_ok
        and requested_meta_valid
        and requested_inside
        and investment_low is not None
        and investment_high is not None
        and investment_low <= target_init_margin <= investment_high
    )
    feasible_bybit = bool(validate_ok and requested_inside)
    feasible_5usdt = bool(feasible_bybit and target_inside)
    if not envelope_valid:
        blocker = "response_envelope_invalid"
    elif not result_schema_valid:
        blocker = "native_result_schema_invalid"
    elif not native_check_success:
        blocker = "native_check_rejected"
    elif not requested_inside:
        blocker = "requested_values_outside_validate_ranges"
    elif not target_inside:
        blocker = "min_investment_gt_5usdt"
    else:
        blocker = None

    last_price = _strict_meta_decimal(meta.get("lastPrice"))
    requested_min = requested.get("min_price")
    requested_max = requested.get("max_price")
    requested_stop = requested.get("stop_loss_price")
    long_liq = _strict_decimal_string(result.get("long_liq_price"))
    short_liq = _strict_decimal_string(result.get("short_liq_price"))

    def pct(num: Decimal | None, den: Decimal | None) -> float | None:
        if num is None or den in (None, Decimal("0")):
            return None
        return float((num / den) * Decimal("100"))

    raw_ret_code = payload.get("retCode")
    raw_native_status_code = payload.get("status_code")
    row = {
        **meta,
        "native_grid_validate_result_contract": NATIVE_GRID_VALIDATE_RESULT_CONTRACT,
        "strict_parser_applied": True,
        "retCode": raw_ret_code if _exact_int64(raw_ret_code) else None,
        "retMsg": _redacted_message(payload.get("retMsg"), "retMsg"),
        "status_code": result_status if _exact_int64(result_status) else None,
        "native_envelope_status_code": (
            raw_native_status_code if _exact_int64(raw_native_status_code) else None
        ),
        "http_status_code": status_code if _exact_int64(status_code) else None,
        "check_code": _strict_safe_check_code(check_code),
        "debug_msg": _redacted_message(debug_msg, "debug_msg"),
        "raw_response_path_redacted": raw_path if type(raw_path) is str else None,
        **range_columns,
        "envelope_valid": bool(envelope_valid),
        "result_schema_valid": bool(result_schema_valid),
        "validate_ok": bool(validate_ok),
        "schema_or_param_rejected": bool(
            not result_schema_valid or (envelope_valid and not native_check_success)
        ),
        **membership,
        "requested_values_inside_validate_ranges": bool(requested_inside),
        "feasible_bybit": feasible_bybit,
        "min_investment_feasible_at_5usdt": feasible_5usdt,
        "feasible_user_5usdt_rule": feasible_5usdt,
        "target_init_margin_usdt": float(target_init_margin),
        "target_init_margin_inside_validate_range": target_inside,
        "long_liq_price": float(long_liq) if long_liq is not None else None,
        "short_liq_price": float(short_liq) if short_liq is not None else None,
        "requested_range_width_pct": pct(
            requested_max - requested_min
            if requested_max is not None and requested_min is not None
            else None,
            requested_min,
        ),
        "requested_stop_loss_distance_from_min_pct": pct(
            requested_min - requested_stop
            if requested_min is not None and requested_stop is not None
            else None,
            requested_min,
        ),
        "requested_stop_loss_distance_from_last_pct": pct(
            last_price - requested_stop
            if last_price is not None and requested_stop is not None
            else None,
            last_price,
        ),
        "long_liq_distance_from_last_pct": pct(
            last_price - long_liq
            if last_price is not None and long_liq is not None
            else None,
            last_price,
        ),
        "short_liq_distance_from_last_pct": pct(
            short_liq - last_price
            if last_price is not None and short_liq is not None
            else None,
            last_price,
        ),
        "blocker_reason": blocker,
        **_strict_error_columns(error_evidence),
    }
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


def _strict_record_rows(df: pl.DataFrame) -> pl.DataFrame:
    bool_columns = {
        *_STRICT_SELECTOR_BOOL_COLUMNS,
        "schema_or_param_rejected",
        "target_init_margin_inside_validate_range",
        "min_investment_feasible_at_5usdt",
        "feasible_user_5usdt_rule",
    }
    range_columns = {
        column
        for _, low_column, high_column, _ in _STRICT_RANGE_FIELDS
        for column in (low_column, high_column)
    }
    required = {
        *CANDIDATE_KEY_COLUMNS,
        *bool_columns,
        *range_columns,
        "native_grid_validate_result_contract",
        "status_code",
        "check_code",
        "blocker_reason",
        "error_reason_code",
        "error_http_status_code",
        "error_ret_code",
        "error_ret_msg",
        "error_debug_msg",
        "error_evidence_json",
        "stop_loss_price",
        "target_init_margin_usdt",
    }
    if df.is_empty() or not required.issubset(df.columns):
        return df.head(0)
    if df.schema["native_grid_validate_result_contract"] != pl.String or any(
        df.schema[column] != pl.Boolean for column in bool_columns
    ):
        return df.head(0)
    return df.filter(
        (
            pl.col("native_grid_validate_result_contract")
            == NATIVE_GRID_VALIDATE_RESULT_CONTRACT
        )
        & pl.col("strict_parser_applied").eq(True).fill_null(False)
        & pl.all_horizontal([pl.col(column).is_not_null() for column in bool_columns])
        & pl.all_horizontal(
            [
                pl.col(column).is_not_null()
                for column in (
                    *CANDIDATE_KEY_COLUMNS,
                    "stop_loss_price",
                    "target_init_margin_usdt",
                )
            ]
        )
    )


def strict_constraint_records(df: pl.DataFrame) -> pl.DataFrame:
    return _strict_record_rows(df)


def strict_existing_keys(path: Path) -> set[tuple[Any, ...]]:
    if not path.exists():
        return set()
    df = _strict_record_rows(pl.read_parquet(path))
    required = {
        *CANDIDATE_KEY_COLUMNS,
        "envelope_valid",
        "result_schema_valid",
        "validate_ok",
        "error_reason_code",
    }
    if df.is_empty() or not required.issubset(df.columns):
        return set()
    if (
        df.schema["envelope_valid"] != pl.Boolean
        or df.schema["result_schema_valid"] != pl.Boolean
    ):
        return set()
    trusted = df.filter(
        pl.col("envelope_valid").eq(True).fill_null(False)
        & pl.col("result_schema_valid").eq(True).fill_null(False)
        & pl.col("validate_ok").eq(True).fill_null(False)
        & pl.col("error_reason_code").is_null()
        & pl.all_horizontal(
            [pl.col(column).is_not_null() for column in CANDIDATE_KEY_COLUMNS]
        )
    )
    return {
        tuple(row.get(column) for column in CANDIDATE_KEY_COLUMNS)
        for row in trusted.select(CANDIDATE_KEY_COLUMNS).to_dicts()
    }


def prepare_strict_constraints(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    strict = _strict_record_rows(pl.read_parquet(path))
    if strict.is_empty():
        path.unlink()
    else:
        strict.write_parquet(path)
    return strict


def append_strict_constraints(path: Path, rows: list[dict[str, Any]]) -> pl.DataFrame:
    invalid = [
        row
        for row in rows
        if type(row) is not dict
        or row.get("native_grid_validate_result_contract")
        != NATIVE_GRID_VALIDATE_RESULT_CONTRACT
        or row.get("strict_parser_applied") is not True
    ]
    if invalid:
        raise ValueError("strict validate rows require the exact result contract")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        _strict_record_rows(pl.read_parquet(path)) if path.exists() else pl.DataFrame()
    )
    incoming = pl.DataFrame(rows) if rows else pl.DataFrame()
    if (
        not incoming.is_empty()
        and _strict_record_rows(incoming).height != incoming.height
    ):
        raise ValueError("strict validate rows require the complete parser schema")
    if existing.is_empty():
        df = incoming
    elif incoming.is_empty():
        df = existing
    else:
        df = pl.concat([existing, incoming], how="diagonal_relaxed")
    if not df.is_empty():
        for column in CANDIDATE_KEY_COLUMNS:
            if column not in df.columns:
                df = df.with_columns(pl.lit(None).alias(column))
        df = df.unique(CANDIDATE_KEY_COLUMNS, keep="last")
        df.write_parquet(path)
    elif path.exists():
        path.unlink()
    return df


def strict_feasible_constraints(
    df: pl.DataFrame, require_5usdt: bool = True
) -> pl.DataFrame:
    df = _strict_record_rows(df)
    bool_columns = list(_STRICT_SELECTOR_BOOL_COLUMNS)
    if require_5usdt:
        bool_columns.extend(
            [
                "target_init_margin_inside_validate_range",
                "min_investment_feasible_at_5usdt",
                "feasible_user_5usdt_rule",
            ]
        )
    required = {
        "native_grid_validate_result_contract",
        "status_code",
        "check_code",
        "blocker_reason",
        "error_reason_code",
        *bool_columns,
    }
    if df.is_empty() or not required.issubset(df.columns):
        return df.head(0)
    if any(df.schema[column] != pl.Boolean for column in bool_columns):
        return df.head(0)
    if (
        df.schema["native_grid_validate_result_contract"] != pl.String
        or df.schema["check_code"] != pl.String
        or str(df.schema["status_code"])
        not in {
            "Int8",
            "Int16",
            "Int32",
            "Int64",
            "UInt8",
            "UInt16",
            "UInt32",
            "UInt64",
        }
    ):
        return df.head(0)
    predicate = (
        (
            pl.col("native_grid_validate_result_contract")
            == NATIVE_GRID_VALIDATE_RESULT_CONTRACT
        )
        & (pl.col("status_code") == NATIVE_GRID_VALIDATE_SUCCESS_STATUS_CODE)
        & (pl.col("check_code") == NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE)
        & pl.col("blocker_reason").is_null()
        & pl.col("error_reason_code").is_null()
    )
    for column in bool_columns:
        predicate = predicate & pl.col(column).eq(True)
    return df.filter(predicate.fill_null(False))


def write_redacted_response(path: Path, response: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact(response), indent=2, sort_keys=True), encoding="utf-8"
    )
