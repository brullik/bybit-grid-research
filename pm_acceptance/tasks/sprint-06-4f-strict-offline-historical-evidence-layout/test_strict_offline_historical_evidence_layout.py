from __future__ import annotations

import ast
import builtins
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import socket
import tarfile
import time
import zipfile

import pytest

from bybit_grid.data.public_batch.historical_plan import build_historical_capture_plan
from bybit_grid.data.public_batch.models import (
    BybitInstrumentMeta,
    BybitServerTime,
    InclusiveMinuteWindow,
)


MINUTE_MS = 60_000
MODULE_NAME = "bybit_grid.data.public_batch.historical_evidence"
TRANSCRIPT_MODULE_NAME = "bybit_grid.data.public_batch.historical_transcript"
RESPONSE_MODULE_NAME = "bybit_grid.data.public_batch.historical_response"
UNAVAILABLE = "historical_evidence_layout_unavailable"
EXPECTED_LAYOUT_SHA256 = "7bdf1ab6cc52fa4ab3cd020bb681df22de239179c93ec2326bf553cdf41541a0"
EXPECTED_FIELD_NAMES = (
    "schema",
    "plan_sha256",
    "transcript_sha256",
    "manifest_sha256",
    "member_count",
    "raw_member_count",
    "total_member_byte_count",
    "max_layout_members",
    "member_names",
    "member_byte_counts",
    "member_sha256s",
    "member_sequence_sha256",
    "transcript_revalidated_bool",
    "manifest_payload_committed_bool",
    "manifest_self_excluded_bool",
    "member_commitments_verified_bool",
    "member_sequence_exact_bool",
    "member_names_safe_bool",
    "raw_body_identity_retained_bool",
    "network_authorized_bool",
    "transport_authorized_bool",
    "filesystem_authorized_bool",
    "archive_authorized_bool",
    "persistence_authorized_bool",
    "store_projection_authorized_bool",
    "store_install_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "source_authenticity_proven_bool",
    "account_eligibility_proven_bool",
    "account_region_eligibility_proven_bool",
    "bybit_product_availability_proven_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
    "transcript",
    "member_bytes",
)
TRUE_EVIDENCE_FLAGS = (
    "transcript_revalidated_bool",
    "manifest_payload_committed_bool",
    "manifest_self_excluded_bool",
    "member_commitments_verified_bool",
    "member_sequence_exact_bool",
    "member_names_safe_bool",
    "raw_body_identity_retained_bool",
)
FALSE_GUARDRAILS = (
    "network_authorized_bool",
    "transport_authorized_bool",
    "filesystem_authorized_bool",
    "archive_authorized_bool",
    "persistence_authorized_bool",
    "store_projection_authorized_bool",
    "store_install_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "source_authenticity_proven_bool",
    "account_eligibility_proven_bool",
    "account_region_eligibility_proven_bool",
    "bybit_product_availability_proven_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
)


def _api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    required = (
        "HistoricalEvidenceError",
        "HistoricalEvidenceLayout",
        "build_historical_evidence_layout",
        "__all__",
    )
    if any(not hasattr(module, name) for name in required):
        raise RuntimeError(UNAVAILABLE)
    return module


def _transcript_api():
    return importlib.import_module(TRANSCRIPT_MODULE_NAME)


def _response_api():
    return importlib.import_module(RESPONSE_MODULE_NAME)


def _canonical_json_bytes(value) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _instrument(server_time: BybitServerTime) -> BybitInstrumentMeta:
    return BybitInstrumentMeta(
        category="linear",
        symbol="BTCUSDT",
        contract_type="LinearPerpetual",
        status="Trading",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        launch_time_ms=0,
        delivery_time_ms=0,
        is_pre_listing=False,
        funding_interval_minutes=480,
        tick_size=Decimal("0.10"),
        qty_step=Decimal("0.001"),
        min_order_qty=Decimal("0.001"),
        min_notional_value=Decimal("5"),
        min_leverage=Decimal("1"),
        max_leverage=Decimal("100"),
        leverage_step=Decimal("0.01"),
        snapshot_server_time_ms=server_time.server_time_ms,
    )


def _plan(*, end_minute=2, include_trade=True, include_mark=True):
    server_time_ms = (end_minute + 2) * MINUTE_MS + 1_234
    server_time = BybitServerTime(
        server_time_ms=server_time_ms,
        time_second=server_time_ms // 1_000,
        time_nano=server_time_ms * 1_000_000,
        top_level_time_ms=server_time_ms,
        last_closed_open_time_ms=(end_minute + 1) * MINUTE_MS,
    )
    all_times = tuple(range(0, end_minute * MINUTE_MS + 1, MINUTE_MS))
    return build_historical_capture_plan(
        instrument=_instrument(server_time),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, end_minute * MINUTE_MS),
        observed_trade_open_times_ms=() if include_trade else all_times,
        observed_mark_open_times_ms=() if include_mark else all_times,
        observed_funding_times_ms=(),
    )


def _trade_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105", "1.5", "150"]


def _mark_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105"]


def _funding_row(timestamp_ms: int):
    return {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingRateTimestamp": str(timestamp_ms),
    }


def _body(request, *, empty_funding=False, response_time_ms=700_123) -> bytes:
    if request.dataset == "trade_kline_1m":
        rows = [
            _trade_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    elif request.dataset == "mark_kline_1m":
        rows = [
            _mark_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    else:
        candidates = [] if empty_funding else [_funding_row(2 * MINUTE_MS), _funding_row(0)]
        rows = [
            row
            for row in candidates
            if request.start_ms <= int(row["fundingRateTimestamp"]) <= request.end_ms
        ]
    result = {"category": "linear", "list": rows}
    if request.dataset != "funding_rate":
        result["symbol"] = "BTCUSDT"
    return json.dumps(
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": result,
            "retExtInfo": {},
            "time": response_time_ms,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _case(*, end_minute=2, include_trade=True, include_mark=True, empty_funding=False):
    plan = _plan(
        end_minute=end_minute,
        include_trade=include_trade,
        include_mark=include_mark,
    )
    response = _response_api()
    bodies = tuple(_body(request, empty_funding=empty_funding) for request in plan.requests)
    receipts = tuple(
        response.accept_historical_response_page(
            plan=plan,
            request=request,
            http_status=200,
            content_type="application/json",
            raw_body_bytes=body,
        )
        for request, body in zip(plan.requests, bodies, strict=True)
    )
    transcript = _transcript_api().reconcile_historical_response_transcript(
        plan=plan,
        receipts=receipts,
        raw_body_bytes=bodies,
    )
    return transcript


def _layout(api, transcript=None):
    source = _case() if transcript is None else transcript
    return api.build_historical_evidence_layout(transcript=source)


def _manifest(layout):
    return json.loads(layout.member_bytes[0])


def _descriptors(names, payloads):
    return [
        {"byte_count": len(payload), "name": name, "sha256": _sha256(payload)}
        for name, payload in zip(names, payloads, strict=True)
    ]


def _assert_tamper_error(api, layout, field_name, value, code):
    object.__setattr__(layout, field_name, value)
    with pytest.raises(api.HistoricalEvidenceError) as caught:
        layout.canonical_json_bytes()
    assert str(caught.value) == code


def test_exact_public_surface_signature_and_field_order():
    api = _api()
    assert api.__all__ == (
        "HistoricalEvidenceError",
        "HistoricalEvidenceLayout",
        "build_historical_evidence_layout",
    )
    assert {name for name in vars(api) if not name.startswith("_")} == set(api.__all__)
    assert issubclass(api.HistoricalEvidenceError, ValueError)
    signature = inspect.signature(api.build_historical_evidence_layout)
    assert tuple(signature.parameters) == ("transcript",)
    parameter = signature.parameters["transcript"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    assert (
        tuple(field.name for field in fields(api.HistoricalEvidenceLayout)) == EXPECTED_FIELD_NAMES
    )


def test_module_ast_has_no_transport_filesystem_archive_clock_or_import_time_calls():
    api = _api()
    source = Path(api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "io",
        "locale",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "ssl",
        "subprocess",
        "tarfile",
        "tempfile",
        "threading",
        "time",
        "urllib",
        "uuid",
        "zipfile",
        "zoneinfo",
        "recording",
        "capture",
        "pagination",
        "reconstruct",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[-1])
    assert forbidden.isdisjoint(imported)
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            assert not isinstance(node.value, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom))


def test_package_exports_remain_byte_for_byte_unchanged():
    _api()
    package = importlib.import_module("bybit_grid.data.public_batch")
    assert package.__all__ == [
        "BybitFundingRate",
        "BybitInstrumentMeta",
        "BybitMarkKline1m",
        "BybitPublicBatchAudit",
        "BybitPublicReplayBatch",
        "BybitServerTime",
        "BybitTradeKline1m",
        "InclusiveMinuteWindow",
        "PublicBatchError",
        "PublicRequestPageAudit",
    ]


def test_exact_06_4e_transcript_model_is_required():
    api = _api()
    for value in ({}, object(), None):
        with pytest.raises(api.HistoricalEvidenceError) as caught:
            api.build_historical_evidence_layout(transcript=value)
        assert str(caught.value) == "transcript_not_exact_model"


def test_transcript_is_revalidated_before_layout_materialization():
    api = _api()
    transcript = _case()
    object.__setattr__(transcript, "request_count", 999)
    with pytest.raises(api.HistoricalEvidenceError) as caught:
        api.build_historical_evidence_layout(transcript=transcript)
    assert str(caught.value) == "transcript_revalidation_failed"
    assert isinstance(caught.value.__cause__, _transcript_api().HistoricalTranscriptError)
    assert str(caught.value.__cause__) == "transcript_counts_invalid"


def test_uninitialized_exact_transcript_wraps_structural_access_failure():
    api = _api()
    transcript_type = _transcript_api().HistoricalResponseTranscript
    forged = object.__new__(transcript_type)
    with pytest.raises(api.HistoricalEvidenceError) as caught:
        api.build_historical_evidence_layout(transcript=forged)
    assert str(caught.value) == "transcript_revalidation_failed"
    assert isinstance(caught.value.__cause__, (AttributeError, TypeError))


def test_success_retains_exact_transcript_and_fixed_member_order():
    api = _api()
    transcript = _case()
    layout = _layout(api, transcript)
    assert layout.transcript is transcript
    assert layout.member_names == (
        "manifest.json",
        "transcript.json",
        "raw/000000.json",
        "raw/000001.json",
        "raw/000002.json",
    )
    assert layout.member_count == 5
    assert layout.raw_member_count == 3
    assert layout.max_layout_members == 258


def test_raw_members_retain_exact_source_byte_objects():
    api = _api()
    transcript = _case()
    layout = _layout(api, transcript)
    assert all(
        member is source
        for member, source in zip(layout.member_bytes[2:], transcript.raw_body_bytes, strict=True)
    )


def test_duplicate_raw_bodies_remain_distinct_indexed_members():
    api = _api()
    transcript = _case(
        end_minute=400,
        include_trade=False,
        include_mark=False,
        empty_funding=True,
    )
    assert len(transcript.raw_body_bytes) >= 2
    assert len(set(transcript.raw_body_bytes)) == 1
    layout = _layout(api, transcript)
    assert layout.raw_member_count == len(transcript.raw_body_bytes)
    assert layout.member_names[2:] == tuple(
        f"raw/{index:06d}.json" for index in range(len(transcript.raw_body_bytes))
    )
    assert len(set(layout.member_names)) == layout.member_count
    assert layout.member_sha256s[2:] == (layout.member_sha256s[2],) * layout.raw_member_count


def test_transcript_member_is_exact_06_4e_canonical_bytes():
    api = _api()
    transcript = _case()
    layout = _layout(api, transcript)
    expected = transcript.canonical_json_bytes()
    assert layout.member_bytes[1] == expected
    assert layout.transcript_sha256 == _sha256(expected) == transcript.sha256()
    assert layout.plan_sha256 == transcript.plan_sha256


def test_manifest_is_exact_compact_sorted_ascii_json_with_one_lf():
    api = _api()
    layout = _layout(api)
    manifest = _manifest(layout)
    assert layout.member_bytes[0] == _canonical_json_bytes(manifest)
    assert layout.member_bytes[0].endswith(b"\n")
    assert not layout.member_bytes[0].endswith(b"\n\n")
    layout.member_bytes[0].decode("ascii")


def test_manifest_commits_payload_members_and_excludes_itself():
    api = _api()
    layout = _layout(api)
    manifest = _manifest(layout)
    assert manifest == {
        "payload_member_count": layout.member_count - 1,
        "payload_members": _descriptors(layout.member_names[1:], layout.member_bytes[1:]),
        "schema": "bybit_public_historical_evidence_manifest_v1",
        "transcript_sha256": layout.transcript_sha256,
    }
    assert "manifest.json" not in tuple(
        descriptor["name"] for descriptor in manifest["payload_members"]
    )


def test_layout_commits_manifest_and_every_payload_member():
    api = _api()
    layout = _layout(api)
    assert layout.member_byte_counts == tuple(len(value) for value in layout.member_bytes)
    assert layout.member_sha256s == tuple(_sha256(value) for value in layout.member_bytes)
    assert layout.manifest_sha256 == layout.member_sha256s[0]
    expected_sequence = _sha256(
        _canonical_json_bytes(_descriptors(layout.member_names, layout.member_bytes))
    )
    assert layout.member_sequence_sha256 == expected_sequence


def test_member_names_are_fixed_unique_ascii_and_archive_safe():
    api = _api()
    layout = _layout(api)
    assert len(set(layout.member_names)) == layout.member_count
    for name in layout.member_names:
        assert type(name) is str and name.isascii()
        assert not name.startswith("/")
        assert ".." not in name
        assert "\\" not in name
        assert not name.endswith("/")


def test_layout_has_no_path_archive_or_write_methods():
    api = _api()
    layout = _layout(api)
    public = {name for name in dir(layout) if not name.startswith("_")}
    forbidden = {
        "archive",
        "extract",
        "install",
        "mkdir",
        "open",
        "path",
        "persist",
        "save",
        "tar",
        "write",
        "zip",
    }
    assert forbidden.isdisjoint(public)
    assert {"canonical_json_bytes", "sha256"}.issubset(public)


def test_member_containers_and_atoms_have_exact_immutable_types():
    api = _api()
    layout = _layout(api)
    assert type(layout.member_names) is tuple
    assert type(layout.member_byte_counts) is tuple
    assert type(layout.member_sha256s) is tuple
    assert type(layout.member_bytes) is tuple
    assert all(type(value) is str for value in layout.member_names)
    assert all(type(value) is int for value in layout.member_byte_counts)
    assert all(type(value) is str for value in layout.member_sha256s)
    assert all(type(value) is bytes for value in layout.member_bytes)


def test_member_count_and_total_bytes_are_exact_non_boolean_ints():
    api = _api()
    layout = _layout(api)
    assert type(layout.member_count) is int
    assert type(layout.raw_member_count) is int
    assert type(layout.total_member_byte_count) is int
    assert layout.total_member_byte_count == sum(map(len, layout.member_bytes))


def test_layout_is_frozen_slotted_hashable_and_factory_only():
    api = _api()
    layout = _layout(api)
    assert not hasattr(layout, "__dict__")
    hash(layout)
    with pytest.raises(FrozenInstanceError):
        layout.schema = "forged"
    with pytest.raises(api.HistoricalEvidenceError) as direct:
        api.HistoricalEvidenceLayout()
    assert str(direct.value) == "layout_factory_only"
    with pytest.raises(api.HistoricalEvidenceError) as replaced:
        replace(layout, schema=layout.schema)
    assert str(replaced.value) == "layout_factory_only"


def test_canonical_layout_omits_retained_transcript_and_member_bytes():
    api = _api()
    layout = _layout(api)
    payload = json.loads(layout.canonical_json_bytes())
    assert "transcript" not in payload
    assert "member_bytes" not in payload
    assert payload["member_names"] == list(layout.member_names)
    assert payload["member_sha256s"] == list(layout.member_sha256s)
    assert payload["member_byte_counts"] == list(layout.member_byte_counts)


def test_canonical_layout_is_deterministic_one_lf_and_matches_literal_sha():
    api = _api()
    first = _layout(api)
    second = _layout(api)
    canonical = first.canonical_json_bytes()
    assert canonical == second.canonical_json_bytes()
    assert canonical.endswith(b"\n") and not canonical.endswith(b"\n\n")
    assert first.sha256() == second.sha256() == EXPECTED_LAYOUT_SHA256


def test_source_byte_change_changes_manifest_and_layout_commitments():
    api = _api()
    first = _layout(api, _case())
    transcript = _case()
    changed = tuple(
        _body(request, response_time_ms=700_124) for request in transcript.plan.requests
    )
    response = _response_api()
    receipts = tuple(
        response.accept_historical_response_page(
            plan=transcript.plan,
            request=request,
            http_status=200,
            content_type="application/json",
            raw_body_bytes=body,
        )
        for request, body in zip(transcript.plan.requests, changed, strict=True)
    )
    second_transcript = _transcript_api().reconcile_historical_response_transcript(
        plan=transcript.plan,
        receipts=receipts,
        raw_body_bytes=changed,
    )
    second = _layout(api, second_transcript)
    assert first.transcript_sha256 != second.transcript_sha256
    assert first.manifest_sha256 != second.manifest_sha256
    assert first.member_sequence_sha256 != second.member_sequence_sha256
    assert first.sha256() != second.sha256()


def test_all_seven_narrow_evidence_flags_are_exact_true():
    api = _api()
    layout = _layout(api)
    for name in TRUE_EVIDENCE_FLAGS:
        assert type(getattr(layout, name)) is bool
        assert getattr(layout, name) is True


def test_every_authority_authenticity_coverage_and_selection_guardrail_is_false():
    api = _api()
    layout = _layout(api)
    for name in FALSE_GUARDRAILS:
        assert type(getattr(layout, name)) is bool
        assert getattr(layout, name) is False


def test_tampered_schema_fails_closed():
    api = _api()
    _assert_tamper_error(api, _layout(api), "schema", "v2", "layout_schema_invalid")


def test_tampered_plan_root_commitment_fails_closed():
    api = _api()
    _assert_tamper_error(
        api, _layout(api), "plan_sha256", "0" * 64, "layout_root_commitments_invalid"
    )


def test_tampered_transcript_root_commitment_fails_closed():
    api = _api()
    _assert_tamper_error(
        api, _layout(api), "transcript_sha256", "0" * 64, "layout_root_commitments_invalid"
    )


def test_tampered_manifest_root_commitment_fails_closed():
    api = _api()
    _assert_tamper_error(
        api, _layout(api), "manifest_sha256", "0" * 64, "layout_root_commitments_invalid"
    )


def test_tampered_counts_and_bool_aliases_fail_closed():
    api = _api()
    _assert_tamper_error(api, _layout(api), "member_count", True, "layout_counts_invalid")
    _assert_tamper_error(api, _layout(api), "raw_member_count", 99, "layout_counts_invalid")
    _assert_tamper_error(api, _layout(api), "max_layout_members", 259, "layout_counts_invalid")


def test_tampered_member_name_container_fails_closed():
    api = _api()
    layout = _layout(api)
    _assert_tamper_error(
        api, layout, "member_names", list(layout.member_names), "layout_member_names_invalid"
    )


def test_path_traversal_and_member_permutation_fail_closed():
    api = _api()
    layout = _layout(api)
    names = ("../manifest.json",) + layout.member_names[1:]
    _assert_tamper_error(api, layout, "member_names", names, "layout_member_names_invalid")
    layout = _layout(api)
    names = (layout.member_names[1], layout.member_names[0]) + layout.member_names[2:]
    _assert_tamper_error(api, layout, "member_names", names, "layout_member_names_invalid")


def test_member_name_str_subclass_equality_bomb_is_rejected_before_comparison():
    api = _api()

    class EqualityBomb(str):
        def __eq__(self, other):
            raise AssertionError("hostile_equality_called")

        __hash__ = str.__hash__

    layout = _layout(api)
    names = (EqualityBomb(layout.member_names[0]),) + layout.member_names[1:]
    _assert_tamper_error(
        api,
        layout,
        "member_names",
        names,
        "layout_member_names_invalid",
    )


def test_tampered_member_bytes_container_and_manifest_fail_closed():
    api = _api()
    layout = _layout(api)
    _assert_tamper_error(
        api, layout, "member_bytes", list(layout.member_bytes), "layout_member_bytes_invalid"
    )
    layout = _layout(api)
    changed = (layout.member_bytes[0] + b" ",) + layout.member_bytes[1:]
    _assert_tamper_error(api, layout, "member_bytes", changed, "layout_member_bytes_invalid")


def test_tampered_transcript_member_bytes_fail_closed():
    api = _api()
    layout = _layout(api)
    changed = (layout.member_bytes[0], layout.member_bytes[1] + b" ") + layout.member_bytes[2:]
    _assert_tamper_error(api, layout, "member_bytes", changed, "layout_member_bytes_invalid")


def test_equal_but_nonidentical_raw_member_bytes_fail_closed():
    api = _api()
    layout = _layout(api)
    clone = bytes(bytearray(layout.member_bytes[2]))
    assert clone == layout.member_bytes[2] and clone is not layout.member_bytes[2]
    changed = layout.member_bytes[:2] + (clone,) + layout.member_bytes[3:]
    _assert_tamper_error(api, layout, "member_bytes", changed, "layout_raw_body_identity_invalid")


def test_tampered_byte_count_commitments_fail_closed():
    api = _api()
    layout = _layout(api)
    changed = (layout.member_byte_counts[0] + 1,) + layout.member_byte_counts[1:]
    _assert_tamper_error(
        api, layout, "member_byte_counts", changed, "layout_member_commitments_invalid"
    )
    layout = _layout(api)
    changed = (True,) + layout.member_byte_counts[1:]
    _assert_tamper_error(
        api, layout, "member_byte_counts", changed, "layout_member_commitments_invalid"
    )


def test_tampered_hash_commitments_and_str_subclasses_fail_closed():
    api = _api()
    layout = _layout(api)
    changed = ("0" * 64,) + layout.member_sha256s[1:]
    _assert_tamper_error(
        api, layout, "member_sha256s", changed, "layout_member_commitments_invalid"
    )

    class HashAlias(str):
        pass

    layout = _layout(api)
    changed = (HashAlias(layout.member_sha256s[0]),) + layout.member_sha256s[1:]
    _assert_tamper_error(
        api, layout, "member_sha256s", changed, "layout_member_commitments_invalid"
    )


def test_tampered_member_sequence_commitment_fails_closed():
    api = _api()
    _assert_tamper_error(
        api, _layout(api), "member_sequence_sha256", "f" * 64, "layout_member_commitments_invalid"
    )


def test_tampered_true_evidence_flag_fails_closed():
    api = _api()
    _assert_tamper_error(
        api, _layout(api), TRUE_EVIDENCE_FLAGS[0], False, "layout_evidence_flags_invalid"
    )


def test_tampered_false_guardrail_fails_closed():
    api = _api()
    _assert_tamper_error(api, _layout(api), FALSE_GUARDRAILS[0], True, "layout_guardrails_invalid")


def test_tampered_retained_transcript_fails_before_member_approval():
    api = _api()
    layout = _layout(api)
    object.__setattr__(layout.transcript, "receipt_count", 999)
    object.__setattr__(layout, "member_sha256s", ("0" * 64,) + layout.member_sha256s[1:])
    with pytest.raises(api.HistoricalEvidenceError) as caught:
        layout.canonical_json_bytes()
    assert str(caught.value) == "transcript_revalidation_failed"


def test_rebound_transcript_instance_serializers_do_not_change_layout(monkeypatch):
    api = _api()
    transcript = _case()
    expected = _layout(api, transcript)
    transcript_type = type(transcript)
    monkeypatch.setattr(transcript_type, "canonical_json_bytes", lambda self: b"forged\n")
    monkeypatch.setattr(transcript_type, "sha256", lambda self: "f" * 64)
    actual = _layout(api, transcript)
    assert actual.transcript_sha256 == expected.transcript_sha256
    assert actual.member_sha256s == expected.member_sha256s


def test_rebound_transcript_post_init_does_not_disable_captured_validation(monkeypatch):
    api = _api()
    transcript = _case()
    monkeypatch.setattr(type(transcript), "__post_init__", lambda self: None)
    object.__setattr__(transcript, "request_count", 999)
    with pytest.raises(api.HistoricalEvidenceError) as caught:
        api.build_historical_evidence_layout(transcript=transcript)
    assert str(caught.value) == "transcript_revalidation_failed"
    assert str(caught.value.__cause__) == "transcript_counts_invalid"


def test_rebound_transcript_module_reconcile_name_is_ignored(monkeypatch):
    api = _api()
    transcript = _case()
    source_module = _transcript_api()
    monkeypatch.setattr(
        source_module,
        "reconcile_historical_response_transcript",
        lambda **kwargs: object(),
    )
    layout = _layout(api, transcript)
    assert layout.transcript is transcript
    assert layout.transcript_revalidated_bool is True


def test_rebound_layout_post_init_cannot_suppress_builder_or_canonical_validation(
    monkeypatch,
):
    api = _api()
    layout = _layout(api)
    values = {
        field.name: getattr(layout, field.name) for field in fields(api.HistoricalEvidenceLayout)
    }
    values["network_authorized_bool"] = True
    monkeypatch.setattr(api.HistoricalEvidenceLayout, "__post_init__", lambda self: None)

    with pytest.raises(api.HistoricalEvidenceError) as builder_caught:
        api._build_layout(**values)
    assert str(builder_caught.value) == "layout_guardrails_invalid"

    object.__setattr__(layout, "network_authorized_bool", True)
    with pytest.raises(api.HistoricalEvidenceError) as canonical_caught:
        layout.canonical_json_bytes()
    assert str(canonical_caught.value) == "layout_guardrails_invalid"


def test_build_performs_no_network_filesystem_archive_clock_or_environment_calls(monkeypatch):
    api = _api()
    transcript = _case()

    def forbidden(*args, **kwargs):
        raise AssertionError("external_authority_called")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "sleep", forbidden)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    monkeypatch.setattr(tarfile, "open", forbidden)
    layout = api.build_historical_evidence_layout(transcript=transcript)
    assert layout.filesystem_authorized_bool is False
    assert layout.archive_authorized_bool is False
    assert layout.network_authorized_bool is False


def test_builder_rejects_positional_variadic_and_extra_authority_inputs():
    api = _api()
    transcript = _case()
    with pytest.raises(TypeError):
        api.build_historical_evidence_layout(transcript)
    forbidden = (
        "path",
        "directory",
        "archive",
        "writer",
        "client",
        "session",
        "clock",
        "environment",
        "persist",
    )
    for name in forbidden:
        with pytest.raises(TypeError):
            api.build_historical_evidence_layout(transcript=transcript, **{name: object()})


def test_manifest_payload_count_is_exact_and_cannot_claim_self_commitment():
    api = _api()
    layout = _layout(api)
    manifest = _manifest(layout)
    assert type(manifest["payload_member_count"]) is int
    assert manifest["payload_member_count"] == layout.member_count - 1
    assert len(manifest["payload_members"]) == layout.member_count - 1
    assert (
        tuple(descriptor["name"] for descriptor in manifest["payload_members"])
        == (layout.member_names[1:])
    )
    assert "manifest.json" not in layout.member_names[1:]


def test_layout_only_produces_in_memory_member_names_bytes_and_commitments():
    api = _api()
    layout = _layout(api)
    assert type(layout.member_names) is tuple
    assert type(layout.member_bytes) is tuple
    assert type(layout.member_sha256s) is tuple
    assert all(type(value) is bytes for value in layout.member_bytes)
    assert layout.persistence_authorized_bool is False
    assert layout.source_authenticity_proven_bool is False
