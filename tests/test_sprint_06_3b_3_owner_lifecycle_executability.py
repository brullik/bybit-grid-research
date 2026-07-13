from __future__ import annotations

from types import MappingProxyType

import pytest

from bybit_grid.data.public_batch.evidence import (
    ALLOWED_BASE_URLS,
    CANONICAL_MEMBERS,
    GUARDRAILS,
    NON_STATUS_ARTIFACT_COUNT,
    canonical_json_bytes,
)
from bybit_grid.data.public_batch.models import PublicBatchError
from bybit_grid.data.public_batch.reconstruct import build_capture_plan, records_from_jsonl


class AlphabeticalReader:
    def __init__(self, member_bytes):
        self.member_bytes = dict(member_bytes)

    def names(self):
        return tuple(sorted(self.member_bytes))

    def read_bytes(self, name):
        return self.member_bytes[name]


@pytest.mark.parametrize(
    "obj",
    [
        {1: "a"},
        {True: "a"},
        MappingProxyType({480: 1}),
        {1: "a", "1": "b"},
        {False: "a", "False": "b"},
    ],
)
def test_non_string_mapping_keys_rejected(obj):
    with pytest.raises(PublicBatchError):
        canonical_json_bytes(obj)


@pytest.mark.parametrize("base_url", ALLOWED_BASE_URLS)
def test_build_capture_plan_freezes_approved_hosts(base_url):
    plan = build_capture_plan(
        run_id="bybit_public_batch_063b_btcusdt_v1",
        symbol="BTCUSDT",
        base_url=base_url,
        timeout_seconds=30,
    )
    assert plan["base_url"] == base_url
    assert [p["plan_id"] for p in plan["plans"]] == [
        "server_time_snapshot",
        "instrument_primary_1000",
        "instrument_alternate_200",
        "trade_primary_1000",
        "trade_alternate_251",
        "mark_primary_1000",
        "mark_alternate_251",
        "funding_primary_backward_200",
        "funding_alternate_chunked_100",
    ]


@pytest.mark.parametrize("bad_url", ["http://api.bybit.com", "https://example.com"])
def test_build_capture_plan_rejects_unapproved_hosts_in_parser(bad_url):
    plan = build_capture_plan(
        run_id="bybit_public_batch_063b_btcusdt_v1",
        symbol="BTCUSDT",
        base_url="https://api.bybit.com",
        timeout_seconds=30,
    )
    plan["base_url"] = bad_url
    with pytest.raises(PublicBatchError):
        records_from_jsonl(b"", capture_plan=plan)


@pytest.mark.parametrize("member", CANONICAL_MEMBERS)
def test_canonical_member_names_are_safe_files(member):
    assert not member.startswith("/")
    assert ".." not in member.split("/")
    assert not member.endswith("/")


@pytest.mark.parametrize("key,value", sorted(GUARDRAILS.items()))
def test_guardrail_values_are_frozen(key, value):
    assert key
    assert type(value) is bool
    if key == "funding_coverage_proven_bool":
        assert value is False


@pytest.mark.parametrize("timeout", [1, 30, 120])
def test_capture_plan_timeout_bounds(timeout):
    plan = build_capture_plan(
        run_id="bybit_public_batch_063b_btcusdt_v1",
        symbol="BTCUSDT",
        base_url="https://api.bybit.com",
        timeout_seconds=timeout,
    )
    assert plan["timeout_seconds"] == timeout


@pytest.mark.parametrize("timeout", [0, 121, True, "30"])
def test_capture_plan_timeout_invalid_values(timeout):
    plan = build_capture_plan(
        run_id="bybit_public_batch_063b_btcusdt_v1",
        symbol="BTCUSDT",
        base_url="https://api.bybit.com",
        timeout_seconds=30,
    )
    plan["timeout_seconds"] = timeout
    with pytest.raises(PublicBatchError):
        records_from_jsonl(b"", capture_plan=plan)


def test_source_derived_non_status_counts_are_truthful():
    from bybit_grid.data.public_batch.evidence import (
        DERIVED_ARTIFACT_COUNT,
        DERIVED_ARTIFACT_MEMBERS,
        SOURCE_ARTIFACT_COUNT,
        SOURCE_ARTIFACT_MEMBERS,
    )

    assert SOURCE_ARTIFACT_MEMBERS == ("recorded_public_responses.jsonl",)
    assert SOURCE_ARTIFACT_COUNT == len(SOURCE_ARTIFACT_MEMBERS) == 1
    assert DERIVED_ARTIFACT_COUNT == len(DERIVED_ARTIFACT_MEMBERS) == 15
    assert NON_STATUS_ARTIFACT_COUNT == SOURCE_ARTIFACT_COUNT + DERIVED_ARTIFACT_COUNT == 16
