from __future__ import annotations

from decimal import Decimal as _Decimal
from decimal import InvalidOperation as _InvalidOperation

from bybit_grid.config import Settings as _Settings


__all__ = (
    "CANONICAL_BYBIT_ENV",
    "CANONICAL_BYBIT_API_BASE_URL",
    "CANONICAL_PRIVATE_GET_ENDPOINTS",
    "CANONICAL_FGRID_VALIDATE_ENDPOINT",
    "CANONICAL_FGRID_GRID_MODE_NEUTRAL",
    "CANONICAL_FGRID_GRID_TYPE_GEOMETRIC",
    "ValidateOnlyBoundaryError",
    "enforce_validate_only_settings",
    "enforce_private_get_request",
    "enforce_validate_only_payload",
)

CANONICAL_BYBIT_ENV = "mainnet"
CANONICAL_BYBIT_API_BASE_URL = "https://api.bybit.com"
CANONICAL_PRIVATE_GET_ENDPOINTS = (
    "/v5/account/info",
    "/v5/account/wallet-balance",
    "/v5/account/fee-rate",
)
CANONICAL_FGRID_VALIDATE_ENDPOINT = "/v5/fgridbot/validate"
CANONICAL_FGRID_GRID_MODE_NEUTRAL = 1
CANONICAL_FGRID_GRID_TYPE_GEOMETRIC = 2

_LOCKED_BYBIT_ENV = CANONICAL_BYBIT_ENV
_LOCKED_BYBIT_API_BASE_URL = CANONICAL_BYBIT_API_BASE_URL
_LOCKED_PRIVATE_GET_ENDPOINTS = CANONICAL_PRIVATE_GET_ENDPOINTS
_LOCKED_FGRID_VALIDATE_ENDPOINT = CANONICAL_FGRID_VALIDATE_ENDPOINT
_LOCKED_FGRID_GRID_MODE_NEUTRAL = CANONICAL_FGRID_GRID_MODE_NEUTRAL
_LOCKED_FGRID_GRID_TYPE_GEOMETRIC = CANONICAL_FGRID_GRID_TYPE_GEOMETRIC

_VALIDATE_PAYLOAD_KEYS = {
    "symbol",
    "leverage",
    "grid_mode",
    "grid_type",
    "min_price",
    "max_price",
    "cell_number",
    "init_margin",
    "stop_loss_price",
}
_DECIMAL_FIELDS = (
    "leverage",
    "min_price",
    "max_price",
    "init_margin",
    "stop_loss_price",
)


class ValidateOnlyBoundaryError(PermissionError):
    pass


def _fail(code: str) -> None:
    raise ValidateOnlyBoundaryError(code)


def _is_ascii_upper_alnum(value: object) -> bool:
    return type(value) is str and value.isascii() and all(
        "A" <= character <= "Z" or "0" <= character <= "9" for character in value
    )


def _symbol_is_canonical(value: object) -> bool:
    return (
        _is_ascii_upper_alnum(value)
        and 2 <= len(value) <= 32
        and value.endswith("USDT")
    )


def _canonical_positive_decimal(value: object) -> _Decimal | None:
    if type(value) is not str or not value or not value.isascii():
        return None
    if value.count(".") > 1:
        return None
    if "." in value:
        integer_part, fractional_part = value.split(".", 1)
        if not fractional_part or fractional_part[-1] == "0":
            return None
        if not fractional_part.isdecimal():
            return None
    else:
        integer_part = value
    if not integer_part or not integer_part.isdecimal():
        return None
    if len(integer_part) > 1 and integer_part[0] == "0":
        return None
    try:
        parsed = _Decimal(value)
    except _InvalidOperation:
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def enforce_validate_only_settings(*, settings):
    if type(settings) is not _Settings:
        _fail("validate_settings_not_exact")
    if type(settings.bybit_env) is not str or settings.bybit_env != _LOCKED_BYBIT_ENV:
        _fail("validate_environment_forbidden")
    if (
        type(settings.bybit_api_base_url) is not str
        or settings.bybit_api_base_url != _LOCKED_BYBIT_API_BASE_URL
    ):
        _fail("validate_api_base_url_forbidden")
    if (
        type(settings.bybit_fgrid_validate_path) is not str
        or settings.bybit_fgrid_validate_path != _LOCKED_FGRID_VALIDATE_ENDPOINT
    ):
        _fail("validate_endpoint_forbidden")
    if (
        type(settings.bybit_fgrid_grid_mode_neutral) is not int
        or settings.bybit_fgrid_grid_mode_neutral != _LOCKED_FGRID_GRID_MODE_NEUTRAL
    ):
        _fail("validate_grid_mode_forbidden")
    if (
        type(settings.bybit_fgrid_grid_type_geometric) is not int
        or settings.bybit_fgrid_grid_type_geometric != _LOCKED_FGRID_GRID_TYPE_GEOMETRIC
    ):
        _fail("validate_grid_type_forbidden")
    if type(settings.bybit_recv_window) is not int or settings.bybit_recv_window != 5000:
        _fail("validate_recv_window_forbidden")
    if type(settings.grid_validate_enabled) is not bool:
        _fail("validate_enabled_flag_invalid")
    if (
        type(settings.live_trading_enabled) is not bool
        or settings.live_trading_enabled is not False
        or type(settings.allow_live_trading) is not str
        or settings.allow_live_trading != "NO"
    ):
        _fail("validate_live_authority_forbidden")
    return None


def enforce_private_get_request(*, endpoint, params):
    if type(endpoint) is not str or endpoint not in _LOCKED_PRIVATE_GET_ENDPOINTS:
        _fail("private_get_endpoint_forbidden")
    if type(params) is not dict:
        _fail("private_get_params_forbidden")
    if any(type(key) is not str or type(value) is not str for key, value in params.items()):
        _fail("private_get_params_forbidden")
    if endpoint == "/v5/account/info":
        if params != {}:
            _fail("private_get_params_forbidden")
    elif endpoint == "/v5/account/wallet-balance":
        if params != {"accountType": "UNIFIED"}:
            _fail("private_get_params_forbidden")
    else:
        if set(params) not in ({"category"}, {"category", "symbol"}):
            _fail("private_get_params_forbidden")
        if params.get("category") != "linear":
            _fail("private_get_params_forbidden")
        if "symbol" in params and not _symbol_is_canonical(params["symbol"]):
            _fail("private_get_params_forbidden")
    return None


def enforce_validate_only_payload(*, payload):
    if type(payload) is not dict:
        _fail("validate_payload_not_exact_dict")
    if any(type(key) is not str for key in payload) or set(payload) != _VALIDATE_PAYLOAD_KEYS:
        _fail("validate_payload_keys_invalid")
    if not _symbol_is_canonical(payload["symbol"]):
        _fail("validate_payload_symbol_forbidden")
    decimal_values = {}
    for field_name in _DECIMAL_FIELDS:
        parsed = _canonical_positive_decimal(payload[field_name])
        if parsed is None:
            _fail("validate_payload_decimal_forbidden")
        decimal_values[field_name] = parsed
    if (
        type(payload["grid_mode"]) is not int
        or payload["grid_mode"] != _LOCKED_FGRID_GRID_MODE_NEUTRAL
    ):
        _fail("validate_payload_grid_mode_forbidden")
    if (
        type(payload["grid_type"]) is not int
        or payload["grid_type"] != _LOCKED_FGRID_GRID_TYPE_GEOMETRIC
    ):
        _fail("validate_payload_grid_type_forbidden")
    if (
        type(payload["cell_number"]) is not int
        or not 2 <= payload["cell_number"] <= 100
    ):
        _fail("validate_payload_cell_number_forbidden")
    if not (
        0
        < decimal_values["stop_loss_price"]
        < decimal_values["min_price"]
        < decimal_values["max_price"]
    ):
        _fail("validate_payload_geometry_forbidden")
    return None
