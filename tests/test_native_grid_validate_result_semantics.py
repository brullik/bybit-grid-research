from __future__ import annotations

import importlib.util
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any, Iterator

import polars as pl

from bybit_grid.bybit.fgrid_constraints import (
    NATIVE_GRID_VALIDATE_RESULT_CONTRACT,
    NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE,
    append_strict_constraints,
    build_strict_validate_error_evidence,
    parse_strict_validate_response,
    prepare_strict_constraints,
    strict_existing_keys,
    strict_feasible_constraints,
)
from bybit_grid.bybit.models import BybitAPIError


NATIVE_GRID_VALIDATE_RESULT_TEST_CONTRACT = "native-grid-validate-result-v1"
ROOT = Path(__file__).resolve().parents[1]
SWEEP_PATH = ROOT / "scripts" / "validate_universe_fgrid_constraints.py"
_SWEEP_MODULE_NAME = "_native_grid_validate_result_contract_sweep"
_FEASIBILITY_FLAGS = (
    "requested_init_margin_inside_validate_range",
    "requested_cell_number_inside_validate_range",
    "requested_leverage_inside_validate_range",
    "requested_min_price_inside_validate_range",
    "requested_max_price_inside_validate_range",
    "requested_stop_loss_price_inside_validate_range",
    "requested_values_inside_validate_ranges",
    "target_init_margin_inside_validate_range",
    "feasible_bybit",
    "min_investment_feasible_at_5usdt",
    "feasible_user_5usdt_rule",
)


def _meta(**overrides: Any) -> dict[str, Any]:
    value = {
        "symbol": "XUSDT",
        "lastPrice": 100.0,
        "tickSize": "0.1",
        "range_width_pct": 0.10,
        "min_price": 95.0,
        "max_price": 105.0,
        "stop_loss_price": 90.0,
        "cell_number_requested": 2,
        "leverage_requested": 1,
        "init_margin_requested": 5.0,
        "stop_loss_mult": 0.95,
    }
    value.update(overrides)
    return value


def _response() -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "status_code": 200,
            "check_code": NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE,
            "debug_msg": "",
            "investment": {"from": "4", "to": "100"},
            "cell_number": {"from": "2", "to": "10"},
            "leverage": {"from": "1", "to": "5"},
            "min_price": {"from": "90", "to": "100"},
            "max_price": {"from": "100", "to": "110"},
            "entry_price": {"from": "95", "to": "105"},
            "stop_loss_price": {"from": "80", "to": "94"},
            "take_profit_price": {"from": "106", "to": "120"},
            "profit": {"from": "0", "to": "100"},
        },
    }


def _assert_no_feasibility(row: dict[str, Any]) -> None:
    assert all(row[name] is False for name in _FEASIBILITY_FLAGS)


@contextmanager
def _loaded_sweep() -> Iterator[types.ModuleType]:
    names = ("scripts", "scripts.build_universe", _SWEEP_MODULE_NAME)
    previous = {name: sys.modules.get(name) for name in names}
    previous_path = list(sys.path)
    scripts_package = types.ModuleType("scripts")
    scripts_package.__path__ = [str(ROOT / "scripts")]
    build_universe_module = types.ModuleType("scripts.build_universe")
    build_universe_module.build_universe = lambda *_args, **_kwargs: {"selected": 0}
    sys.modules["scripts"] = scripts_package
    sys.modules["scripts.build_universe"] = build_universe_module
    spec = importlib.util.spec_from_file_location(_SWEEP_MODULE_NAME, SWEEP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SWEEP_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path[:] = previous_path
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class _Stats:
    api_calls_attempted = 0
    api_calls_succeeded = 0
    api_calls_failed = 0
    max_observed_endpoint_limit = None
    min_observed_limit_status = None
    rate_limit_10006_count = 0


def _run_validate_symbol(
    sweep: types.ModuleType,
    responses: list[dict[str, Any] | BaseException],
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    raw_dir: Path,
) -> tuple[list[dict[str, Any]], int, int, dict[str, int | None], int]:
    class FakeClient:
        calls = 0

        def __init__(self, *_args: Any, **_kwargs: Any):
            self.stats = _Stats()

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def validate_grid_bot(self, _payload: dict[str, Any]) -> dict[str, Any]:
            value = responses[FakeClient.calls]
            FakeClient.calls += 1
            self.stats.api_calls_attempted += 1
            if isinstance(value, BaseException):
                self.stats.api_calls_failed += 1
                raise value
            self.stats.api_calls_succeeded += 1
            return value

    sweep.BybitClient = FakeClient
    args = SimpleNamespace(
        stop_after_first_5usdt_feasible=True,
        user_threshold=5.0,
        exhaustive=False,
    )
    result = sweep._validate_symbol(
        {},
        candidates,
        object(),
        args,
        object(),
        set(),
        Lock(),
        raw_dir,
    )
    return (*result, FakeClient.calls)


def test_strict_parser_accepts_only_complete_official_example_shape():
    assert (
        NATIVE_GRID_VALIDATE_RESULT_TEST_CONTRACT
        == NATIVE_GRID_VALIDATE_RESULT_CONTRACT
    )
    row = parse_strict_validate_response(_meta(), _response(), status_code=200)
    assert (
        row["native_grid_validate_result_contract"]
        == NATIVE_GRID_VALIDATE_RESULT_CONTRACT
    )
    assert row["strict_parser_applied"] is True
    assert row["envelope_valid"] is True
    assert row["result_schema_valid"] is True
    assert row["validate_ok"] is True
    assert row["feasible_bybit"] is True
    assert row["feasible_user_5usdt_rule"] is True
    assert row["blocker_reason"] is None
    assert (
        parse_strict_validate_response(_meta(), _response())["feasible_bybit"] is True
    )


def test_strict_parser_never_falls_back_to_top_level_result_fields():
    nested = _response()["result"]
    flattened = {"retCode": 0, **nested}
    row = parse_strict_validate_response(_meta(), flattened, status_code=200)
    assert row["result_schema_valid"] is False
    _assert_no_feasibility(row)

    aliased = _response()
    investment = aliased["result"].pop("investment")
    aliased["result"]["investment_from"] = investment["from"]
    aliased["result"]["investment_to"] = investment["to"]
    row = parse_strict_validate_response(_meta(), aliased, status_code=200)
    assert row["result_schema_valid"] is False
    _assert_no_feasibility(row)

    duplicate_alias = _response()
    duplicate_alias["result"]["investment_from"] = "4"
    row = parse_strict_validate_response(_meta(), duplicate_alias, status_code=200)
    assert row["result_schema_valid"] is False
    _assert_no_feasibility(row)


def test_required_result_fields_and_range_bounds_are_complete():
    required_ranges = (
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
    for name in required_ranges:
        missing_range = _response()
        del missing_range["result"][name]
        row = parse_strict_validate_response(_meta(), missing_range, status_code=200)
        assert row["result_schema_valid"] is False
        _assert_no_feasibility(row)
        for bound in ("from", "to"):
            missing_bound = _response()
            del missing_bound["result"][name][bound]
            row = parse_strict_validate_response(
                _meta(), missing_bound, status_code=200
            )
            assert row["result_schema_valid"] is False
            _assert_no_feasibility(row)


def test_status_and_check_code_require_exact_success_pair():
    cases: list[tuple[dict[str, Any], int | None]] = []
    for status in (0, 201, 200.0, "200", True, None):
        response = _response()
        response["result"]["status_code"] = status
        cases.append((response, 200))
    for check_code in ("FGRID_CHECK_CODE_SUCCESS", "UNKNOWN", "", None, 0):
        response = _response()
        response["result"]["check_code"] = check_code
        cases.append((response, 200))
    for ret_code in (1, "0", True, None):
        response = _response()
        response["retCode"] = ret_code
        cases.append((response, 200))
    no_ret_code = _response()
    del no_ret_code["retCode"]
    cases.extend([(no_ret_code, 200), (_response(), 201), (_response(), 500)])
    for response, http_status in cases:
        row = parse_strict_validate_response(_meta(), response, status_code=http_status)
        assert row["validate_ok"] is False
        _assert_no_feasibility(row)


def test_debug_message_must_be_exact_empty_string_for_success():
    for value in ("param error", " ", None, 0, [], {}):
        response = _response()
        response["result"]["debug_msg"] = value
        row = parse_strict_validate_response(_meta(), response, status_code=200)
        assert row["validate_ok"] is False
        _assert_no_feasibility(row)
        if type(value) is not str:
            assert row["blocker_reason"] == "native_result_schema_invalid"
    missing = _response()
    del missing["result"]["debug_msg"]
    assert parse_strict_validate_response(_meta(), missing)["validate_ok"] is False
    top_level = _response()
    top_level["debug_msg"] = "param error"
    row = parse_strict_validate_response(_meta(), top_level, status_code=200)
    assert row["validate_ok"] is False
    _assert_no_feasibility(row)


def test_range_atoms_must_be_finite_decimal_strings():
    for value in (4, 4.0, True, None, "", "NaN", "Infinity", "1e9999", "1e-9999"):
        response = _response()
        response["result"]["investment"]["from"] = value
        row = parse_strict_validate_response(_meta(), response, status_code=200)
        assert row["result_schema_valid"] is False
        _assert_no_feasibility(row)


def test_range_bounds_must_be_ordered_and_domain_valid():
    mutations = (
        ("investment", "from", "101"),
        ("investment", "from", "0"),
        ("cell_number", "from", "2.5"),
        ("leverage", "from", "0"),
        ("min_price", "from", "-1"),
        ("profit", "from", "-0.1"),
    )
    for name, bound, value in mutations:
        response = _response()
        response["result"][name][bound] = value
        row = parse_strict_validate_response(_meta(), response, status_code=200)
        assert row["result_schema_valid"] is False
        _assert_no_feasibility(row)


def test_requested_meta_values_must_be_finite_and_non_boolean():
    fields = (
        "init_margin_requested",
        "cell_number_requested",
        "leverage_requested",
        "min_price",
        "max_price",
        "stop_loss_price",
    )
    for field in fields:
        for value in (None, True, float("nan"), float("inf"), "not-a-number"):
            row = parse_strict_validate_response(
                _meta(**{field: value}), _response(), status_code=200
            )
            _assert_no_feasibility(row)


def test_each_requested_value_must_be_inside_its_named_range():
    cases = (
        (
            "init_margin_requested",
            101.0,
            {},
            "requested_init_margin_inside_validate_range",
        ),
        (
            "cell_number_requested",
            11,
            {},
            "requested_cell_number_inside_validate_range",
        ),
        ("leverage_requested", 6, {}, "requested_leverage_inside_validate_range"),
        (
            "min_price",
            89.0,
            {"stop_loss_price": 80.0},
            "requested_min_price_inside_validate_range",
        ),
        ("max_price", 111.0, {}, "requested_max_price_inside_validate_range"),
        (
            "stop_loss_price",
            94.5,
            {},
            "requested_stop_loss_price_inside_validate_range",
        ),
    )
    for field, value, extra, flag in cases:
        row = parse_strict_validate_response(
            _meta(**{field: value, **extra}), _response(), status_code=200
        )
        assert row[flag] is False
        assert row["feasible_bybit"] is False
        assert row["feasible_user_5usdt_rule"] is False
        assert row["blocker_reason"] == "requested_values_outside_validate_ranges"


def test_range_edges_are_inclusive_and_grid_count_is_integral():
    edge_meta = _meta(
        init_margin_requested=4.0,
        cell_number_requested=2,
        leverage_requested=1,
        min_price=90.0,
        max_price=110.0,
        stop_loss_price=80.0,
    )
    row = parse_strict_validate_response(edge_meta, _response(), status_code=200)
    assert row["requested_values_inside_validate_ranges"] is True
    assert row["feasible_bybit"] is True
    non_integral = parse_strict_validate_response(
        _meta(cell_number_requested=2.5), _response(), status_code=200
    )
    _assert_no_feasibility(non_integral)


def test_target_five_usdt_requires_strict_investment_membership():
    response = _response()
    response["result"]["investment"] = {"from": "4", "to": "4.5"}
    row = parse_strict_validate_response(
        _meta(init_margin_requested=4.25), response, status_code=200
    )
    assert row["feasible_bybit"] is True
    assert row["target_init_margin_inside_validate_range"] is False
    assert row["feasible_user_5usdt_rule"] is False
    assert row["blocker_reason"] == "min_investment_gt_5usdt"


def test_invalid_result_forces_every_feasibility_flag_false():
    invalid_payloads = []
    missing = _response()
    del missing["result"]["profit"]
    invalid_payloads.append(missing)
    rejected = _response()
    rejected["result"]["check_code"] = "FGRID_CHECK_CODE_REJECTED"
    invalid_payloads.append(rejected)
    nonfinite = _response()
    nonfinite["result"]["leverage"]["to"] = "NaN"
    invalid_payloads.append(nonfinite)
    for payload in invalid_payloads:
        _assert_no_feasibility(
            parse_strict_validate_response(_meta(), payload, status_code=200)
        )


def test_blocker_precedence_and_contract_version_are_deterministic():
    envelope = _response()
    envelope["retCode"] = 10001
    del envelope["result"]["investment"]
    assert (
        parse_strict_validate_response(_meta(leverage_requested=99), envelope)[
            "blocker_reason"
        ]
        == "response_envelope_invalid"
    )

    schema = _response()
    del schema["result"]["investment"]
    schema["result"]["check_code"] = "REJECTED"
    assert parse_strict_validate_response(_meta(), schema)["blocker_reason"] == (
        "native_result_schema_invalid"
    )

    rejected = _response()
    rejected["result"]["check_code"] = "REJECTED"
    assert (
        parse_strict_validate_response(_meta(leverage_requested=99), rejected)[
            "blocker_reason"
        ]
        == "native_check_rejected"
    )

    outside = parse_strict_validate_response(
        _meta(leverage_requested=99), _response(), status_code=200
    )
    assert outside["blocker_reason"] == "requested_values_outside_validate_ranges"

    too_low = _response()
    too_low["result"]["investment"] = {"from": "4", "to": "4.5"}
    assert (
        parse_strict_validate_response(
            _meta(init_margin_requested=4.25), too_low, status_code=200
        )["blocker_reason"]
        == "min_investment_gt_5usdt"
    )

    success = parse_strict_validate_response(_meta(), _response(), status_code=200)
    assert success["blocker_reason"] is None
    assert success["native_grid_validate_result_contract"] == (
        NATIVE_GRID_VALIDATE_RESULT_CONTRACT
    )


def test_strict_output_retains_only_redacted_structured_error_evidence():
    canary = "NATIVE_GRID_ERROR_CANARY"

    class HostileError(BybitAPIError):
        def __str__(self) -> str:
            raise AssertionError("exception text must never be inspected")

    exc = HostileError(
        endpoint="/v5/fgridbot/validate",
        status_code=400,
        ret_code=10001,
        ret_msg=canary,
        debug_msg=canary,
        reason_code="api_error",
        response_data={
            "retCode": 10001,
            "retMsg": canary,
            "secret": canary,
            "result": {
                "status_code": 400,
                "check_code": canary,
                "debug_msg": canary,
                "investment": {"from": canary, "to": canary},
            },
        },
    )
    evidence = build_strict_validate_error_evidence(exc)
    assert set(evidence) == {
        "reason_code",
        "http_status_code",
        "retCode",
        "retMsg",
        "debug_msg",
        "response_data",
    }
    encoded = json.dumps(evidence, sort_keys=True)
    assert len(encoded.encode("utf-8")) <= 1024
    assert canary not in encoded
    assert "secret" not in encoded
    assert "investment" not in encoded
    row = parse_strict_validate_response(
        _meta(), _response(), status_code=200, error_evidence=evidence
    )
    _assert_no_feasibility(row)
    assert canary not in row["error_evidence_json"]


def test_sweep_uses_strict_parser_and_preserves_api_error_structure(tmp_path: Path):
    canary = "SWEEP_EXCEPTION_TEXT_CANARY"
    exc = BybitAPIError(
        endpoint="/v5/fgridbot/validate",
        status_code=400,
        ret_code=10001,
        ret_msg=canary,
        debug_msg=canary,
        reason_code="api_error",
        response_data={
            "retCode": 10001,
            "retMsg": canary,
            "result": {
                "status_code": 400,
                "check_code": NATIVE_GRID_VALIDATE_SUCCESS_CHECK_CODE,
                "debug_msg": canary,
            },
        },
    )
    with _loaded_sweep() as sweep:
        assert sweep.STRICT_NATIVE_GRID_VALIDATE_SWEEP_CONTRACT == (
            NATIVE_GRID_VALIDATE_RESULT_CONTRACT
        )
        assert sweep.append_constraints is append_strict_constraints
        rows, skipped, errors, _, calls = _run_validate_symbol(
            sweep,
            [exc],
            [({}, _meta())],
            tmp_path / "raw",
        )
    assert skipped == 0 and errors == 1 and calls == 1
    assert rows[0]["native_grid_validate_result_contract"] == (
        NATIVE_GRID_VALIDATE_RESULT_CONTRACT
    )
    _assert_no_feasibility(rows[0])
    evidence = json.loads(rows[0]["error_evidence_json"])
    assert evidence["response_data"]["result"]["status_code"] == 400
    raw_text = next((tmp_path / "raw").glob("*.json")).read_text(encoding="utf-8")
    assert canary not in raw_text


def test_sweep_does_not_stop_or_resume_from_legacy_or_invalid_rows(tmp_path: Path):
    legacy_path = tmp_path / "legacy.parquet"
    pl.DataFrame(
        [{**_meta(), "feasible_bybit": True, "feasible_user_5usdt_rule": True}]
    ).write_parquet(legacy_path)
    prepared = prepare_strict_constraints(legacy_path)
    assert prepared.is_empty()
    assert not legacy_path.exists()

    invalid_path = tmp_path / "invalid.parquet"
    invalid = parse_strict_validate_response(
        _meta(), {"retCode": 0, "result": {}}, status_code=200
    )
    append_strict_constraints(invalid_path, [invalid])
    assert strict_existing_keys(invalid_path) == set()

    second_meta = _meta(min_price=96.0, max_price=104.0)
    with _loaded_sweep() as sweep:
        rows, _, _, _, calls = _run_validate_symbol(
            sweep,
            [
                {"retCode": 0, "result": {"investment": {"from": "1", "to": "2"}}},
                _response(),
            ],
            [({}, _meta()), ({}, second_meta)],
            tmp_path / "raw",
        )
    assert calls == 2 and len(rows) == 2
    assert rows[0]["feasible_user_5usdt_rule"] is False
    assert rows[1]["feasible_user_5usdt_rule"] is True


def test_sweep_stops_only_after_strict_five_usdt_success(tmp_path: Path):
    with _loaded_sweep() as sweep:
        rows, _, _, _, calls = _run_validate_symbol(
            sweep,
            [_response(), _response()],
            [({}, _meta()), ({}, _meta(min_price=96.0, max_price=104.0))],
            tmp_path / "raw",
        )
    assert calls == 1 and len(rows) == 1
    assert rows[0]["feasible_user_5usdt_rule"] is True


def test_feasible_artifact_and_report_exclude_legacy_or_partial_rows(
    tmp_path: Path, monkeypatch: Any
):
    valid = parse_strict_validate_response(_meta(), _response(), status_code=200)
    legacy = {
        **_meta(symbol="LEGACY"),
        "feasible_bybit": True,
        "feasible_user_5usdt_rule": True,
        "blocker_reason": None,
    }
    partial = {
        "symbol": "PARTIAL",
        "native_grid_validate_result_contract": NATIVE_GRID_VALIDATE_RESULT_CONTRACT,
        "strict_parser_applied": True,
        "feasible_bybit": True,
        "feasible_user_5usdt_rule": True,
        "blocker_reason": None,
    }
    mixed = pl.concat(
        [pl.DataFrame([value]) for value in (valid, legacy, partial)],
        how="diagonal_relaxed",
    )
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "data" / "processed" / "feasible.parquet"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"legacy-artifact")
    stale_report = tmp_path / "reports" / "sprint_02_fgrid_constraints_report.md"
    stale_report.parent.mkdir(parents=True)
    stale_report.write_text("legacy report", encoding="utf-8")
    with _loaded_sweep() as sweep:
        sweep.reset_strict_derived_outputs(artifact, stale_report)
        assert not artifact.exists() and not stale_report.exists()
        attempts, bybit, five = sweep.finalize_outputs(mixed, artifact)
    assert attempts["symbol"].to_list() == ["XUSDT"]
    assert bybit["symbol"].to_list() == ["XUSDT"]
    assert five["symbol"].to_list() == ["XUSDT"]
    assert pl.read_parquet(artifact)["symbol"].to_list() == ["XUSDT"]
    report_text = (
        tmp_path / "reports" / "sprint_02_fgrid_constraints_report.md"
    ).read_text(encoding="utf-8")
    assert "symbols tested: 1" in report_text
    assert strict_feasible_constraints(mixed, require_5usdt=True)[
        "symbol"
    ].to_list() == ["XUSDT"]
