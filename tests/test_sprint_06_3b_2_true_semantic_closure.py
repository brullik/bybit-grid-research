from __future__ import annotations

import json
from decimal import Decimal
from types import MappingProxyType
from urllib.error import URLError

import pytest

from bybit_grid.data.public_batch.evidence import (
    ALLOWED_BASE_URLS,
    CANONICAL_MEMBERS,
    NON_STATUS_ARTIFACT_COUNT,
    canonical_json_bytes,
    parse_canonical_jsonl_bytes,
)
from bybit_grid.data.public_batch.models import PublicBatchError
from bybit_grid.data.public_batch.recording import RecordingPublicClient, RecordedPublicResponse
from bybit_grid.data.public_batch.reconstruct import ReplayClient


def test_non_string_plain_mapping_keys_fail_without_collision():
    for obj in ({1: "a"}, {True: "a"}, {1: "a", "1": "b"}, {False: "a", "False": "b"}):
        with pytest.raises(PublicBatchError):
            canonical_json_bytes(obj)


def test_mapping_proxy_int_keys_are_lossless_for_model_counts():
    assert canonical_json_bytes(MappingProxyType({480: 1})) == b'{"480":1}'


def test_jsonl_canonical_enforcement():
    parse_canonical_jsonl_bytes("x.jsonl", b'{"a":1}\n')
    for bad in (b'{"a":1}', b'{"a":1}\n\n', b'{"b":2,"a":1}\n', b'{"a":1} \n'):
        with pytest.raises(PublicBatchError):
            parse_canonical_jsonl_bytes("x.jsonl", bad)


def test_complete_status_count_constant_is_derived_from_members():
    assert NON_STATUS_ARTIFACT_COUNT == len(CANONICAL_MEMBERS) - 2 == 16


def test_connectivity_probe_import_safe_and_hosts_exact():
    import scripts.probe_bybit_public_connectivity as probe

    assert tuple(probe.ALLOWED) == ALLOWED_BASE_URLS
    with pytest.raises(SystemExit):
        probe.main(["--base-url", "http://api.bybit.com", "--timeout-seconds", "1"])


def test_transport_error_has_context_and_no_record():
    def opener(_req, timeout=30):
        raise URLError("dns")

    c = RecordingPublicClient(opener=opener, max_attempts=1, backoff_seconds=Decimal("0"))
    with pytest.raises(
        PublicBatchError,
        match=r"transport_error:URLError:plan_id=server_time_snapshot:endpoint=/v5/market/time:attempt=1",
    ):
        c.for_plan("server_time_snapshot").public_get("/v5/market/time", {})
    assert c.records == []


class _Response:
    status = 200
    headers = {"content-type": "application/json"}
    closed = False

    def getcode(self):
        return self.status

    def read(self):
        return b'{"retCode":0,"result":{},"time":0}'

    def close(self):
        self.closed = True


def test_normal_response_closes():
    res = _Response()
    c = RecordingPublicClient(opener=lambda req, timeout=30: res, max_attempts=1)
    c.for_plan("server_time_snapshot").public_get("/v5/market/time", {})
    assert res.closed is True


def test_replay_client_assert_exhausted_detects_tail():
    body = '{"retCode":0,"result":{},"time":0}'
    rec = RecordedPublicResponse(
        1,
        "/v5/market/time",
        {},
        200,
        "application/json",
        body,
        __import__("hashlib").sha256(body.encode()).hexdigest(),
        json.loads(body),
    )
    rc = ReplayClient((rec,), "server_time_snapshot")
    with pytest.raises(PublicBatchError, match="unconsumed"):
        rc.assert_exhausted()
