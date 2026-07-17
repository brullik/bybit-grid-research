from __future__ import annotations

from typing import Any

from bybit_grid.logging import redact


STRICT_API_RESPONSE_ENVELOPE_CONTRACT = "strict-envelope-v1"
REDACTED = "***REDACTED***"
_REASON_CODES = {
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
_INT64_MIN = -(2**63)
_INT64_MAX = (2**63) - 1
_RETRY_CODE_UNSET = object()


def _exact_int64(value: object) -> bool:
    return type(value) is int and _INT64_MIN <= value <= _INT64_MAX


def _safe_text(value: object, label: str) -> str | None:
    if type(value) is not str:
        return None
    if value == "":
        return ""
    safe = redact({label: value})
    if type(safe) is dict and type(safe.get(label)) is str:
        return safe[label]
    return REDACTED


def _safe_endpoint(value: object) -> str:
    if type(value) is not str:
        return "<invalid-endpoint>"
    safe = redact(value)
    return safe if type(safe) is str else "<invalid-endpoint>"


class BybitAPIError(RuntimeError):
    def __init__(
        self,
        endpoint: str,
        status_code: int | None,
        ret_code: int | None,
        ret_msg: str | None,
        debug_msg: str | None = None,
        response_data: dict[str, Any] | None = None,
        reason_code: str = "api_error",
        retry_ret_code: int | None | object = _RETRY_CODE_UNSET,
    ):
        safe_endpoint = _safe_endpoint(endpoint)
        safe_status = status_code if _exact_int64(status_code) else None
        safe_ret_code = ret_code if _exact_int64(ret_code) else None
        safe_reason = (
            reason_code
            if type(reason_code) is str and reason_code in _REASON_CODES
            else "api_error"
        )
        safe_retry_ret_code = (
            safe_ret_code
            if retry_ret_code is _RETRY_CODE_UNSET
            else retry_ret_code
            if _exact_int64(retry_ret_code)
            else None
        )
        safe_ret_msg = _safe_text(ret_msg, "retMsg")
        safe_debug_msg = _safe_text(debug_msg, "debug_msg")
        response_without_rate_headers = (
            {
                key: value
                for key, value in response_data.items()
                if not (type(key) is str and key == "rate_limit_headers")
            }
            if type(response_data) is dict
            else {}
        )
        try:
            safe_response = redact(response_without_rate_headers)
        except RecursionError:
            safe_response = {}
        if type(safe_response) is not dict:
            safe_response = {}

        super().__init__(
            "Bybit API error "
            f"endpoint={safe_endpoint} status_code={safe_status} "
            f"retCode={safe_ret_code} reason={safe_reason}"
        )
        self.endpoint = safe_endpoint
        self.status_code = safe_status
        self.ret_code = safe_ret_code
        self.retry_ret_code = safe_retry_ret_code
        self.ret_msg = safe_ret_msg
        self.debug_msg = safe_debug_msg
        self.response_data = safe_response
        self.reason_code = safe_reason


class BybitResponseEnvelopeError(BybitAPIError):
    def __init__(
        self,
        endpoint: str,
        status_code: int | None,
        reason_code: str,
    ):
        super().__init__(
            endpoint=endpoint,
            status_code=status_code,
            ret_code=None,
            ret_msg=None,
            debug_msg=None,
            response_data=None,
            reason_code=reason_code,
            retry_ret_code=None,
        )
