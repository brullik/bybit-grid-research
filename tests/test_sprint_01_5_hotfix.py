import json

import httpx
import polars as pl

from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import Settings
from bybit_grid.data.mark_klines import normalize_mark_kline_rows
from bybit_grid.data.quality import build_quality_report, detect_1m_gaps
from bybit_grid.logging import redact


def _settings():
    return Settings(
        bybit_api_key="key", bybit_api_secret="secret", bybit_api_base_url="https://example.test"
    )


def test_private_get_signs_same_query_string_sent(monkeypatch):
    client = BybitClient(_settings())
    captured = {}

    def fake_get(url, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    monkeypatch.setattr(client.http, "get", fake_get)
    client.private_get("/v5/private", {"b": 2, "a": 1})
    assert captured["url"] == "/v5/private?a=1&b=2"
    assert captured["params"] is None
    client.close()


def test_private_post_signs_exact_body_sent(monkeypatch):
    client = BybitClient(_settings())
    captured = {}

    def fake_post(url, content=None, headers=None):
        captured.update({"url": url, "content": content, "headers": headers})
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    monkeypatch.setattr(client.http, "post", fake_post)
    body = {"symbol": "BTCUSDT", "note": "тест", "gridNum": 10}
    client.private_post("/v5/fgridbot/validate", body)
    expected = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    assert captured["content"] == expected
    assert captured["headers"]["Content-Type"] == "application/json"
    client.close()


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
# RED probe only: no behavior
