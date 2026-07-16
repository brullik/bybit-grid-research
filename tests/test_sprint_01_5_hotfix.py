import ast
import json
from pathlib import Path

import httpx
import polars as pl
import pytest

import bybit_grid.bybit.client as client_api
from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.validate_only import (
    CANONICAL_FGRID_VALIDATE_ENDPOINT,
    ValidateOnlyBoundaryError,
)
from bybit_grid.config import Settings
from bybit_grid.common import source_safety_audit as safety_audit_api
from bybit_grid.data.mark_klines import normalize_mark_kline_rows
from bybit_grid.data.quality import build_quality_report, detect_1m_gaps
from bybit_grid.logging import redact


def _settings():
    return Settings(
        _env_file=None,
        bybit_env="mainnet",
        bybit_api_base_url="https://api.bybit.com",
        bybit_api_key="key",
        bybit_api_secret="secret",
        bybit_recv_window=5000,
        grid_validate_enabled=True,
        live_trading_enabled=False,
        allow_live_trading="NO",
    )


def _validate_payload():
    return {
        "symbol": "BTCUSDT",
        "leverage": "1",
        "grid_mode": 1,
        "grid_type": 2,
        "min_price": "58500",
        "max_price": "71500",
        "cell_number": 10,
        "init_margin": "100",
        "stop_loss_price": "55250",
    }


def test_private_get_signs_same_query_string_sent(monkeypatch):
    client = BybitClient(_settings())
    captured = {}

    def fake_sign(secret, target):
        captured["secret"] = secret
        captured["signing_target"] = target
        return "signature"

    def fake_get(url, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    monkeypatch.setattr(client_api, "sign_v5", fake_sign)
    monkeypatch.setattr(client.private_http, "get", fake_get)
    client.private_get(
        "/v5/account/fee-rate",
        {"symbol": "BTCUSDT", "category": "linear"},
    )
    exact_query = "category=linear&symbol=BTCUSDT"
    assert captured["url"] == f"/v5/account/fee-rate?{exact_query}"
    assert captured["params"] is None
    assert captured["secret"] == "secret"
    assert captured["signing_target"].endswith(exact_query)
    client.close()


def test_private_post_is_exact_refusal_without_transport(monkeypatch):
    client = BybitClient(_settings())
    called = False

    def fake_post(url, content=None, headers=None):
        nonlocal called
        called = True
        raise AssertionError("private transport must not be reached")

    monkeypatch.setattr(client.private_http, "post", fake_post)
    with pytest.raises(
        ValidateOnlyBoundaryError,
        match="^generic_private_post_forbidden$",
    ):
        client.private_post(CANONICAL_FGRID_VALIDATE_ENDPOINT, _validate_payload())
    assert called is False
    client.close()


def test_validate_grid_bot_signs_exact_body_sent(monkeypatch):
    client = BybitClient(_settings())
    captured = {}

    def fake_sign(secret, target):
        captured["secret"] = secret
        captured["signing_target"] = target
        return "signature"

    def fake_post(url, content=None, headers=None):
        captured.update({"url": url, "content": content, "headers": headers})
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    monkeypatch.setattr(client_api, "sign_v5", fake_sign)
    monkeypatch.setattr(client.private_http, "post", fake_post)
    body = _validate_payload()
    client.validate_grid_bot(body)
    expected = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    assert captured["url"] == CANONICAL_FGRID_VALIDATE_ENDPOINT
    assert captured["content"] == expected
    assert captured["secret"] == "secret"
    assert captured["signing_target"].endswith(captured["content"])
    assert captured["headers"]["Content-Type"] == "application/json"
    client.close()


def test_prepared_private_helpers_allow_one_retry_invocation(monkeypatch):
    client = BybitClient(_settings())
    calls = {"get": 0, "post": 0}
    monkeypatch.setattr(client_api, "sign_v5", lambda secret, target: "signature")

    def fake_get(url, params=None, headers=None):
        calls["get"] += 1
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    def fake_post(url, content=None, headers=None):
        calls["post"] += 1
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    monkeypatch.setattr(client.private_http, "get", fake_get)
    monkeypatch.setattr(client.private_http, "post", fake_post)

    decorated_get = client._private_get

    def invoke_get_once(prepared):
        result = decorated_get(prepared)
        with pytest.raises(
            ValidateOnlyBoundaryError,
            match="^private_get_prepared_request_invalid$",
        ):
            decorated_get(prepared)
        with pytest.raises(
            ValidateOnlyBoundaryError,
            match="^private_get_prepared_request_invalid$",
        ):
            BybitClient._private_get.__wrapped__(client, prepared)
        return result

    monkeypatch.setattr(client, "_private_get", invoke_get_once)
    client.private_get("/v5/account/info")
    assert calls["get"] == 1

    decorated_post = client._private_validate_post

    def invoke_post_once(prepared):
        result = decorated_post(prepared)
        with pytest.raises(
            ValidateOnlyBoundaryError,
            match="^validate_prepared_request_invalid$",
        ):
            decorated_post(prepared)
        with pytest.raises(
            ValidateOnlyBoundaryError,
            match="^validate_prepared_request_invalid$",
        ):
            BybitClient._private_validate_post.__wrapped__(client, prepared)
        return result

    monkeypatch.setattr(client, "_private_validate_post", invoke_post_once)
    client.validate_grid_bot(_validate_payload())
    assert calls["post"] == 1
    client.close()


def test_source_audit_rejects_structural_transport_and_preflight_variants():
    client_source = """
class BybitClient:
    def _private_validate_post(self, prepared):
        return self.private_http.post(
            CANONICAL_FGRID_VALIDATE_ENDPOINT,
            json=prepared,
        )

    def create_grid_bot(self):
        raise NotImplementedError()

    def close_grid_bot(self):
        raise NotImplementedError()
"""
    client_violations = safety_audit_api._audit_tree(
        Path("src/bybit_grid/bybit/client.py"),
        ast.parse(client_source),
    )
    assert any(
        "canonical validate transport shape is required" in item
        for item in client_violations
    )

    early_path_source = """
def _validate_symbol(settings):
    return BybitClient(settings)

def main():
    output = Path("report.json")
    settings = load_settings()
    enforce_validate_only_settings(settings=settings)
    return output
"""
    early_path_violations = safety_audit_api._audit_tree(
        Path("scripts/validate_universe_fgrid_constraints.py"),
        ast.parse(early_path_source),
    )
    assert any(
        "validate universe policy preflight must precede credentials and threads"
        in item
        for item in early_path_violations
    )

    nested_reload_source = """
def _validate_symbol(settings):
    reload_later = lambda: load_settings()
    return BybitClient(settings), reload_later()

def main():
    settings = load_settings()
    enforce_validate_only_settings(settings=settings)
"""
    nested_reload_violations = safety_audit_api._audit_tree(
        Path("scripts/validate_universe_fgrid_constraints.py"),
        ast.parse(nested_reload_source),
    )
    assert any(
        "validate universe workers must use preflighted settings" in item
        for item in nested_reload_violations
    )

    missing_structure_violations = safety_audit_api._audit_tree(
        Path("scripts/validate_universe_fgrid_constraints.py"),
        ast.parse("VALUE = 1\n"),
    )
    assert any(
        "validate universe policy preflight must precede credentials and threads"
        in item
        for item in missing_structure_violations
    )
    assert any(
        "validate universe workers must use preflighted settings" in item
        for item in missing_structure_violations
    )


def test_mark_price_kline_5_fields_nullable_volume_turnover():
    df = normalize_mark_kline_rows([["60000", "1", "2", "0.5", "1.5"]], "BTCUSDT", "linear")
    assert df["source"][0] == "mark-price-kline"
    assert df["volume"][0] is None
    assert df["turnover"][0] is None


def test_quality_boundary_duplicate_and_bad_ohlc():
    df = pl.DataFrame(
        {
            "symbol": ["BTCUSDT", "BTCUSDT", "BTCUSDT", "BTCUSDT"],
            "open_time_ms": [60_000, 180_000, 180_000, 240_000],
            "source": ["kline", "kline", "kline", "kline"],
            "open": [1.0, 1.0, 1.0, 5.0],
            "high": [2.0, 2.0, 2.0, 4.0],
            "low": [0.5, 0.5, 0.5, 3.0],
            "close": [1.5, 1.5, 1.5, 4.5],
        }
    )
    gaps = detect_1m_gaps(df, expected_start_ms=0, expected_end_ms=300_000)
    assert set(gaps["gap_type"].to_list()) == {"start_boundary", "internal", "end_boundary"}
    report = build_quality_report(df, 0, 300_000)
    assert report["duplicate_count"] == 1
    assert report["bad_ohlc_count"] == 1


def test_redaction_covers_headers_and_raw_strings():
    data = redact(
        {
            "headers": {"X-BAPI-API-KEY": "abc", "X-BAPI-SIGN": "sig", "X-BAPI-TIMESTAMP": "123"},
            "apiKey": "k",
            "apiSecret": "s",
            "api-key": "ak",
            "api-secret": "as",
            "raw": "X-BAPI-API-KEY: abc X-BAPI-SIGN: sig apiSecret=secret",
        }
    )
    assert data["headers"]["X-BAPI-API-KEY"] == "***REDACTED***"
    assert data["headers"]["X-BAPI-SIGN"] == "***REDACTED***"
    assert data["headers"]["X-BAPI-TIMESTAMP"] == "123"
    assert data["apiKey"] == "***REDACTED***"
    assert data["apiSecret"] == "***REDACTED***"
    assert "abc" not in data["raw"] and "sig" not in data["raw"] and "secret" not in data["raw"]
