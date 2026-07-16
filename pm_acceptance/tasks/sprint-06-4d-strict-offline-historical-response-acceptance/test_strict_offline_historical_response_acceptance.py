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

from bybit_grid.data.public_batch.historical_plan import (
    HistoricalCapturePlan,
    HistoricalRequestSpec,
    build_historical_capture_plan,
)
from bybit_grid.data.public_batch.models import (
    BybitFundingRate,
    BybitInstrumentMeta,
    BybitMarkKline1m,
    BybitServerTime,
    BybitTradeKline1m,
    InclusiveMinuteWindow,
)


MINUTE_MS = 60_000
MODULE_NAME = "bybit_grid.data.public_batch.historical_response"
UNAVAILABLE = "historical_response_page_unavailable"
MAX_BODY = 1_048_576
ACCEPTED_CONTENT_TYPES = (
    "application/json",
    "Application/JSON",
    " application/json ; charset = utf-8 ",
    '\tAPPLICATION/JSON;charset="UTF-8"\t',
)
EXPECTED_ONE_TRADE_REQUEST_BYTES = (
    b'{"dataset":"trade_kline_1m","end_ms":0,"endpoint":"/v5/market/kline",'
    b'"limit":1,"pagination":"missing_windows_ascending","params":[["category",'
    b'"linear"],["symbol","BTCUSDT"],["interval","1"],["start",0],["end",0],'
    b'["limit",1]],"requested_minute_count":1,"sequence_id":1,"start_ms":0,'
    b'"target_row_count":1}\n'
)
EXPECTED_ONE_TRADE_ROWS_BYTES = (
    b'[{"category":"linear","close":"105","closed_bool":true,"high":"110",'
    b'"low":"90","open":"100","open_time_ms":0,"source":"bybit_trade_kline_1m",'
    b'"symbol":"BTCUSDT","turnover":"150","volume":"1.5"}]\n'
)
EXPECTED_ONE_TRADE_RECEIPT_BYTES = (
    b'{"canonical_row_order":"timestamp_ascending","category":"linear",'
    b'"content_type":"application/json","credentials_allowed_bool":false,'
    b'"dataset":"trade_kline_1m","endpoint":"/v5/market/kline",'
    b'"exact_kline_coverage_bool":true,"filesystem_authorized_bool":false,'
    b'"first_timestamp_ms":0,"funding_coverage_proven_bool":false,'
    b'"funding_page_unsaturated_bool":false,'
    b'"historical_market_data_coverage_proven_bool":false,"http_status":200,'
    b'"last_timestamp_ms":0,"live_execution_authorized_bool":false,'
    b'"max_json_depth":8,"max_json_tokens":20000,"max_response_body_bytes":1048576,'
    b'"native_equivalence_proven_bool":false,'
    b'"native_grid_mutation_authorized_bool":false,"network_authorized_bool":false,'
    b'"ordinary_order_authorized_bool":false,'
    b'"parameter_selection_authorized_bool":false,'
    b'"persistence_authorized_bool":false,'
    b'"plan_sha256":"fe5cfa02780324f54bca7b5e050a1bd0b28703bd1cd760c391e81c16eef53c42",'
    b'"position_mutation_authorized_bool":false,"private_api_allowed_bool":false,'
    b'"raw_body_byte_count":157,'
    b'"raw_body_sha256":"82ca39daa542244e5f10d0c55cf10346247d056c9935151a0d8996d64db7fe52",'
    b'"request_end_ms":0,"request_limit":1,'
    b'"request_sha256":"492fe8d1fcf235195246d12931d27e087311af5339b0ffb6a06c979aa363b26a",'
    b'"request_start_ms":0,"request_target_row_count":1,"response_time_ms":700123,'
    b'"row_count":1,"rows":[{"category":"linear","close":"105",'
    b'"closed_bool":true,"high":"110","low":"90","open":"100",'
    b'"open_time_ms":0,"source":"bybit_trade_kline_1m","symbol":"BTCUSDT",'
    b'"turnover":"150","volume":"1.5"}],'
    b'"rows_sha256":"bf50c00bb5a6ff627cb55ff99ad6a7d887a6ab782ff8fba0ce63f3b257817986",'
    b'"schema":"bybit_public_historical_response_receipt_v1","sequence_id":1,'
    b'"source_row_order":"reverse_start_time",'
    b'"sufficient_for_parameter_selection_bool":false,"symbol":"BTCUSDT",'
    b'"telegram_authorized_bool":false,'
    b'"timestamps_sha256":"c14196f132c1e9be0508ae80ab52fcb3e1d3fc05880415f3dc980971df207c9e",'
    b'"wallet_authorized_bool":false}\n'
)


def _api():
    try:
        historical_response = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    required = (
        "MAX_HISTORICAL_RESPONSE_BODY_BYTES",
        "HistoricalResponseError",
        "HistoricalResponseReceipt",
        "accept_historical_response_page",
        "__all__",
    )
    if any(not hasattr(historical_response, name) for name in required):
        raise RuntimeError(UNAVAILABLE)
    return historical_response


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


def _plan_request(
    dataset: str,
    *,
    start_minute: int = 0,
    end_minute: int = 2,
) -> tuple[HistoricalCapturePlan, HistoricalRequestSpec]:
    server_minute = max(11, end_minute + 2)
    server_time_ms = server_minute * MINUTE_MS + 1_234
    server_time = BybitServerTime(
        server_time_ms=server_time_ms,
        time_second=server_time_ms // 1_000,
        time_nano=server_time_ms * 1_000_000,
        top_level_time_ms=server_time_ms,
        last_closed_open_time_ms=(server_minute - 1) * MINUTE_MS,
    )
    timestamps = tuple(value * MINUTE_MS for value in range(start_minute, end_minute + 1))
    observed_trade = timestamps if dataset != "trade_kline_1m" else ()
    observed_mark = timestamps if dataset != "mark_kline_1m" else ()
    plan = build_historical_capture_plan(
        instrument=_instrument(server_time),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(
            start_minute * MINUTE_MS,
            end_minute * MINUTE_MS,
        ),
        observed_trade_open_times_ms=observed_trade,
        observed_mark_open_times_ms=observed_mark,
        observed_funding_times_ms=(),
    )
    request = next(item for item in plan.requests if item.dataset == dataset)
    return plan, request


def _trade_row(timestamp_ms: int) -> list[str]:
    return [str(timestamp_ms), "100", "110", "90", "105", "1.5", "150"]


def _mark_row(timestamp_ms: int) -> list[str]:
    return [str(timestamp_ms), "100", "110", "90", "105"]


def _funding_row(timestamp_ms: int, rate: str = "0.0001") -> dict[str, str]:
    return {
        "symbol": "BTCUSDT",
        "fundingRate": rate,
        "fundingRateTimestamp": str(timestamp_ms),
    }


def _root(request: HistoricalRequestSpec, rows, *, response_time_ms: int = 700_123):
    result = {"category": "linear", "list": rows}
    if request.dataset != "funding_rate":
        result["symbol"] = "BTCUSDT"
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": result,
        "retExtInfo": {},
        "time": response_time_ms,
    }


def _body(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _valid_body(request: HistoricalRequestSpec) -> bytes:
    if request.dataset == "trade_kline_1m":
        rows = [
            _trade_row(timestamp)
            for timestamp in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    elif request.dataset == "mark_kline_1m":
        rows = [
            _mark_row(timestamp)
            for timestamp in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    else:
        rows = [_funding_row(request.end_ms), _funding_row(0)]
        rows = [
            row
            for row in rows
            if request.start_ms <= int(row["fundingRateTimestamp"]) <= request.end_ms
        ]
    return _body(_root(request, rows))


def _accept(api, plan, request, raw_body_bytes, **overrides):
    values = {
        "plan": plan,
        "request": request,
        "http_status": 200,
        "content_type": "application/json; charset=utf-8",
        "raw_body_bytes": raw_body_bytes,
    }
    values.update(overrides)
    return api.accept_historical_response_page(**values)


def _assert_error(api, code: str, plan, request, raw_body_bytes, **overrides):
    with pytest.raises(api.HistoricalResponseError) as caught:
        _accept(api, plan, request, raw_body_bytes, **overrides)
    assert str(caught.value) == code


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


def _timestamp_digest(values: tuple[int, ...]) -> str:
    return hashlib.sha256(_canonical_json_bytes(list(values))).hexdigest()


def test_exact_public_surface_signature_constant_and_receipt_field_order():
    api = _api()
    assert api.MAX_HISTORICAL_RESPONSE_BODY_BYTES == MAX_BODY
    assert issubclass(api.HistoricalResponseError, ValueError)
    assert type(api.__all__) is tuple
    assert api.__all__ == (
        "MAX_HISTORICAL_RESPONSE_BODY_BYTES",
        "HistoricalResponseError",
        "HistoricalResponseReceipt",
        "accept_historical_response_page",
    )
    signature = inspect.signature(api.accept_historical_response_page)
    assert tuple(signature.parameters) == (
        "plan",
        "request",
        "http_status",
        "content_type",
        "raw_body_bytes",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert all(
        parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values()
    )
    assert tuple(field.name for field in fields(api.HistoricalResponseReceipt)) == (
        "schema",
        "plan_sha256",
        "request_sha256",
        "sequence_id",
        "dataset",
        "endpoint",
        "category",
        "symbol",
        "request_start_ms",
        "request_end_ms",
        "request_limit",
        "request_target_row_count",
        "http_status",
        "content_type",
        "response_time_ms",
        "raw_body_byte_count",
        "raw_body_sha256",
        "max_response_body_bytes",
        "max_json_depth",
        "max_json_tokens",
        "row_count",
        "first_timestamp_ms",
        "last_timestamp_ms",
        "timestamps_sha256",
        "rows_sha256",
        "source_row_order",
        "canonical_row_order",
        "exact_kline_coverage_bool",
        "funding_page_unsaturated_bool",
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
        "rows",
    )
    assert "__dict__" not in api.HistoricalResponseReceipt.__slots__


def test_module_ast_has_no_external_recording_or_import_time_call_surface():
    api = _api()
    tree = ast.parse(inspect.getsource(api))
    forbidden_roots = {
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "locale",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "socket",
        "ssl",
        "subprocess",
        "threading",
        "time",
        "urllib",
        "uuid",
        "zoneinfo",
    }
    imported = set()
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
            imported_modules.add(node.module)
    assert imported.isdisjoint(forbidden_roots)
    assert not any(name == "recording" or name.endswith(".recording") for name in imported_modules)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            assert not isinstance(node.value, ast.Call)
        elif isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    assert {name for name in vars(api) if not name.startswith("_")} == set(api.__all__)


def test_package_exports_remain_exactly_unchanged():
    api = _api()
    public_batch = importlib.import_module("bybit_grid.data.public_batch")
    assert api.__name__ == MODULE_NAME
    assert public_batch.__all__ == [
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
    assert "HistoricalResponseReceipt" not in public_batch.__all__


def test_exact_model_identity_and_request_object_membership_are_required():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    _assert_error(api, "plan_not_exact_model", object(), request, body)
    _assert_error(api, "request_not_exact_model", plan, object(), body)
    equal_clone = replace(request)
    assert equal_clone == request and equal_clone is not request
    _assert_error(api, "request_not_member_of_plan", plan, equal_clone, body)


def test_object_setattr_tampered_plan_and_request_are_revalidated_fail_closed():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    object.__setattr__(plan, "symbol", "ETHUSDT")
    _assert_error(api, "plan_invariants_invalid", plan, request, body)

    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    object.__setattr__(request, "limit", request.limit + 1)
    _assert_error(api, "request_invariants_invalid", plan, request, body)

    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    object.__setattr__(request, "params", list(request.params))
    _assert_error(api, "request_invariants_invalid", plan, request, body)

    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    object.__setattr__(plan, "requests", None)
    _assert_error(api, "plan_invariants_invalid", plan, request, body)


def test_http_status_requires_exact_non_bool_200():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    for status in (True, 200.0, "200", 199, 201):
        _assert_error(api, "http_status_not_exact_200", plan, request, body, http_status=status)


def test_content_type_parser_is_narrow_ascii_and_receipt_is_canonical():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    for content_type in ACCEPTED_CONTENT_TYPES:
        receipt = _accept(api, plan, request, body, content_type=content_type)
        assert receipt.content_type == "application/json"
    for content_type in (
        "application/problem+json",
        "text/json",
        "application/json; charset=latin-1",
        "application/json; charset=utf-8; charset=utf-8",
        "application/json; boundary=x",
        "application/json;",
        "application/json, text/plain",
        "application/json\r\nX: y",
        "application/json\x00",
        'application/json; charset="utf-8" extra',
        "application/jsön",
        b"application/json",
    ):
        _assert_error(
            api,
            "content_type_not_accepted_json",
            plan,
            request,
            body,
            content_type=content_type,
        )


def test_raw_body_requires_exact_nonempty_bytes():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    for body in (bytearray(b"{}"), memoryview(b"{}"), "{}"):
        _assert_error(api, "raw_body_not_exact_bytes", plan, request, body)
    _assert_error(api, "response_body_empty", plan, request, b"")


def test_private_body_cap_accepts_exact_limit_and_rejects_limit_plus_one():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    exact = body + b" " * (MAX_BODY - len(body))
    assert _accept(api, plan, request, exact).raw_body_byte_count == MAX_BODY
    _assert_error(api, "response_body_too_large", plan, request, exact + b" ")


def test_public_body_cap_rebinding_cannot_weaken_private_policy(monkeypatch):
    api = _api()
    monkeypatch.setattr(api, "MAX_HISTORICAL_RESPONSE_BODY_BYTES", 10**9)
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    oversized = body + b" " * (MAX_BODY + 1 - len(body))
    _assert_error(api, "response_body_too_large", plan, request, oversized)


def test_utf8_is_strict_and_bom_is_not_silently_removed():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    _assert_error(api, "response_utf8_invalid", plan, request, b"\xff")
    _assert_error(
        api,
        "response_json_invalid",
        plan,
        request,
        b"\xef\xbb\xbf" + _valid_body(request),
    )


def test_json_duplicate_keys_are_rejected_at_root_and_nested_levels():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    root_duplicate = b'{"retCode":0,"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[]},"retExtInfo":{},"time":1}'
    nested_duplicate = b'{"retCode":0,"retMsg":"OK","result":{"category":"linear","category":"linear","list":[]},"retExtInfo":{},"time":1}'
    _assert_error(api, "response_json_duplicate_key", plan, request, root_duplicate)
    _assert_error(api, "response_json_duplicate_key", plan, request, nested_duplicate)


def test_json_floats_are_rejected_everywhere():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    raw = b'{"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[],"extra":1.0},"retExtInfo":{},"time":1}'
    _assert_error(api, "response_json_float_forbidden", plan, request, raw)


def test_json_nonfinite_constants_are_rejected_everywhere():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for token in (b"NaN", b"Infinity", b"-Infinity"):
        raw = (
            b'{"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[]},"retExtInfo":{},"time":'
            + token
            + b"}"
        )
        _assert_error(api, "response_json_nonfinite_forbidden", plan, request, raw)


def test_every_json_integer_is_restricted_to_signed_int64():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for value in ((1 << 63), -(1 << 63) - 1):
        root = _root(request, [])
        root["retExtInfo"] = {"value": value}
        _assert_error(
            api,
            "response_json_integer_out_of_int64",
            plan,
            request,
            _body(root),
        )
    huge = (
        b'{"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[]},"retExtInfo":{},"time":'
        + b"9" * 5_000
        + b"}"
    )
    _assert_error(api, "response_json_integer_out_of_int64", plan, request, huge)


def test_json_integer_negative_zero_is_noncanonical():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    raw = b'{"retCode":0,"retMsg":"OK","result":{"category":"linear","list":[]},"retExtInfo":{},"time":-0}'
    _assert_error(api, "response_json_integer_noncanonical", plan, request, raw)


def test_json_syntax_and_excessive_nesting_fail_with_stable_errors():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    _assert_error(api, "response_json_invalid", plan, request, b"{")
    depth_eight = b"[" * 8 + b"0" + b"]" * 8
    _assert_error(api, "response_root_shape_invalid", plan, request, depth_eight)
    depth_nine = b"[" * 9 + b"0" + b"]" * 9
    _assert_error(api, "response_json_depth_exceeded", plan, request, depth_nine)


def test_json_scanner_rejects_exact_token_limit_plus_one_before_parsing():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    exactly_19_999_tokens = b"[" + b"0," * 9_998 + b"0]"
    _assert_error(
        api,
        "response_root_shape_invalid",
        plan,
        request,
        exactly_19_999_tokens,
    )
    exactly_20_001_tokens = b"[" + b"0," * 9_999 + b"0]"
    assert len(exactly_20_001_tokens) < MAX_BODY
    _assert_error(
        api,
        "response_json_token_limit_exceeded",
        plan,
        request,
        exactly_20_001_tokens,
    )


def test_json_scanner_handles_escape_parity_and_unicode_escape_without_false_structure():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for ret_msg in ('O\\"K', "O\\\\K", "O\\u005bK"):
        root = _root(request, [])
        root["retMsg"] = ret_msg
        _assert_error(
            api,
            "response_top_level_invalid",
            plan,
            request,
            _body(root),
        )


def test_json_scanner_rejects_unclosed_strings_and_mismatched_closers():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for raw in (b'{"retCode":"unterminated}', b"[}", b"{]", b"[[0]"):
        _assert_error(api, "response_json_invalid", plan, request, raw)


def test_json_rejects_lone_surrogate_escapes_and_accepts_valid_pairs():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for token in (b"\\ud800", b"\\udc00"):
        raw = (
            b'{"retCode":0,"retMsg":"'
            + token
            + b'","result":{"category":"linear","list":[]},"retExtInfo":{},"time":1}'
        )
        _assert_error(
            api,
            "response_json_unicode_scalar_invalid",
            plan,
            request,
            raw,
        )
    valid_pair = b'{"retCode":0,"retMsg":"\\ud83d\\ude00","result":{"category":"linear","list":[]},"retExtInfo":{},"time":1}'
    _assert_error(api, "response_top_level_invalid", plan, request, valid_pair)


def test_json_scanner_accepts_full_1000_row_trade_envelope():
    api = _api()
    plan, request = _plan_request("trade_kline_1m", start_minute=0, end_minute=999)
    receipt = _accept(api, plan, request, _valid_body(request))
    assert receipt.row_count == 1000
    assert receipt.first_timestamp_ms == 0
    assert receipt.last_timestamp_ms == 999 * MINUTE_MS


def test_root_requires_exact_documented_key_set_and_object_shape():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    _assert_error(api, "response_root_shape_invalid", plan, request, b"[]")
    for mutation in ("missing", "extra"):
        root = _root(request, [])
        if mutation == "missing":
            root.pop("retExtInfo")
        else:
            root["traceId"] = "forbidden"
        _assert_error(api, "response_root_shape_invalid", plan, request, _body(root))


def test_top_level_status_identity_and_empty_extension_are_exact():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    variants = (
        {"retCode": True},
        {"retCode": 1},
        {"retCode": "0"},
        {"retMsg": "ok"},
        {"retMsg": 0},
        {"retExtInfo": []},
        {"retExtInfo": {"warning": "x"}},
    )
    for mutation in variants:
        root = _root(request, [])
        root.update(mutation)
        _assert_error(api, "response_top_level_invalid", plan, request, _body(root))


def test_top_level_time_is_exact_nonnegative_int64():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    for response_time in (True, "1", -1, 1 << 63):
        root = _root(request, [])
        root["time"] = response_time
        code = (
            "response_json_integer_out_of_int64"
            if response_time == 1 << 63
            else "response_time_invalid"
        )
        _assert_error(api, code, plan, request, _body(root))


def test_kline_result_requires_exact_shape_category_symbol_and_list():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    rows = [_trade_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, 0)]
    variants = (
        {"category": "inverse"},
        {"symbol": "ETHUSDT"},
        {"list": "not-a-list"},
        {"extra": "forbidden"},
    )
    for mutation in variants:
        root = _root(request, rows)
        root["result"].update(mutation)
        code = (
            "response_identity_mismatch"
            if "category" in mutation or "symbol" in mutation
            else "response_result_shape_invalid"
        )
        _assert_error(api, code, plan, request, _body(root))


def test_funding_result_requires_exact_shape_and_has_no_result_symbol():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    root = _root(request, [])
    root["result"]["symbol"] = "BTCUSDT"
    _assert_error(api, "response_result_shape_invalid", plan, request, _body(root))
    root = _root(request, [])
    root["result"]["category"] = "inverse"
    _assert_error(api, "response_identity_mismatch", plan, request, _body(root))


def test_trade_page_success_returns_exact_typed_canonical_rows():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    receipt = _accept(api, plan, request, _valid_body(request))
    assert type(receipt.rows) is tuple
    assert all(type(row) is BybitTradeKline1m for row in receipt.rows)
    assert tuple(row.open_time_ms for row in receipt.rows) == (0, MINUTE_MS, 2 * MINUTE_MS)
    assert receipt.source_row_order == "reverse_start_time"
    assert receipt.canonical_row_order == "timestamp_ascending"
    assert receipt.exact_kline_coverage_bool is True
    assert receipt.funding_page_unsaturated_bool is False


def test_mark_page_success_returns_exact_typed_canonical_rows():
    api = _api()
    plan, request = _plan_request("mark_kline_1m")
    receipt = _accept(api, plan, request, _valid_body(request))
    assert all(type(row) is BybitMarkKline1m for row in receipt.rows)
    assert tuple(row.open_time_ms for row in receipt.rows) == (0, MINUTE_MS, 2 * MINUTE_MS)
    assert all(row.closed_bool is True for row in receipt.rows)


def test_kline_rows_require_exact_documented_width_and_string_atoms():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    good = [_trade_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, 0)]
    for bad_row in (good[0][:-1], good[0] + ["extra"], {"row": good[0]}, [0, *good[0][1:]]):
        rows = [list(row) for row in good]
        rows[0] = bad_row
        _assert_error(
            api,
            "kline_row_shape_invalid",
            plan,
            request,
            _body(_root(request, rows)),
        )


def test_kline_response_order_is_exactly_newest_first():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    rows = [_trade_row(value) for value in (0, MINUTE_MS, 2 * MINUTE_MS)]
    _assert_error(
        api,
        "kline_order_invalid",
        plan,
        request,
        _body(_root(request, rows)),
    )


def test_kline_page_must_cover_every_requested_minute_exactly():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    missing = [_trade_row(value) for value in (2 * MINUTE_MS, 0)]
    duplicate = [_trade_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, MINUTE_MS)]
    for rows in (missing, duplicate):
        _assert_error(
            api,
            "kline_coverage_invalid",
            plan,
            request,
            _body(_root(request, rows)),
        )


def test_kline_timestamp_grammar_alignment_and_int64_are_strict():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    good = [_trade_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, 0)]
    for timestamp in (
        "+120000",
        "01",
        "120001",
        str(1 << 63),
        "１２００００",
        "9" * 129,
    ):
        rows = [list(row) for row in good]
        rows[0][0] = timestamp
        _assert_error(
            api,
            "kline_timestamp_invalid",
            plan,
            request,
            _body(_root(request, rows)),
        )


def test_kline_decimal_grammar_finiteness_and_ohlc_are_fail_closed():
    api = _api()
    plan, request = _plan_request("mark_kline_1m")
    good = [_mark_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, 0)]
    for invalid in (
        "NaN",
        "Infinity",
        "1e2",
        "+100",
        "01",
        "-0",
        "１.０",
        "1" * 129,
    ):
        rows = [list(row) for row in good]
        rows[0][1] = invalid
        _assert_error(api, "kline_value_invalid", plan, request, _body(_root(request, rows)))
    rows = [list(row) for row in good]
    rows[0][2] = "80"
    _assert_error(api, "kline_value_invalid", plan, request, _body(_root(request, rows)))


def test_trade_volume_and_turnover_are_exact_nonnegative_decimals():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    good = [_trade_row(value) for value in (2 * MINUTE_MS, MINUTE_MS, 0)]
    for index, invalid in ((5, "-1"), (6, "1e3")):
        rows = [list(row) for row in good]
        rows[0][index] = invalid
        _assert_error(api, "kline_value_invalid", plan, request, _body(_root(request, rows)))


def test_empty_funding_page_is_valid_but_never_proves_coverage():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    receipt = _accept(api, plan, request, _body(_root(request, [])))
    assert receipt.rows == ()
    assert receipt.row_count == 0
    assert receipt.first_timestamp_ms is None
    assert receipt.last_timestamp_ms is None
    assert receipt.funding_page_unsaturated_bool is True
    assert receipt.funding_coverage_proven_bool is False
    assert receipt.historical_market_data_coverage_proven_bool is False


def test_funding_input_order_is_unspecified_and_output_is_canonical_ascending():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=2)
    receipts = []
    for timestamps in ((MINUTE_MS, 0, 2 * MINUTE_MS), (0, 2 * MINUTE_MS, MINUTE_MS)):
        rows = [_funding_row(value) for value in timestamps]
        receipt = _accept(api, plan, request, _body(_root(request, rows)))
        receipts.append(receipt)
        assert all(type(row) is BybitFundingRate for row in receipt.rows)
        assert tuple(row.funding_time_ms for row in receipt.rows) == (
            0,
            MINUTE_MS,
            2 * MINUTE_MS,
        )
        assert receipt.source_row_order == "unspecified"
        assert receipt.canonical_row_order == "timestamp_ascending"
    assert receipts[0].raw_body_sha256 != receipts[1].raw_body_sha256
    assert receipts[0].timestamps_sha256 == receipts[1].timestamps_sha256
    assert receipts[0].rows_sha256 == receipts[1].rows_sha256
    assert receipts[0].rows == receipts[1].rows


def test_funding_page_rejects_200_row_saturation_before_row_validation():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=2)
    rows = [_funding_row(0)] * 200
    _assert_error(
        api,
        "funding_page_saturated",
        plan,
        request,
        _body(_root(request, rows)),
    )


def test_funding_199_row_boundary_is_accepted_and_201_is_saturated():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=198)
    rows = [_funding_row(value * MINUTE_MS) for value in reversed(range(199))]
    receipt = _accept(api, plan, request, _body(_root(request, rows)))
    assert receipt.row_count == 199
    assert receipt.first_timestamp_ms == 0
    assert receipt.last_timestamp_ms == 198 * MINUTE_MS
    rows_201 = [_funding_row(0)] * 201
    _assert_error(
        api,
        "funding_page_saturated",
        plan,
        request,
        _body(_root(request, rows_201)),
    )


def test_funding_page_row_count_may_not_exceed_request_target():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=1)
    rows = [_funding_row(0), _funding_row(MINUTE_MS), _funding_row(2 * MINUTE_MS)]
    _assert_error(
        api,
        "funding_row_limit_exceeded",
        plan,
        request,
        _body(_root(request, rows)),
    )


def test_funding_rows_require_exact_object_key_set_and_string_atoms():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=1)
    variants = (
        {"symbol": "BTCUSDT", "fundingRate": "0.1"},
        {**_funding_row(0), "extra": "x"},
        {**_funding_row(0), "fundingRateTimestamp": 0},
    )
    for row in variants:
        _assert_error(
            api,
            "funding_row_shape_invalid",
            plan,
            request,
            _body(_root(request, [row])),
        )


def test_funding_row_symbol_and_rate_are_strict():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=1)
    for mutation in (
        {"symbol": "ETHUSDT"},
        {"fundingRate": "NaN"},
        {"fundingRate": "1e-4"},
        {"fundingRate": "+0.1"},
    ):
        row = _funding_row(0)
        row.update(mutation)
        code = "response_identity_mismatch" if "symbol" in mutation else "funding_value_invalid"
        _assert_error(api, code, plan, request, _body(_root(request, [row])))


def test_funding_timestamps_must_be_canonical_minute_aligned_int64_strings():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=1)
    for timestamp in ("+0", "00", "1", str(1 << 63), "０", "9" * 129):
        row = _funding_row(0)
        row["fundingRateTimestamp"] = timestamp
        _assert_error(
            api,
            "funding_timestamp_invalid",
            plan,
            request,
            _body(_root(request, [row])),
        )


def test_funding_timestamps_must_be_unique():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=2)
    rows = [_funding_row(0), _funding_row(0)]
    _assert_error(
        api,
        "funding_duplicate_timestamp",
        plan,
        request,
        _body(_root(request, rows)),
    )


def test_funding_timestamps_must_stay_inside_exact_request_range():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=1, end_minute=2)
    for timestamp in (0, 3 * MINUTE_MS):
        _assert_error(
            api,
            "funding_timestamp_out_of_range",
            plan,
            request,
            _body(_root(request, [_funding_row(timestamp)])),
        )


def test_funding_plus_one_ms_window_accepts_only_next_aligned_minute():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=249)
    assert request.start_ms == 198 * MINUTE_MS + 1
    receipt = _accept(
        api,
        plan,
        request,
        _body(_root(request, [_funding_row(199 * MINUTE_MS)])),
    )
    assert receipt.first_timestamp_ms == 199 * MINUTE_MS
    _assert_error(
        api,
        "funding_timestamp_out_of_range",
        plan,
        request,
        _body(_root(request, [_funding_row(198 * MINUTE_MS)])),
    )


def test_receipt_binds_plan_request_body_timestamps_and_rows_with_sha256():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    receipt = _accept(api, plan, request, body)
    assert receipt.plan_sha256 == plan.sha256()
    assert receipt.sequence_id == request.sequence_id
    assert receipt.dataset == request.dataset
    assert receipt.endpoint == request.endpoint
    assert receipt.raw_body_sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.raw_body_byte_count == len(body)
    assert (
        receipt.max_response_body_bytes,
        receipt.max_json_depth,
        receipt.max_json_tokens,
    ) == (1_048_576, 8, 20_000)
    timestamps = tuple(row.open_time_ms for row in receipt.rows)
    assert receipt.timestamps_sha256 == _timestamp_digest(timestamps)
    assert len(receipt.request_sha256) == len(receipt.rows_sha256) == 64


def test_plan_digest_does_not_trust_rebound_plan_serialization_methods(monkeypatch):
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    expected = plan.sha256()
    monkeypatch.setattr(HistoricalCapturePlan, "sha256", lambda _self: "0" * 64)
    monkeypatch.setattr(
        HistoricalCapturePlan,
        "canonical_json_bytes",
        lambda _self: b'{"forged":true}\n',
    )
    receipt = _accept(api, plan, request, _valid_body(request))
    assert receipt.plan_sha256 == expected


def test_raw_body_digest_changes_with_whitespace_but_semantic_row_digest_does_not():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    compact = _valid_body(request)
    spaced = compact + b" \n"
    first = _accept(api, plan, request, compact)
    second = _accept(api, plan, request, spaced)
    assert first.raw_body_sha256 != second.raw_body_sha256
    assert first.timestamps_sha256 == second.timestamps_sha256
    assert first.rows_sha256 == second.rows_sha256
    assert first.rows == second.rows


def test_decimal_scale_variants_have_identical_typed_rows_and_row_digest():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    first = _accept(
        api,
        plan,
        request,
        _body(_root(request, [_funding_row(0, "0.1")])),
    )
    second = _accept(
        api,
        plan,
        request,
        _body(_root(request, [_funding_row(0, "0.1000")])),
    )
    assert first.raw_body_sha256 != second.raw_body_sha256
    assert first.rows == second.rows
    assert first.timestamps_sha256 == second.timestamps_sha256
    assert first.rows_sha256 == second.rows_sha256
    assert json.loads(first.canonical_json_bytes())["rows"][0]["funding_rate"] == "0.1"


def test_receipt_canonical_json_has_exact_lf_and_sha256():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=2)
    rows = [_funding_row(MINUTE_MS), _funding_row(0)]
    receipt = _accept(api, plan, request, _body(_root(request, rows)))
    data = receipt.canonical_json_bytes()
    assert type(data) is bytes
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    decoded = json.loads(data)
    assert data == _canonical_json_bytes(decoded)
    assert receipt.sha256() == hashlib.sha256(data).hexdigest()
    assert decoded["rows"][0]["funding_time_ms"] == 0
    assert decoded["rows"][0]["funding_rate"] == "0.0001"


def test_complete_one_row_receipt_and_component_hashes_match_literal_fixture():
    api = _api()
    plan, request = _plan_request("trade_kline_1m", start_minute=0, end_minute=0)
    body = _valid_body(request)
    receipt = _accept(api, plan, request, body)
    request_payload = {
        field.name: (
            [list(pair) for pair in request.params]
            if field.name == "params"
            else getattr(request, field.name)
        )
        for field in fields(request)
    }
    assert _canonical_json_bytes(request_payload) == EXPECTED_ONE_TRADE_REQUEST_BYTES
    assert hashlib.sha256(EXPECTED_ONE_TRADE_REQUEST_BYTES).hexdigest() == receipt.request_sha256
    assert receipt.plan_sha256 == "fe5cfa02780324f54bca7b5e050a1bd0b28703bd1cd760c391e81c16eef53c42"
    assert (
        receipt.request_sha256 == "492fe8d1fcf235195246d12931d27e087311af5339b0ffb6a06c979aa363b26a"
    )
    assert (
        receipt.raw_body_sha256
        == "82ca39daa542244e5f10d0c55cf10346247d056c9935151a0d8996d64db7fe52"
    )
    assert (
        receipt.timestamps_sha256
        == "c14196f132c1e9be0508ae80ab52fcb3e1d3fc05880415f3dc980971df207c9e"
    )
    assert receipt.rows_sha256 == "bf50c00bb5a6ff627cb55ff99ad6a7d887a6ab782ff8fba0ce63f3b257817986"
    assert hashlib.sha256(EXPECTED_ONE_TRADE_ROWS_BYTES).hexdigest() == receipt.rows_sha256
    assert receipt.canonical_json_bytes() == EXPECTED_ONE_TRADE_RECEIPT_BYTES
    assert receipt.sha256() == "0e71bf8f4047ca346a8f572b215846bea5109254ce3cfb45de0a6da5769aaac0"


def test_receipt_is_deeply_immutable_hashable_and_deterministic():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    body = _valid_body(request)
    first = _accept(api, plan, request, body)
    second = _accept(api, plan, request, body)
    assert first == second
    assert hash(first) == hash(second)
    assert hash(first.rows[0]) == hash(second.rows[0])
    with pytest.raises(FrozenInstanceError):
        first.symbol = "ETHUSDT"
    with pytest.raises(TypeError):
        first.rows[0] = first.rows[0]


def test_every_authority_and_coverage_guardrail_is_exact_false():
    api = _api()
    plan, request = _plan_request("funding_rate", start_minute=0, end_minute=0)
    receipt = _accept(api, plan, request, _body(_root(request, [])))
    guardrails = (
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
    assert tuple(getattr(receipt, name) for name in guardrails) == (False,) * len(guardrails)
    for name in guardrails:
        with pytest.raises(api.HistoricalResponseError, match="^receipt_factory_only$"):
            replace(receipt, **{name: True})


def test_receipt_is_factory_only_and_replace_cannot_forge_evidence():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    receipt = _accept(api, plan, request, _valid_body(request))
    with pytest.raises(api.HistoricalResponseError, match="^receipt_factory_only$"):
        api.HistoricalResponseReceipt()
    with pytest.raises(api.HistoricalResponseError, match="^receipt_factory_only$"):
        replace(receipt, raw_body_sha256="0" * 64)


def test_object_setattr_tampered_receipt_refuses_canonicalization_and_hashing():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    receipt = _accept(api, plan, request, _valid_body(request))
    object.__setattr__(receipt, "network_authorized_bool", True)
    with pytest.raises(api.HistoricalResponseError, match="^receipt_guardrails_invalid$"):
        receipt.canonical_json_bytes()
    with pytest.raises(api.HistoricalResponseError, match="^receipt_guardrails_invalid$"):
        receipt.sha256()


def test_forbidden_transport_path_clock_and_cap_kwargs_are_rejected():
    api = _api()
    plan, request = _plan_request("trade_kline_1m")
    values = {
        "plan": plan,
        "request": request,
        "http_status": 200,
        "content_type": "application/json",
        "raw_body_bytes": _valid_body(request),
    }
    for forbidden in (
        {"client": object()},
        {"headers": {}},
        {"base_url": "https://api.bybit.com"},
        {"path": "/tmp/response.json"},
        {"now_ms": 0},
        {"max_body_bytes": MAX_BODY + 1},
        {"persist": True},
    ):
        with pytest.raises(TypeError):
            api.accept_historical_response_page(**values, **forbidden)


def test_acceptance_calls_no_network_filesystem_or_wall_clock(monkeypatch):
    api = _api()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("forbidden_external_surface_called")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "time_ns", forbidden)
    monkeypatch.setattr(time, "monotonic", forbidden)

    plan, request = _plan_request("trade_kline_1m")
    receipt = _accept(api, plan, request, _valid_body(request))
    assert receipt.sha256() == hashlib.sha256(receipt.canonical_json_bytes()).hexdigest()
