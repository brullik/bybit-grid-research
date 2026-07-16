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
import time

import pytest

from bybit_grid.data.public_batch.historical_plan import build_historical_capture_plan
from bybit_grid.data.public_batch.models import (
    BybitInstrumentMeta,
    BybitServerTime,
    InclusiveMinuteWindow,
)


MINUTE_MS = 60_000
MODULE_NAME = "bybit_grid.data.public_batch.historical_transcript"
RESPONSE_MODULE_NAME = "bybit_grid.data.public_batch.historical_response"
UNAVAILABLE = "historical_response_transcript_unavailable"
EXPECTED_TRANSCRIPT_SHA256 = "7f44962c80c7d8e501ace9d1b265a8fa7d24f3df83f53fef445c81376b43156a"
EXPECTED_FIELD_NAMES = (
    "schema",
    "plan_sha256",
    "request_count",
    "receipt_count",
    "raw_body_page_count",
    "total_raw_body_byte_count",
    "max_transcript_pages",
    "max_transcript_raw_body_bytes",
    "request_sha256s",
    "raw_body_sha256s",
    "receipt_sha256s",
    "request_sequence_sha256",
    "raw_body_sequence_sha256",
    "receipt_sequence_sha256",
    "trade_row_count",
    "mark_row_count",
    "funding_row_count",
    "trade_first_timestamp_ms",
    "trade_last_timestamp_ms",
    "mark_first_timestamp_ms",
    "mark_last_timestamp_ms",
    "funding_first_timestamp_ms",
    "funding_last_timestamp_ms",
    "trade_timestamps_sha256",
    "mark_timestamps_sha256",
    "funding_timestamps_sha256",
    "trade_rows_sha256",
    "mark_rows_sha256",
    "funding_rows_sha256",
    "request_graph_reconciled_bool",
    "raw_bodies_reverified_bool",
    "receipts_canonical_match_bool",
    "sequence_exact_bool",
    "cross_page_timestamps_unique_bool",
    "canonical_dataset_row_order_bool",
    "network_authorized_bool",
    "filesystem_authorized_bool",
    "persistence_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
    "plan",
    "receipts",
    "raw_body_bytes",
    "trade_rows",
    "mark_rows",
    "funding_rows",
)
FALSE_GUARDRAILS = (
    "network_authorized_bool",
    "filesystem_authorized_bool",
    "persistence_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
)
TRUE_RECONCILIATION_FLAGS = (
    "request_graph_reconciled_bool",
    "raw_bodies_reverified_bool",
    "receipts_canonical_match_bool",
    "sequence_exact_bool",
    "cross_page_timestamps_unique_bool",
    "canonical_dataset_row_order_bool",
)


def _api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    required = (
        "MAX_HISTORICAL_TRANSCRIPT_PAGES",
        "MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES",
        "HistoricalTranscriptError",
        "HistoricalResponseTranscript",
        "reconcile_historical_response_transcript",
        "__all__",
    )
    if any(not hasattr(module, name) for name in required):
        raise RuntimeError(UNAVAILABLE)
    return module


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


def _plan(*, include_trade=True, include_mark=True):
    server_time_ms = 11 * MINUTE_MS + 1_234
    server_time = BybitServerTime(
        server_time_ms=server_time_ms,
        time_second=server_time_ms // 1_000,
        time_nano=server_time_ms * 1_000_000,
        top_level_time_ms=server_time_ms,
        last_closed_open_time_ms=10 * MINUTE_MS,
    )
    all_times = (0, MINUTE_MS, 2 * MINUTE_MS)
    return build_historical_capture_plan(
        instrument=_instrument(server_time),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 2 * MINUTE_MS),
        observed_trade_open_times_ms=() if include_trade else all_times,
        observed_mark_open_times_ms=() if include_mark else all_times,
        observed_funding_times_ms=(),
    )


def _trade_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105", "1.5", "150"]


def _mark_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105"]


def _funding_row(timestamp_ms: int, rate="0.0001"):
    return {
        "symbol": "BTCUSDT",
        "fundingRate": rate,
        "fundingRateTimestamp": str(timestamp_ms),
    }


def _body(request, *, funding_rows=None, response_time_ms=700_123) -> bytes:
    if request.dataset == "trade_kline_1m":
        rows = [
            _trade_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    elif request.dataset == "mark_kline_1m":
        rows = [
            _mark_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    else:
        rows = (
            [_funding_row(2 * MINUTE_MS), _funding_row(0)] if funding_rows is None else funding_rows
        )
        rows = [
            row
            for row in rows
            if request.start_ms <= int(row["fundingRateTimestamp"]) <= request.end_ms
        ]
    result = {"category": "linear", "list": rows}
    if request.dataset != "funding_rate":
        result["symbol"] = "BTCUSDT"
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": result,
        "retExtInfo": {},
        "time": response_time_ms,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _case(*, include_trade=True, include_mark=True, funding_rows=None):
    plan = _plan(include_trade=include_trade, include_mark=include_mark)
    response = _response_api()
    bodies = tuple(_body(request, funding_rows=funding_rows) for request in plan.requests)
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
    return plan, receipts, bodies


def _reconcile(api, plan, receipts, bodies, **kwargs):
    values = {"plan": plan, "receipts": receipts, "raw_body_bytes": bodies}
    values.update(kwargs)
    return api.reconcile_historical_response_transcript(**values)


def _assert_error(api, code, plan, receipts, bodies, **kwargs):
    with pytest.raises(api.HistoricalTranscriptError) as caught:
        _reconcile(api, plan, receipts, bodies, **kwargs)
    assert str(caught.value) == code


def test_exact_public_surface_constants_signature_and_field_order():
    api = _api()
    assert api.__all__ == (
        "HistoricalResponseTranscript",
        "HistoricalTranscriptError",
        "MAX_HISTORICAL_TRANSCRIPT_PAGES",
        "MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES",
        "reconcile_historical_response_transcript",
    )
    public = {name for name in vars(api) if not name.startswith("_")}
    assert public == set(api.__all__)
    assert api.MAX_HISTORICAL_TRANSCRIPT_PAGES == 256
    assert api.MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES == 268_435_456
    assert issubclass(api.HistoricalTranscriptError, ValueError)
    signature = inspect.signature(api.reconcile_historical_response_transcript)
    assert tuple(signature.parameters) == ("plan", "receipts", "raw_body_bytes")
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )
    assert (
        tuple(field.name for field in fields(api.HistoricalResponseTranscript))
        == EXPECTED_FIELD_NAMES
    )


def test_module_ast_has_no_transport_filesystem_clock_or_import_time_calls():
    api = _api()
    source = Path(api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "socket",
        "ssl",
        "subprocess",
        "threading",
        "time",
        "urllib",
        "uuid",
        "zoneinfo",
        "recording",
        "capture",
        "pagination",
        "reconstruct",
        "evidence",
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
            value = node.value
            assert not isinstance(value, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom))


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


def test_exact_plan_model_is_required():
    api = _api()
    plan, receipts, bodies = _case()
    _assert_error(api, "plan_not_exact_model", {}, receipts, bodies)
    _assert_error(api, "plan_not_exact_model", object(), receipts, bodies)
    assert _reconcile(api, plan, receipts, bodies).plan is plan


def test_tampered_plan_and_nested_requests_are_revalidated():
    api = _api()
    plan, receipts, bodies = _case()
    object.__setattr__(plan, "request_count", 999)
    _assert_error(api, "plan_invariants_invalid", plan, receipts, bodies)
    plan, receipts, bodies = _case()
    object.__setattr__(plan.requests[0], "limit", 999)
    _assert_error(api, "plan_invariants_invalid", plan, receipts, bodies)


def test_receipts_and_raw_bodies_require_exact_tuples():
    api = _api()
    plan, receipts, bodies = _case()
    _assert_error(api, "receipts_not_exact_tuple", plan, list(receipts), bodies)
    _assert_error(api, "raw_body_bytes_not_exact_tuple", plan, receipts, list(bodies))


def test_lengths_must_exactly_match_plan_request_graph():
    api = _api()
    plan, receipts, bodies = _case()
    _assert_error(api, "transcript_length_mismatch", plan, receipts[:-1], bodies)
    _assert_error(api, "transcript_length_mismatch", plan, receipts, bodies + (b"x",))


def test_every_receipt_requires_exact_06_4d_type():
    api = _api()
    plan, receipts, bodies = _case()
    wrong = (object(),) + receipts[1:]
    _assert_error(api, "receipt_not_exact_model", plan, wrong, bodies)


def test_every_raw_body_requires_exact_immutable_bytes():
    api = _api()
    plan, receipts, bodies = _case()
    for value in (bytearray(bodies[0]), memoryview(bodies[0]), bodies[0].decode()):
        wrong = (value,) + bodies[1:]
        _assert_error(api, "raw_body_not_exact_bytes", plan, receipts, wrong)


def test_receipt_order_is_exact_plan_sequence_order():
    api = _api()
    plan, receipts, bodies = _case()
    wrong = (receipts[1], receipts[0]) + receipts[2:]
    _assert_error(api, "receipt_request_binding_invalid", plan, wrong, bodies)


def test_receipt_request_and_plan_identity_are_independently_bound():
    api = _api()
    plan, receipts, bodies = _case()
    object.__setattr__(receipts[0], "plan_sha256", "0" * 64)
    _assert_error(api, "receipt_request_binding_invalid", plan, receipts, bodies)


def test_tampered_receipt_invariants_fail_before_body_reverification():
    api = _api()
    plan, receipts, bodies = _case()
    object.__setattr__(receipts[0], "row_count", 99)
    bad_bodies = (b"not json",) + bodies[1:]
    _assert_error(api, "receipt_invariants_invalid", plan, receipts, bad_bodies)

    plan, receipts, bodies = _case()
    object.__setattr__(receipts[0], "plan_sha256", "0" * 64)
    object.__setattr__(receipts[1], "row_count", 99)
    _assert_error(api, "receipt_invariants_invalid", plan, receipts, bodies)


def test_each_raw_body_is_reparsed_by_the_exact_06_4d_boundary():
    api = _api()
    plan, receipts, bodies = _case()
    bad = (b'{"retCode":0}',) + bodies[1:]
    with pytest.raises(api.HistoricalTranscriptError) as caught:
        _reconcile(api, plan, receipts, bad)
    assert str(caught.value) == "raw_body_reverification_failed"
    assert str(caught.value.__cause__) == "response_root_shape_invalid"


def test_semantically_equal_but_byte_different_body_cannot_reuse_receipt():
    api = _api()
    plan, receipts, bodies = _case()
    changed = (bodies[0] + b" ",) + bodies[1:]
    _assert_error(api, "receipt_canonical_mismatch", plan, receipts, changed)


def test_rebound_plan_serializers_do_not_change_independent_plan_digest(monkeypatch):
    api = _api()
    plan, receipts, bodies = _case()
    expected = _reconcile(api, plan, receipts, bodies).plan_sha256
    monkeypatch.setattr(type(plan), "canonical_json_bytes", lambda self: b"forged\n")
    monkeypatch.setattr(type(plan), "sha256", lambda self: "f" * 64)
    assert _reconcile(api, plan, receipts, bodies).plan_sha256 == expected


def test_rebound_receipt_serializers_do_not_change_independent_receipt_digest(monkeypatch):
    api = _api()
    plan, receipts, bodies = _case()
    expected = _reconcile(api, plan, receipts, bodies).receipt_sha256s
    monkeypatch.setattr(type(receipts[0]), "canonical_json_bytes", lambda self: b"forged\n")
    monkeypatch.setattr(type(receipts[0]), "sha256", lambda self: "f" * 64)
    assert _reconcile(api, plan, receipts, bodies).receipt_sha256s == expected


def test_success_retains_exact_plan_receipts_and_raw_bodies():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    assert transcript.plan is plan
    assert transcript.receipts is receipts
    assert transcript.raw_body_bytes is bodies
    assert (
        transcript.request_count == transcript.receipt_count == transcript.raw_body_page_count == 3
    )
    assert transcript.trade_rows[0] is receipts[0].rows[0]
    assert transcript.mark_rows[0] is receipts[1].rows[0]
    assert any(transcript.funding_rows[0] is row for row in receipts[2].rows)


def test_trade_and_mark_rows_are_canonical_across_pages():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    assert tuple(row.open_time_ms for row in transcript.trade_rows) == (0, 60_000, 120_000)
    assert tuple(row.open_time_ms for row in transcript.mark_rows) == (0, 60_000, 120_000)
    assert transcript.trade_row_count == transcript.mark_row_count == 3


def test_funding_rows_canonicalize_across_unspecified_page_order():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    assert tuple(row.funding_time_ms for row in transcript.funding_rows) == (0, 120_000)
    assert transcript.funding_first_timestamp_ms == 0
    assert transcript.funding_last_timestamp_ms == 120_000


def test_funding_source_permutation_changes_evidence_not_semantic_dataset_digest():
    api = _api()
    plan_a, receipts_a, bodies_a = _case(funding_rows=[_funding_row(120_000), _funding_row(0)])
    plan_b, receipts_b, bodies_b = _case(funding_rows=[_funding_row(0), _funding_row(120_000)])
    first = _reconcile(api, plan_a, receipts_a, bodies_a)
    second = _reconcile(api, plan_b, receipts_b, bodies_b)
    assert first.funding_rows_sha256 == second.funding_rows_sha256
    assert first.funding_timestamps_sha256 == second.funding_timestamps_sha256
    assert first.raw_body_sequence_sha256 != second.raw_body_sequence_sha256
    assert first.sha256() != second.sha256()


def test_empty_funding_is_valid_but_proves_no_coverage():
    api = _api()
    plan, receipts, bodies = _case(include_trade=False, include_mark=False, funding_rows=[])
    transcript = _reconcile(api, plan, receipts, bodies)
    assert transcript.trade_rows == transcript.mark_rows == transcript.funding_rows == ()
    assert transcript.funding_row_count == 0
    assert transcript.funding_first_timestamp_ms is transcript.funding_last_timestamp_ms is None
    assert transcript.funding_timestamps_sha256 == hashlib.sha256(b"[]\n").hexdigest()
    assert transcript.funding_coverage_proven_bool is False
    assert transcript.historical_market_data_coverage_proven_bool is False


def test_request_body_and_receipt_sequence_digests_are_ordered_commitments():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    assert (
        transcript.request_sequence_sha256
        == hashlib.sha256(_canonical_json_bytes(list(transcript.request_sha256s))).hexdigest()
    )
    assert (
        transcript.raw_body_sequence_sha256
        == hashlib.sha256(_canonical_json_bytes(list(transcript.raw_body_sha256s))).hexdigest()
    )
    assert (
        transcript.receipt_sequence_sha256
        == hashlib.sha256(_canonical_json_bytes(list(transcript.receipt_sha256s))).hexdigest()
    )
    assert transcript.raw_body_sha256s == tuple(hashlib.sha256(body).hexdigest() for body in bodies)
    assert transcript.receipt_sha256s == tuple(
        hashlib.sha256(receipt.canonical_json_bytes()).hexdigest() for receipt in receipts
    )


def test_sequence_and_dataset_digests_reject_tuple_and_str_subclasses():
    api = _api()
    plan, receipts, bodies = _case()

    class TupleAlias(tuple):
        pass

    class StringAlias(str):
        pass

    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(transcript, "request_sha256s", TupleAlias(transcript.request_sha256s))
    with pytest.raises(
        api.HistoricalTranscriptError,
        match="^transcript_sequence_digests_invalid$",
    ):
        transcript.canonical_json_bytes()

    transcript = _reconcile(api, plan, receipts, bodies)
    aliased_items = (StringAlias(transcript.request_sha256s[0]),) + transcript.request_sha256s[1:]
    object.__setattr__(transcript, "request_sha256s", aliased_items)
    with pytest.raises(
        api.HistoricalTranscriptError,
        match="^transcript_sequence_digests_invalid$",
    ):
        transcript.canonical_json_bytes()

    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(
        transcript,
        "request_sequence_sha256",
        StringAlias(transcript.request_sequence_sha256),
    )
    with pytest.raises(
        api.HistoricalTranscriptError,
        match="^transcript_sequence_digests_invalid$",
    ):
        transcript.canonical_json_bytes()

    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(
        transcript,
        "trade_rows_sha256",
        StringAlias(transcript.trade_rows_sha256),
    )
    with pytest.raises(
        api.HistoricalTranscriptError,
        match="^transcript_dataset_digests_invalid$",
    ):
        transcript.canonical_json_bytes()


def test_timestamp_endpoints_reject_bool_and_decimal_integer_aliases():
    api = _api()
    plan, receipts, bodies = _case()
    for name, value in (
        ("trade_first_timestamp_ms", False),
        ("mark_first_timestamp_ms", Decimal("0")),
        ("funding_first_timestamp_ms", False),
    ):
        transcript = _reconcile(api, plan, receipts, bodies)
        object.__setattr__(transcript, name, value)
        with pytest.raises(
            api.HistoricalTranscriptError,
            match="^transcript_timestamp_endpoints_invalid$",
        ):
            transcript.canonical_json_bytes()


def test_canonical_json_omits_raw_bodies_but_keeps_commitments():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    payload = json.loads(transcript.canonical_json_bytes())
    assert "raw_body_bytes" not in payload
    assert payload["raw_body_sha256s"] == list(transcript.raw_body_sha256s)
    assert payload["total_raw_body_byte_count"] == sum(map(len, bodies))


def test_canonical_json_retains_plan_receipts_and_aggregate_rows():
    api = _api()
    plan, receipts, bodies = _case()
    payload = json.loads(_reconcile(api, plan, receipts, bodies).canonical_json_bytes())
    assert payload["plan"]["schema"] == "bybit_public_historical_capture_plan_v1"
    assert len(payload["receipts"]) == len(receipts)
    assert len(payload["trade_rows"]) == 3
    assert len(payload["mark_rows"]) == 3
    assert len(payload["funding_rows"]) == 2


def test_canonical_json_has_one_lf_is_deterministic_and_matches_literal_sha():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    first = transcript.canonical_json_bytes()
    second = transcript.canonical_json_bytes()
    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert transcript.sha256() == hashlib.sha256(first).hexdigest()
    assert transcript.sha256() == EXPECTED_TRANSCRIPT_SHA256


def test_transcript_is_frozen_slotted_hashable_and_deeply_immutable():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    assert not hasattr(transcript, "__dict__")
    assert hash(transcript) == hash(transcript)
    assert type(transcript.receipts) is tuple
    assert type(transcript.raw_body_bytes) is tuple
    with pytest.raises(FrozenInstanceError):
        transcript.schema = "changed"


def test_transcript_is_factory_only_and_dataclasses_replace_cannot_forge():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    with pytest.raises(api.HistoricalTranscriptError, match="^transcript_factory_only$"):
        api.HistoricalResponseTranscript()
    with pytest.raises(api.HistoricalTranscriptError, match="^transcript_factory_only$"):
        replace(transcript, network_authorized_bool=True)


def test_all_six_narrow_reconciliation_flags_are_exact_true():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    for name in TRUE_RECONCILIATION_FLAGS:
        assert type(getattr(transcript, name)) is bool and getattr(transcript, name) is True


def test_every_authority_coverage_and_selection_guardrail_is_exact_false():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    for name in FALSE_GUARDRAILS:
        assert type(getattr(transcript, name)) is bool and getattr(transcript, name) is False


def test_public_constant_rebinding_cannot_weaken_private_limits(monkeypatch):
    api = _api()
    plan, receipts, bodies = _case()
    monkeypatch.setattr(api, "MAX_HISTORICAL_TRANSCRIPT_PAGES", 999_999)
    monkeypatch.setattr(api, "MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES", 999_999_999)
    transcript = _reconcile(api, plan, receipts, bodies)
    assert transcript.max_transcript_pages == 256
    assert transcript.max_transcript_raw_body_bytes == 268_435_456


def test_tampered_scalar_or_digest_refuses_canonicalization_and_hashing():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(transcript, "receipt_sequence_sha256", "0" * 64)
    with pytest.raises(
        api.HistoricalTranscriptError, match="^transcript_sequence_digests_invalid$"
    ):
        transcript.canonical_json_bytes()
    with pytest.raises(
        api.HistoricalTranscriptError, match="^transcript_sequence_digests_invalid$"
    ):
        transcript.sha256()


def test_tampered_retained_plan_refuses_canonicalization():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(plan, "request_count", 44)
    with pytest.raises(api.HistoricalTranscriptError, match="^plan_invariants_invalid$"):
        transcript.canonical_json_bytes()


def test_tampered_retained_receipt_refuses_canonicalization():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(receipts[0], "row_count", 999)
    with pytest.raises(api.HistoricalTranscriptError, match="^receipt_invariants_invalid$"):
        transcript.canonical_json_bytes()


def test_tampered_retained_raw_body_refuses_canonicalization():
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(transcript, "raw_body_bytes", (bodies[0] + b" ",) + bodies[1:])
    with pytest.raises(api.HistoricalTranscriptError, match="^receipt_canonical_mismatch$"):
        transcript.canonical_json_bytes()


def test_tampered_aggregate_rows_refuse_canonicalization(monkeypatch):
    api = _api()
    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    object.__setattr__(
        transcript, "funding_rows", transcript.funding_rows + transcript.funding_rows[:1]
    )
    with pytest.raises(api.HistoricalTranscriptError, match="^transcript_rows_invalid$"):
        transcript.canonical_json_bytes()

    plan, receipts, bodies = _case()
    transcript = _reconcile(api, plan, receipts, bodies)
    clone = replace(transcript.funding_rows[0])
    assert clone == transcript.funding_rows[0] and clone is not transcript.funding_rows[0]
    monkeypatch.setattr(type(clone), "__eq__", lambda self, other: True)
    object.__setattr__(
        transcript,
        "funding_rows",
        (clone,) + transcript.funding_rows[1:],
    )
    with pytest.raises(api.HistoricalTranscriptError, match="^transcript_rows_invalid$"):
        transcript.canonical_json_bytes()


def test_validation_order_is_plan_then_container_then_length_then_items():
    api = _api()
    plan, receipts, bodies = _case()
    object.__setattr__(plan, "request_count", 999)
    _assert_error(api, "plan_invariants_invalid", plan, [], [])
    plan, receipts, bodies = _case()
    _assert_error(api, "receipts_not_exact_tuple", plan, list(receipts), list(bodies))
    _assert_error(api, "raw_body_bytes_not_exact_tuple", plan, receipts, list(bodies))
    _assert_error(api, "transcript_length_mismatch", plan, (object(),), bodies)


def test_forbidden_transport_path_clock_cap_and_variadic_kwargs_are_rejected():
    api = _api()
    plan, receipts, bodies = _case()
    forbidden = (
        "client",
        "session",
        "callback",
        "transport",
        "host",
        "base_url",
        "headers",
        "cookies",
        "credential",
        "api_key",
        "secret",
        "timeout",
        "retry",
        "proxy",
        "path",
        "clock",
        "max_pages",
        "max_raw_body_bytes",
        "network",
        "live",
    )
    for name in forbidden:
        with pytest.raises(TypeError):
            _reconcile(api, plan, receipts, bodies, **{name: object()})
    with pytest.raises(TypeError):
        api.reconcile_historical_response_transcript(plan, receipts, bodies)


def test_reconciliation_performs_no_network_filesystem_or_wall_clock_calls(monkeypatch):
    api = _api()
    plan, receipts, bodies = _case()

    def forbidden(*args, **kwargs):
        raise AssertionError("external_surface_called")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    transcript = _reconcile(api, plan, receipts, bodies)
    assert transcript.raw_bodies_reverified_bool is True
