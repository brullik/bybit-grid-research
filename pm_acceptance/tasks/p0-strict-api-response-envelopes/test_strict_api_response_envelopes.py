from __future__ import annotations

import ast
import json
import logging
import traceback
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest

import bybit_grid.bybit.client as client_mod
import bybit_grid.bybit.fgrid_constraints as fgrid_mod
import bybit_grid.bybit.models as models_mod


TASK_ID = "p0-strict-api-response-envelopes"
SENTINEL = "strict_api_response_envelope_unavailable"
CONTRACT_VERSION = "strict-envelope-v1"
REDACTED = "***REDACTED***"
ROOT = Path(client_mod.__file__).resolve().parents[3]
ORDINARY_TEST_SHA256 = {
    "tests/test_sprint_01_8_hotfix.py": "ef6bdee45a1281e78a34fe134ec341f098c68e80d68653680c55dbd8131a8e7f",
    "tests/test_sprint_02.py": "3be383f49a83feef18b5966cfecb4dbeaa8cf867f44fe2e9803d08c2362ba801",
}
REQUIRED_IMPLEMENTATION_PATHS = (
    "scripts/smoke_private_account.py",
    "src/bybit_grid/bybit/client.py",
    "src/bybit_grid/bybit/fgrid_constraints.py",
    "src/bybit_grid/bybit/models.py",
    "tests/test_sprint_01_8_hotfix.py",
    "tests/test_sprint_02.py",
)
RED_REQUIRED_PATHS = REQUIRED_IMPLEMENTATION_PATHS
account_smoke: Any | None = None


def _ordinary_contract(path: str) -> tuple[str, str] | None:
    try:
        raw = (ROOT / path).read_bytes()
        source = raw.decode("utf-8", "strict")
        tree = ast.parse(source, filename=path)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    values: list[str] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "STRICT_API_RESPONSE_ENVELOPE_TEST_CONTRACT"
            and isinstance(statement.value, ast.Constant)
            and type(statement.value.value) is str
        ):
            values.append(statement.value.value)
    if values != [CONTRACT_VERSION]:
        return None
    import hashlib

    return CONTRACT_VERSION, hashlib.sha256(raw).hexdigest()


def _available() -> None:
    global account_smoke
    modules = (client_mod, fgrid_mod, models_mod)
    if any(
        getattr(module, "STRICT_API_RESPONSE_ENVELOPE_CONTRACT", None)
        != CONTRACT_VERSION
        for module in modules
    ):
        raise RuntimeError(SENTINEL)
    if account_smoke is None:
        try:
            import importlib

            account_smoke = importlib.import_module("scripts.smoke_private_account")
        except ModuleNotFoundError as exc:
            raise RuntimeError(SENTINEL) from exc
    if (
        getattr(account_smoke, "STRICT_API_RESPONSE_ENVELOPE_CONTRACT", None)
        != CONTRACT_VERSION
    ):
        raise RuntimeError(SENTINEL)
    for path, expected_sha in ORDINARY_TEST_SHA256.items():
        if _ordinary_contract(path) != (CONTRACT_VERSION, expected_sha):
            raise RuntimeError(SENTINEL)


def _client() -> client_mod.BybitClient:
    instance = object.__new__(client_mod.BybitClient)
    instance.stats = client_mod.BybitClientStats()
    return instance


def _response_bytes(body: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=body)


def _response(payload: Any, status: int = 200) -> httpx.Response:
    return _response_bytes(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        status,
    )


def _reason(exc_info: pytest.ExceptionInfo[BaseException]) -> str:
    return getattr(exc_info.value, "reason_code", "")


class _CallContextVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...], ast.Call]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append((tuple(self.class_stack), tuple(self.function_stack), node))
        self.generic_visit(node)


def _attribute_path(node: ast.expr) -> tuple[str, ...] | None:
    atoms: list[str] = []
    while isinstance(node, ast.Attribute):
        atoms.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    atoms.append(node.id)
    return tuple(reversed(atoms))


def _is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _meta() -> dict[str, Any]:
    return {
        "symbol": "XUSDT",
        "lastPrice": 1.0,
        "tickSize": "0.1",
        "range_width_pct": 0.02,
        "min_price": 0.9,
        "max_price": 1.1,
        "stop_loss_price": 0.8,
        "cell_number_requested": 5,
        "leverage_requested": 2,
        "init_margin_requested": 5.0,
    }


def _ranges() -> dict[str, Any]:
    return {
        "investment": {"from": "4", "to": "100"},
        "cell_number": {"from": "2", "to": "10"},
        "leverage": {"from": "1", "to": "5"},
    }


def test_v5_exact_integer_success() -> None:
    _available()
    payload = {"retCode": 0, "retMsg": "OK", "result": {"ok": True}}
    assert _client()._handle_response("/v5/test", _response(payload), "test") == payload


def test_v5_exact_integer_api_failure() -> None:
    _available()
    with pytest.raises(models_mod.BybitAPIError) as exc_info:
        _client()._handle_response(
            "/v5/test", _response({"retCode": 10001, "retMsg": "bad"}), "test"
        )
    assert type(exc_info.value) is models_mod.BybitAPIError
    assert exc_info.value.ret_code == 10001
    assert exc_info.value.reason_code == "api_error"


def test_http_failure_cannot_be_overridden_by_success_marker() -> None:
    _available()
    for status in (400, 429, 500):
        with pytest.raises(models_mod.BybitAPIError) as exc_info:
            _client()._handle_response(
                "/v5/test", _response({"retCode": 0}, status), "test"
            )
        assert exc_info.value.status_code == status
        assert _reason(exc_info) == "http_status_error"
        assert client_mod._is_retryable(exc_info.value) is (status in {429, 500})


def test_retryable_retcode_is_exact_integer_only() -> None:
    _available()
    with pytest.raises(models_mod.BybitAPIError) as retryable:
        _client()._handle_response("/v5/test", _response({"retCode": 10006}), "test")
    assert client_mod._is_retryable(retryable.value)
    with pytest.raises(models_mod.BybitResponseEnvelopeError) as invalid:
        _client()._handle_response("/v5/test", _response({"retCode": "10006"}), "test")
    assert _reason(invalid) == "response_marker_type_invalid"
    assert not client_mod._is_retryable(invalid.value)
    with pytest.raises(models_mod.BybitAPIError) as native_retcode:
        _client()._handle_validate_response(
            "/v5/fgridbot/validate", _response({"retCode": 10006}), "test"
        )
    assert client_mod._is_retryable(native_retcode.value)
    with pytest.raises(models_mod.BybitAPIError) as native_status:
        _client()._handle_validate_response(
            "/v5/fgridbot/validate", _response({"status_code": 10006}), "test"
        )
    assert native_status.value.ret_code == 10006
    assert not client_mod._is_retryable(native_status.value)


def test_native_validate_retcode_success() -> None:
    _available()
    payload = {"retCode": 0, "result": {}}
    assert (
        _client()._handle_validate_response(
            "/v5/fgridbot/validate", _response(payload), "test"
        )
        == payload
    )


def test_native_validate_status_code_success() -> None:
    _available()
    payload = {"status_code": 200, "result": {}}
    assert (
        _client()._handle_validate_response(
            "/v5/fgridbot/validate", _response(payload), "test"
        )
        == payload
    )


def test_native_validate_non_success_marker_is_api_error() -> None:
    _available()
    for payload, code in (({"retCode": 10001}, 10001), ({"status_code": 400}, 400)):
        with pytest.raises(models_mod.BybitAPIError) as exc_info:
            _client()._handle_validate_response(
                "/v5/fgridbot/validate", _response(payload), "test"
            )
        assert type(exc_info.value) is models_mod.BybitAPIError
        assert exc_info.value.ret_code == code


def test_native_validate_compatible_dual_success() -> None:
    _available()
    payload = {"retCode": 0, "status_code": 200, "result": {}}
    assert (
        _client()._handle_validate_response(
            "/v5/fgridbot/validate", _response(payload), "test"
        )
        == payload
    )


def test_native_validate_compatible_dual_failure() -> None:
    _available()
    for payload, retryable in (
        ({"retCode": 10001, "status_code": 400}, False),
        ({"retCode": 10006, "status_code": 400}, True),
    ):
        with pytest.raises(models_mod.BybitAPIError) as exc_info:
            _client()._handle_validate_response(
                "/v5/fgridbot/validate", _response(payload), "test"
            )
        assert type(exc_info.value) is models_mod.BybitAPIError
        assert exc_info.value.ret_code == payload["retCode"]
        assert client_mod._is_retryable(exc_info.value) is retryable


def test_native_validate_conflicting_markers_fail_closed() -> None:
    _available()
    for payload in (
        {"retCode": 0, "status_code": 400},
        {"retCode": 10001, "status_code": 200},
    ):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_validate_response(
                "/v5/fgridbot/validate", _response(payload), "test"
            )
        assert _reason(exc_info) == "response_marker_conflict"


def test_empty_body_fails_closed() -> None:
    _available()
    for status in (200, 500):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response_bytes(b"", status), "test")
        assert _reason(exc_info) == "response_body_empty"


def test_whitespace_and_malformed_json_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _available()
    for body in (
        b"   \r\n\t",
        b"{",
        b'{"retCode":0 trailing}',
        b'{"retCode":0,"result":' + (b"1" * 5000) + b"}",
    ):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response_bytes(body), "test")
        assert _reason(exc_info) == "response_json_invalid"
    recursion_response = _response_bytes(b'{"retCode":0,"result":1.5}', 500)

    def raise_recursion(_value: str) -> float:
        raise RecursionError

    with monkeypatch.context() as patch:
        patch.setattr(client_mod, "_parse_finite_float", raise_recursion)
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as recursion_error:
            _client()._handle_response("/v5/test", recursion_response, "test")
    assert _reason(recursion_error) == "response_json_invalid"
    assert recursion_error.value.__cause__ is None
    assert recursion_error.value.__context__ is None
    assert client_mod._is_retryable(recursion_error.value)


def test_invalid_utf8_fails_without_raw_evidence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _available()
    caplog.set_level(logging.DEBUG)
    canary = b"UTF8_BODY_CANARY_\xff"
    with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
        _client()._handle_response("/v5/test", _response_bytes(canary), "test")
    assert _reason(exc_info) == "response_utf8_invalid"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    evidence = (
        str(exc_info.value)
        + "".join(traceback.format_exception(exc_info.value))
        + caplog.text
    ).encode()
    assert b"UTF8_BODY_CANARY" not in evidence


def test_duplicate_top_level_marker_rejected() -> None:
    _available()
    body = b'{"retCode":0,"retCode":1}'
    with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
        _client()._handle_response("/v5/test", _response_bytes(body), "test")
    assert _reason(exc_info) == "response_json_duplicate_key"


def test_duplicate_nested_key_rejected() -> None:
    _available()
    body = b'{"retCode":0,"result":{"x":1,"x":2}}'
    with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
        _client()._handle_response("/v5/test", _response_bytes(body), "test")
    assert _reason(exc_info) == "response_json_duplicate_key"


def test_nonfinite_json_constants_rejected() -> None:
    _available()
    for constant in (b"NaN", b"Infinity", b"-Infinity", b"1e400", b"-1e400"):
        body = b'{"retCode":0,"result":{"value":' + constant + b"}}"
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response_bytes(body), "test")
        assert _reason(exc_info) == "response_json_nonfinite"


def test_non_object_json_roots_rejected() -> None:
    _available()
    for body in (b"[]", b"null", b'"text"', b"1", b"true"):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response_bytes(body), "test")
        assert _reason(exc_info) == "response_root_not_object"


def test_missing_success_marker_rejected_on_http_2xx() -> None:
    _available()
    for payload in ({}, {"retMsg": "OK"}, {"result": {"ok": True}}):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response(payload), "test")
        assert _reason(exc_info) == "response_marker_missing"


def test_retcode_requires_exact_int64() -> None:
    _available()
    values = (None, True, False, 0.0, "0", 2**63, -(2**63) - 1)
    for value in values:
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response(
                "/v5/test", _response({"retCode": value}), "test"
            )
        assert _reason(exc_info) == "response_marker_type_invalid"
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as native_exc:
            _client()._handle_validate_response(
                "/v5/fgridbot/validate",
                _response({"retCode": value}),
                "test",
            )
        assert _reason(native_exc) == "response_marker_type_invalid"


def test_native_status_code_requires_exact_int64() -> None:
    _available()
    values = (None, True, False, 200.0, "200", 2**63, -(2**63) - 1)
    for value in values:
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_validate_response(
                "/v5/fgridbot/validate",
                _response({"status_code": value}),
                "test",
            )
        assert _reason(exc_info) == "response_marker_type_invalid"


def test_status_alias_forbidden_for_v5_gets() -> None:
    _available()
    for payload in ({"status_code": 200}, {"retCode": 0, "status_code": 200}):
        with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
            _client()._handle_response("/v5/test", _response(payload), "test")
        assert _reason(exc_info) == "response_marker_alias_forbidden"


def test_message_evidence_requires_exact_strings() -> None:
    _available()
    for key in ("retMsg", "debug_msg"):
        for value in (None, True, 7, 1.5, [], {}):
            with pytest.raises(models_mod.BybitResponseEnvelopeError) as exc_info:
                _client()._handle_response(
                    "/v5/test", _response({"retCode": 0, key: value}), "test"
                )
            assert _reason(exc_info) == "response_message_type_invalid"
            with pytest.raises(models_mod.BybitResponseEnvelopeError) as native_exc:
                _client()._handle_validate_response(
                    "/v5/fgridbot/validate",
                    _response({"retCode": 0, key: value}),
                    "test",
                )
            assert _reason(native_exc) == "response_message_type_invalid"


def test_api_error_evidence_is_safe_by_construction(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    _available()
    caplog.set_level(logging.INFO)
    canaries = (
        "RET_MESSAGE_CANARY",
        "DEBUG_MESSAGE_CANARY",
        "NESTED_SECRET_CANARY",
        "REASON_CANARY",
        "LIMIT_HEADER_CANARY",
        "LIMIT_STATUS_HEADER_CANARY",
        "LIMIT_RESET_HEADER_CANARY",
    )
    payload = {
        "retCode": 10001,
        "retMsg": canaries[0],
        "debug_msg": canaries[1],
        "result": {"api_secret": canaries[2]},
    }
    response = httpx.Response(
        200,
        json=payload,
        headers={
            "X-Bapi-Limit": canaries[4],
            "X-Bapi-Limit-Status": canaries[5],
            "X-Bapi-Limit-Reset-Timestamp": canaries[6],
        },
    )
    with pytest.raises(models_mod.BybitAPIError) as exc_info:
        _client()._handle_response("/v5/test", response, "test")
    error = exc_info.value
    assert "rate_limit_headers" not in error.response_data
    persisted = tmp_path / "error_evidence.json"
    persisted.write_text(
        json.dumps(error.response_data, sort_keys=True), encoding="utf-8"
    )
    evidence = json.dumps(
        {
            "text": str(error),
            "ret_msg": error.ret_msg,
            "debug_msg": error.debug_msg,
            "response_data": error.response_data,
            "logs": caplog.text,
        },
        sort_keys=True,
    ) + persisted.read_text(encoding="utf-8")
    for canary in canaries:
        assert canary not in evidence
    assert REDACTED in evidence
    direct = models_mod.BybitAPIError(
        "/v5/test",
        400,
        10001,
        canaries[0],
        canaries[1],
        {"api_secret": canaries[2]},
        reason_code=canaries[3],
    )
    assert canaries[3] not in str(direct)
    assert direct.reason_code == "api_error"
    invalid_atoms = models_mod.BybitAPIError(
        "/v5/test",
        True,
        2**63,
        None,
        None,
        None,
        reason_code={"reason": canaries[3]},
    )
    assert invalid_atoms.status_code is None
    assert invalid_atoms.ret_code is None
    assert invalid_atoms.reason_code == "api_error"
    assert canaries[3] not in str(invalid_atoms)

    class HostileKey:
        __hash__ = object.__hash__

        def __eq__(self, _other: object) -> bool:
            raise AssertionError("response keys must not run caller equality")

        def __ne__(self, _other: object) -> bool:
            raise AssertionError("response keys must not run caller inequality")

    hostile_key_error = models_mod.BybitAPIError(
        "/v5/test",
        400,
        10001,
        None,
        None,
        {HostileKey(): "safe"},
    )
    assert type(hostile_key_error.response_data) is dict
    deep_response: dict[str, Any] = {"leaf": "safe"}
    for _ in range(2000):
        deep_response = {"nested": deep_response}
    deep_error = models_mod.BybitAPIError(
        "/v5/test",
        200,
        10006,
        None,
        None,
        deep_response,
    )
    assert deep_error.response_data == {}
    assert deep_error.status_code == 200
    assert deep_error.ret_code == 10006
    assert deep_error.reason_code == "api_error"
    assert client_mod._is_retryable(deep_error)


def test_downstream_classifiers_and_transport_remain_fail_closed(
    tmp_path: Path,
) -> None:
    _available()
    assert RED_REQUIRED_PATHS == REQUIRED_IMPLEMENTATION_PATHS
    assert all((ROOT / path).is_file() for path in RED_REQUIRED_PATHS)
    assert account_smoke._status(None) == "not-run"
    assert account_smoke._status({"retCode": 0}) == "ok"
    malformed: tuple[Any, ...] = (
        {},
        {"retCode": None},
        {"retCode": "0"},
        {"retCode": True},
        {"retCode": 0, "status_code": 400},
        {"retCode": 0, "retMsg": None},
        {"retCode": 0, "debug_msg": []},
        [],
    )
    for payload in malformed:
        assert account_smoke._status(payload) == "error"
        row = fgrid_mod.parse_validate_response(
            _meta(),
            {**payload, "result": _ranges()} if type(payload) is dict else payload,
            status_code=200,
        )
        assert row["envelope_valid"] is False
        assert row["validate_ok"] is False
        assert row["feasible_bybit"] is False
        assert row["feasible_user_5usdt_rule"] is False
        assert row["blocker_reason"] == "response_envelope_invalid"
        assert row["retCode"] is None or type(row["retCode"]) is int
        assert row["status_code"] is None or type(row["status_code"]) is int
        assert row["retMsg"] is None
        assert row["debug_msg"] is None
    nested_message = fgrid_mod.parse_validate_response(
        _meta(),
        {"retCode": 0, "result": {**_ranges(), "debug_msg": 7}},
        status_code=200,
    )
    assert nested_message["envelope_valid"] is False
    assert nested_message["validate_ok"] is False
    assert nested_message["feasible_bybit"] is False
    assert nested_message["feasible_user_5usdt_rule"] is False
    assert nested_message["blocker_reason"] == "response_envelope_invalid"
    assert nested_message["debug_msg"] is None

    semantic_rejection = fgrid_mod.parse_validate_response(
        _meta(),
        {"retCode": 0, "result": {**_ranges(), "debug_msg": "param error"}},
    )
    assert semantic_rejection["schema_or_param_rejected"] is True
    assert semantic_rejection["validate_ok"] is False
    assert semantic_rejection["debug_msg"] == REDACTED

    fgrid_canary = "FGRID_PERSIST_CANARY"
    safe_row = fgrid_mod.parse_validate_response(
        _meta(),
        {
            "retCode": 0,
            "retMsg": fgrid_canary,
            "result": {**_ranges(), "debug_msg": fgrid_canary},
        },
        status_code=True,
    )
    assert safe_row["validate_ok"] is True
    assert safe_row["retMsg"] == REDACTED
    assert safe_row["debug_msg"] == REDACTED
    assert safe_row["http_status_code"] is None
    constraints_path = tmp_path / "constraints.parquet"
    fgrid_mod.append_constraints(constraints_path, [safe_row])
    persisted_rows = pl.read_parquet(constraints_path).to_dicts()
    assert fgrid_canary not in json.dumps(persisted_rows, sort_keys=True, default=str)
    assert fgrid_canary.encode() not in constraints_path.read_bytes()
    client_source = Path(client_mod.__file__).read_text(encoding="utf-8")
    client_tree = ast.parse(client_source, filename=str(client_mod.__file__))
    assert client_mod.CANONICAL_FGRID_VALIDATE_ENDPOINT == "/v5/fgridbot/validate"
    parent_by_child = {
        child: parent
        for parent in ast.walk(client_tree)
        for child in ast.iter_child_nodes(parent)
    }
    audit = _CallContextVisitor()
    audit.visit(client_tree)
    post_calls = [
        entry
        for entry in audit.calls
        if isinstance(entry[2].func, ast.Attribute) and entry[2].func.attr == "post"
    ]
    assert len(post_calls) == 1
    post_classes, post_functions, post_call = post_calls[0]
    assert _attribute_path(post_call.func) == ("self", "private_http", "post")
    private_post_attributes = [
        node
        for node in ast.walk(client_tree)
        if isinstance(node, ast.Attribute)
        and _attribute_path(node) == ("self", "private_http", "post")
    ]
    assert private_post_attributes == [post_call.func]
    assert not any(
        isinstance(call.func, ast.Attribute) and call.func.attr in {"request", "send"}
        for _, _, call in audit.calls
    )
    assert post_classes == ("BybitClient",)
    assert post_functions == ("_private_validate_post",)
    assert len(post_call.args) == 1
    assert _is_name(post_call.args[0], "CANONICAL_FGRID_VALIDATE_ENDPOINT")
    assert len(post_call.keywords) == 2
    assert all(keyword.arg is not None for keyword in post_call.keywords)
    assert {keyword.arg for keyword in post_call.keywords} == {"content", "headers"}
    post_keywords = {keyword.arg: keyword.value for keyword in post_call.keywords}
    assert _attribute_path(post_keywords["content"]) == ("prepared", "json_body")
    assert _is_name(post_keywords["headers"], "headers")
    post_assign = parent_by_child.get(post_call)
    assert isinstance(post_assign, ast.Assign)
    assert post_assign.value is post_call
    assert len(post_assign.targets) == 1
    assert _is_name(post_assign.targets[0], "response")

    validate_calls = [
        entry
        for entry in audit.calls
        if _attribute_path(entry[2].func) == ("self", "_handle_validate_response")
    ]
    assert len(validate_calls) == 1
    validate_classes, validate_functions, validate_call = validate_calls[0]
    assert validate_classes == ("BybitClient",)
    assert validate_functions == ("_private_validate_post",)
    assert len(validate_call.args) == 3
    assert _is_name(validate_call.args[0], "CANONICAL_FGRID_VALIDATE_ENDPOINT")
    assert _is_name(validate_call.args[1], "response")
    assert (
        isinstance(validate_call.args[2], ast.Constant)
        and type(validate_call.args[2].value) is str
        and validate_call.args[2].value == "bybit_post_validate"
    )
    assert validate_call.keywords == []
    validate_assign = parent_by_child.get(validate_call)
    assert isinstance(validate_assign, ast.Assign)
    assert validate_assign.value is validate_call
    assert len(validate_assign.targets) == 1
    assert _is_name(validate_assign.targets[0], "data")

    validate_methods = [
        node
        for node in ast.walk(client_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_private_validate_post"
        and isinstance(parent_by_child.get(node), ast.ClassDef)
        and parent_by_child[node].name == "BybitClient"
    ]
    assert len(validate_methods) == 1
    stored_names = [
        node.id
        for node in ast.walk(validate_methods[0])
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    ]
    assert stored_names.count("response") == 1
    assert stored_names.count("data") == 1
    data_returns = [
        node
        for node in ast.walk(validate_methods[0])
        if isinstance(node, ast.Return) and _is_name(node.value, "data")
    ]
    assert len(data_returns) == 1

    method_calls = [
        call
        for classes, functions, call in audit.calls
        if classes == ("BybitClient",) and functions == ("_private_validate_post",)
    ]
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "_authorize_active_attempt"
        for call in method_calls
    )
    assert any(
        _attribute_path(call.func) == ("self", "_private_headers")
        for call in method_calls
    )
    with pytest.raises(client_mod.ValidateOnlyBoundaryError) as wrong_endpoint:
        _client()._handle_validate_response(
            "/v5/market/tickers", _response({"status_code": 200}), "test"
        )
    assert "validate_response_endpoint_forbidden" in str(wrong_endpoint.value)
    with pytest.raises(Exception) as forbidden:
        client_mod.BybitClient.private_post(object(), "/v5/order/create", {})
    assert "generic_private_post_forbidden" in str(forbidden.value)
