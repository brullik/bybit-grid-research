from decimal import Decimal

import pytest

from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload
from bybit_grid.config import Settings
from bybit_grid.live.execution_engine import ExecutionEngine
from bybit_grid.logging import redact
from scripts.validate_sample_grid import _refusal_reason


def test_fgrid_validate_payload_has_new_schema_not_old_fields():
    payload = build_fgrid_validate_payload("BTCUSDT", Decimal("65000"), Decimal("0.1"))
    assert {"symbol", "leverage", "grid_mode", "grid_type", "min_price", "max_price", "cell_number", "init_margin", "stop_loss_price"} <= payload.keys()
    assert not {"category", "lowerPrice", "upperPrice", "gridNum", "investment", "sampleOnly"} & payload.keys()


def test_fgrid_rounding_respects_tick_size():
    payload = build_fgrid_validate_payload(
        "BTCUSDT", Decimal("101.03"), Decimal("0.5"), lower_mult=Decimal("0.90"), upper_mult=Decimal("1.10"), stop_loss_mult=Decimal("0.85")
    )
    assert payload["min_price"] == "90.5"
    assert payload["max_price"] == "111.5"
    assert payload["stop_loss_price"] == "85.5"


def test_dynamic_payload_rejects_invalid_min_max():
    with pytest.raises(ValueError, match="lower_mult"):
        build_fgrid_validate_payload("BTCUSDT", Decimal("100"), Decimal("0.1"), lower_mult=Decimal("1.1"), upper_mult=Decimal("0.9"))


def test_non_dry_run_refuses_when_grid_validate_disabled():
    settings = Settings(grid_validate_enabled=False, bybit_api_key="k", bybit_api_secret="s")
    assert _refusal_reason(settings) == "GRID_VALIDATE_ENABLED is false"


def test_create_close_remain_not_implemented_when_guard_allows():
    settings = Settings(live_trading_enabled=True, allow_live_trading="YES")
    client = BybitClient(settings)
    engine = ExecutionEngine(settings)
    with pytest.raises(NotImplementedError):
        client.create_grid_bot(runtime_live=True)
    with pytest.raises(NotImplementedError):
        client.close_grid_bot(runtime_live=True)
    with pytest.raises(NotImplementedError):
        engine.create_grid_bot(runtime_live=True)
    with pytest.raises(NotImplementedError):
        engine.close_grid_bot(runtime_live=True)
    client.close()


def test_redaction_covers_payload_response_headers_and_secret_like_keys():
    data = redact({"headers": {"X-BAPI-API-KEY": "key", "X-BAPI-SIGN": "sig"}, "payload": {"apiSecret": "secret"}, "response": {"signature": "signature", "secret": "hidden"}})
    assert data["headers"]["X-BAPI-API-KEY"] == "***REDACTED***"
    assert data["headers"]["X-BAPI-SIGN"] == "***REDACTED***"
    assert data["payload"]["apiSecret"] == "***REDACTED***"
    assert data["response"]["signature"] == "***REDACTED***"
    assert data["response"]["secret"] == "***REDACTED***"
