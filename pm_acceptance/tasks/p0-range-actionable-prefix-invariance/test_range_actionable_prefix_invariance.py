from __future__ import annotations

import ast
import hashlib
import importlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


TASK_ID = "p0-range-actionable-prefix-invariance"
SENTINEL = "range_actionable_prefix_invariance_contract_unavailable"
CONTRACT_VERSION = "range-actionable-prefix-invariance-v1"
MODULE_CONTRACT_NAME = "RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT"
TEST_CONTRACT_NAME = "RANGE_ACTIONABLE_PREFIX_INVARIANCE_TEST_CONTRACT"
ORDINARY_TEST_PATH = "tests/test_range_actionable_prefix_invariance.py"
ORDINARY_TEST_SHA256 = (
    "42bb644e18e1e82ce60e687a04952bbcb21596b8b4fb85fe0922868e2beed4e1"
)
REQUIRED_IMPLEMENTATION_PATHS = (
    "src/bybit_grid/research/range_actionable_events.py",
    ORDINARY_TEST_PATH,
)
RED_REQUIRED_PATHS = REQUIRED_IMPLEMENTATION_PATHS
MINUTE_MS = 60_000
BASE_MS = 1_800_000_000_000
PROFILE_RULES = {
    "actionable_density_v2": (15, 5, (15, 30)),
    "actionable_density_v3": (30, 10, (15, 30)),
    "strict_actionable_v2": (60, 20, (15, 30, 60)),
}
_implementation_module: Any | None = None


def _implementation() -> Any:
    global _implementation_module
    if _implementation_module is not None:
        return _implementation_module
    try:
        _implementation_module = importlib.import_module(
            "bybit_grid.research.range_actionable_events"
        )
    except Exception:
        raise RuntimeError(SENTINEL) from None
    return _implementation_module


def _root() -> Path:
    return Path(_implementation().__file__).resolve().parents[3]


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
    module = _implementation()
    if getattr(module, MODULE_CONTRACT_NAME, None) != CONTRACT_VERSION:
        raise RuntimeError(SENTINEL)
    if (
        _exact_assignment(Path(module.__file__).resolve(), MODULE_CONTRACT_NAME)
        != CONTRACT_VERSION
    ):
        raise RuntimeError(SENTINEL)
    if _ordinary_contract() != (CONTRACT_VERSION, ORDINARY_TEST_SHA256):
        raise RuntimeError(SENTINEL)


def _candidate(
    minute: int,
    *,
    profile: str = "actionable_density_v2",
    symbol: str = "XUSDT",
    lookback: int = 15,
    raw_id: str | None = None,
    quality: float = 10.0,
    crosses: int = 8,
    low: float = 99.0,
    high: float = 101.0,
    timestamp_ms: int | None = None,
    outside_minutes: int | float | None = None,
) -> dict[str, object]:
    timestamp = BASE_MS + minute * MINUTE_MS if timestamp_ms is None else timestamp_ms
    candidate_id = (
        raw_id if raw_id is not None else f"{symbol}-{profile}-{minute}-{lookback}"
    )
    return {
        "symbol": symbol,
        "profile_name": profile,
        "candidate_id": candidate_id,
        "raw_candidate_id": candidate_id,
        "signal_time_ms": timestamp,
        "lookback_minutes": lookback,
        "current_close": (low + high) / 2.0,
        "range_low": low,
        "range_high": high,
        "range_mid": (low + high) / 2.0,
        "range_height_pct": (high - low) / ((low + high) / 2.0),
        "range_height_atr_14": 10.0,
        "amplitude_score": 0.5,
        "range_quality_score": quality,
        "current_position_in_range": 0.5,
        "midline_crosses": crosses,
        "touches_lower_zone": 4,
        "touches_upper_zone": 4,
        "data_quality_ok": True,
        "zero_volume_candles_in_window": 0,
        "missing_candles_in_window": 0,
        "bad_ohlc_in_window": 0,
        "minutes_outside_midzone_before_reentry": outside_minutes,
    }


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def _qualifying_rows(
    profile: str,
    *,
    symbol: str = "XUSDT",
    low: float = 99.0,
    high: float = 101.0,
) -> list[dict[str, object]]:
    duration, count, lookbacks = PROFILE_RULES[profile]
    rows: list[dict[str, object]] = []
    for index in range(count):
        minute = round(index * (duration - 1) / (count - 1))
        rows.append(
            _candidate(
                minute,
                profile=profile,
                symbol=symbol,
                lookback=lookbacks[index % len(lookbacks)],
                raw_id=f"{symbol}-{profile}-{index:02d}",
                quality=10.0 + index,
                crosses=8 + index,
                low=low,
                high=high,
            )
        )
    return rows


def _build(
    rows_or_frame: list[dict[str, object]] | pl.DataFrame,
    *,
    event_cfg: Any | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    frame = (
        rows_or_frame
        if isinstance(rows_or_frame, pl.DataFrame)
        else _frame(rows_or_frame)
    )
    return _implementation().build_actionable_events(frame, event_cfg=event_cfg)


def _event_dicts(events: pl.DataFrame) -> list[dict[str, object]]:
    if events.is_empty():
        return []
    columns = [
        name
        for name in (
            "symbol",
            "profile_name",
            "decision_time_ms",
            "range_action_event_id",
        )
        if name in events.columns
    ]
    return events.sort(columns).to_dicts() if columns else events.to_dicts()


def _only_event(rows: list[dict[str, object]]) -> dict[str, object]:
    _regimes, events = _build(rows)
    records = _event_dicts(events)
    assert len(records) == 1
    return records[0]


def _expected_id(regime_id: str, decision_time_ms: int, raw_id: str) -> str:
    payload = f"{CONTRACT_VERSION}|{regime_id}|{int(decision_time_ms)}|{raw_id}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def test_contract_markers_and_exact_implementation_scope() -> None:
    _available()
    assert RED_REQUIRED_PATHS == REQUIRED_IMPLEMENTATION_PATHS
    assert all((_root() / path).is_file() for path in REQUIRED_IMPLEMENTATION_PATHS)
    assert getattr(_implementation(), MODULE_CONTRACT_NAME) == CONTRACT_VERSION
    assert _ordinary_contract() == (CONTRACT_VERSION, ORDINARY_TEST_SHA256)


def test_all_three_profiles_emit_at_the_earliest_qualifying_prefix() -> None:
    _available()
    for profile, (duration, count, lookbacks) in PROFILE_RULES.items():
        rows = _qualifying_rows(profile)
        for cutoff in sorted({int(row["signal_time_ms"]) for row in rows})[:-1]:
            prefix = [row for row in rows if int(row["signal_time_ms"]) <= cutoff]
            assert _build(prefix)[1].is_empty()
        event = _only_event(rows)
        assert event["decision_time_ms"] == BASE_MS + (duration - 1) * MINUTE_MS
        assert event["regime_duration_minutes"] == duration
        assert event["raw_candidates_in_regime"] == count
        assert event["lookbacks_observed"] == ",".join(map(str, lookbacks))


def test_duration_uses_inclusive_whole_minute_formula() -> None:
    _available()
    first = BASE_MS + 30_000
    rows = [
        _candidate(0, timestamp_ms=first, raw_id="duration-0", lookback=15),
        _candidate(
            0, timestamp_ms=first + 3 * MINUTE_MS, raw_id="duration-1", lookback=30
        ),
        _candidate(
            0, timestamp_ms=first + 7 * MINUTE_MS, raw_id="duration-2", lookback=15
        ),
        _candidate(
            0, timestamp_ms=first + 11 * MINUTE_MS, raw_id="duration-3", lookback=30
        ),
        _candidate(
            0,
            timestamp_ms=first + 14 * MINUTE_MS - 1,
            raw_id="duration-too-early",
            lookback=15,
        ),
    ]
    assert _build(rows)[1].is_empty()
    rows.append(
        _candidate(
            0,
            timestamp_ms=first + 14 * MINUTE_MS,
            raw_id="duration-decision",
            lookback=30,
        )
    )
    event = _only_event(rows)
    assert event["decision_time_ms"] == first + 14 * MINUTE_MS
    assert event["regime_duration_minutes"] == 15


def test_candidate_count_delays_decision_after_duration_is_met() -> None:
    _available()
    rows = [
        _candidate(minute, raw_id=f"count-{index}", lookback=(15, 30)[index % 2])
        for index, minute in enumerate((0, 5, 10, 14))
    ]
    assert _build(rows)[1].is_empty()
    rows.append(_candidate(15, raw_id="count-decision", lookback=15))
    event = _only_event(rows)
    assert event["decision_time_ms"] == BASE_MS + 15 * MINUTE_MS
    assert event["raw_candidates_in_regime"] == 5


def test_unique_lookback_count_delays_decision_after_other_thresholds() -> None:
    _available()
    rows = [
        _candidate(minute, raw_id=f"lookback-{index}", lookback=15)
        for index, minute in enumerate((0, 4, 8, 12, 14))
    ]
    assert _build(rows)[1].is_empty()
    rows.append(_candidate(15, raw_id="lookback-decision", lookback=30))
    event = _only_event(rows)
    assert event["decision_time_ms"] == BASE_MS + 15 * MINUTE_MS
    assert event["lookbacks_observed"] == "15,30"


def test_event_fields_and_regime_evidence_are_snapshotted_at_decision() -> None:
    _available()
    rows = _qualifying_rows("actionable_density_v2")
    decision = rows[-1]
    prefix_event = _only_event(rows)
    suffix = [
        _candidate(
            16,
            raw_id="future-high-score",
            lookback=60,
            quality=999.0,
            crosses=999,
            low=99.05,
            high=100.95,
        ),
        _candidate(
            18,
            raw_id="future-new-lookback",
            lookback=120,
            quality=1_000.0,
            crosses=1_000,
            low=99.05,
            high=100.95,
        ),
    ]
    full_event = _only_event(rows + suffix)
    assert full_event == prefix_event
    assert full_event["raw_candidate_id"] == decision["raw_candidate_id"]
    assert full_event["best_lookback_minutes"] == decision["lookback_minutes"]
    assert full_event["range_low"] == decision["range_low"]
    assert full_event["range_high"] == decision["range_high"]
    assert full_event["range_mid"] == decision["range_mid"]
    assert full_event["range_quality_score"] == decision["range_quality_score"]
    assert full_event["raw_candidates_in_regime"] == 5
    assert full_event["lookbacks_observed"] == "15,30"


def test_decision_and_signal_timestamps_are_identical_snapshots() -> None:
    _available()
    event = _only_event(_qualifying_rows("actionable_density_v3"))
    decision_ms = BASE_MS + 29 * MINUTE_MS
    expected_utc = datetime.fromtimestamp(
        decision_ms / 1000, tz=timezone.utc
    ).isoformat()
    assert event["decision_time_ms"] == decision_ms
    assert event["signal_time_ms"] == decision_ms
    assert event["decision_time_utc"] == expected_utc
    assert event["signal_time_utc"] == expected_utc


def test_every_timestamp_cutoff_is_suffix_prefix_invariant() -> None:
    _available()
    for profile in PROFILE_RULES:
        rows = _qualifying_rows(profile)
        decision_minute = PROFILE_RULES[profile][0] - 1
        rows.extend(
            [
                _candidate(
                    decision_minute + 2,
                    profile=profile,
                    raw_id=f"{profile}-suffix-a",
                    lookback=120,
                    quality=500.0,
                ),
                _candidate(
                    decision_minute + 4,
                    profile=profile,
                    raw_id=f"{profile}-suffix-b",
                    lookback=240,
                    quality=600.0,
                ),
            ]
        )
        full_events = _build(rows)[1]
        for cutoff in sorted({int(row["signal_time_ms"]) for row in rows}):
            prefix = [row for row in rows if int(row["signal_time_ms"]) <= cutoff]
            prefix_records = _event_dicts(_build(prefix)[1])
            known = full_events.filter(pl.col("decision_time_ms") <= cutoff)
            assert prefix_records == _event_dicts(known)


def test_action_event_ids_are_deterministic_and_contract_versioned() -> None:
    _available()
    module = _implementation()
    regime_id = "0123456789abcdef0123456789abcdef"
    decision_ms = BASE_MS + 14 * MINUTE_MS
    raw_id = "deterministic-raw-candidate"
    expected = _expected_id(regime_id, decision_ms, raw_id)
    assert module.stable_action_event_id(regime_id, decision_ms, raw_id) == expected
    assert module.stable_action_event_id(regime_id, decision_ms, raw_id) == expected
    assert re.fullmatch(r"[0-9a-f]{32}", expected)
    event = _only_event(_qualifying_rows("actionable_density_v2"))
    assert event["actionable_event_semantics_version"] == CONTRACT_VERSION
    assert event["range_action_event_id"] == _expected_id(
        str(event["range_regime_id"]),
        int(event["decision_time_ms"]),
        str(event["raw_candidate_id"]),
    )


def test_same_time_tie_break_is_total_and_input_order_independent() -> None:
    _available()
    rows = [
        _candidate(0, raw_id="tie-prefix-0", lookback=15),
        _candidate(5, raw_id="tie-prefix-1", lookback=30),
        _candidate(10, raw_id="tie-prefix-2", lookback=15),
        _candidate(14, raw_id="quality-low", quality=20.0, crosses=99, lookback=60),
        _candidate(14, raw_id="cross-low", quality=30.0, crosses=8, lookback=60),
        _candidate(14, raw_id="lookback-low", quality=30.0, crosses=9, lookback=30),
        _candidate(14, raw_id="tie-z", quality=30.0, crosses=9, lookback=60),
        _candidate(14, raw_id="tie-a", quality=30.0, crosses=9, lookback=60),
    ]
    forward = _only_event(rows)
    reverse = _only_event(list(reversed(rows)))
    rotated = _only_event(rows[3:] + rows[:3])
    assert forward == reverse == rotated
    assert forward["raw_candidate_id"] == "tie-a"
    assert forward["raw_candidates_in_regime"] == 8
    assert forward["decision_time_ms"] == BASE_MS + 14 * MINUTE_MS


def test_symbol_boundaries_never_pool_qualification_evidence() -> None:
    _available()
    minutes = (0, 5, 10, 14)
    rows = [
        _candidate(
            minute,
            symbol=symbol,
            raw_id=f"{symbol}-{index}",
            lookback=(15, 30)[index % 2],
        )
        for symbol in ("XUSDT", "YUSDT")
        for index, minute in enumerate(minutes)
    ]
    assert _build(rows)[1].is_empty()
    qualified = _qualifying_rows("actionable_density_v2", symbol="XUSDT")
    qualified += _qualifying_rows("actionable_density_v2", symbol="YUSDT")
    assert {row["symbol"] for row in _event_dicts(_build(qualified)[1])} == {
        "XUSDT",
        "YUSDT",
    }


def test_profile_boundaries_never_pool_qualification_evidence() -> None:
    _available()
    v2 = [
        _candidate(
            minute,
            profile="actionable_density_v2",
            raw_id=f"v2-{index}",
            lookback=(15, 30)[index % 2],
        )
        for index, minute in enumerate((0, 5, 10, 14))
    ]
    v3 = [
        _candidate(
            minute,
            profile="actionable_density_v3",
            raw_id=f"v3-{index}",
            lookback=(15, 30)[index % 2],
        )
        for index, minute in enumerate((0, 4, 8, 12, 16, 20, 24, 27, 29))
    ]
    assert _build(v2 + v3)[1].is_empty()


def test_cluster_boundaries_never_pool_qualification_evidence() -> None:
    _available()
    rows = [
        _candidate(
            minute,
            raw_id=f"cluster-a-{index}",
            lookback=(15, 30)[index % 2],
            low=99.0,
            high=101.0,
        )
        for index, minute in enumerate((0, 7, 14))
    ]
    rows.extend(
        _candidate(
            minute,
            raw_id=f"cluster-b-{index}",
            lookback=(15, 30)[index % 2],
            low=199.0,
            high=201.0,
        )
        for index, minute in enumerate((0, 14))
    )
    assert _build(rows)[1].is_empty()


def test_gap_boundaries_never_pool_qualification_evidence() -> None:
    _available()
    rows = [
        _candidate(minute, raw_id=f"gap-a-{index}", lookback=(15, 30)[index % 2])
        for index, minute in enumerate((0, 2, 4))
    ]
    rows.extend(
        _candidate(minute, raw_id=f"gap-b-{index}", lookback=(15, 30)[index % 2])
        for index, minute in enumerate((20, 21))
    )
    assert _build(rows)[1].is_empty()


def test_empty_and_missing_schema_inputs_fail_safely() -> None:
    _available()
    frames = [
        pl.DataFrame(),
        pl.DataFrame({"symbol": ["XUSDT"]}),
        pl.DataFrame(
            {
                "symbol": ["XUSDT"],
                "profile_name": ["actionable_density_v2"],
                "signal_time_ms": [BASE_MS],
            }
        ),
    ]
    for frame in frames:
        regimes, events = _build(frame)
        assert regimes.is_empty()
        assert events.is_empty()


def test_unknown_profiles_and_invalid_required_values_fail_safely() -> None:
    _available()
    unknown = [_candidate(0, profile="unknown_profile", raw_id="unknown")]
    assert _build(unknown)[1].is_empty()
    for field in (
        "symbol",
        "profile_name",
        "signal_time_ms",
        "lookback_minutes",
        "raw_candidate_id",
        "range_low",
        "range_high",
    ):
        rows = _qualifying_rows("actionable_density_v2")
        rows[-1][field] = None
        regimes, events = _build(rows)
        assert regimes.is_empty() or events.is_empty()
        assert events.is_empty()


def test_reentry_is_fail_closed_never_predecision_and_bounded() -> None:
    _available()
    module = _implementation()
    rows = _qualifying_rows("actionable_density_v2")
    decision_ms = BASE_MS + 14 * MINUTE_MS
    rows.extend(
        [
            _candidate(16, raw_id="reentry-missing", lookback=15),
            _candidate(
                18,
                raw_id="reentry-below",
                lookback=30,
                outside_minutes=29,
            ),
        ]
    )
    cfg = module.ActionableEventConfig(
        allow_reentry_events=True,
        min_minutes_outside_midzone_before_reentry=30,
        max_events_per_regime=2,
    )
    fail_closed = _event_dicts(_build(rows, event_cfg=cfg)[1])
    assert len(fail_closed) == 1
    assert fail_closed[0]["decision_time_ms"] == decision_ms
    eligible = rows + [
        _candidate(
            20,
            raw_id="reentry-eligible-a",
            lookback=15,
            outside_minutes=30,
        ),
        _candidate(
            22,
            raw_id="reentry-eligible-b",
            lookback=30,
            outside_minutes=31,
        ),
    ]
    events = _event_dicts(_build(eligible, event_cfg=cfg)[1])
    assert len(events) == 2
    assert all(int(event["decision_time_ms"]) >= decision_ms for event in events)
    assert [event["decision_time_ms"] for event in events] == sorted(
        event["decision_time_ms"] for event in events
    )


def test_multi_group_output_and_ids_are_deterministic_under_row_permutation() -> None:
    _available()
    rows = _qualifying_rows("actionable_density_v2", symbol="YUSDT")
    rows += _qualifying_rows("actionable_density_v3", symbol="XUSDT")
    forward = _event_dicts(_build(rows)[1])
    reverse = _event_dicts(_build(list(reversed(rows)))[1])
    interleaved = _event_dicts(_build(rows[::2] + rows[1::2])[1])
    assert forward == reverse == interleaved
    assert len(forward) == 2
    assert len({row["range_action_event_id"] for row in forward}) == 2
