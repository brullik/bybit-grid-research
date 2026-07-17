from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from bybit_grid.research.outcome_core import outcome_fast, outcome_numpy
from bybit_grid.research import outcome_summary


OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_TEST_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)
CONTRACT = "outcome-window-completeness-provenance-v1"
WINDOW_VERSION = "exact-minute-outcome-window-v1"
OUTCOME_VERSION = "v5_exact_outcome_window_provenance"
ACTIONABLE_VERSION = "range-actionable-prefix-invariance-v1"
SENTINEL = "outcome_window_completeness_provenance_contract_unavailable"
MINUTE_MS = 60_000
SIGNAL_MS = 120_000
ENTRY_MS = 180_000


def _load_audit_module():
    repo_root = Path(outcome_numpy.__file__).resolve().parents[4]
    path = repo_root / "scripts" / "audit_outcome_semantics.py"
    spec = importlib.util.spec_from_file_location(
        "audit_outcome_semantics_contract", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit_module()
CORES = (outcome_numpy, outcome_fast)
CLAIM_FIELDS = (
    "first_exit_side",
    "first_exit_ambiguous_bool",
    "first_exit_time_ms",
    "minutes_to_first_exit",
    "time_inside_range_minutes",
    "inside_range_candle_count",
    "inside_range_ratio",
    "max_high_above_range_pct",
    "max_low_below_range_pct",
    "max_close_distance_from_mid_pct",
    "first_sl_side",
    "first_sl_ambiguous_bool",
    "first_sl_time_ms",
    "minutes_to_first_sl",
    "sl_hit_bool",
    "future_close_level_cross_count",
    "future_intrabar_level_touch_count",
    "future_unique_grid_levels_touched_count",
    "future_internal_level_close_cross_count",
    "future_internal_level_intrabar_touch_count",
    "fill_activity_lower_bound_proxy",
    "fill_activity_upper_bound_proxy",
    "future_grid_level_cross_count",
    "future_midline_cross_count",
    "future_upper_zone_touch_count",
    "future_lower_zone_touch_count",
    "grid_crossings_per_hour",
    "mark_price_max_deviation_from_last_pct",
    "label_stayed_in_range_until_horizon",
    "label_sl_hit_before_horizon",
    "label_good_chop_proxy",
    "label_low_activity_proxy",
    "label_high_breakout_risk_proxy",
)
DIAGNOSTIC_FIELDS = (
    "future_expected_minutes_count",
    "future_observed_expected_minutes_count",
    "future_coverage_minutes",
    "future_missing_minutes_count",
    "future_off_grid_rows_count",
    "future_duplicate_timestamp_count",
    "future_invalid_timestamp_rows_count",
    "future_bad_ohlc_count",
)


def _available() -> None:
    try:
        outcome_semantics = importlib.import_module(
            "bybit_grid.research.outcome_semantics"
        )
    except Exception:
        pytest.fail(SENTINEL)
    markers = (
        getattr(
            outcome_numpy,
            "OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT",
            None,
        ),
        getattr(
            outcome_fast,
            "OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT",
            None,
        ),
        getattr(
            AUDIT,
            "OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT",
            None,
        ),
        getattr(
            outcome_summary,
            "OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT",
            None,
        ),
        getattr(
            outcome_semantics,
            "OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT",
            None,
        ),
    )
    if markers != (CONTRACT, CONTRACT, CONTRACT, CONTRACT, CONTRACT):
        pytest.fail(SENTINEL)


def _event(**updates) -> dict:
    event = {
        "range_action_event_id": "evt-1",
        "range_regime_id": "regime-1",
        "symbol": "BTCUSDT",
        "profile_name": "range-actionable-v1",
        "actionable_event_semantics_version": ACTIONABLE_VERSION,
        "decision_time_ms": SIGNAL_MS,
        "signal_time_ms": SIGNAL_MS,
        "range_low": 99.0,
        "range_high": 101.0,
        "range_mid": 100.0,
        "range_height_atr_14": 1.0,
    }
    event.update(updates)
    return event


def _klines(
    timestamps: list[int],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    closes: list[float] | None = None,
) -> pl.DataFrame:
    size = len(timestamps)
    return pl.DataFrame(
        {
            "open_time_ms": timestamps,
            "open": opens if opens is not None else [100.0] * size,
            "high": highs if highs is not None else [100.5] * size,
            "low": lows if lows is not None else [99.5] * size,
            "close": closes if closes is not None else [100.0] * size,
            "volume": [1.0] * size,
        }
    )


def _run(core, frame: pl.DataFrame, event: dict | None = None) -> dict:
    rows = core.compute_event_outcomes(
        _event() if event is None else event,
        frame,
        pl.DataFrame(),
        pl.DataFrame(),
        horizons=[3],
        grid_counts=[5],
        sl_atr_buffers=[0.5],
        profile_name="candidate-outcomes-v1",
        range_run_id="range-run-1",
        outcome_run_id="outcome-run-1",
    )
    assert len(rows) == 1
    return rows[0]


def _complete_frame() -> pl.DataFrame:
    return _klines([ENTRY_MS, ENTRY_MS + MINUTE_MS, ENTRY_MS + 2 * MINUTE_MS])


def _assert_ineligible(row: dict, reason: str) -> None:
    assert row["future_data_complete_bool"] is False
    assert row["future_outcome_eligible_bool"] is False
    assert row["future_outcome_ineligible_reason"] == reason
    assert all(row[field] is None for field in CLAIM_FIELDS)


def test_contract_markers_versions_and_outcome_id_material() -> None:
    _available()
    assert outcome_numpy.OUTCOME_WINDOW_SEMANTICS_VERSION == WINDOW_VERSION
    assert outcome_fast.OUTCOME_WINDOW_SEMANTICS_VERSION == WINDOW_VERSION
    assert AUDIT.OUTCOME_WINDOW_SEMANTICS_VERSION == WINDOW_VERSION
    assert outcome_numpy.OUTCOME_SEMANTICS_VERSION == OUTCOME_VERSION
    assert AUDIT.OUTCOME_SEMANTICS_VERSION == OUTCOME_VERSION
    current = outcome_numpy.deterministic_outcome_id("e", 3, 5, 0.5)
    legacy = outcome_numpy.deterministic_outcome_id(
        "e", 3, 5, 0.5, window_semantics_version="row-count-legacy"
    )
    assert current != legacy


@pytest.mark.parametrize("core", CORES)
def test_exact_grid_persists_causal_window_and_is_eligible(core) -> None:
    _available()
    row = _run(core, _complete_frame())
    assert row["decision_time_ms"] == SIGNAL_MS
    assert row["signal_time_ms"] == SIGNAL_MS
    assert row["actionable_event_semantics_version"] == ACTIONABLE_VERSION
    assert row["decision_time_source"] == "event_decision_time"
    assert row["causal_provenance_complete_bool"] is True
    assert row["entry_time_ms"] == ENTRY_MS
    assert row["outcome_end_exclusive_ms"] == ENTRY_MS + 3 * MINUTE_MS
    assert row["outcome_window_semantics_version"] == WINDOW_VERSION
    assert row["future_data_complete_bool"] is True
    assert row["future_outcome_eligible_bool"] is True
    assert row["future_outcome_ineligible_reason"] is None
    assert [row[field] for field in DIAGNOSTIC_FIELDS] == [3, 3, 3, 0, 0, 0, 0, 0]


@pytest.mark.parametrize("core", CORES)
def test_entry_plus_30_seconds_plus_2_minutes_is_not_complete(core) -> None:
    _available()
    row = _run(core, _klines([ENTRY_MS, ENTRY_MS + 30_000, ENTRY_MS + 2 * MINUTE_MS]))
    assert row["future_rows_available"] == 3
    assert row["future_observed_expected_minutes_count"] == 2
    assert row["future_missing_minutes_count"] == 1
    assert row["future_off_grid_rows_count"] == 1
    _assert_ineligible(row, "missing_minutes|off_grid_rows")


@pytest.mark.parametrize("core", CORES)
def test_extra_off_grid_row_invalidates_otherwise_exact_grid(core) -> None:
    _available()
    times = [
        ENTRY_MS,
        ENTRY_MS + 30_000,
        ENTRY_MS + MINUTE_MS,
        ENTRY_MS + 2 * MINUTE_MS,
    ]
    row = _run(core, _klines(times))
    assert row["future_observed_expected_minutes_count"] == 3
    assert row["future_missing_minutes_count"] == 0
    assert row["future_off_grid_rows_count"] == 1
    _assert_ineligible(row, "off_grid_rows")


@pytest.mark.parametrize("core", CORES)
@pytest.mark.parametrize("missing_index", [0, 1, 2])
def test_missing_expected_minute_is_explicit_and_ineligible(
    core, missing_index
) -> None:
    _available()
    times = [ENTRY_MS, ENTRY_MS + MINUTE_MS, ENTRY_MS + 2 * MINUTE_MS]
    del times[missing_index]
    row = _run(core, _klines(times))
    assert row["future_rows_available"] == 2
    assert row["future_missing_minutes_count"] == 1
    _assert_ineligible(row, "missing_minutes")


@pytest.mark.parametrize("core", CORES)
def test_duplicate_expected_timestamp_is_explicit_and_ineligible(core) -> None:
    _available()
    row = _run(
        core,
        _klines(
            [
                ENTRY_MS,
                ENTRY_MS + MINUTE_MS,
                ENTRY_MS + MINUTE_MS,
                ENTRY_MS + 2 * MINUTE_MS,
            ]
        ),
    )
    assert row["future_rows_available"] == 4
    assert row["future_observed_expected_minutes_count"] == 3
    assert row["future_duplicate_timestamp_count"] == 1
    _assert_ineligible(row, "duplicate_timestamps")


def test_duplicate_zero_volume_diagnostics_match_reference_and_fast() -> None:
    _available()
    frame = _klines(
        [
            ENTRY_MS,
            ENTRY_MS + MINUTE_MS,
            ENTRY_MS + MINUTE_MS,
            ENTRY_MS + 2 * MINUTE_MS,
        ]
    ).with_columns(pl.Series("volume", [1.0, 1.0, 0.0, 1.0]))
    reference = _run(outcome_numpy, frame)
    fast = _run(outcome_fast, frame)
    assert reference["future_rows_available"] == fast["future_rows_available"] == 4
    assert reference["future_duplicate_timestamp_count"] == 1
    assert fast["future_duplicate_timestamp_count"] == 1
    assert (
        reference["future_zero_volume_count"] == fast["future_zero_volume_count"] == 1
    )


@pytest.mark.parametrize("core", CORES)
def test_fractional_timestamp_dtype_cannot_be_truncated_into_exact_grid(core) -> None:
    _available()
    row = _run(
        core,
        _klines(
            [
                ENTRY_MS + 0.5,
                ENTRY_MS + MINUTE_MS,
                ENTRY_MS + 2 * MINUTE_MS,
            ]
        ),
    )
    assert row["future_rows_available"] == 3
    assert row["future_observed_expected_minutes_count"] == 0
    assert row["future_missing_minutes_count"] == 3
    assert row["future_invalid_timestamp_rows_count"] == 3
    _assert_ineligible(row, "missing_minutes|invalid_timestamps")


@pytest.mark.parametrize("core", CORES)
def test_nullable_kline_timestamp_is_rejected_consistently(core) -> None:
    _available()
    frame = _klines([ENTRY_MS, ENTRY_MS + MINUTE_MS, ENTRY_MS + 2 * MINUTE_MS, None])
    with pytest.raises(ValueError, match="timestamps must be non-null"):
        _run(core, frame)


@pytest.mark.parametrize("core", CORES)
def test_missing_ohlc_schema_is_rejected_consistently(core) -> None:
    _available()
    for column in ("open", "high", "low", "close"):
        with pytest.raises(ValueError, match="timestamp/OHLC columns are missing"):
            _run(core, _complete_frame().drop(column))


@pytest.mark.parametrize("core", CORES)
def test_completely_empty_frame_is_an_explicit_missing_window(core) -> None:
    _available()
    row = _run(core, pl.DataFrame())
    assert row["future_rows_available"] == 0
    assert row["future_missing_minutes_count"] == 3
    _assert_ineligible(row, "missing_minutes")


@pytest.mark.parametrize("core", CORES)
def test_exclusive_end_row_is_not_counted(core) -> None:
    _available()
    frame = _klines(
        [
            ENTRY_MS,
            ENTRY_MS + MINUTE_MS,
            ENTRY_MS + 2 * MINUTE_MS,
            ENTRY_MS + 3 * MINUTE_MS,
        ]
    )
    row = _run(core, frame)
    assert row["future_rows_available"] == 3
    assert row["future_data_complete_bool"] is True


@pytest.mark.parametrize("core", CORES)
def test_zero_volume_is_diagnostic_but_does_not_forge_incompleteness(core) -> None:
    _available()
    frame = _complete_frame().with_columns(pl.Series("volume", [1.0, 0.0, 1.0]))
    row = _run(core, frame)
    assert row["future_zero_volume_count"] == 1
    assert row["future_data_complete_bool"] is True
    assert row["future_outcome_eligible_bool"] is True


@pytest.mark.parametrize("core", CORES)
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("open", np.nan),
        ("high", np.inf),
        ("low", 0.0),
        ("close", -1.0),
        ("high", 99.0),
        ("low", 101.0),
    ],
)
def test_nonfinite_nonpositive_or_invalid_ohlc_envelope_is_ineligible(
    core, column, value
) -> None:
    _available()
    values = {
        "opens": [100.0, 100.0, 100.0],
        "highs": [100.5, 100.5, 100.5],
        "lows": [99.5, 99.5, 99.5],
        "closes": [100.0, 100.0, 100.0],
    }
    values[
        {"open": "opens", "high": "highs", "low": "lows", "close": "closes"}[column]
    ][1] = value
    row = _run(
        core,
        _klines([ENTRY_MS, ENTRY_MS + MINUTE_MS, ENTRY_MS + 2 * MINUTE_MS], **values),
    )
    assert row["future_bad_ohlc_count"] == 1
    _assert_ineligible(row, "invalid_ohlc")


@pytest.mark.parametrize("core", CORES)
def test_complete_window_retains_boolean_and_first_event_claims(core) -> None:
    _available()
    frame = _klines(
        [ENTRY_MS, ENTRY_MS + MINUTE_MS, ENTRY_MS + 2 * MINUTE_MS],
        highs=[100.5, 103.0, 100.5],
        lows=[99.5, 97.0, 99.5],
    )
    row = _run(core, frame)
    assert row["first_exit_side"] == "ambiguous_both"
    assert row["first_exit_ambiguous_bool"] is True
    assert row["first_exit_time_ms"] == ENTRY_MS + MINUTE_MS
    assert row["first_sl_side"] == "ambiguous_both"
    assert row["first_sl_ambiguous_bool"] is True
    assert row["sl_hit_bool"] is True
    assert isinstance(row["label_stayed_in_range_until_horizon"], bool)


@pytest.mark.parametrize("core", CORES)
def test_decision_before_signal_is_rejected(core) -> None:
    _available()
    with pytest.raises(ValueError, match="decision_time_ms"):
        _run(core, _complete_frame(), _event(decision_time_ms=SIGNAL_MS - 1))


@pytest.mark.parametrize("core", CORES)
def test_entry_is_strictly_next_minute_after_canonical_decision(core) -> None:
    _available()
    decision = SIGNAL_MS + MINUTE_MS - 1
    entry = SIGNAL_MS + MINUTE_MS
    frame = _klines([entry, entry + MINUTE_MS, entry + 2 * MINUTE_MS])
    row = _run(
        core,
        frame,
        _event(signal_time_ms=decision, decision_time_ms=decision),
    )
    assert row["signal_time_ms"] == decision
    assert row["decision_time_ms"] == decision
    assert row["entry_time_ms"] == entry
    assert row["future_data_complete_bool"] is True


@pytest.mark.parametrize("core", CORES)
def test_explicit_decision_signal_mismatch_is_rejected(core) -> None:
    _available()
    with pytest.raises(ValueError, match="must equal"):
        _run(core, _complete_frame(), _event(decision_time_ms=SIGNAL_MS + 1))


@pytest.mark.parametrize("core", CORES)
def test_negative_authoritative_decision_is_rejected_by_producer(core) -> None:
    _available()
    with pytest.raises(ValueError, match="must be nonnegative"):
        _run(
            core,
            _klines([0, MINUTE_MS, 2 * MINUTE_MS]),
            _event(signal_time_ms=-MINUTE_MS, decision_time_ms=-MINUTE_MS),
        )


@pytest.mark.parametrize("core", CORES)
@pytest.mark.parametrize(
    ("field", "value"),
    [("signal_time_ms", 120_000.0), ("decision_time_ms", "120000")],
)
def test_noninteger_causal_timestamps_are_rejected(core, field, value) -> None:
    _available()
    with pytest.raises(ValueError, match="exact integers"):
        _run(core, _complete_frame(), _event(**{field: value}))


@pytest.mark.parametrize("core", CORES)
def test_versioned_event_requires_explicit_decision_and_supported_version(core) -> None:
    _available()
    missing = _event()
    missing.pop("decision_time_ms")
    with pytest.raises(ValueError, match="requires explicit decision_time_ms"):
        _run(core, _complete_frame(), missing)
    with pytest.raises(ValueError, match="unsupported"):
        _run(
            core,
            _complete_frame(),
            _event(actionable_event_semantics_version="unknown-actionable-version"),
        )


@pytest.mark.parametrize("core", CORES)
def test_event_range_profile_is_preserved_separately_from_outcome_profile(core) -> None:
    _available()
    row = _run(core, _complete_frame())
    assert row["profile_name"] == "range-actionable-v1"
    assert row["range_profile_name"] == "range-actionable-v1"
    assert row["outcome_profile_name"] == "candidate-outcomes-v1"


@pytest.mark.parametrize("core", CORES)
def test_versioned_event_missing_range_profile_is_rejected(core) -> None:
    _available()
    event = _event()
    event.pop("profile_name")
    with pytest.raises(ValueError, match="requires profile_name"):
        _run(core, _complete_frame(), event)


@pytest.mark.parametrize("core", CORES)
def test_unversioned_legacy_signal_fallback_is_non_authoritative(core) -> None:
    _available()
    event = _event()
    event.pop("actionable_event_semantics_version")
    event.pop("decision_time_ms")
    row = _run(core, _complete_frame(), event)
    assert row["outcome_semantics_version"] == "v4_native_grid_geometry"
    assert row["decision_time_ms"] == SIGNAL_MS
    assert row["decision_time_source"] == "legacy_signal_fallback"
    assert row["causal_provenance_complete_bool"] is False
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "authoritative decision-time provenance invalid" in result["failures"]


@pytest.mark.parametrize("core", CORES)
@pytest.mark.parametrize("profile", ["", "   ", 5])
def test_invalid_event_range_profile_is_rejected(core, profile) -> None:
    _available()
    with pytest.raises(ValueError, match="profile_name"):
        _run(core, _complete_frame(), _event(profile_name=profile))


def test_reference_and_fast_window_and_provenance_fields_match() -> None:
    _available()
    frame = _klines([ENTRY_MS, ENTRY_MS + 30_000, ENTRY_MS + 2 * MINUTE_MS])
    reference = _run(outcome_numpy, frame)
    fast = _run(outcome_fast, frame)
    fields = (
        "outcome_id",
        "decision_time_ms",
        "signal_time_ms",
        "entry_time_ms",
        "outcome_end_exclusive_ms",
        "outcome_window_semantics_version",
        "profile_name",
        "range_profile_name",
        "outcome_profile_name",
        *DIAGNOSTIC_FIELDS,
        "future_data_complete_bool",
        "future_outcome_eligible_bool",
        "future_outcome_ineligible_reason",
        "future_rows_available",
        "future_zero_volume_count",
        *CLAIM_FIELDS,
    )
    assert {field: reference[field] for field in fields} == {
        field: fast[field] for field in fields
    }


def test_semantic_audit_accepts_generated_complete_and_incomplete_rows() -> None:
    _available()
    rows = [
        _run(outcome_numpy, _complete_frame()),
        _run(
            outcome_numpy,
            _klines([ENTRY_MS, ENTRY_MS + 30_000, ENTRY_MS + 2 * MINUTE_MS]),
            _event(range_action_event_id="evt-2"),
        ),
    ]
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame(rows))
    assert result == {"outcome_window_semantic_audit_ok": True, "failures": []}


def test_semantic_audit_rejects_forged_row_count_completeness() -> None:
    _available()
    row = _run(
        outcome_numpy,
        _klines([ENTRY_MS, ENTRY_MS + 30_000, ENTRY_MS + 2 * MINUTE_MS]),
    )
    row["future_data_complete_bool"] = True
    row["future_outcome_eligible_bool"] = True
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert (
        "future_data_complete_bool inconsistent with exact grid" in result["failures"]
    )
    assert (
        "future outcome eligibility inconsistent with exact grid" in result["failures"]
    )


def test_semantic_audit_rejects_legacy_or_missing_window_version() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["outcome_window_semantics_version"] = "row-count-legacy"
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "outcome_window_semantics_version invalid" in result["failures"]
    missing = pl.DataFrame([row]).drop("outcome_window_semantics_version")
    result = AUDIT.validate_outcome_window_semantics(missing)
    assert result["outcome_window_semantic_audit_ok"] is False
    assert result["failures"][0].startswith("missing outcome-window columns:")


def test_semantic_audit_rejects_tampered_exclusive_end() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["outcome_end_exclusive_ms"] += MINUTE_MS
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert (
        "outcome entry/end does not match decision-derived exact horizon"
        in result["failures"]
    )


def test_semantic_audit_rejects_claims_retained_on_incomplete_window() -> None:
    _available()
    row = _run(outcome_numpy, _klines([ENTRY_MS, ENTRY_MS + 2 * MINUTE_MS]))
    row["label_stayed_in_range_until_horizon"] = False
    row["first_exit_side"] = "none"
    row["label_unknown_future_claim"] = False
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "ineligible horizon retains future-dependent claim" in result["failures"]


def test_semantic_audit_rejects_impossible_diagnostic_conservation() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["future_rows_available"] = 2
    row["future_off_grid_rows_count"] = 1
    row["future_data_complete_bool"] = False
    row["future_outcome_eligible_bool"] = False
    row["future_outcome_ineligible_reason"] = "off_grid_rows"
    for field in CLAIM_FIELDS:
        row[field] = None
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert (
        "outcome window grid diagnostics do not conserve horizon" in result["failures"]
    )


@pytest.mark.parametrize(
    "updates",
    [
        {
            "future_rows_available": 4,
            "future_data_complete_bool": False,
            "future_outcome_eligible_bool": False,
            "future_outcome_ineligible_reason": None,
        },
        {
            "future_invalid_timestamp_rows_count": 1,
            "future_data_complete_bool": False,
            "future_outcome_eligible_bool": False,
            "future_outcome_ineligible_reason": "invalid_timestamps",
        },
    ],
)
def test_semantic_audit_rejects_unpartitioned_or_overlapping_row_diagnostics(
    updates,
) -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row.update(updates)
    for field in CLAIM_FIELDS:
        row[field] = None
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert (
        "outcome window grid diagnostics do not conserve horizon" in result["failures"]
    )


def test_semantic_audit_rejects_null_claim_on_eligible_window() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["future_close_level_cross_count"] = None
    row["label_good_chop_proxy"] = None
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "eligible horizon has null future-dependent claim" in result["failures"]
    assert "eligible horizon labels must be bool" in result["failures"]


def test_semantic_audit_rejects_inconsistent_first_event_time() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["first_exit_side"] = "up"
    row["first_exit_time_ms"] = None
    row["minutes_to_first_exit"] = None
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "first exit time claim inconsistent" in result["failures"]


def test_semantic_audit_rejects_inconsistent_inside_and_activity_claims() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["inside_range_candle_count"] = 0
    row["time_inside_range_minutes"] = 2
    row["inside_range_ratio"] = 0.8
    row["label_good_chop_proxy"] = False
    row["label_low_activity_proxy"] = True
    row["label_high_breakout_risk_proxy"] = False
    row["future_grid_level_cross_count"] = row["future_close_level_cross_count"] + 1
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "inside-range count/minutes/ratio inconsistent" in result["failures"]
    assert "grid activity aliases/bounds inconsistent" in result["failures"]


def test_semantic_audit_rejects_fractional_counts_and_forged_activity_rate() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["future_close_level_cross_count"] = 0.5
    row["future_grid_level_cross_count"] = 0.5
    row["fill_activity_lower_bound_proxy"] = 0.5
    row["grid_crossings_per_hour"] = 999.0
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "eligible horizon count claims must be exact integers" in result["failures"]
    assert "grid crossings per hour inconsistent" in result["failures"]


def test_event_horizon_causal_window_fields_are_invariant_across_probes(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    first = _run(outcome_numpy, _complete_frame())
    second = dict(first)
    second["grid_count"] = 6
    second["grid_cell_number"] = 6
    second["grid_price_level_count"] = 7
    second["grid_interval_count"] = 6
    second["outcome_id"] = outcome_numpy.deterministic_outcome_id("evt-1", 3, 6, 0.5)
    for field in (
        "decision_time_ms",
        "signal_time_ms",
        "entry_time_ms",
        "outcome_end_exclusive_ms",
    ):
        second[field] += MINUTE_MS
    frame = pl.DataFrame([first, second])
    result = AUDIT.validate_outcome_window_semantics(frame)
    assert result["outcome_window_semantic_audit_ok"] is False
    assert (
        "event-horizon causal/window provenance is not invariant" in result["failures"]
    )
    monkeypatch.setattr(outcome_summary, "read_outcomes", lambda _root: frame)
    with pytest.raises(ValueError, match="causal/window provenance is not invariant"):
        outcome_summary.build_summaries(tmp_path)


def test_semantic_audit_rejects_mixed_v4_v5_and_tampered_id() -> None:
    _available()
    v5 = _run(outcome_numpy, _complete_frame())
    v4 = dict(v5)
    v4["range_action_event_id"] = "legacy-event"
    v4["outcome_semantics_version"] = "v4_native_grid_geometry"
    v4["outcome_id"] = outcome_numpy.deterministic_outcome_id(
        "legacy-event",
        3,
        5,
        0.5,
        semantics_version="v4_native_grid_geometry",
    )
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([v5, v4]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "outcome_semantics_version is not uniform v5" in result["failures"]
    assert "outcome_id does not match v5 semantic material" in result["failures"]


def test_semantic_audit_requires_explicit_range_profile_provenance() -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["range_profile_name"] = None
    result = AUDIT.validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "range profile provenance overwritten" in result["failures"]


def test_summary_claims_use_only_eligible_rows(monkeypatch, tmp_path: Path) -> None:
    _available()
    complete = _run(outcome_numpy, _complete_frame())
    incomplete = _run(
        outcome_numpy,
        _klines([ENTRY_MS, ENTRY_MS + 2 * MINUTE_MS]),
        _event(range_action_event_id="evt-incomplete"),
    )
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([complete, incomplete]),
    )
    _, _, perf = outcome_summary.build_summaries(tmp_path)
    assert perf["outcome_rows_total"] == 2
    assert perf["future_outcome_eligible_rows"] == 1
    assert perf["future_outcome_ineligible_rows"] == 1
    assert perf["future_outcome_eligible_rate"] == 0.5
    assert perf["future_outcome_eligible_unique_event_horizon_rows"] == 1
    exit_distribution = perf["first_exit_side_distribution"]
    assert len(exit_distribution) == 1
    assert exit_distribution[0]["first_exit_side"] == "none"
    assert exit_distribution[0].get("count", exit_distribution[0].get("len")) == 1
    assert len(perf["sl_probe_summary"]) == 1
    assert len(perf["grid_activity_summary"]) == 1


def test_summary_fails_closed_on_legacy_or_mixed_semantics(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["outcome_semantics_version"] = "v4_native_grid_geometry"
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([row]),
    )
    with pytest.raises(ValueError, match="uniform v5"):
        outcome_summary.build_summaries(tmp_path)


def test_summary_fails_closed_on_null_authoritative_provenance(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["actionable_event_semantics_version"] = None
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([row]),
    )
    with pytest.raises(ValueError, match="authoritative event/range provenance"):
        outcome_summary.build_summaries(tmp_path)


def test_summary_rejects_order_dependent_event_horizon_eligibility(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    eligible = _run(outcome_numpy, _complete_frame())
    ineligible = _run(
        outcome_numpy,
        _klines([ENTRY_MS, ENTRY_MS + 2 * MINUTE_MS]),
    )
    ineligible["grid_count"] = 10
    ineligible["grid_cell_number"] = 10
    ineligible["grid_price_level_count"] = 11
    ineligible["grid_interval_count"] = 10
    ineligible["outcome_id"] = outcome_numpy.deterministic_outcome_id(
        "evt-1", 3, 10, 0.5
    )
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([eligible, ineligible]),
    )
    with pytest.raises(ValueError, match="causal/window provenance is not invariant"):
        outcome_summary.build_summaries(tmp_path)


def test_summary_rejects_impossible_diagnostics_before_reporting(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["future_rows_available"] = 2
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([row]),
    )
    with pytest.raises(ValueError, match="grid diagnostics do not conserve horizon"):
        outcome_summary.build_summaries(tmp_path)


def test_summary_requires_exact_boolean_causal_provenance(
    monkeypatch, tmp_path: Path
) -> None:
    _available()
    row = _run(outcome_numpy, _complete_frame())
    row["causal_provenance_complete_bool"] = 1
    monkeypatch.setattr(
        outcome_summary,
        "read_outcomes",
        lambda _root: pl.DataFrame([row]),
    )
    with pytest.raises(ValueError, match="decision-time provenance invalid"):
        outcome_summary.build_summaries(tmp_path)


@pytest.mark.parametrize("core", CORES)
def test_invalid_parameter_domains_fail_before_outcome_computation(core) -> None:
    _available()
    base = {
        "horizons": [3],
        "grid_counts": [5],
        "sl_atr_buffers": [0.5],
        "profile_name": "candidate-outcomes-v1",
    }
    invalid = (
        {"horizons": []},
        {"horizons": [0]},
        {"horizons": [True]},
        {"horizons": [3.0]},
        {"horizons": [3, 3]},
        {"grid_counts": []},
        {"grid_counts": [1]},
        {"grid_counts": [True]},
        {"grid_counts": [5.0]},
        {"grid_counts": [5, 5]},
        {"sl_atr_buffers": []},
        {"sl_atr_buffers": [float("nan")]},
        {"sl_atr_buffers": [float("inf")]},
        {"sl_atr_buffers": [True]},
        {"sl_atr_buffers": [0.5, 0.5]},
        {"profile_name": ""},
    )
    for update in invalid:
        arguments = base | update
        with pytest.raises(ValueError):
            core.compute_event_outcomes(
                _event(),
                _complete_frame(),
                pl.DataFrame(),
                pl.DataFrame(),
                **arguments,
            )


@pytest.mark.parametrize("core", CORES)
def test_invalid_event_identity_cannot_enter_id_material(core) -> None:
    _available()
    for update in (
        {"range_action_event_id": ""},
        {"range_action_event_id": None},
        {"symbol": ""},
        {"symbol": None},
    ):
        with pytest.raises(ValueError):
            _run(core, _complete_frame(), _event(**update))


def test_diagnostics_are_exact_integers_and_reason_order_is_canonical() -> None:
    _available()
    frame = _klines(
        [ENTRY_MS, ENTRY_MS + 30_000, ENTRY_MS + 2 * MINUTE_MS],
        highs=[100.5, np.inf, 100.5],
    )
    row = _run(outcome_numpy, frame)
    assert all(type(row[field]) is int for field in DIAGNOSTIC_FIELDS)
    assert row["future_outcome_ineligible_reason"] == (
        "missing_minutes|off_grid_rows|invalid_ohlc"
    )
