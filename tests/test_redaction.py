from bybit_grid.logging import redact


def test_redacts_secret_signature_and_key():
    data = redact(
        {
            "api_key": "abc",
            "api_secret": "def",
            "nested": {"signature": "sig"},
            "msg": "X-BAPI-SIGN: hello secret=world",
        }
    )
    assert data["api_key"] == "***REDACTED***"
    assert data["api_secret"] == "***REDACTED***"
    assert data["nested"]["signature"] == "***REDACTED***"
    assert "hello" not in data["msg"] and "world" not in data["msg"]
