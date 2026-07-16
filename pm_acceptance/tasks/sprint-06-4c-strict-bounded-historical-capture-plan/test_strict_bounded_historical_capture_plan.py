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

from bybit_grid.data.public_batch.models import (
    BybitInstrumentMeta,
    BybitServerTime,
    InclusiveMinuteWindow,
)


MINUTE_MS = 60_000
MODULE_NAME = "bybit_grid.data.public_batch.historical_plan"
UNAVAILABLE = "historical_capture_plan_unavailable"


def _api():
    try:
        historical_plan = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    required = (
        "MAX_PLAN_SPAN_MINUTES",
        "KLINE_LIMIT",
        "FUNDING_LIMIT",
        "FUNDING_TARGET_RECORDS",
        "MAX_TOTAL_REQUESTS",
        "MAX_TOTAL_RESPONSE_ROWS",
        "HistoricalPlanError",
        "HistoricalRequestSpec",
        "HistoricalCapturePlan",
        "build_historical_capture_plan",
        "__all__",
    )
    if any(not hasattr(historical_plan, name) for name in required):
        raise RuntimeError(UNAVAILABLE)
    return historical_plan


def _server(*, last_closed_minute: int = 50_000, subminute_ms: int = 1_234):
    server_time_ms = (last_closed_minute + 1) * MINUTE_MS + subminute_ms
    return BybitServerTime(
        server_time_ms=server_time_ms,
        time_second=server_time_ms // 1_000,
        time_nano=server_time_ms * 1_000_000,
        top_level_time_ms=server_time_ms,
        last_closed_open_time_ms=last_closed_minute * MINUTE_MS,
    )


def _instrument(
    server_time: BybitServerTime,
    *,
    symbol: str = "BTCUSDT",
    launch_time_ms: int = 0,
    delivery_time_ms: int = 0,
    contract_type: str = "LinearPerpetual",
    status: str = "Trading",
    quote_coin: str = "USDT",
    settle_coin: str = "USDT",
    is_pre_listing: bool = False,
    funding_interval_minutes: int = 480,
    snapshot_server_time_ms: int | None = None,
):
    return BybitInstrumentMeta(
        category="linear",
        symbol=symbol,
        contract_type=contract_type,
        status=status,
        base_coin="BTC",
        quote_coin=quote_coin,
        settle_coin=settle_coin,
        launch_time_ms=launch_time_ms,
        delivery_time_ms=delivery_time_ms,
        is_pre_listing=is_pre_listing,
        funding_interval_minutes=funding_interval_minutes,
        tick_size=Decimal("0.10"),
        qty_step=Decimal("0.001"),
        min_order_qty=Decimal("0.001"),
        min_notional_value=Decimal("5"),
        min_leverage=Decimal("1"),
        max_leverage=Decimal("100"),
        leverage_step=Decimal("0.01"),
        snapshot_server_time_ms=(
            server_time.server_time_ms
            if snapshot_server_time_ms is None
            else snapshot_server_time_ms
        ),
    )


def _kwargs(
    *,
    start_minute: int = 0,
    end_minute: int = 180,
    funding_interval_minutes: int = 60,
):
    server_time = _server()
    return {
        "instrument": _instrument(
            server_time,
            funding_interval_minutes=funding_interval_minutes,
        ),
        "server_time": server_time,
        "requested_window": InclusiveMinuteWindow(
            start_minute * MINUTE_MS,
            end_minute * MINUTE_MS,
        ),
        "observed_trade_open_times_ms": (),
        "observed_mark_open_times_ms": (),
        "observed_funding_times_ms": (),
    }


def _build(api, **overrides):
    values = _kwargs()
    values.update(overrides)
    return api.build_historical_capture_plan(**values)


def _assert_plan_error(api, code: str, **overrides):
    with pytest.raises(api.HistoricalPlanError) as caught:
        _build(api, **overrides)
    assert str(caught.value) == code


def _minutes(start: int, end: int):
    return tuple(value * MINUTE_MS for value in range(start, end + 1))


def _observed_except(row_count: int, missing_indices: set[int]) -> tuple[int, ...]:
    return tuple(index * MINUTE_MS for index in range(row_count) if index not in missing_indices)


def _funding_digest(values: tuple[int, ...]) -> str:
    data = (
        json.dumps(list(values), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def test_exact_public_constants_signature_and_model_field_order():
    api = _api()
    assert issubclass(api.HistoricalPlanError, ValueError)
    assert (
        api.MAX_PLAN_SPAN_MINUTES,
        api.KLINE_LIMIT,
        api.FUNDING_LIMIT,
        api.FUNDING_TARGET_RECORDS,
        api.MAX_TOTAL_REQUESTS,
        api.MAX_TOTAL_RESPONSE_ROWS,
    ) == (44_640, 1000, 200, 199, 256, 100_000)
    assert type(api.__all__) is tuple
    assert api.__all__ == (
        "FUNDING_LIMIT",
        "FUNDING_TARGET_RECORDS",
        "HistoricalCapturePlan",
        "HistoricalPlanError",
        "HistoricalRequestSpec",
        "KLINE_LIMIT",
        "MAX_PLAN_SPAN_MINUTES",
        "MAX_TOTAL_REQUESTS",
        "MAX_TOTAL_RESPONSE_ROWS",
        "build_historical_capture_plan",
    )
    signature = inspect.signature(api.build_historical_capture_plan)
    assert tuple(signature.parameters) == (
        "instrument",
        "server_time",
        "requested_window",
        "observed_trade_open_times_ms",
        "observed_mark_open_times_ms",
        "observed_funding_times_ms",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert all(
        parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values()
    )
    assert tuple(field.name for field in fields(api.HistoricalRequestSpec)) == (
        "sequence_id",
        "dataset",
        "endpoint",
        "pagination",
        "start_ms",
        "end_ms",
        "limit",
        "target_row_count",
        "requested_minute_count",
        "params",
    )
    assert tuple(field.name for field in fields(api.HistoricalCapturePlan)) == (
        "schema",
        "category",
        "symbol",
        "launch_cutoff_open_time_ms",
        "delivery_cutoff_open_time_ms",
        "request_start_open_time_ms",
        "request_cutoff_open_time_ms",
        "server_cutoff_open_time_ms",
        "funding_interval_minutes",
        "observed_trade_row_count",
        "observed_mark_row_count",
        "observed_funding_row_count",
        "observed_funding_times_sha256",
        "trade_missing_row_count",
        "mark_missing_row_count",
        "funding_recapture_observation_upper_bound",
        "plan_span_minutes",
        "request_count",
        "planned_max_response_rows",
        "max_plan_span_minutes",
        "max_total_requests",
        "max_total_response_rows",
        "network_authorized_bool",
        "credentials_allowed_bool",
        "private_api_allowed_bool",
        "live_execution_authorized_bool",
        "funding_coverage_proven_bool",
        "historical_market_data_coverage_proven_bool",
        "parameter_selection_authorized_bool",
        "sufficient_for_parameter_selection_bool",
        "native_equivalence_proven_bool",
        "requests",
    )
    assert "__dict__" not in api.HistoricalRequestSpec.__slots__
    assert "__dict__" not in api.HistoricalCapturePlan.__slots__


def test_module_ast_has_no_forbidden_import_or_import_time_call_surface():
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
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(forbidden_roots)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            assert not isinstance(value, ast.Call)
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    assert {name for name in vars(api) if not name.startswith("_")} == set(api.__all__)


def test_plan_identity_guardrails_and_fixed_caps_are_exact():
    api = _api()
    plan = _build(api)
    assert not hasattr(plan, "__dict__")
    assert not hasattr(plan.requests[0], "__dict__")
    assert (plan.schema, plan.category, plan.symbol) == (
        "bybit_public_historical_capture_plan_v1",
        "linear",
        "BTCUSDT",
    )
    assert (
        plan.max_plan_span_minutes,
        plan.max_total_requests,
        plan.max_total_response_rows,
    ) == (44_640, 256, 100_000)
    assert (
        plan.network_authorized_bool,
        plan.credentials_allowed_bool,
        plan.private_api_allowed_bool,
        plan.live_execution_authorized_bool,
        plan.funding_coverage_proven_bool,
        plan.historical_market_data_coverage_proven_bool,
        plan.parameter_selection_authorized_bool,
        plan.sufficient_for_parameter_selection_bool,
        plan.native_equivalence_proven_bool,
    ) == (False, False, False, False, False, False, False, False, False)


def test_launch_cutoff_ceil_excludes_partial_launch_minute():
    api = _api()
    server_time = _server(last_closed_minute=20)
    instrument = _instrument(server_time, launch_time_ms=MINUTE_MS + 1)
    _assert_plan_error(
        api,
        "window_before_launch",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(MINUTE_MS, 5 * MINUTE_MS),
    )
    plan = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(2 * MINUTE_MS, 5 * MINUTE_MS),
    )
    assert plan.launch_cutoff_open_time_ms == 2 * MINUTE_MS
    assert plan.request_start_open_time_ms == 2 * MINUTE_MS


def test_delivery_cutoff_excludes_delivery_containing_minute():
    api = _api()
    server_time = _server(last_closed_minute=20)
    instrument = _instrument(server_time, delivery_time_ms=10 * MINUTE_MS + 123)
    _assert_plan_error(
        api,
        "window_at_or_after_delivery",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 10 * MINUTE_MS),
    )
    plan = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 9 * MINUTE_MS),
    )
    assert plan.delivery_cutoff_open_time_ms == 9 * MINUTE_MS
    assert plan.request_cutoff_open_time_ms == 9 * MINUTE_MS


def test_zero_delivery_has_no_delivery_cutoff():
    api = _api()
    plan = _build(api)
    assert plan.delivery_cutoff_open_time_ms is None
    assert plan.request_cutoff_open_time_ms == 180 * MINUTE_MS


def test_server_cutoff_rejects_after_last_closed_minute():
    api = _api()
    server_time = _server(last_closed_minute=11)
    instrument = _instrument(server_time)
    _assert_plan_error(
        api,
        "window_after_last_closed",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 12 * MINUTE_MS),
    )
    plan = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 11 * MINUTE_MS),
    )
    assert plan.server_cutoff_open_time_ms == 11 * MINUTE_MS


def test_instrument_snapshot_is_bound_to_exact_server_time():
    api = _api()
    server_time = _server()
    instrument = _instrument(
        server_time,
        snapshot_server_time_ms=server_time.server_time_ms - 1,
    )
    _assert_plan_error(
        api,
        "instrument_server_time_mismatch",
        instrument=instrument,
        server_time=server_time,
    )


def test_symbol_and_server_component_identity_are_strict():
    api = _api()
    server_time = _server()
    for symbol in ("A", "A" * 33, "BTC-USDT", "ＢＴＣＵＳＤＴ"):
        _assert_plan_error(
            api,
            "instrument_symbol_invalid",
            instrument=_instrument(server_time, symbol=symbol),
            server_time=server_time,
        )
    for symbol in ("AB", "A" * 32):
        plan = _build(
            api,
            instrument=_instrument(server_time, symbol=symbol),
            server_time=server_time,
        )
        assert plan.symbol == symbol
    for forged_server in (
        replace(server_time, time_second=server_time.time_second + 2),
        replace(server_time, time_nano=server_time.time_nano + 1_000_000),
        replace(server_time, top_level_time_ms=server_time.top_level_time_ms + 1_000),
    ):
        _assert_plan_error(
            api,
            "server_time_identity_invalid",
            instrument=_instrument(
                forged_server,
                snapshot_server_time_ms=forged_server.server_time_ms,
            ),
            server_time=forged_server,
        )


def test_int64_and_instrument_lifecycle_bounds_are_fail_closed():
    api = _api()
    max_int64 = (1 << 63) - 1
    too_large_aligned = (max_int64 // MINUTE_MS + 1) * MINUTE_MS
    ordinary_server = _server()

    _assert_plan_error(
        api,
        "instrument_lifecycle_invalid",
        instrument=_instrument(ordinary_server, launch_time_ms=max_int64),
        server_time=ordinary_server,
    )
    _assert_plan_error(
        api,
        "instrument_lifecycle_invalid",
        instrument=_instrument(
            ordinary_server,
            launch_time_ms=10 * MINUTE_MS,
            delivery_time_ms=5 * MINUTE_MS,
        ),
        server_time=ordinary_server,
    )
    _assert_plan_error(
        api,
        "window_time_out_of_int64",
        requested_window=InclusiveMinuteWindow(too_large_aligned, too_large_aligned),
    )

    huge_server = _server(last_closed_minute=max_int64 // MINUTE_MS + 2)
    _assert_plan_error(
        api,
        "server_time_identity_invalid",
        instrument=_instrument(huge_server),
        server_time=huge_server,
    )


def test_exact_model_identity_is_required():
    api = _api()
    values = _kwargs()
    _assert_plan_error(api, "instrument_not_exact_model", instrument=object())
    _assert_plan_error(api, "server_time_not_exact_model", server_time=object())
    _assert_plan_error(api, "requested_window_not_exact_model", requested_window=(0, 1))
    assert type(values["instrument"]) is BybitInstrumentMeta


def test_replay_ineligible_instrument_is_rejected():
    api = _api()
    server_time = _server()
    invalid_variants = (
        {"contract_type": "LinearFutures"},
        {"status": "Settled"},
        {"quote_coin": "USDC"},
        {"settle_coin": "USDC"},
        {"is_pre_listing": True},
        {"funding_interval_minutes": 0},
    )
    for variant in invalid_variants:
        instrument = _instrument(server_time, **variant)
        _assert_plan_error(
            api,
            "instrument_not_replay_eligible",
            instrument=instrument,
            server_time=server_time,
        )


def test_plan_span_exact_limit_passes_and_limit_plus_one_fails():
    api = _api()
    server_time = _server(last_closed_minute=50_000)
    instrument = _instrument(server_time, funding_interval_minutes=480)
    all_rows = _minutes(0, 44_639)
    plan = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 44_639 * MINUTE_MS),
        observed_trade_open_times_ms=all_rows,
        observed_mark_open_times_ms=all_rows,
    )
    assert plan.plan_span_minutes == 44_640
    _assert_plan_error(
        api,
        "plan_span_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 44_640 * MINUTE_MS),
    )


def test_trade_missing_windows_split_at_1000_oldest_first():
    api = _api()
    window = InclusiveMinuteWindow(0, 1000 * MINUTE_MS)
    plan = _build(
        api,
        requested_window=window,
        observed_mark_open_times_ms=_minutes(0, 1000),
    )
    trade = tuple(spec for spec in plan.requests if spec.dataset == "trade_kline_1m")
    assert [(spec.start_ms, spec.end_ms, spec.limit) for spec in trade] == [
        (0, 999 * MINUTE_MS, 1000),
        (1000 * MINUTE_MS, 1000 * MINUTE_MS, 1),
    ]
    assert all(spec.pagination == "missing_windows_ascending" for spec in trade)


def test_mark_missing_windows_split_at_1000_oldest_first():
    api = _api()
    window = InclusiveMinuteWindow(0, 1000 * MINUTE_MS)
    plan = _build(
        api,
        requested_window=window,
        observed_trade_open_times_ms=_minutes(0, 1000),
    )
    mark = tuple(spec for spec in plan.requests if spec.dataset == "mark_kline_1m")
    assert [(spec.start_ms, spec.end_ms, spec.limit) for spec in mark] == [
        (0, 999 * MINUTE_MS, 1000),
        (1000 * MINUTE_MS, 1000 * MINUTE_MS, 1),
    ]
    assert all(spec.endpoint == "/v5/market/mark-price-kline" for spec in mark)


def test_observed_trade_timestamps_create_exact_resume_holes():
    api = _api()
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 10 * MINUTE_MS),
        observed_trade_open_times_ms=(3 * MINUTE_MS, 7 * MINUTE_MS),
        observed_mark_open_times_ms=_minutes(0, 10),
    )
    trade = tuple(spec for spec in plan.requests if spec.dataset == "trade_kline_1m")
    assert [(spec.start_ms, spec.end_ms) for spec in trade] == [
        (0, 2 * MINUTE_MS),
        (4 * MINUTE_MS, 6 * MINUTE_MS),
        (8 * MINUTE_MS, 10 * MINUTE_MS),
    ]
    assert plan.trade_missing_row_count == 9


def test_observed_mark_timestamps_create_independent_resume_holes():
    api = _api()
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 8 * MINUTE_MS),
        observed_trade_open_times_ms=_minutes(0, 8),
        observed_mark_open_times_ms=(2 * MINUTE_MS, 5 * MINUTE_MS),
    )
    mark = tuple(spec for spec in plan.requests if spec.dataset == "mark_kline_1m")
    assert [(spec.start_ms, spec.end_ms) for spec in mark] == [
        (0, MINUTE_MS),
        (3 * MINUTE_MS, 4 * MINUTE_MS),
        (6 * MINUTE_MS, 8 * MINUTE_MS),
    ]
    assert plan.mark_missing_row_count == 7


def test_fully_observed_klines_emit_no_kline_requests():
    api = _api()
    observed = _minutes(0, 12)
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 12 * MINUTE_MS),
        observed_trade_open_times_ms=observed,
        observed_mark_open_times_ms=observed,
    )
    assert all(spec.dataset == "funding_rate" for spec in plan.requests)
    assert plan.trade_missing_row_count == 0
    assert plan.mark_missing_row_count == 0
    assert plan.request_count >= 1


def test_observed_inputs_must_be_exact_tuples():
    api = _api()
    _assert_plan_error(
        api,
        "observed_trade_open_times_ms_not_exact_tuple",
        observed_trade_open_times_ms=[],
    )
    _assert_plan_error(
        api,
        "observed_mark_open_times_ms_not_exact_tuple",
        observed_mark_open_times_ms=iter(()),
    )
    _assert_plan_error(
        api,
        "observed_funding_times_ms_not_exact_tuple",
        observed_funding_times_ms=frozenset(),
    )


def test_observed_members_must_be_exact_ints():
    api = _api()
    _assert_plan_error(
        api,
        "observed_trade_open_times_ms_timestamp_not_exact_int",
        observed_trade_open_times_ms=(False,),
    )
    _assert_plan_error(
        api,
        "observed_mark_open_times_ms_timestamp_not_exact_int",
        observed_mark_open_times_ms=(Decimal("0"),),
    )
    _assert_plan_error(
        api,
        "observed_funding_times_ms_timestamp_not_exact_int",
        observed_funding_times_ms=(True,),
    )


def test_observed_members_must_be_strictly_increasing_and_unique():
    api = _api()
    _assert_plan_error(
        api,
        "observed_trade_open_times_ms_timestamps_not_strictly_increasing",
        observed_trade_open_times_ms=(MINUTE_MS, MINUTE_MS),
    )
    _assert_plan_error(
        api,
        "observed_mark_open_times_ms_timestamps_not_strictly_increasing",
        observed_mark_open_times_ms=(2 * MINUTE_MS, MINUTE_MS),
    )
    _assert_plan_error(
        api,
        "observed_funding_times_ms_timestamps_not_strictly_increasing",
        observed_funding_times_ms=(MINUTE_MS, 0),
    )


def test_observed_members_must_be_minute_aligned():
    api = _api()
    _assert_plan_error(
        api,
        "observed_trade_open_times_ms_timestamp_not_minute_aligned",
        observed_trade_open_times_ms=(1,),
    )
    _assert_plan_error(
        api,
        "observed_mark_open_times_ms_timestamp_not_minute_aligned",
        observed_mark_open_times_ms=(MINUTE_MS + 1,),
    )
    _assert_plan_error(
        api,
        "observed_funding_times_ms_timestamp_not_minute_aligned",
        observed_funding_times_ms=(2 * MINUTE_MS + 1,),
    )


def test_observed_members_must_stay_inside_requested_cutoffs():
    api = _api()
    window = InclusiveMinuteWindow(5 * MINUTE_MS, 10 * MINUTE_MS)
    _assert_plan_error(
        api,
        "observed_trade_open_times_ms_timestamp_outside_requested_window",
        requested_window=window,
        observed_trade_open_times_ms=(4 * MINUTE_MS,),
    )
    _assert_plan_error(
        api,
        "observed_mark_open_times_ms_timestamp_outside_requested_window",
        requested_window=window,
        observed_mark_open_times_ms=(11 * MINUTE_MS,),
    )
    _assert_plan_error(
        api,
        "observed_funding_times_ms_timestamp_outside_requested_window",
        requested_window=window,
        observed_funding_times_ms=(4 * MINUTE_MS,),
    )


def test_funding_is_full_range_recapture_despite_observed_history():
    api = _api()
    window = InclusiveMinuteWindow(0, 249 * MINUTE_MS)
    empty = _build(api, requested_window=window)
    observed = _build(
        api,
        requested_window=window,
        observed_funding_times_ms=_minutes(0, 249),
    )
    empty_specs = tuple(spec for spec in empty.requests if spec.dataset == "funding_rate")
    observed_specs = tuple(spec for spec in observed.requests if spec.dataset == "funding_rate")
    assert empty_specs == observed_specs
    assert observed.observed_funding_row_count == 250
    assert empty.observed_funding_times_sha256 == _funding_digest(())
    assert observed.observed_funding_times_sha256 == _funding_digest(_minutes(0, 249))
    assert observed.funding_coverage_proven_bool is False
    assert observed.historical_market_data_coverage_proven_bool is False


def test_funding_windows_use_199_target_200_limit_and_plus_one_ms_partition():
    api = _api()
    values = _kwargs(start_minute=0, end_minute=249, funding_interval_minutes=480)
    plan = api.build_historical_capture_plan(**values)
    funding = tuple(spec for spec in plan.requests if spec.dataset == "funding_rate")
    assert [(spec.start_ms, spec.end_ms) for spec in funding] == [
        (198 * MINUTE_MS + 1, 249 * MINUTE_MS),
        (0, 198 * MINUTE_MS),
    ]
    assert [spec.target_row_count for spec in funding] == [51, 199]
    assert [spec.limit for spec in funding] == [200, 200]
    oldest_first = tuple(reversed(funding))
    assert oldest_first[0].end_ms + 1 == oldest_first[1].start_ms


def test_funding_partition_is_independent_of_current_instrument_interval():
    api = _api()
    server_time = _server()
    window = InclusiveMinuteWindow(0, 600 * MINUTE_MS)
    fast = _build(
        api,
        instrument=_instrument(server_time, funding_interval_minutes=1),
        server_time=server_time,
        requested_window=window,
    )
    slow = _build(
        api,
        instrument=_instrument(server_time, funding_interval_minutes=480),
        server_time=server_time,
        requested_window=window,
    )
    fast_specs = tuple(spec for spec in fast.requests if spec.dataset == "funding_rate")
    slow_specs = tuple(spec for spec in slow.requests if spec.dataset == "funding_rate")
    assert fast_specs == slow_specs
    assert [(spec.start_ms, spec.end_ms, spec.target_row_count) for spec in fast_specs] == [
        (596 * MINUTE_MS + 1, 600 * MINUTE_MS, 4),
        (397 * MINUTE_MS + 1, 596 * MINUTE_MS, 199),
        (198 * MINUTE_MS + 1, 397 * MINUTE_MS, 199),
        (0, 198 * MINUTE_MS, 199),
    ]
    assert [spec.limit for spec in fast_specs] == [200, 200, 200, 200]
    assert fast.funding_interval_minutes == 1
    assert slow.funding_interval_minutes == 480


def test_funding_specs_have_exact_backward_literals_and_params():
    api = _api()
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 10 * MINUTE_MS),
        observed_trade_open_times_ms=_minutes(0, 10),
        observed_mark_open_times_ms=_minutes(0, 10),
    )
    assert len(plan.requests) == 1
    spec = plan.requests[0]
    assert (spec.dataset, spec.endpoint, spec.pagination) == (
        "funding_rate",
        "/v5/market/funding/history",
        "backward_full_range",
    )
    assert spec.params == (
        ("category", "linear"),
        ("symbol", "BTCUSDT"),
        ("startTime", 0),
        ("endTime", 10 * MINUTE_MS),
        ("limit", 200),
    )


def test_kline_specs_have_exact_relative_endpoints_and_param_order():
    api = _api()
    plan = _build(api, requested_window=InclusiveMinuteWindow(0, MINUTE_MS))
    trade, mark = plan.requests[:2]
    assert (trade.dataset, trade.endpoint, trade.pagination) == (
        "trade_kline_1m",
        "/v5/market/kline",
        "missing_windows_ascending",
    )
    assert trade.params == (
        ("category", "linear"),
        ("symbol", "BTCUSDT"),
        ("interval", "1"),
        ("start", 0),
        ("end", MINUTE_MS),
        ("limit", 2),
    )
    assert mark.params == trade.params
    assert mark.endpoint == "/v5/market/mark-price-kline"
    assert all(
        "http" not in spec.endpoint and "host" not in dict(spec.params) for spec in plan.requests
    )


def test_global_order_sequence_and_semantic_keys_are_exact():
    api = _api()
    server_time = _server()
    plan = _build(
        api,
        instrument=_instrument(server_time, funding_interval_minutes=1),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 249 * MINUTE_MS),
        observed_trade_open_times_ms=(3 * MINUTE_MS,),
        observed_mark_open_times_ms=(5 * MINUTE_MS,),
    )
    datasets = [spec.dataset for spec in plan.requests]
    first_mark = datasets.index("mark_kline_1m")
    first_funding = datasets.index("funding_rate")
    assert all(value == "trade_kline_1m" for value in datasets[:first_mark])
    assert all(value == "mark_kline_1m" for value in datasets[first_mark:first_funding])
    assert all(value == "funding_rate" for value in datasets[first_funding:])
    assert [spec.sequence_id for spec in plan.requests] == list(range(1, plan.request_count + 1))
    keys = [(spec.dataset, spec.start_ms, spec.end_ms) for spec in plan.requests]
    assert len(keys) == len(set(keys))


def test_exact_totals_charge_kline_rows_and_full_funding_limits():
    api = _api()
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 10 * MINUTE_MS),
        observed_trade_open_times_ms=(0, MINUTE_MS),
        observed_mark_open_times_ms=(0,),
    )
    assert plan.trade_missing_row_count == 9
    assert plan.mark_missing_row_count == 10
    assert plan.funding_recapture_observation_upper_bound == 11
    assert plan.request_count == 3
    assert plan.planned_max_response_rows == 9 + 10 + 200
    assert plan.planned_max_response_rows == sum(spec.limit for spec in plan.requests)


def test_exact_request_count_256_and_257_boundary():
    api = _api()
    server_time = _server(last_closed_minute=50_000)
    instrument = _instrument(server_time)
    window = InclusiveMinuteWindow(0, 44_639 * MINUTE_MS)
    all_mark = _minutes(0, 44_639)
    accepted = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        observed_trade_open_times_ms=_observed_except(
            44_640,
            {2 * index for index in range(31)},
        ),
        observed_mark_open_times_ms=all_mark,
    )
    assert accepted.request_count == 256
    _assert_plan_error(
        api,
        "request_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        observed_trade_open_times_ms=_observed_except(
            44_640,
            {2 * index for index in range(32)},
        ),
        observed_mark_open_times_ms=all_mark,
    )


def test_request_limit_precedes_response_rows_when_both_are_exceeded():
    api = _api()
    server_time = _server(last_closed_minute=50_000)
    _assert_plan_error(
        api,
        "request_limit_exceeded",
        instrument=_instrument(server_time),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 44_639 * MINUTE_MS),
    )


def test_exact_response_rows_100000_and_100001_boundary():
    api = _api()
    server_time = _server(last_closed_minute=40_000)
    instrument = _instrument(server_time)
    window = InclusiveMinuteWindow(0, 33_233 * MINUTE_MS)
    accepted = _build(
        api,
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        observed_trade_open_times_ms=_minutes(33_166, 33_233),
    )
    assert accepted.request_count == 236
    assert accepted.planned_max_response_rows == 100_000
    _assert_plan_error(
        api,
        "response_row_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        observed_trade_open_times_ms=_minutes(33_167, 33_233),
    )


def test_models_are_deeply_immutable_hashable_and_deterministic():
    api = _api()
    first = _build(api)
    second = _build(api)
    assert first == second
    assert first.requests == second.requests
    assert hash(first) == hash(second)
    assert hash(first.requests[0]) == hash(second.requests[0])
    with pytest.raises(FrozenInstanceError):
        first.symbol = "ETHUSDT"
    with pytest.raises(TypeError):
        first.requests[0].params[0] = ("category", "inverse")


def test_direct_model_construction_rejects_forged_guardrails_caps_and_totals():
    api = _api()
    plan = _build(api)
    for forged in (
        {"schema": "weaker_v2"},
        {"category": "inverse"},
        {"symbol": "btcusdt"},
        {"observed_funding_times_sha256": "not-a-sha256"},
        {"launch_cutoff_open_time_ms": plan.request_start_open_time_ms + MINUTE_MS},
        {"server_cutoff_open_time_ms": plan.request_cutoff_open_time_ms - MINUTE_MS},
    ):
        with pytest.raises(api.HistoricalPlanError, match="^plan_identity_invalid$"):
            replace(plan, **forged)
    for guardrail in (
        "network_authorized_bool",
        "credentials_allowed_bool",
        "private_api_allowed_bool",
        "live_execution_authorized_bool",
        "funding_coverage_proven_bool",
        "historical_market_data_coverage_proven_bool",
        "parameter_selection_authorized_bool",
        "sufficient_for_parameter_selection_bool",
        "native_equivalence_proven_bool",
    ):
        with pytest.raises(api.HistoricalPlanError, match="^plan_guardrails_invalid$"):
            replace(plan, **{guardrail: True})
    with pytest.raises(api.HistoricalPlanError, match="^plan_fixed_limits_invalid$"):
        replace(plan, max_total_requests=257)
    with pytest.raises(api.HistoricalPlanError, match="^plan_totals_invalid$"):
        replace(plan, request_count=plan.request_count + 1)
    reordered = tuple(reversed(plan.requests))
    with pytest.raises(api.HistoricalPlanError, match="^plan_requests_invalid$"):
        replace(plan, requests=reordered)
    bad_sequence = (replace(plan.requests[0], sequence_id=2),) + plan.requests[1:]
    with pytest.raises(api.HistoricalPlanError, match="^plan_requests_invalid$"):
        replace(plan, requests=bad_sequence)


def test_direct_request_construction_rejects_noncanonical_params():
    api = _api()
    plan = _build(api)
    spec = plan.requests[0]
    forged_variants = (
        {"params": dict(spec.params)},
        {"endpoint": "https://api.bybit.com/v5/market/kline"},
        {"dataset": "funding"},
        {"pagination": "cursor"},
        {"limit": spec.limit + 1},
        {"target_row_count": spec.target_row_count + 1},
        {"requested_minute_count": spec.requested_minute_count + 1},
        {"params": spec.params + (("api_key", "forbidden"),)},
    )
    for forged in forged_variants:
        with pytest.raises(api.HistoricalPlanError, match="^request_spec_invalid$"):
            replace(spec, **forged)
    funding = next(request for request in plan.requests if request.dataset == "funding_rate")
    for forged in (
        {"target_row_count": funding.target_row_count - 1},
        {"start_ms": funding.start_ms + 1},
        {"params": funding.params[:-1] + (("limit", 199),)},
    ):
        with pytest.raises(api.HistoricalPlanError, match="^request_spec_invalid$"):
            replace(funding, **forged)


def test_public_constant_rebinding_cannot_weaken_private_policy(monkeypatch):
    api = _api()
    monkeypatch.setattr(api, "MAX_PLAN_SPAN_MINUTES", 10**9)
    monkeypatch.setattr(api, "KLINE_LIMIT", 10**9)
    monkeypatch.setattr(api, "FUNDING_LIMIT", 10**9)
    monkeypatch.setattr(api, "FUNDING_TARGET_RECORDS", 10**9)
    monkeypatch.setattr(api, "MAX_TOTAL_REQUESTS", 10**9)
    monkeypatch.setattr(api, "MAX_TOTAL_RESPONSE_ROWS", 10**9)

    server_time = _server(last_closed_minute=50_000)
    instrument = _instrument(server_time, funding_interval_minutes=480)
    _assert_plan_error(
        api,
        "plan_span_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 44_640 * MINUTE_MS),
    )

    full_window = InclusiveMinuteWindow(0, 44_639 * MINUTE_MS)
    all_mark = _minutes(0, 44_639)
    _assert_plan_error(
        api,
        "request_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=full_window,
        observed_trade_open_times_ms=_observed_except(
            44_640,
            {2 * index for index in range(32)},
        ),
        observed_mark_open_times_ms=all_mark,
    )

    _assert_plan_error(
        api,
        "response_row_limit_exceeded",
        instrument=instrument,
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, 33_233 * MINUTE_MS),
        observed_trade_open_times_ms=_minutes(33_167, 33_233),
    )

    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 1000 * MINUTE_MS),
        observed_mark_open_times_ms=_minutes(0, 1000),
    )
    assert (
        plan.max_plan_span_minutes,
        plan.max_total_requests,
        plan.max_total_response_rows,
    ) == (44_640, 256, 100_000)
    trade = tuple(request for request in plan.requests if request.dataset == "trade_kline_1m")
    funding = tuple(request for request in plan.requests if request.dataset == "funding_rate")
    assert [request.limit for request in trade] == [1000, 1]
    assert all(request.limit == 200 for request in funding)
    assert all(request.target_row_count <= 199 for request in funding)


def test_canonical_json_has_one_lf_and_sha256_binds_exact_bytes():
    api = _api()
    plan = _build(
        api,
        requested_window=InclusiveMinuteWindow(0, 0),
        observed_trade_open_times_ms=(0,),
        observed_mark_open_times_ms=(0,),
    )
    data = plan.canonical_json_bytes()
    assert type(data) is bytes
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    decoded = json.loads(data)
    assert data == (
        json.dumps(decoded, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    assert plan.sha256() == hashlib.sha256(data).hexdigest()
    assert len(plan.sha256()) == 64
    assert decoded["observed_funding_times_sha256"] == _funding_digest(())
    assert decoded["historical_market_data_coverage_proven_bool"] is False
    assert decoded["parameter_selection_authorized_bool"] is False
    assert decoded["sufficient_for_parameter_selection_bool"] is False
    assert decoded["native_equivalence_proven_bool"] is False
    assert decoded["requests"][0]["params"] == [
        ["category", "linear"],
        ["symbol", "BTCUSDT"],
        ["startTime", 0],
        ["endTime", 0],
        ["limit", 200],
    ]


def test_forbidden_client_header_host_clock_and_cap_surfaces_are_rejected():
    api = _api()
    values = _kwargs()
    for forbidden in (
        {"client": object()},
        {"headers": {"X-BAPI-API-KEY": "not-a-secret"}},
        {"base_url": "https://api.bybit.com"},
        {"host": "api.bybit.com"},
        {"now_ms": 0},
        {"max_requests": 257},
        {"kline_limit": 1001},
    ):
        with pytest.raises(TypeError):
            api.build_historical_capture_plan(**values, **forbidden)


def test_planning_calls_no_network_filesystem_or_wall_clock(monkeypatch):
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

    plan = _build(api)
    assert plan.request_count == len(plan.requests)
    assert plan.sha256() == hashlib.sha256(plan.canonical_json_bytes()).hexdigest()
