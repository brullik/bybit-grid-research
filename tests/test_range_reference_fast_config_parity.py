from __future__ import annotations

import ast
import importlib.util
import inspect
import math
import random
import types
from dataclasses import replace
from pathlib import Path
from typing import Any

import polars as pl
import pytest

import bybit_grid.research.range_core.adapter as range_adapter
import bybit_grid.research.range_detector as range_detector
from bybit_grid.research.range_core import FUNNEL_KEYS, numpy_fast, python_reference
from bybit_grid.research.range_core.adapter import (
    arrays_from_frame,
    detect_ranges_core_with_funnel,
)
from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile


SENTINEL = "range_reference_fast_config_parity_contract_unavailable"
CONTRACT_VERSION = "range-reference-fast-config-parity-v1"
MODULE_CONTRACT_NAME = "RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT"
RANGE_REFERENCE_FAST_CONFIG_PARITY_TEST_CONTRACT = (
    "range-reference-fast-config-parity-v1"
)
BASE_MS = 1_800_000_000_000
MINUTE_MS = 60_000


def _load_build_range_candidates() -> Any:
    path = (
        Path(range_detector.__file__).resolve().parents[3]
        / "scripts"
        / "build_range_candidates.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ordinary_test_build_range_candidates",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(SENTINEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_range_candidates = _load_build_range_candidates()
PRODUCTION_MODULES = (
    build_range_candidates,
    range_detector,
    range_adapter,
    numpy_fast,
    python_reference,
)


def _available() -> None:
    if any(
        getattr(module, MODULE_CONTRACT_NAME, None) != CONTRACT_VERSION
        for module in PRODUCTION_MODULES
    ):
        raise RuntimeError(SENTINEL)


def _profile(**changes: object) -> RangeProfile:
    base = RangeProfile(
        name="parity_fixture",
        range_height_pct_min=0.0,
        range_height_pct_max=1.0,
        range_height_atr_min=0.0,
        range_height_atr_max=1_000_000.0,
        min_midline_cross_count=0,
        min_touches_lower_zone=1,
        min_touches_upper_zone=1,
        max_abs_slope_pct_per_window=1.0,
        max_zero_volume_window_pct=1.0,
        require_current_middle_zone=True,
        require_lower_upper_entries=True,
        min_path_length_over_range=0.0,
        min_range_quality_score=0.0,
    )
    return replace(base, **changes)


def _wave_frame(
    n: int = 40,
    *,
    final_close: float | None = None,
    with_turnover: bool = True,
) -> pl.DataFrame:
    closes = [99.8 if index % 2 == 0 else 100.2 for index in range(n)]
    if final_close is not None and closes:
        closes[-1] = final_close
    data: dict[str, object] = {
        "open_time_ms": [BASE_MS + index * MINUTE_MS for index in range(n)],
        "open": closes,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": closes,
        "volume": [1.0] * n,
    }
    if with_turnover:
        data["turnover"] = [close for close in closes]
    return pl.DataFrame(data)


def _assert_value_equal(left: object, right: object) -> None:
    if type(left) is float or type(right) is float:
        assert type(left) is float
        assert type(right) is float
        left_float = float(left)
        right_float = float(right)
        if math.isnan(left_float) or math.isnan(right_float):
            assert math.isnan(left_float) and math.isnan(right_float)
        else:
            assert math.isclose(
                left_float,
                right_float,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
    else:
        assert type(left) is type(right)
        assert left == right


def _assert_frames_equal(left: pl.DataFrame, right: pl.DataFrame) -> None:
    assert left.columns == right.columns
    assert left.schema == right.schema
    assert left.height == right.height
    for left_row, right_row in zip(left.to_dicts(), right.to_dicts(), strict=True):
        assert left_row.keys() == right_row.keys()
        for key in left_row:
            _assert_value_equal(left_row[key], right_row[key])


def _assert_funnel(funnel: dict[str, int], output_height: int) -> None:
    assert type(funnel) is dict
    assert tuple(funnel) == FUNNEL_KEYS
    assert all(type(value) is int and value >= 0 for value in funnel.values())
    accounted = sum(
        funnel[key]
        for key in FUNNEL_KEYS
        if key not in {"total_window_positions", "insufficient_history_rejection_count"}
    )
    assert accounted == funnel["total_window_positions"]
    assert funnel["raw_candidate_pass_count"] == output_height


def _module_tree(module: object) -> ast.Module:
    path = Path(getattr(module, "__file__", ""))
    assert path.is_file()
    return ast.parse(path.read_text(encoding="utf-8", errors="strict"))


def _assert_no_cross_core_reference(
    module: object,
    *,
    forbidden_modules: tuple[str, ...],
    forbidden_callables: tuple[str, ...],
    forbidden_routes: tuple[object, ...],
) -> None:
    tree = _module_tree(module)
    imported_callable_aliases: set[str] = set()

    def module_matches(candidate: str) -> bool:
        normalized = candidate.lstrip(".")
        return any(
            normalized == forbidden
            or normalized.startswith(f"{forbidden}.")
            or forbidden.endswith(f".{normalized}")
            for forbidden in forbidden_modules
            if normalized
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not module_matches(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported = ".".join(
                    part for part in (node.module or "", alias.name) if part
                )
                assert not module_matches(imported)
                if alias.name in forbidden_callables:
                    imported_callable_aliases.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {
                    *forbidden_callables,
                    *imported_callable_aliases,
                }
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_callables
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            assert not module_matches(node.value)
            assert node.value not in forbidden_callables

    def code_names(code: types.CodeType) -> set[str]:
        names = set(code.co_names)
        for constant in code.co_consts:
            if isinstance(constant, types.CodeType):
                names.update(code_names(constant))
        return names

    def is_forbidden_route(value: object) -> bool:
        return any(value is route for route in forbidden_routes)

    for value in vars(module).values():
        assert not is_forbidden_route(value)
        if not inspect.isfunction(value) or value.__module__ != module.__name__:
            continue
        assert all(
            not is_forbidden_route(value.__globals__.get(name))
            for name in code_names(value.__code__)
        )
        assert all(not is_forbidden_route(item) for item in (value.__defaults__ or ()))
        assert all(
            not is_forbidden_route(item)
            for item in (value.__kwdefaults__ or {}).values()
        )
        for cell in value.__closure__ or ():
            try:
                captured = cell.cell_contents
            except ValueError:
                continue
            assert not is_forbidden_route(captured)


def _assert_no_multiplied_sign_test(module: object) -> None:
    tree = _module_tree(module)

    for scope in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        assignments: dict[str, ast.expr] = {}
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                assignments[node.targets[0].id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.value is not None:
                    assignments[node.target.id] = node.value

        def resolve(node: ast.expr, seen: frozenset[str] = frozenset()) -> ast.expr:
            if (
                isinstance(node, ast.Name)
                and node.id in assignments
                and node.id not in seen
            ):
                return resolve(assignments[node.id], seen | {node.id})
            return node

        def call_name(node: ast.Call) -> str:
            if isinstance(node.func, ast.Name):
                return node.func.id
            if isinstance(node.func, ast.Attribute):
                return node.func.attr
            return ""

        def is_side_expression(node: ast.expr) -> bool:
            node = resolve(node)
            if isinstance(node, (ast.Compare, ast.BinOp)):
                return isinstance(node, ast.Compare) or isinstance(node.op, ast.Sub)
            if not isinstance(node, ast.Call):
                return False
            if call_name(node) == "subtract" and len(node.args) >= 2:
                return True
            return (
                call_name(node) == "sign"
                and bool(node.args)
                and is_side_expression(node.args[0])
            )

        def is_multiplied_sides(node: ast.expr) -> bool:
            node = resolve(node)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                operands = (node.left, node.right)
            elif (
                isinstance(node, ast.Call)
                and call_name(node) == "multiply"
                and len(node.args) >= 2
            ):
                operands = (node.args[0], node.args[1])
            else:
                return False
            return all(is_side_expression(operand) for operand in operands)

        multiplied_sides = [
            node
            for node in ast.walk(scope)
            if isinstance(node, (ast.BinOp, ast.Call))
            and is_multiplied_sides(node)
        ]
        assert multiplied_sides == []


def _run(
    frame: pl.DataFrame,
    config: DetectionConfig,
    profile: RangeProfile | None = None,
) -> tuple[pl.DataFrame, dict[str, int]]:
    selected = profile or RANGE_PROFILES[config.profile_name]
    reference = python_reference.detect_from_frame(
        frame,
        "XUSDT",
        config,
        selected,
    )
    reference_again, reference_funnel = python_reference.detect_from_frame_with_funnel(
        frame,
        "XUSDT",
        config,
        selected,
    )
    fast, fast_funnel = numpy_fast.detect_ranges(
        arrays_from_frame(frame),
        "XUSDT",
        selected,
        config.lookbacks,
        config=config,
    )
    _assert_frames_equal(reference, reference_again)
    _assert_frames_equal(reference, fast)
    _assert_funnel(reference_funnel, reference.height)
    _assert_funnel(fast_funnel, fast.height)
    assert reference_funnel == fast_funnel
    return reference, reference_funnel


def test_direct_reference_fast_all_fields_and_funnel_match() -> None:
    _available()
    output, funnel = _run(
        _wave_frame(),
        DetectionConfig(lookbacks=(10, 20)),
        _profile(),
    )
    assert output.height == 52
    assert funnel["total_window_positions"] == 52
    assert funnel["raw_candidate_pass_count"] == 52
    assert set(output.columns) >= {
        "candidate_id",
        "signal_time_ms",
        "range_low",
        "range_high",
        "range_quality_score",
        "turnover_sum_window",
        "volume_sum_window",
    }


def test_core_sources_are_distinct_and_do_not_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _available()
    assert python_reference.detect_from_frame is not numpy_fast.detect_ranges
    assert (
        python_reference.detect_from_frame_with_funnel
        is not numpy_fast.detect_ranges
    )
    assert Path(python_reference.__file__).resolve().name == "python_reference.py"
    assert Path(numpy_fast.__file__).resolve().name == "numpy_fast.py"
    assert (
        Path(python_reference.detect_from_frame.__code__.co_filename).resolve()
        == Path(python_reference.__file__).resolve()
    )
    assert (
        Path(
            python_reference.detect_from_frame_with_funnel.__code__.co_filename
        ).resolve()
        == Path(python_reference.__file__).resolve()
    )
    assert (
        Path(numpy_fast.detect_ranges.__code__.co_filename).resolve()
        == Path(numpy_fast.__file__).resolve()
    )
    shared_routes = (
        range_adapter.detect_ranges_core,
        range_adapter.detect_ranges_core_with_funnel,
        range_detector.detect_range_candidates,
    )
    reference_forbidden_routes = (numpy_fast.detect_ranges, *shared_routes)
    fast_forbidden_routes = (
        python_reference.detect_from_frame,
        python_reference.detect_from_frame_with_funnel,
        *shared_routes,
    )
    _assert_no_cross_core_reference(
        python_reference,
        forbidden_modules=("bybit_grid.research.range_core.numpy_fast",),
        forbidden_callables=(
            "detect_ranges",
            "detect_ranges_core",
            "detect_ranges_core_with_funnel",
            "detect_range_candidates",
        ),
        forbidden_routes=reference_forbidden_routes,
    )
    _assert_no_cross_core_reference(
        numpy_fast,
        forbidden_modules=("bybit_grid.research.range_core.python_reference",),
        forbidden_callables=(
            "detect_from_frame",
            "detect_from_frame_with_funnel",
            "detect_ranges_core",
            "detect_ranges_core_with_funnel",
            "detect_range_candidates",
        ),
        forbidden_routes=fast_forbidden_routes,
    )
    _assert_no_multiplied_sign_test(python_reference)
    _assert_no_multiplied_sign_test(numpy_fast)

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("cross_core_delegation")

    frame = _wave_frame(10)
    config = DetectionConfig(lookbacks=(10,))
    profile = _profile()
    with monkeypatch.context() as isolated:
        isolated.setattr(numpy_fast, "detect_ranges", forbidden)
        isolated.setattr(range_adapter, "detect_ranges_core", forbidden)
        isolated.setattr(range_adapter, "detect_ranges_core_with_funnel", forbidden)
        isolated.setattr(range_detector, "detect_range_candidates", forbidden)
        assert python_reference.detect_from_frame(
            frame,
            "XUSDT",
            config,
            profile,
        ).height == 1
        instrumented, instrumented_funnel = (
            python_reference.detect_from_frame_with_funnel(
                frame,
                "XUSDT",
                config,
                profile,
            )
        )
        assert instrumented.height == 1
        _assert_funnel(instrumented_funnel, 1)
    with monkeypatch.context() as isolated:
        isolated.setattr(python_reference, "detect_from_frame", forbidden)
        isolated.setattr(
            python_reference,
            "detect_from_frame_with_funnel",
            forbidden,
        )
        isolated.setattr(range_adapter, "detect_ranges_core", forbidden)
        isolated.setattr(range_adapter, "detect_ranges_core_with_funnel", forbidden)
        isolated.setattr(range_detector, "detect_range_candidates", forbidden)
        fast, _ = numpy_fast.detect_ranges(
            arrays_from_frame(frame),
            "XUSDT",
            profile,
            config.lookbacks,
            config=config,
        )
        assert fast.height == 1


def test_frame_comparator_rejects_schema_and_python_type_drift() -> None:
    _available()
    with pytest.raises(AssertionError):
        _assert_frames_equal(
            pl.DataFrame({"value": [1]}, schema={"value": pl.Int64}),
            pl.DataFrame({"value": [1.0]}, schema={"value": pl.Float64}),
        )
    with pytest.raises(AssertionError):
        _assert_value_equal(True, 1)
    with pytest.raises(AssertionError):
        _assert_value_equal(1, 1.0)


def test_funnel_contract_rejects_missing_typed_and_unconserved_counts() -> None:
    _available()
    valid = {key: 0 for key in FUNNEL_KEYS}
    _assert_funnel(valid, 0)
    missing = valid.copy()
    missing.pop("slope_rejection_count")
    with pytest.raises(AssertionError):
        _assert_funnel(missing, 0)
    wrong_type = valid.copy()
    wrong_type["total_window_positions"] = True
    with pytest.raises(AssertionError):
        _assert_funnel(wrong_type, 0)
    unconserved = valid.copy()
    unconserved["total_window_positions"] = 1
    with pytest.raises(AssertionError):
        _assert_funnel(unconserved, 0)


def test_mid_zone_width_controls_both_cores() -> None:
    _available()
    frame = _wave_frame(10, final_close=100.2)
    wide, _ = _run(
        frame,
        DetectionConfig(lookbacks=(10,), mid_zone_pct=0.30),
        _profile(),
    )
    narrow, funnel = _run(
        frame,
        DetectionConfig(lookbacks=(10,), mid_zone_pct=0.10),
        _profile(),
    )
    assert wide.height == 1
    assert narrow.is_empty()
    assert funnel["middle_zone_rejection_count"] == 1
    exact_mid, _ = _run(
        _wave_frame(10, final_close=100.0),
        DetectionConfig(lookbacks=(10,), mid_zone_pct=0.0),
        _profile(),
    )
    assert exact_mid.height == 1


def test_lower_and_upper_zone_widths_control_touch_boundary() -> None:
    _available()
    frame = pl.DataFrame(
        {
            "open_time_ms": [BASE_MS + index * MINUTE_MS for index in range(5)],
            "open": [99.8, 100.2, 99.8, 100.2, 100.0],
            "high": [101.0, 100.65, 100.65, 100.65, 100.65],
            "low": [99.0, 99.35, 99.35, 99.35, 99.35],
            "close": [99.8, 100.2, 99.8, 100.2, 100.0],
            "volume": [1.0] * 5,
        }
    )
    profile = _profile(min_touches_lower_zone=2, min_touches_upper_zone=2)
    loose, _ = _run(
        frame,
        DetectionConfig(
            lookbacks=(5,),
            lower_zone_pct=0.20,
            upper_zone_pct=0.20,
        ),
        profile,
    )
    tight, funnel = _run(
        frame,
        DetectionConfig(
            lookbacks=(5,),
            lower_zone_pct=0.10,
            upper_zone_pct=0.10,
        ),
        profile,
    )
    assert loose.height == 1
    assert tight.is_empty()
    assert funnel["touch_count_rejection_count"] == 1
    for lower_boundary, upper_boundary in ((0.0, 1.0), (1.0, 0.0)):
        boundary_output, _ = _run(
            _wave_frame(5, final_close=100.0),
            DetectionConfig(
                lookbacks=(5,),
                lower_zone_pct=lower_boundary,
                mid_zone_pct=0.0,
                upper_zone_pct=upper_boundary,
                max_zero_volume_window_pct=1.0,
                min_range_height_pct=0.0,
                min_valid_candle_pct=1.0,
            ),
            _profile(),
        )
        assert boundary_output.height == 1


def test_minimum_height_and_zero_volume_config_control_both_cores() -> None:
    _available()
    frame = _wave_frame(20).with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(0.0)
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    accepted, _ = _run(
        frame,
        DetectionConfig(
            lookbacks=(20,),
            min_range_height_pct=0.001,
            max_zero_volume_window_pct=0.05,
        ),
        _profile(),
    )
    zero_rejected, zero_funnel = _…843 tokens truncated…_rejection_count"] == 0
    assert funnel["raw_candidate_pass_count"] == 3

    internal_duplicate = _wave_frame(5).with_columns(
        pl.Series(
            "open_time_ms",
            [
                BASE_MS,
                BASE_MS + MINUTE_MS,
                BASE_MS + MINUTE_MS,
                BASE_MS + 3 * MINUTE_MS,
                BASE_MS + 4 * MINUTE_MS,
            ],
        )
    )
    duplicate_output, duplicate_funnel = _run(
        internal_duplicate,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    assert duplicate_output.is_empty()
    assert duplicate_funnel["missing_window_rejection_count"] == 0
    assert duplicate_funnel["duplicate_timestamp_rejection_count"] == 1


def test_irregular_internal_minute_steps_are_missing() -> None:
    _available()
    frame = _wave_frame(5).with_columns(
        pl.Series(
            "open_time_ms",
            [
                BASE_MS,
                BASE_MS + MINUTE_MS,
                BASE_MS + 90_000,
                BASE_MS + 210_000,
                BASE_MS + 4 * MINUTE_MS,
            ],
        )
    )
    output, funnel = _run(
        frame,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    assert output.is_empty()
    assert funnel["missing_window_rejection_count"] == 1
    assert funnel["duplicate_timestamp_rejection_count"] == 0

    off_epoch = _wave_frame(5).with_columns(
        (pl.col("open_time_ms") + 12_345).alias("open_time_ms")
    )
    off_epoch_output, off_epoch_funnel = _run(
        off_epoch,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    assert off_epoch_output.height == 1
    assert off_epoch_funnel["missing_window_rejection_count"] == 0


def test_bad_ohlc_slope_and_quality_have_exact_funnel_ownership() -> None:
    _available()
    bad = _wave_frame(5).with_columns(
        pl.when(pl.int_range(pl.len()) == 2)
        .then(98.0)
        .otherwise(pl.col("high"))
        .alias("high")
    )
    _, bad_funnel = _run(
        bad,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    slope = pl.DataFrame(
        {
            "open_time_ms": [BASE_MS + index * MINUTE_MS for index in range(5)],
            "open": [99.0, 99.5, 100.0, 100.5, 101.0],
            "high": [102.0] * 5,
            "low": [98.0] * 5,
            "close": [99.0, 99.5, 100.0, 100.5, 101.0],
            "volume": [1.0] * 5,
        }
    )
    _, slope_funnel = _run(
        slope,
        DetectionConfig(lookbacks=(5,), mid_zone_pct=1.0),
        _profile(
            require_current_middle_zone=False,
            max_abs_slope_pct_per_window=0.005,
        ),
    )
    quality_output, quality_funnel = _run(
        _wave_frame(5),
        DetectionConfig(lookbacks=(5,)),
        _profile(min_range_quality_score=1_000_000.0),
    )
    no_cross_output, no_cross_funnel = _run(
        _wave_frame(5).with_columns(
            pl.lit(100.0).alias("open"),
            pl.lit(100.0).alias("close"),
        ),
        DetectionConfig(lookbacks=(5,)),
        _profile(min_midline_cross_count=1),
    )
    assert bad_funnel["bad_ohlc_window_rejection_count"] == 1
    assert slope_funnel["slope_rejection_count"] == 1
    assert quality_output.is_empty()
    assert quality_funnel["quality_score_rejection_count"] == 1
    assert no_cross_output.is_empty()
    assert no_cross_funnel["midline_cross_rejection_count"] == 1


def test_adapter_propagates_exact_config_and_rejects_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _available()
    frame = _wave_frame(10, final_close=100.2)
    cfg = DetectionConfig(lookbacks=(10,), mid_zone_pct=0.10)
    direct, direct_funnel = _run(frame, cfg, _profile())
    adapted, adapted_funnel = detect_ranges_core_with_funnel(
        arrays_from_frame(frame),
        "XUSDT",
        _profile(),
        cfg.lookbacks,
        core="numpy_fast",
        config=cfg,
    )
    _assert_frames_equal(direct, adapted)
    _assert_funnel(adapted_funnel, adapted.height)
    assert direct_funnel == adapted_funnel
    reference_adapted, reference_adapted_funnel = detect_ranges_core_with_funnel(
        arrays_from_frame(frame),
        "XUSDT",
        _profile(),
        cfg.lookbacks,
        core="python_reference",
        config=cfg,
    )
    _assert_frames_equal(direct, reference_adapted)
    _assert_funnel(reference_adapted_funnel, reference_adapted.height)
    assert direct_funnel == reference_adapted_funnel
    with pytest.raises(ValueError, match="config.lookbacks must exactly match"):
        detect_ranges_core_with_funnel(
            arrays_from_frame(frame),
            "XUSDT",
            _profile(),
            (5,),
            core="numpy_fast",
            config=cfg,
        )

    full_config = DetectionConfig(
        lookbacks=(5,),
        lower_zone_pct=0.11,
        mid_zone_pct=0.22,
        upper_zone_pct=0.33,
        max_zero_volume_window_pct=0.44,
        min_range_height_pct=0.005,
        min_valid_candle_pct=1.0,
        profile_name="explicit_custom",
    )
    full_profile = _profile(name="explicit_custom")
    captured: list[str] = []

    def fast_spy(
        arrays,
        symbol,
        profile,
        lookbacks,
        *,
        config,
    ):
        del arrays, symbol
        assert profile is full_profile
        assert lookbacks == full_config.lookbacks
        assert config is full_config
        captured.append("numpy_fast")
        return pl.DataFrame(), {key: 0 for key in FUNNEL_KEYS}

    def reference_spy(frame, symbol, config, profile):
        del frame, symbol
        assert profile is full_profile
        assert config is full_config
        captured.append("python_reference")
        return pl.DataFrame(), {key: 0 for key in FUNNEL_KEYS}

    original_fast = numpy_fast.detect_ranges
    with monkeypatch.context() as isolated:
        isolated.setattr(numpy_fast, "detect_ranges", fast_spy)
        for name, value in vars(range_adapter).items():
            if value is original_fast:
                isolated.setattr(range_adapter, name, fast_spy)
        detect_ranges_core_with_funnel(
            arrays_from_frame(_wave_frame(5)),
            "XUSDT",
            full_profile,
            full_config.lookbacks,
            core="numpy_fast",
            config=full_config,
        )
    original_reference = python_reference.detect_from_frame_with_funnel
    with monkeypatch.context() as isolated:
        isolated.setattr(
            python_reference,
            "detect_from_frame_with_funnel",
            reference_spy,
        )
        for name, value in vars(range_adapter).items():
            if value is original_reference:
                isolated.setattr(range_adapter, name, reference_spy)
        detect_ranges_core_with_funnel(
            arrays_from_frame(_wave_frame(5)),
            "XUSDT",
            full_profile,
            full_config.lookbacks,
            core="python_reference",
            config=full_config,
        )
    assert captured == ["numpy_fast", "python_reference"]


def test_legacy_direct_fast_tuple_uses_default_config() -> None:
    _available()
    frame = _wave_frame(20)
    modern, modern_funnel = numpy_fast.detect_ranges(
        arrays_from_frame(frame),
        "XUSDT",
        _profile(),
        (10,),
        config=DetectionConfig(lookbacks=(10,)),
    )
    legacy, legacy_funnel = numpy_fast.detect_ranges(
        arrays_from_frame(frame),
        "XUSDT",
        _profile(),
        lookbacks=(10,),
    )
    adapted, adapted_funnel = detect_ranges_core_with_funnel(
        arrays_from_frame(frame),
        "XUSDT",
        _profile(),
        (10,),
        core="numpy_fast",
    )
    _assert_frames_equal(modern, legacy)
    _assert_frames_equal(legacy, adapted)
    _assert_funnel(modern_funnel, modern.height)
    _assert_funnel(legacy_funnel, legacy.height)
    _assert_funnel(adapted_funnel, adapted.height)
    assert modern_funnel == legacy_funnel
    assert legacy_funnel == adapted_funnel
    with pytest.raises(ValueError, match="config.lookbacks must exactly match"):
        numpy_fast.detect_ranges(
            arrays_from_frame(frame),
            "XUSDT",
            _profile(),
            lookbacks=(10,),
            config=DetectionConfig(lookbacks=(5,)),
        )


def test_empty_short_alias_and_permutation_inputs_remain_equivalent() -> None:
    _available()
    empty, empty_funnel = _run(
        _wave_frame(0),
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    short, short_funnel = _run(
        _wave_frame(3),
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    alias = _wave_frame(10, with_turnover=False).rename(
        {
            "open_time_ms": "timestamp_ms",
            "open": "open_price",
            "high": "high_price",
            "low": "low_price",
            "close": "close_price",
        }
    )
    alias_output, _ = _run(
        alias,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    forward, _ = _run(
        _wave_frame(20),
        DetectionConfig(lookbacks=(10,)),
        _profile(),
    )
    reverse, _ = _run(
        _wave_frame(20).reverse(),
        DetectionConfig(lookbacks=(10,)),
        _profile(),
    )
    assert empty.is_empty()
    assert empty_funnel["total_window_positions"] == 0
    assert short.is_empty()
    assert short_funnel["insufficient_history_rejection_count"] == 2
    assert alias_output.height == 6
    _assert_frames_equal(forward, reverse)


def test_nullable_nonfinite_values_recover_and_sums_are_stable() -> None:
    _available()
    nullable = _wave_frame(30).with_columns(
        pl.Series("volume", [None] + [1.0] * 29, dtype=pl.Float64),
        pl.Series("turnover", [None] + [1.0] * 29, dtype=pl.Float64),
    )
    nullable_output, _ = _run(
        nullable,
        DetectionConfig(
            lookbacks=(30,),
            max_zero_volume_window_pct=0.05,
        ),
        _profile(),
    )
    assert nullable_output.height == 1
    assert nullable_output["zero_volume_candles_in_window"][0] == 1
    assert nullable_output["volume_sum_window"][0] == 29.0
    assert nullable_output["turnover_sum_window"][0] == 29.0

    missing_columns = _wave_frame(5).select(
        ["open_time_ms", "open", "high", "low", "close"]
    )
    missing_output, _ = _run(
        missing_columns,
        DetectionConfig(lookbacks=(5,)),
        _profile(),
    )
    assert missing_output.height == 1
    assert missing_output["zero_volume_candles_in_window"][0] == 0
    assert missing_output["volume_sum_window"][0] == 5.0
    assert missing_output["turnover_sum_window"][0] == 0.0

    for invalid in (None, float("nan"), float("inf"), float("-inf"), -1.0):
        normalized = _wave_frame(5).with_columns(
            pl.Series("volume", [invalid, 1.0, 1.0, 1.0, 1.0], dtype=pl.Float64),
            pl.Series("turnover", [invalid, 1.0, 1.0, 1.0, 1.0], dtype=pl.Float64),
        )
        normalized_output, _ = _run(
            normalized,
            DetectionConfig(lookbacks=(5,), max_zero_volume_window_pct=1.0),
            _profile(max_zero_volume_window_pct=1.0),
        )
        assert normalized_output.height == 1
        assert normalized_output["zero_volume_candles_in_window"][0] == 1
        assert normalized_output["volume_sum_window"][0] == 4.0
        assert normalized_output["turnover_sum_window"][0] == 4.0

    for invalid_column in ("close", "high"):
        recovering = _wave_frame(80).with_columns(
            pl.when(pl.int_range(pl.len()) == 0)
            .then(float("nan"))
            .otherwise(pl.col(invalid_column))
            .alias(invalid_column)
        )
        recovered, _ = _run(
            recovering,
            DetectionConfig(lookbacks=(30,)),
            _profile(),
        )
        recovered_row = recovered.filter(
            pl.col("signal_time_ms") == BASE_MS + 60 * MINUTE_MS
        )
        assert recovered_row.height == 1
        assert type(recovered_row["atr_60"][0]) is float
        assert math.isfinite(recovered_row["atr_60"][0])

    dynamic = _wave_frame(80).with_columns(
        pl.Series("volume", [1e20] + [1.0] * 79, dtype=pl.Float64),
        pl.Series("turnover", [1e20] + [1.0] * 79, dtype=pl.Float64),
    )
    dynamic_output, _ = _run(
        dynamic,
        DetectionConfig(lookbacks=(30,)),
        _profile(),
    )
    later = dynamic_output.filter(pl.col("signal_time_ms") == BASE_MS + 59 * MINUTE_MS)
    assert later.height == 1
    assert later["volume_sum_window"][0] == 30.0
    assert later["turnover_sum_window"][0] == 30.0

    widths = [float((index - 1) % 4 + 1) for index in range(1, 16)]
    atr_dynamic = pl.DataFrame(
        {
            "open_time_ms": [BASE_MS + index * MINUTE_MS for index in range(16)],
            "open": [100.0] * 16,
            "high": [1e20] + [100.0 + width / 2 for width in widths],
            "low": [99.0] + [100.0 - width / 2 for width in widths],
            "close": [100.0] * 16,
            "volume": [1.0] * 16,
        }
    )
    atr_output, atr_funnel = _run(
        atr_dynamic,
        DetectionConfig(lookbacks=(14,), mid_zone_pct=1.0),
        _profile(
            range_height_atr_min=30.0,
            require_current_middle_zone=False,
        ),
    )
    assert atr_output.is_empty()
    assert atr_funnel["range_height_rejection_count"] == 1
    assert atr_funnel["range_atr_rejection_count"] == 2

    extreme_closes = [1e300, 1e-300, 1e300]
    extreme_returns = pl.DataFrame(
        {
            "open_time_ms": [BASE_MS + index * MINUTE_MS for index in range(3)],
            "open": extreme_closes,
            "high": extreme_closes,
            "low": extreme_closes,
            "close": extreme_closes,
            "volume": [1.0] * 3,
        }
    )
    extreme_output, _ = _run(
        extreme_returns,
        DetectionConfig(lookbacks=(3,)),
        _profile(require_current_middle_zone=False, min_midline_cross_count=2),
    )
    assert extreme_output.height == 1
    assert extreme_output["midline_crosses"][0] == 2
    assert extreme_output["mean_abs_return_inside_range"][0] > 1_000.0
    assert extreme_output["realized_volatility"][0] > 1_000.0


def test_worker_propagates_advertised_zero_volume_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _available()
    captured: list[DetectionConfig] = []

    def fake_detect(
        arrays,
        symbol,
        profile,
        lookbacks,
        *,
        core,
        config,
    ):
        del arrays, symbol, profile, lookbacks, core
        captured.append(config)
        return pl.DataFrame(), {key: 0 for key in build_range_candidates.REJECTION_KEYS}

    monkeypatch.setattr(
        build_range_candidates, "_read_symbol", lambda *args: _wave_frame(5)
    )
    monkeypatch.setattr(
        build_range_candidates,
        "detect_ranges_core_with_funnel",
        fake_detect,
    )
    result = build_range_candidates._worker(
        {"symbol": "XUSDT"},
        {
            "data_dir": str(tmp_path),
            "raw_output_dir": str(tmp_path / "raw"),
            "event_output_dir": str(tmp_path / "event"),
            "regime_output_dir": str(tmp_path / "regime"),
            "actionable_output_dir": str(tmp_path / "actionable"),
            "output_layer": "raw",
            "lookbacks": "5",
            "profile": "broad_diagnostic",
            "core": "numpy_fast",
            "max_zero_volume_window_pct": 0.0,
            "cooldown_mode": "none",
        },
    )
    assert result["candles_scanned"] == 5
    assert len(captured) == 1
    assert captured[0].lookbacks == (5,)
    assert captured[0].max_zero_volume_window_pct == 0.0
    assert result["max_zero_volume_window_pct"] == 0.0

    monkeypatch.setattr(
        build_range_candidates,
        "load_manifest",
        lambda _path: pl.DataFrame(
            {"symbol": ["XUSDT"], "estimated_kline_rows": [5]}
        ),
    )
    monkeypatch.setattr(
        build_range_candidates.sys,
        "argv",
        [
            "build_range_candidates.py",
            "--dry-run-plan",
            "--max-zero-volume-window-pct",
            "0.0",
        ],
    )
    build_range_candidates.main()
    assert "max_zero_volume_window_pct=0.0" in capsys.readouterr().out


def test_seeded_randomized_direct_parity() -> None:
    _available()
    randomizer = random.Random(155)
    profiles = (
        RANGE_PROFILES["broad_diagnostic"],
        RANGE_PROFILES["balanced_research"],
        RANGE_PROFILES["strict_research"],
    )
    for _case in range(96):
        count = randomizer.randint(5, 60)
        timestamps: list[int] = []
        current = BASE_MS
        for index in range(count):
            if index:
                current += randomizer.choice(
                    (MINUTE_MS, MINUTE_MS, MINUTE_MS, 2 * MINUTE_MS, 0)
                )
            timestamps.append(current)
        closes = [100.0 + randomizer.uniform(-2.0, 2.0) for _ in range(count)]
        highs = [close + randomizer.uniform(0.0, 2.0) for close in closes]
        lows = [close - randomizer.uniform(0.0, 2.0) for close in closes]
        volumes = [
            0.0 if randomizer.random() < 0.05 else randomizer.uniform(0.1, 5.0)
            for _ in range(count)
        ]
        frame = pl.DataFrame(
            {
                "open_time_ms": timestamps,
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        config = DetectionConfig(
            lookbacks=(randomizer.choice((5, 10, 15)),),
            lower_zone_pct=randomizer.choice((0.10, 0.20, 0.30)),
            mid_zone_pct=randomizer.choice((0.10, 0.30, 0.70)),
            upper_zone_pct=randomizer.choice((0.10, 0.20, 0.30)),
            max_zero_volume_window_pct=randomizer.choice((0.0, 0.05, 0.20)),
            min_range_height_pct=randomizer.choice((0.0001, 0.01, 0.03)),
        )
        _run(frame, config, randomizer.choice(profiles))


@pytest.mark.parametrize(
    ("field", "invalid_values"),
    [
        (
            "lookbacks",
            [[], (), [5], "5", None],
        ),
        (
            "lookbacks",
            [
                (5, 5),
                (0,),
                (-1,),
                (True,),
                (1.0,),
                ("5",),
                (None,),
                (float("nan"),),
                (float("inf"),),
                (float("-inf"),),
            ],
        ),
        (
            "lower_zone_pct",
            [True, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.1, 1.1],
        ),
        (
            "mid_zone_pct",
            [True, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.1, 1.1],
        ),
        (
            "upper_zone_pct",
            [True, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.1, 1.1],
        ),
        (
            "max_zero_volume_window_pct",
            [True, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.1, 1.1],
        ),
        (
            "min_range_height_pct",
            [True, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.1],
        ),
        (
            "min_valid_candle_pct",
            [
                True,
                "1.0",
                None,
                float("nan"),
                float("inf"),
                float("-inf"),
                0.0,
                0.99,
                1.01,
            ],
        ),
        ("profile_name", ["", " "]),
        ("profile_name", [None, 1, True]),
    ],
)
def test_invalid_advertised_config_fails_closed(
    field: str,
    invalid_values: list[object],
) -> None:
    _available()
    for value in invalid_values:
        with pytest.raises(ValueError, match=field):
            DetectionConfig(**{field: value})
