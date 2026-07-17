from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import types
from decimal import Decimal
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

import bybit_grid.bybit.fgrid_constraints as fgrid_mod
from bybit_grid.bybit.models import BybitAPIError


TASK_ID = "p1-native-grid-validate-result-semantics"
SENTINEL = "native_grid_validate_result_contract_unavailable"
CONTRACT_VERSION = "native-grid-validate-result-v1"
TEST_CONTRACT_NAME = "NATIVE_GRID_VALIDATE_RESULT_TEST_CONTRACT"
MODULE_CONTRACT_NAME = "NATIVE_GRID_VALIDATE_RESULT_CONTRACT"
SWEEP_CONTRACT_NAME = "STRICT_NATIVE_GRID_VALIDATE_SWEEP_CONTRACT"
ROOT = Path(fgrid_mod.__file__).resolve().parents[3]
ORDINARY_TEST_PATH = "tests/test_native_grid_validate_result_semantics.py"
ORDINARY_TEST_SHA256 = (
    "8bd75bdaad12b07e09b833527e6e776db86d7e59b5671abaacf6db5f92be91d0"
)
REQUIRED_IMPLEMENTATION_PATHS = (
    "scripts/validate_universe_fgrid_constraints.py",
    "src/bybit_grid/bybit/fgrid_constraints.py",
    ORDINARY_TEST_PATH,
)
RED_REQUIRED_PATHS = REQUIRED_IMPLEMENTATION_PATHS
RANGE_NAMES = (
    "investment",
    "cell_number",
    "leverage",
    "min_price",
    "max_price",
    "entry_price",
    "stop_loss_price",
    "take_profit_price",
    "profit",
)
FALSE_ON_INVALID = (
    "feasible_bybit",
    "min_investment_feasible_at_5usdt",
    "feasible_user_5usdt_rule",
    "target_init_margin_inside_validate_range",
)
ERROR_EVIDENCE_KEYS = {
    "reason_code",
    "http_status_code",
    "retCode",
    "retMsg",
    "debug_msg",
    "response_data",
}
RESPONSE_EVIDENCE_KEYS = {"retCode", "status_code", "retMsg", "result"}
RESULT_EVIDENCE_KEYS = {"status_code", "check_code", "debug_msg"}
_sweep_module: Any | None = None


def _exact_assignment(path: Path, name: str) -> str | None:
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    values: list[str] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and isinstance(statement.value, ast.Constant)
            and type(statement.value.value) is str
        ):
            values.append(statement.value.value)
    return values[0] if values == [CONTRACT_VERSION] else None


def _ordinary_contract() -> tuple[str, str] | None:
    path = ROOT / ORDINARY_TEST_PATH
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if _exact_assignment(path, TEST_CONTRACT_NAME) != CONTRACT_VERSION:
        return None
    return CONTRACT_VERSION, hashlib.sha256(raw).hexdigest()


def _available() -> None:
    if getattr(fgrid_mod, MODULE_CONTRACT_NAME, None) != CONTRACT_VERSION:
        raise RuntimeError(SENTINEL)
    script_path = ROOT / REQUIRED_IMPLEMENTATION_PATHS[0]
    if _exact_assignment(script_path, SWEEP_CONTRACT_NAME) != CONTRACT_VERSION:
        raise RuntimeError(SENTINEL)
    if _ordinary_contract() != (CONTRACT_VERSION, ORDINARY_TEST_SHA256):
        raise RuntimeError(SENTINEL)


def _load_sweep() -> Any:
    global _sweep_module
    if _sweep_module is not None:
        return _sweep_module
    script_path = ROOT / REQUIRED_IMPLEMENTATION_PATHS[0]
    spec = importlib.util.spec_from_file_location(
        "_p1_native_grid_validate_result_sweep",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("strict sweep script is not importable")
    module = importlib.util.module_from_spec(spec)
    scripts_stub = types.ModuleType("scripts")
    scripts_stub.__path__ = [str(ROOT / "scripts")]
    build_universe_stub = types.ModuleType("scripts.build_universe")

    def build_universe(*_args: object, **_kwargs: object) -> dict[str, int]:
        return {"selected": 0}

    build_universe_stub.build_universe = build_universe
    prior_modules = {
        name: sys.modules.get(name) for name in ("scripts", "scripts.build_universe")
    }
    prior_path = list(sys.path)
    try:
        sys.modules["scripts"] = scripts_stub
        sys.modules["scripts.build_universe"] = build_universe_stub
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = prior_path
        for name, prior in prior_modules.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    _sweep_module = module
    return module


def _meta(symbol: str = "XUSDT") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "profile_name": "strict_fixture",
        "lastPrice": "100",
        "tickSize": "0.1",
        "range_width_pct": "0.10",
        "min_price": "95",
        "max_price": "105",
        "stop_loss_price": "90",
        "cell_number_requested": 5,
        "leverage_requested": 2,
        "init_margin_requested": "5",
        "stop_loss_mult": "0.95",
    }


def _result() -> dict[str, Any]:
    return {
        "status_code": 200,
        "check_code": "FGRID_CHECK_CODE_UNSPECIFIED",
        "debug_msg": "",
        "investment": {"from": "4", "to": "100"},
        "cell_number": {"from": "2", "to": "10"},
        "leverage": {"from": "1", "to": "5"},
        "min_price": {"from": "90", "to": "100"},
        "max_price": {"from": "100", "to": "110"},
        "entry_price": {"from": "90", "to": "110"},
        "stop_loss_price": {"from": "80", "to": "94"},
        "take_profit_price": {"from": "106", "to": "120"},
        "profit": {"from": "0", "to": "10"},
    }


def _response() -> dict[str, Any]:
    return {"retCode": 0, "retMsg": "", "result": _result()}


def _parse(
    meta: dict[str, Any] | None = None,
    response: dict[str, Any] | object | None = None,
    *,
    http_status: int | None = 200,
    error_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fgrid_mod.parse_strict_validate_response(
        _meta() if meta is None else meta,
        _response() if response is None else response,
        status_code=http_status,
        raw_path="data/processed/fgrid_validate_raw_redacted/X.json",
        error_evidence=error_evidence,
    )


def _assert_rejected(row: dict[str, Any]) -> None:
    assert row["native_grid_validate_result_contract"] == CONTRACT_VERSION
    assert type(row["result_schema_valid"]) is bool
    for field in FALSE_ON_INVALID:
        assert row[field] is False
    assert type(row["blocker_reason"]) is str and row["blocker_reason"]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _copy_with_symbol(row: dict[str, Any], symbol: str) -> dict[str, Any]:
    copied = dict(row)
    copied["symbol"] = symbol
    copied["profile_name"] = symbol.lower()
    return copied


def test_strict_parser_accepts_only_complete_official_example_shape() -> None:
    _available()
    assert RED_REQUIRED_PATHS == REQUIRED_IMPLEMENTATION_PATHS
    assert all((ROOT / path).is_file() for path in RED_REQUIRED_PATHS)
    row = _parse()
    assert row["native_grid_validate_result_contract"] == CONTRACT_VERSION
    assert row["result_schema_valid"] is True
    assert row["validate_ok"] is True
    assert row["feasible_bybit"] is True
    assert row["min_investment_feasible_at_5usdt"] is True
    assert row["feasible_user_5usdt_rule"] is True
    assert row["target_init_margin_inside_validate_range"] is True
    assert row["blocker_reason"] is None
    assert row["status_code"] == 200
    assert row["check_code"] == "FGRID_CHECK_CODE_UNSPECIFIED"
    assert row["investment_min"] == 4.0
    assert row["investment_max"] == 100.0
    assert row["error_evidence_json"] is None
    assert _parse(http_status=None)["validate_ok"] is True


def test_strict_parser_never_falls_back_to_top_level_result_fields() -> None:
    _available()
    ranges = _result()
    flattened = {
        "retCode": 0,
        **ranges,
        "investment_from": "4",
        "investment_to": "100",
    }
    aliased_result = _result()
    aliased_result.pop("investment")
    aliased_result["investment_from"] = "4"
    aliased_result["investment_to"] = "100"
    for payload in (
        flattened,
        {"retCode": 0, "result": None, **ranges},
        {"retCode": 0, "result": aliased_result},
        {"retCode": 0, "result": {**ranges, "investment": None}},
    ):
        _assert_rejected(_parse(response=payload))
    assert (
        _parse(response=flattened)["blocker_reason"] == "native_result_schema_invalid"
    )


def test_required_result_fields_and_range_bounds_are_complete() -> None:
    _available()
    for field in ("status_code", "check_code", "debug_msg", *RANGE_NAMES):
        payload = _response()
        del payload["result"][field]
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["result_schema_valid"] is False
    for range_name in RANGE_NAMES:
        for bound in ("from", "to"):
            payload = _response()
            del payload["result"][range_name][bound]
            row = _parse(response=payload)
            _assert_rejected(row)
            assert row["result_schema_valid"] is False

    class DictSubclass(dict[str, Any]):
        pass

    payload = _response()
    payload["result"]["investment"] = DictSubclass(payload["result"]["investment"])
    assert _parse(response=payload)["result_schema_valid"] is False
    extra_bound = _response()
    extra_bound["result"]["investment"]["unit"] = "USDT"
    assert _parse(response=extra_bound)["result_schema_valid"] is False


def test_status_and_check_code_require_exact_success_pair() -> None:
    _available()

    class StringSubclass(str):
        pass

    for value in (None, True, 200.0, "200", 0, 400):
        payload = _response()
        payload["result"]["status_code"] = value
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["validate_ok"] is False
    for value in (
        None,
        True,
        "",
        "FGRID_CHECK_CODE_SUCCESS",
        "FGRID_CHECK_CODE_REJECTED",
        StringSubclass("FGRID_CHECK_CODE_UNSPECIFIED"),
    ):
        payload = _response()
        payload["result"]["check_code"] = value
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["validate_ok"] is False
    for outer in ({}, {"retCode": 1, "result": _result()}):
        row = _parse(response=outer)
        _assert_rejected(row)
        assert row["validate_ok"] is False
        assert row["blocker_reason"] == "response_envelope_invalid"
    for http_status in (True, 199, 201, 400, "200"):
        row = _parse(http_status=http_status)  # type: ignore[arg-type]
        _assert_rejected(row)
        assert row["validate_ok"] is False
        assert row["blocker_reason"] == "response_envelope_invalid"


def test_debug_message_must_be_exact_empty_string_for_success() -> None:
    _available()

    class StringSubclass(str):
        pass

    for value in (None, True, 0, [], {}, "param error", " ", StringSubclass("")):
        payload = _response()
        payload["result"]["debug_msg"] = value
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["validate_ok"] is False
        assert row["blocker_reason"] in {
            "response_envelope_invalid",
            "native_result_schema_invalid",
            "native_check_rejected",
        }
    top_level = _response()
    top_level["debug_msg"] = "TOP_LEVEL_DEBUG_CANARY"
    row = _parse(response=top_level)
    _assert_rejected(row)
    assert row["validate_ok"] is False
    assert row["blocker_reason"] == "native_check_rejected"


def test_range_atoms_must_be_finite_decimal_strings() -> None:
    _available()

    class StringSubclass(str):
        pass

    for value in (
        None,
        True,
        4,
        4.0,
        Decimal("4"),
        "",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        "1e9999",
        "1e-9999",
        StringSubclass("4"),
    ):
        payload = _response()
        payload["result"]["investment"]["from"] = value
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["result_schema_valid"] is False


def test_range_bounds_must_be_ordered_and_domain_valid() -> None:
    _available()
    mutations = (
        ("investment", "from", "101"),
        ("investment", "from", "-1"),
        ("investment", "from", "0"),
        ("cell_number", "from", "2.5"),
        ("cell_number", "from", "0"),
        ("leverage", "from", "0"),
        ("min_price", "from", "0"),
        ("profit", "from", "-0.01"),
    )
    for range_name, bound, value in mutations:
        payload = _response()
        payload["result"][range_name][bound] = value
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["result_schema_valid"] is False


def test_requested_meta_values_must_be_finite_and_non_boolean() -> None:
    _available()
    requested_fields = (
        "cell_number_requested",
        "leverage_requested",
        "init_margin_requested",
        "min_price",
        "max_price",
        "stop_loss_price",
    )
    for field in requested_fields:
        for value in (None, True, False, float("nan"), float("inf"), "NaN", "Infinity"):
            meta = _meta()
            meta[field] = value
            _assert_rejected(_parse(meta=meta))
    for meta in (
        {**_meta(), "cell_number_requested": 2.5},
        {**_meta(), "min_price": "105", "max_price": "95"},
        {**_meta(), "stop_loss_price": "95", "min_price": "95"},
    ):
        _assert_rejected(_parse(meta=meta))


def test_each_requested_value_must_be_inside_its_named_range() -> None:
    _available()
    outside = {
        "cell_number_requested": 11,
        "leverage_requested": 6,
        "init_margin_requested": "101",
        "min_price": "101",
        "max_price": "99",
        "stop_loss_price": "95",
    }
    for field, value in outside.items():
        meta = _meta()
        meta[field] = value
        row = _parse(meta=meta)
        _assert_rejected(row)
        assert row["result_schema_valid"] is True
        assert row["blocker_reason"] == "requested_values_outside_validate_ranges"


def test_range_edges_are_inclusive_and_grid_count_is_integral() -> None:
    _available()
    edge_meta = _meta()
    edge_meta.update(
        {
            "cell_number_requested": 2,
            "leverage_requested": 5,
            "init_margin_requested": "4",
            "min_price": "90",
            "max_price": "110",
            "stop_loss_price": "80",
        }
    )
    edge = _parse(meta=edge_meta)
    assert edge["validate_ok"] is True
    assert edge["feasible_bybit"] is True
    assert edge["blocker_reason"] is None
    fractional = _meta()
    fractional["cell_number_requested"] = 5.5
    _assert_rejected(_parse(meta=fractional))
    fractional_bound = _response()
    fractional_bound["result"]["cell_number"]["to"] = "10.5"
    row = _parse(response=fractional_bound)
    _assert_rejected(row)
    assert row["result_schema_valid"] is False


def test_target_five_usdt_requires_strict_investment_membership() -> None:
    _available()
    exact = _response()
    exact["result"]["investment"] = {"from": "5", "to": "5"}
    admitted = _parse(response=exact)
    assert admitted["target_init_margin_inside_validate_range"] is True
    assert admitted["feasible_user_5usdt_rule"] is True
    high = _response()
    high["result"]["investment"] = {"from": "6", "to": "100"}
    high_meta = _meta()
    high_meta["init_margin_requested"] = "10"
    row = _parse(meta=high_meta, response=high)
    assert row["result_schema_valid"] is True
    assert row["validate_ok"] is True
    assert row["feasible_bybit"] is True
    assert row["target_init_margin_inside_validate_range"] is False
    assert row["feasible_user_5usdt_rule"] is False
    assert row["blocker_reason"] == "min_investment_gt_5usdt"


def test_invalid_result_forces_every_feasibility_flag_false() -> None:
    _available()
    payloads = []
    missing = _response()
    del missing["result"]["profit"]
    payloads.append(missing)
    rejected = _response()
    rejected["result"]["check_code"] = "FGRID_CHECK_CODE_REJECTED"
    payloads.append(rejected)
    malformed = _response()
    malformed["result"]["investment"]["from"] = "NaN"
    payloads.append(malformed)
    for payload in payloads:
        row = _parse(response=payload)
        _assert_rejected(row)
        assert row["validate_ok"] is False
        for field in FALSE_ON_INVALID:
            assert type(row[field]) is bool


def test_blocker_precedence_and_contract_version_are_deterministic() -> None:
    _available()
    envelope = {"result": {"check_code": "bad"}}
    schema = _response()
    del schema["result"]["investment"]
    schema["result"]["check_code"] = "bad"
    check = _response()
    check["result"]["check_code"] = "bad"
    outside_meta = _meta()
    outside_meta["leverage_requested"] = 50
    high = _response()
    high["result"]["investment"] = {"from": "6", "to": "100"}
    high_meta = _meta()
    high_meta["init_margin_requested"] = "10"
    cases = (
        (_parse(response=envelope), "response_envelope_invalid"),
        (_parse(response=schema), "native_result_schema_invalid"),
        (_parse(meta=outside_meta, response=check), "native_check_rejected"),
        (
            _parse(meta=outside_meta),
            "requested_values_outside_validate_ranges",
        ),
        (_parse(meta=high_meta, response=high), "min_investment_gt_5usdt"),
        (_parse(), None),
    )
    for row, blocker in cases:
        assert row["native_grid_validate_result_contract"] == CONTRACT_VERSION
        assert row["blocker_reason"] == blocker
        repeated = dict(row)
        assert repeated["blocker_reason"] == blocker


def test_strict_output_retains_only_redacted_structured_error_evidence() -> None:
    _available()
    canary = "STRICT_ERROR_EVIDENCE_CANARY"
    error = BybitAPIError(
        "/v5/fgridbot/validate",
        429,
        10006,
        canary,
        canary,
        {
            "retCode": 10006,
            "status_code": 429,
            "retMsg": canary,
            "result": {
                "status_code": 400,
                "check_code": "FGRID_CHECK_CODE_REJECTED",
                "debug_msg": canary,
                "investment": {"from": "1", "to": "999"},
                "public_note": canary,
            },
            "api_secret": canary,
            "raw_body": canary,
        },
        reason_code="api_error",
    )
    evidence = fgrid_mod.build_strict_validate_error_evidence(error)
    assert type(evidence) is dict
    assert set(evidence) == ERROR_EVIDENCE_KEYS
    assert type(evidence["response_data"]) is dict
    assert set(evidence["response_data"]) <= RESPONSE_EVIDENCE_KEYS
    nested = evidence["response_data"].get("result", {})
    assert type(nested) is dict
    assert set(nested) <= RESULT_EVIDENCE_KEYS
    assert nested.get("status_code") == 400
    assert nested.get("check_code") == "FGRID_CHECK_CODE_REJECTED"
    serialized = _canonical_json(evidence)
    assert len(serialized.encode("utf-8")) <= 1024
    assert canary not in serialized
    assert "investment" not in serialized
    assert "raw_body" not in serialized
    unknown = fgrid_mod.build_strict_validate_error_evidence(RuntimeError(canary))
    assert type(unknown) is dict and set(unknown) == ERROR_EVIDENCE_KEYS
    assert canary not in _canonical_json(unknown)
    row = _parse(response=error.response_data, http_status=429, error_evidence=evidence)
    _assert_rejected(row)
    assert row["error_evidence_json"] == _canonical_json(evidence)
    assert canary not in _canonical_json(row)


def test_sweep_uses_strict_parser_and_preserves_api_error_structure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _available()
    sweep = _load_sweep()
    source_path = ROOT / REQUIRED_IMPLEMENTATION_PATHS[0]
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "bybit_grid.bybit.fgrid_constraints"
        for alias in node.names
    }
    assert "parse_strict_validate_response" in imported
    assert "build_strict_validate_error_evidence" in imported
    assert "parse_validate_response" not in imported
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and any(isinstance(arg, ast.Name) and arg.id == "exc" for arg in node.args)
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "exc"
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "payload"
        for node in ast.walk(tree)
    )
    canary = "SWEEP_STRUCTURED_ERROR_CANARY"
    error = BybitAPIError(
        "/v5/fgridbot/validate",
        429,
        10006,
        canary,
        canary,
        {
            "retCode": 10006,
            "result": {
                "status_code": 400,
                "check_code": "FGRID_CHECK_CODE_REJECTED",
                "debug_msg": canary,
                "raw": canary,
            },
            "raw": canary,
        },
    )

    class Stats:
        api_calls_attempted = 1
        api_calls_succeeded = 0
        api_calls_failed = 1
        max_observed_endpoint_limit = None
        min_observed_limit_status = None
        rate_limit_10006_count = 1

    class FailingClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.stats = Stats()

        def __enter__(self) -> FailingClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def validate_grid_bot(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise error

    monkeypatch.setattr(sweep, "BybitClient", FailingClient)
    args = SimpleNamespace(
        stop_after_first_5usdt_feasible=False,
        user_threshold=5.0,
        exhaustive=False,
    )
    rows, skipped, errors, _stats = sweep._validate_symbol(
        {"symbol": "XUSDT"},
        [({}, _meta())],
        object(),
        args,
        object(),
        set(),
        Lock(),
        tmp_path / "raw",
    )
    assert skipped == 0 and errors == 1 and len(rows) == 1
    _assert_rejected(rows[0])
    assert rows[0]["http_status_code"] == 429
    persisted = _canonical_json(rows[0])
    raw_text = "".join(
        path.read_text(encoding="utf-8") for path in (tmp_path / "raw").iterdir()
    )
    assert canary not in persisted + raw_text
    assert rows[0]["error_evidence_json"] is not None


def test_sweep_does_not_stop_or_resume_from_legacy_or_invalid_rows(
    tmp_path: Path,
) -> None:
    _available()
    valid = _parse()
    envelope = _copy_with_symbol(_parse(response={"result": _result()}), "ENVELOPE")
    schema_payload = _response()
    del schema_payload["result"]["investment"]
    schema = _copy_with_symbol(_parse(response=schema_payload), "SCHEMA")
    rejected_payload = _response()
    rejected_payload["result"]["check_code"] = "FGRID_CHECK_CODE_REJECTED"
    rejected = _copy_with_symbol(_parse(response=rejected_payload), "REJECTED")
    legacy = _copy_with_symbol(valid, "LEGACY")
    legacy["native_grid_validate_result_contract"] = "legacy-v0"
    legacy["result_schema_valid"] = True
    legacy["validate_ok"] = True
    legacy["feasible_user_5usdt_rule"] = True
    path = tmp_path / "constraints.parquet"
    pl.DataFrame(
        [valid, envelope, schema, rejected, legacy], infer_schema_length=None
    ).write_parquet(path)
    expected = {fgrid_mod.candidate_key(valid)}
    assert fgrid_mod.strict_existing_keys(path) == expected
    fgrid_mod.prepare_strict_constraints(path)
    persisted = pl.read_parquet(path)
    assert set(persisted["native_grid_validate_result_contract"].drop_nulls()) == {
        CONTRACT_VERSION
    }
    assert "LEGACY" not in persisted["symbol"].to_list()
    assert fgrid_mod.strict_existing_keys(path) == expected
    for invalid in (envelope, schema, rejected):
        assert fgrid_mod.candidate_key(invalid) not in fgrid_mod.strict_existing_keys(
            path
        )


def test_sweep_stops_only_after_strict_five_usdt_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _available()
    sweep = _load_sweep()
    invalid = _response()
    invalid["result"]["check_code"] = "FGRID_CHECK_CODE_REJECTED"
    invalid["result"]["investment"] = {"from": "1", "to": "100"}
    responses = [invalid, _response(), _response()]

    class Stats:
        api_calls_attempted = 0
        api_calls_succeeded = 0
        api_calls_failed = 0
        max_observed_endpoint_limit = None
        min_observed_limit_status = None
        rate_limit_10006_count = 0

    class SequenceClient:
        calls = 0

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.stats = Stats()

        def __enter__(self) -> SequenceClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def validate_grid_bot(self, _payload: dict[str, Any]) -> dict[str, Any]:
            response = responses[type(self).calls]
            type(self).calls += 1
            self.stats.api_calls_attempted = type(self).calls
            self.stats.api_calls_succeeded = type(self).calls
            return response

    observed_batches: list[list[dict[str, Any]]] = []
    original_should_stop = sweep.should_stop_symbol

    def strict_stop_spy(
        rows: list[dict[str, Any]], threshold: Decimal, exhaustive: bool
    ) -> bool:
        observed_batches.append([dict(row) for row in rows])
        return original_should_stop(rows, threshold, exhaustive)

    monkeypatch.setattr(sweep, "BybitClient", SequenceClient)
    monkeypatch.setattr(sweep, "should_stop_symbol", strict_stop_spy)
    candidates = []
    for index in range(3):
        meta = _meta()
        meta["profile_name"] = f"profile_{index}"
        meta["stop_loss_mult"] = f"0.9{index}"
        candidates.append(({}, meta))
    args = SimpleNamespace(
        stop_after_first_5usdt_feasible=True,
        user_threshold=5.0,
        exhaustive=False,
    )
    rows, skipped, errors, _stats = sweep._validate_symbol(
        {"symbol": "XUSDT"},
        candidates,
        object(),
        args,
        object(),
        set(),
        Lock(),
        tmp_path / "raw",
    )
    assert skipped == 0 and errors == 0
    assert SequenceClient.calls == 2 and len(rows) == 2
    assert rows[0]["feasible_user_5usdt_rule"] is False
    assert rows[1]["feasible_user_5usdt_rule"] is True
    assert observed_batches
    assert all(
        row["native_grid_validate_result_contract"] == CONTRACT_VERSION
        and row["result_schema_valid"] is True
        and row["validate_ok"] is True
        and row["feasible_user_5usdt_rule"] is True
        and row["blocker_reason"] is None
        for batch in observed_batches
        for row in batch
    )


def test_feasible_artifact_and_report_exclude_legacy_or_partial_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _available()
    valid = _parse()
    legacy = _copy_with_symbol(valid, "LEGACY")
    legacy["native_grid_validate_result_contract"] = "legacy-v0"
    forged = pl.DataFrame(
        {
            "symbol": ["FORGED"],
            "native_grid_validate_result_contract": [CONTRACT_VERSION],
            "result_schema_valid": [True],
            "validate_ok": [True],
            "feasible_bybit": [True],
            "min_investment_feasible_at_5usdt": [True],
            "feasible_user_5usdt_rule": [True],
            "target_init_margin_inside_validate_range": [True],
            "blocker_reason": [None],
            "status_code": [200],
            "check_code": ["FGRID_CHECK_CODE_UNSPECIFIED"],
        }
    )
    assert fgrid_mod.strict_constraint_records(forged).is_empty()
    assert fgrid_mod.strict_feasible_constraints(forged).is_empty()
    mixed = pl.concat(
        [pl.DataFrame([valid, legacy], infer_schema_length=None), forged],
        how="diagonal_relaxed",
    )
    assert fgrid_mod.strict_constraint_records(mixed)["symbol"].to_list() == ["XUSDT"]
    selected = fgrid_mod.strict_feasible_constraints(mixed)
    assert selected["symbol"].to_list() == ["XUSDT"]
    assert fgrid_mod.strict_feasible_constraints(
        pl.DataFrame({"symbol": ["X"]})
    ).is_empty()
    sweep = _load_sweep()
    monkeypatch.chdir(tmp_path)
    output = Path("data/processed/fgrid_validate_constraints.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)
    mixed.write_parquet(output)
    stale_artifact = Path("data/processed/fgrid_feasible_configs.parquet")
    pl.DataFrame({"symbol": ["STALE_LEGACY"]}).write_parquet(stale_artifact)
    stale_report = Path("reports/sprint_02_fgrid_constraints_report.md")
    stale_report.parent.mkdir(parents=True, exist_ok=True)
    stale_report.write_text("STALE_REPORT_CANARY", encoding="utf-8")
    universe = tmp_path / "empty_universe.parquet"
    pl.DataFrame({"symbol": []}, schema={"symbol": pl.String}).write_parquet(universe)

    class SettingsStub:
        grid_validate_enabled = True

        @staticmethod
        def require_private_credentials() -> None:
            return None

    monkeypatch.setattr(sweep, "load_settings", SettingsStub)
    monkeypatch.setattr(
        sweep,
        "_enforce_validate_only_settings",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(ROOT / REQUIRED_IMPLEMENTATION_PATHS[0]),
            "--universe",
            str(universe),
            "--max-symbols",
            "0",
        ],
    )
    sweep.main()
    artifact = pl.read_parquet("data/processed/fgrid_feasible_configs.parquet")
    assert artifact["symbol"].to_list() == ["XUSDT"]
    persisted = pl.read_parquet(output)
    assert "LEGACY" not in persisted["symbol"].to_list()
    report_text = Path("reports/sprint_02_fgrid_constraints_report.md").read_text(
        encoding="utf-8"
    )
    assert "symbols tested: 1" in report_text
    assert "percent satisfying 5 USDT rule: 100.0%" in report_text
    assert "LEGACY" not in report_text
    assert "FORGED" not in report_text
    assert "STALE_REPORT_CANARY" not in report_text
