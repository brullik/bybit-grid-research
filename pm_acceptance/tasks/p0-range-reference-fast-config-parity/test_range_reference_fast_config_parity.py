from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path
from typing import Any


TASK_ID = "p0-range-reference-fast-config-parity"
SENTINEL = "range_reference_fast_config_parity_contract_unavailable"
CONTRACT_VERSION = "range-reference-fast-config-parity-v1"
MODULE_CONTRACT_NAME = "RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT"
TEST_CONTRACT_NAME = "RANGE_REFERENCE_FAST_CONFIG_PARITY_TEST_CONTRACT"
ORDINARY_TEST_PATH = "tests/test_range_reference_fast_config_parity.py"
ORDINARY_TEST_SHA256 = (
    "46d5c2b47048145345eaa92d2159752281a1229e3e5323e36d0853b3ef538f7d"
)
MODULE_PATHS = (
    "scripts/build_range_candidates.py",
    "src/bybit_grid/research/range_detector.py",
    "src/bybit_grid/research/range_core/adapter.py",
    "src/bybit_grid/research/range_core/numpy_fast.py",
    "src/bybit_grid/research/range_core/python_reference.py",
)
REQUIRED_IMPLEMENTATION_PATHS = (*MODULE_PATHS, ORDINARY_TEST_PATH)
RED_REQUIRED_PATHS = REQUIRED_IMPLEMENTATION_PATHS
_modules_cache: dict[str, Any] | None = None


def _modules() -> dict[str, Any]:
    global _modules_cache
    if _modules_cache is not None:
        return _modules_cache
    names = {
        "build_range_candidates": "scripts.build_range_candidates",
        "range_detector": "bybit_grid.research.range_detector",
        "adapter": "bybit_grid.research.range_core.adapter",
        "numpy_fast": "bybit_grid.research.range_core.numpy_fast",
        "python_reference": "bybit_grid.research.range_core.python_reference",
    }
    try:
        _modules_cache = {
            key: importlib.import_module(name) for key, name in names.items()
        }
    except Exception:
        raise RuntimeError(SENTINEL) from None
    return _modules_cache


def _root() -> Path:
    return Path(_modules()["range_detector"].__file__).resolve().parents[3]


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
    path = _root() / ORDINARY_TEST_PATH
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if _exact_assignment(path, TEST_CONTRACT_NAME) != CONTRACT_VERSION:
        return None
    return CONTRACT_VERSION, hashlib.sha256(raw).hexdigest()


def _available() -> None:
    modules = _modules()
    for key, path in zip(modules, MODULE_PATHS, strict=True):
        module = modules[key]
        if getattr(module, MODULE_CONTRACT_NAME, None) != CONTRACT_VERSION:
            raise RuntimeError(SENTINEL)
        if (
            _exact_assignment(Path(module.__file__).resolve(), MODULE_CONTRACT_NAME)
            != CONTRACT_VERSION
        ):
            raise RuntimeError(SENTINEL)
        if Path(module.__file__).resolve() != (_root() / path).resolve():
            raise RuntimeError(SENTINEL)
    if _ordinary_contract() != (CONTRACT_VERSION, ORDINARY_TEST_SHA256):
        raise RuntimeError(SENTINEL)


def test_contract_markers_and_exact_implementation_scope() -> None:
    _available()
    assert RED_REQUIRED_PATHS == REQUIRED_IMPLEMENTATION_PATHS
    assert all((_root() / path).is_file() for path in REQUIRED_IMPLEMENTATION_PATHS)
    assert _ordinary_contract() == (CONTRACT_VERSION, ORDINARY_TEST_SHA256)

import math
import random
from dataclasses import replace

import polars as pl
import pytest

from bybit_grid.research.range_core import numpy_fast, python_reference
from bybit_grid.research.range_core.adapter import (
    arrays_from_frame,
    detect_ranges_core_with_funnel,
)
from bybit_grid.research.range_detector import DetectionConfig, detect_range_candidates
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile
from scripts import build_range_candidates


RANGE_REFERENCE_FAST_CONFIG_PARITY_TEST_CONTRACT = (
    "range-reference-fast-config-parity-v1"
)
BASE_MS = 1_800_000_000_000
MINUTE_MS = 60_000


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
    if isinstance(left, float) or isinstance(right, float):
        assert left is not None and right is not None
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
        assert left == right


def _assert_frames_equal(left: pl.DataFrame, right: pl.DataFrame) -> None:
    assert left.columns == right.columns
    assert left.height == right.height
    for left_row, right_row in zip(left.to_dicts(), right.to_dicts(), strict=True):
        assert left_row.keys() == right_row.keys()
        for key in left_row:
            _assert_value_equal(left_row[key], right_row[key])


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
    zero_rejected, zero_funnel = _run(
        frame,
        DetectionConfig(
            lookbacks=(20,),
            min_range_height_pct=0.001,
            max_zero_volume_window_pct=0.0,
        ),
        _profile(),
    )
    height_rejected, height_funnel = _run(
        _wave_frame(20),
        DetectionConfig(lookbacks=(20,), min_range_height_pct=0.03),
        _profile(),
    )
    assert accepted.height == 1
    assert zero_rejected.is_empty()
    assert zero_funnel["zero_volume_window_rejection_count"] == 1
    assert height_rejected.is_empty()
    assert height_funnel["range_height_rejection_count"] == 1


def test_profile_name_and_lookbacks_are_effective() -> None:
    _available()
    frame = _wave_frame(40)
    broad = detect_range_candidates(
        frame,
        "XUSDT",
        DetectionConfig(lookbacks=(10,), profile_name="broad_diagnostic"),
    )
    strict = detect_range_candidates(
        frame,
        "XUSDT",
        DetectionConfig(lookbacks=(10,), profile_name="strict_research"),
    )
    output, funnel = _run(
        frame,
        DetectionConfig(lookbacks=(10, 20)),
        _profile(),
    )
    assert broad.height > strict.height
    assert set(output["lookback_minutes"].to_list()) == {10, 20}
    assert funnel["total_window_positions"] == 52
    custom = DetectionConfig(lookbacks=(10,), profile_name="explicit_custom")
    explicit, _ = _run(frame, custom, _profile(name="explicit_custom"))
    assert explicit.height > 0
    with pytest.raises(ValueError, match="profile_name must name"):
        detect_range_candidates(frame, "XUSDT", custom)


def test_min_valid_candle_pct_is_explicitly_versioned_strict() -> None:
    _available()
    assert DetectionConfig(min_valid_candle_pct=1.0).min_valid_candle_pct == 1.0
    with pytest.raises(
        ValueError,
        match="range-reference-fast-config-parity-v1 requires min_valid_candle_pct=1.0",
    ):
        DetectionConfig(min_valid_candle_pct=0.99)


def test_duplicate_before_window_is_not_counted_inside_window() -> None:
    _available()
    frame = _wave_frame(6).with_columns(
        pl.Series(
            "open_time_ms",
            [
                BASE_MS,
                BASE_MS,
                BASE_MS + MINUTE_MS,
                BASE_MS + 2 * MINUTE_MS,
                BASE_MS + 3 * MINUTE_MS,
                BASE_MS + 4 * MINUTE_MS,
            ],
        )
    )
    output, funnel = _run(
        frame,
        DetectionConfig(lookbacks=(3,)),
        _profile(),
    )
    assert output.height == 3
    assert funnel["total_window_positions"] == 4
    assert funnel["missing_window_rejection_count"] == 1
    assert funnel["duplicate_timestamp_rejection_count"] == 0
    assert funnel["raw_candidate_pass_count"] == 3


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
    assert bad_funnel["bad_ohlc_window_rejection_count"] == 1
    assert slope_funnel["slope_rejection_count"] == 1
    assert quality_output.is_empty()
    assert quality_funnel["quality_score_rejection_count"] == 1


def test_adapter_propagates_exact_config_and_rejects_mismatch() -> None:
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
        (10,),
    )
    _assert_frames_equal(modern, legacy)
    assert modern_funnel == legacy_funnel


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

    recovering = _wave_frame(80).with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(float("nan"))
        .otherwise(pl.col("high"))
        .alias("high")
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
    assert recovered_row["atr_60"][0] is not None

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
        _profile(require_current_middle_zone=False),
    )
    assert extreme_output.height == 1
    assert extreme_output["mean_abs_return_inside_range"][0] > 1_000.0
    assert extreme_output["realized_volatility"][0] > 1_000.0


def test_worker_propagates_advertised_zero_volume_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
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
    ("kwargs", "message"),
    [
        ({"lookbacks": ()}, "lookbacks"),
        ({"lookbacks": (5, 5)}, "lookbacks"),
        ({"lookbacks": (0,)}, "lookbacks"),
        ({"lower_zone_pct": 1.1}, "lower_zone_pct"),
        ({"mid_zone_pct": -0.1}, "mid_zone_pct"),
        ({"upper_zone_pct": -0.1}, "upper_zone_pct"),
        ({"max_zero_volume_window_pct": 1.1}, "max_zero_volume_window_pct"),
        ({"min_range_height_pct": -0.1}, "min_range_height_pct"),
        ({"max_zero_volume_window_pct": "0.1"}, "max_zero_volume_window_pct"),
        ({"min_range_height_pct": None}, "min_range_height_pct"),
        ({"mid_zone_pct": float("nan")}, "mid_zone_pct"),
        ({"lower_zone_pct": True}, "lower_zone_pct"),
        ({"profile_name": ""}, "profile_name"),
    ],
)
def test_invalid_advertised_config_fails_closed(
    kwargs: dict[str, object],
    message: str,
) -> None:
    _available()
    with pytest.raises(ValueError, match=message):
        DetectionConfig(**kwargs)
