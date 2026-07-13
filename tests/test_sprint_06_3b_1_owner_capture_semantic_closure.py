from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from types import MappingProxyType
from urllib.error import URLError

import pytest

from bybit_grid.data.public_batch.audit import audit_instrument_universe
from bybit_grid.data.public_batch.evidence import canonical_json_bytes
from bybit_grid.data.public_batch.models import BybitInstrumentMeta, PublicBatchError
from bybit_grid.data.public_batch.recording import RecordedPublicResponse, RecordingPublicClient


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        ('{"a":1}', {"a": True}),
        ('{"a":0}', {"a": False}),
        ('{"a":[1]}', {"a": [True]}),
        ('{"a":{"b":1}}', {"a": {"b": True}}),
    ],
)
def test_recorded_payload_exact_json_type_identity_rejects_bool_int_aliases(raw, parsed):
    with pytest.raises(PublicBatchError, match="parsed_payload_mismatch"):
        RecordedPublicResponse(
            1, "/v5/market/time", {}, 200, "application/json", raw, _sha(raw), parsed
        )


def test_mapping_proxy_instrument_universe_audit_canonical_serializes():
    row = BybitInstrumentMeta(
        "linear",
        "BTCUSDT",
        "LinearPerpetual",
        "Trading",
        "BTC",
        "USDT",
        "USDT",
        1,
        0,
        False,
        480,
        Decimal("0.1"),
        Decimal("0.001"),
        Decimal("0.001"),
        Decimal("5"),
        Decimal("1"),
        Decimal("100"),
        Decimal("0.01"),
        120000,
    )
    audit = audit_instrument_universe((row,))
    assert type(audit.contract_type_counts) is MappingProxyType
    assert json.loads(canonical_json_bytes(audit))["universe_audit_ok"] is True


@pytest.mark.parametrize("attempts", [True, 0, 11, "3"])
def test_recording_client_constructor_bounds(attempts):
    with pytest.raises(PublicBatchError):
        RecordingPublicClient(max_attempts=attempts)


def test_transport_failure_does_not_fabricate_response_body():
    def opener(_req, timeout=10):
        raise URLError("dns")

    client = RecordingPublicClient(opener=opener, max_attempts=1, backoff_seconds=Decimal("0"))
    with pytest.raises(PublicBatchError, match="transport_error"):
        client.for_plan("server_time_snapshot").public_get("/v5/market/time", {})
    assert client.records == []


def test_normal_runner_has_no_fixture_completion_flag():
    import scripts.run_bybit_public_batch_evidence as runner

    parser_text = open(runner.__file__, encoding="utf-8").read()
    assert "no-network-fixture-mode" not in parser_text
    assert "owner_network_capture_not_run_by_codex" not in parser_text
