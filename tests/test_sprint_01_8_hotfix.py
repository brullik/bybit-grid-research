import json
from pathlib import Path

import httpx
import pytest

from bybit_grid.bybit.client import BybitClient, _is_retryable
from bybit_grid.bybit.models import BybitAPIError, BybitResponseEnvelopeError
from bybit_grid.config import Settings
from scripts.smoke_private_account import (
    SENSITIVE_WALLET_AMOUNT_KEYS,
    _status,
    sanitize_private_account_snapshot,
)
from scripts.validate_sample_grid import static_payload


STRICT_API_RESPONSE_ENVELOPE_TEST_CONTRACT = "strict-envelope-v1"


def _response(payload: dict, http_status: int = 200) -> httpx.Response:
    return httpx.Response(http_status, json=payload)


def _client() -> BybitClient:
    return BybitClient(Settings())


def test_handle_response_standard_v5_success_retcode_zero_passes():
    client = _client()
    try:
        payload = {"retCode": 0, "retMsg": "OK", "result": {"ok": True}}
        assert (
            client._handle_response("/v5/test", _response(payload), "test") == payload
        )
    finally:
        client.close()


def test_handle_response_standard_v5_error_retcode_10001_raises():
    client = _client()
    try:
        payload = {"retCode": 10001, "retMsg": "parameter error", "result": {}}
        with pytest.raises(BybitAPIError) as exc_info:
            client._handle_response("/v5/test", _response(payload), "test")
        assert exc_info.value.ret_code == 10001
        assert exc_info.value.response_data["retMsg"] == "***REDACTED***"
        assert "parameter error" not in str(exc_info.value)
        assert not _is_retryable(exc_info.value)
    finally:
        client.close()


def test_handle_validate_response_status_code_200_passes():
    client = _client()
    try:
        payload = {"status_code": 200, "debug_msg": "", "result": {"ok": True}}
        assert (
            client._handle_validate_response(
                "/v5/fgridbot/validate", _response(payload), "test"
            )
            == payload
        )
    finally:
        client.close()


def test_handle_validate_response_status_code_400_raises():
    client = _client()
    try:
        payload = {"status_code": 400, "debug_msg": "bad request", "result": {}}
        with pytest.raises(BybitAPIError) as exc_info:
            client._handle_validate_response(
                "/v5/fgridbot/validate",
                _response(payload, http_status=400),
                "test",
            )
        assert exc_info.value.ret_code == 400
        assert exc_info.value.response_data["debug_msg"] == "***REDACTED***"
        assert not _is_retryable(exc_info.value)
    finally:
        client.close()


def test_handle_validate_response_error_with_http_200_raises():
    client = _client()
    try:
        payload = {"status_code": 400, "debug_msg": "schema rejected", "result": {}}
        with pytest.raises(BybitAPIError) as exc_info:
            client._handle_validate_response(
                "/v5/fgridbot/validate", _response(payload), "test"
            )
        assert exc_info.value.ret_code == 400
        assert exc_info.value.response_data["debug_msg"] == "***REDACTED***"
        assert not _is_retryable(exc_info.value)
    finally:
        client.close()


def test_retryable_retcode_10006_is_classified_retryable():
    client = _client()
    try:
        payload = {"retCode": 10006, "retMsg": "too many visits", "result": {}}
        with pytest.raises(BybitAPIError) as exc_info:
            client._handle_response("/v5/test", _response(payload), "test")
        assert _is_retryable(exc_info.value)
    finally:
        client.close()


def test_string_retcode_and_http_2xx_without_marker_fail_closed():
    client = _client()
    try:
        for payload, reason in [
            ({"retCode": "10006"}, "response_marker_type_invalid"),
            ({}, "response_marker_missing"),
            ({"status_code": 200}, "response_marker_alias_forbidden"),
        ]:
            with pytest.raises(BybitResponseEnvelopeError) as exc_info:
                client._handle_response("/v5/test", _response(payload), "test")
            assert exc_info.value.reason_code == reason
            assert not _is_retryable(exc_info.value)
    finally:
        client.close()


def test_private_account_status_requires_explicit_exact_success_marker():
    assert _status(None) == "not-run"
    assert _status({"retCode": 0}) == "ok"
    for value in (
        {},
        {"retCode": None},
        {"retCode": "0"},
        {"retCode": True},
        {"retCode": 0, "status_code": 400},
        {"retCode": 0, "retMsg": None},
        {"retCode": 0, "debug_msg": []},
        [],
    ):
        assert _status(value) == "error"


def test_private_account_snapshot_redacts_sensitive_wallet_amount_keys(tmp_path: Path):
    raw_info = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "unifiedMarginStatus": 5,
            "marginMode": "REGULAR_MARGIN",
            "dcpStatus": "OFF",
            "smpGroup": 0,
            "spotHedgingStatus": "OFF",
            "totalEquity": "12345.67",
        },
    }
    raw_wallet = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                {
                    "accountType": "UNIFIED",
                    "totalEquity": "12345.67",
                    "totalWalletBalance": "12345.67",
                    "coin": [
                        {
                            "coin": "USDT",
                            "walletBalance": "1000",
                            "equity": "1000",
                            "usdValue": "1000",
                            "cumRealisedPnl": "1",
                            "unrealisedPnl": "2",
                        }
                    ],
                }
            ]
        },
    }
    sanitized = sanitize_private_account_snapshot(raw_info, raw_wallet)
    out = tmp_path / "account_info_redacted.json"
    out.write_text(json.dumps(sanitized), encoding="utf-8")
    saved = out.read_text(encoding="utf-8")
    assert sanitized["wallet_balance"] == {
        "retCode": 0,
        "retMsg": "OK",
        "accountType": "UNIFIED",
        "coin_count": 1,
        "coins": ["USDT"],
        "balance_values_redacted": True,
    }
    for key in SENSITIVE_WALLET_AMOUNT_KEYS:
        assert key not in saved


def test_static_dry_run_payload_uses_new_fgrid_validate_schema_only():
    payload = static_payload("BTCUSDT", "1", 10, "100")
    assert {
        "symbol",
        "leverage",
        "grid_mode",
        "grid_type",
        "min_price",
        "max_price",
        "cell_number",
        "init_margin",
        "stop_loss_price",
    } <= payload.keys()
    assert (
        not {
            "lowerPrice",
            "upperPrice",
            "gridNum",
            "investment",
            "sampleOnly",
            "category",
        }
        & payload.keys()
    )
