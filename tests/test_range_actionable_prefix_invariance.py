from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import polars as pl
import pytest

from bybit_grid.research.range_actionable_events import (
    RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT,
    ActionableEventConfig,
    build_actionable_events,
    stable_action_event_id,
)


RANGE_ACTIONABLE_PREFIX_INVARIANCE_TEST_CONTRACT = (
    "range-actionable-prefix-invariance-v1"
)
MINUTE_MS = 60_000
BASE_MS = 1_800_000_000_000
PROFILE_RULES = {
    "actionable_density_v2": (15, 5, (15, 30)),
    "actionable_density_v3": (30, 10, (15, 30)),
    "strict_actionable_v2": (60, 20, (15, 30, 60)),
}


def _row(
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
    outside: int | None = None,
) -> dict[str, object]:
    candidate_id = raw_id or f"{symbol}-{profile}-{minute}-{lookback}"
    return {
        "symbol": symbol,
        "profile_name": profile,
        "candidate_id": candidate_id,
        "raw_candidate_id": candidate_id,
        "signal_time_ms": BASE_MS + minute * MINUTE_MS,
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
        "minutes_outside_midzone_before_reentry": outside,
    }


def _qualifying(profile: str, *, symbol: str = "XUSDT") -> list[dict[str, object]]:
    duration, count, lookbacks = PROFILE_RULES[profile]
    return [
        _row(
            round(index * (duration - 1) / (count - 1)),
            profile=profile,
            symbol=symbol,
            lookback=lookbacks[index % len(lookbacks)],
            raw_id=f"{symbol}-{profile}-{index:02d}",
            quality=10.0 + index,
            crosses=8 + index,
        )
        for index in range(count)
    ]


def _events(
    rows: list[dict[str, object]] | pl.DataFrame,
    *,
    cfg: ActionableEventConfig | None = None,
) -> list[dict[str, object]]:
    frame = rows if isinstance(rows, pl.DataFrame) else pl.DataFrame(rows)
    _regimes, events = build_actionable_events(frame, event_cfg=cfg)
    if events.is_empty():
        return []
    return events.sort(
        ["symbol", "profile_name", "decision_time_ms", "range_action_event_id"]
    ).to_dicts()


@pytest.mark.parametrize("profile", tuple(PROFILE_RULES))
def test_primary_event_appears_only_at_earliest_qualifying_prefix(
    profile: str,
) -> None:
    duration, count, lookbacks = PROFILE_RULES[profile]
    rows = _qualifying(profile)
    assert _events(rows[:-1]) == []
    event = _events(rows)
    assert len(event) == 1
    assert event[0]["decision_time_ms"] == BASE_MS + (duration - 1) * MINUTE_MS
    assert event[0]["signal_time_ms"] == event[0]["decision_time_ms"]
    assert event[0]["regime_duration_minutes"] == duration
    assert event[0]["raw_candidates_in_regime"] == count
    assert event[0]["lookbacks_observed"] == ",".join(map(str, lookbacks))


def test_suffix_cannot_rewrite_decision_snapshot() -> None:
    rows = _qualifying("actionable_density_v2")
    prefix = _events(rows)
    rows.extend(
        [
            _row(16, raw_id="suffix-score", lookback=60, quality=999.0),
            _row(18, raw_id="suffix-lookback", lookback=120, quality=1_000.0),
        ]
    )
    assert _events(rows) == prefix
    assert prefix[0]["raw_candidates_in_regime"] == 5
    assert prefix[0]["lookbacks_observed"] == "15,30"


def test_same_timestamp_tie_break_and_id_are_input_order_independent() -> None:
    rows = [
        _row(0, raw_id="prefix-0", lookback=15),
        _row(5, raw_id="prefix-1", lookback=30),
        _row(10, raw_id="prefix-2", lookback=15),
        _row(14, raw_id="quality-low", quality=20.0, crosses=99, lookback=60),
        _row(14, raw_id="cross-low", quality=30.0, crosses=8, lookback=60),
        _row(14, raw_id="lookback-low", quality=30.0, crosses=9, lookback=30),
        _row(14, raw_id="tie-z", quality=30.0, crosses=9, lookback=60),
        _row(14, raw_id="tie-a", quality=30.0, crosses=9, lookback=60),
    ]
    forward = _events(rows)
    assert forward == _events(list(reversed(rows)))
    assert forward[0]["raw_candidate_id"] == "tie-a"
    event = forward[0]
    expected = hashlib.sha256(
        (
            f"{RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT}|"
            f"{event['range_regime_id']}|{event['decision_time_ms']}|tie-a"
        ).encode()
    ).hexdigest()[:32]
    assert (
        stable_action_event_id(
            str(event["range_regime_id"]), int(event["decision_time_ms"]), "tie-a"
        )
        == expected
    )
    assert event["range_action_event_id"] == expected
    assert (
        event["actionable_event_semantics_version"]
        == RANGE_ACTIONABLE_PREFIX_INVARIANCE_TEST_CONTRACT
    )


def test_conflicting_duplicate_identity_poisons_the_atomic_batch() -> None:
    rows = [
        _row(0, raw_id="prefix-0", lookback=15),
        _row(5, raw_id="prefix-1", lookback=30),
        _row(10, raw_id="prefix-2", lookback=15),
        _row(12, raw_id="prefix-3", lookback=30),
        _row(14, raw_id="duplicate", lookback=15, low=99.0, high=101.0),
        _row(14, raw_id="duplicate", lookback=15, low=99.01, high=101.0),
    ]
    assert _events(rows) == []
    assert _events(list(reversed(rows))) == []


def test_invalid_atomic_batch_cannot_qualify_but_later_invalid_suffix_is_local() -> (
    None
):
    decision_rows = [
        _row(0, raw_id="prefix", lookback=15),
        _row(14, raw_id="decision-1", lookback=30),
        _row(14, raw_id="decision-2", lookback=15),
        _row(14, raw_id="decision-3", lookback=30),
        _row(14, raw_id="decision-4", lookback=15),
        _row(14, raw_id="invalid", lookback=30),
    ]
    decision_rows[-1]["range_low"] = None
    assert _events(decision_rows) == []

    qualified = _qualifying("actionable_density_v2")
    expected = _events(qualified)
    invalid_suffix = _row(16, raw_id="invalid-suffix", lookback=15)
    invalid_suffix["range_high"] = None
    assert _events(qualified + [invalid_suffix]) == expected


def test_every_cutoff_matches_the_known_full_result() -> None:
    rows = _qualifying("actionable_density_v3")
    rows.extend(
        [
            _row(
                31,
                profile="actionable_density_v3",
                raw_id="suffix-a",
                lookback=60,
            ),
            _row(
                33,
                profile="actionable_density_v3",
                raw_id="suffix-b",
                lookback=120,
            ),
        ]
    )
    full = _events(rows)
    for cutoff in sorted({int(row["signal_time_ms"]) for row in rows}):
        prefix = [row for row in rows if int(row["signal_time_ms"]) <= cutoff]
        known = [row for row in full if int(row["decision_time_ms"]) <= cutoff]
        assert _events(prefix) == known


def test_symbol_cluster_and_gap_evidence_are_isolated() -> None:
    symbol_fragments = [
        _row(
            minute,
            symbol=symbol,
            raw_id=f"{symbol}-{index}",
            lookback=(15, 30)[index % 2],
        )
        for symbol in ("XUSDT", "YUSDT")
        for index, minute in enumerate((0, 5, 10, 14))
    ]
    assert _events(symbol_fragments) == []

    cluster_fragments = [
        _row(
            minute,
            raw_id=f"cluster-a-{index}",
            lookback=(15, 30)[index % 2],
        )
        for index, minute in enumerate((0, 7, 14))
    ]
    cluster_fragments.extend(
        _row(
            minute,
            raw_id=f"cluster-b-{index}",
            lookback=(15, 30)[index % 2],
            low=199.0,
            high=201.0,
        )
        for index, minute in enumerate((0, 14))
    )
    assert _events(cluster_fragments) == []

    gap_fragments = [
        _row(minute, raw_id=f"gap-{index}", lookback=(15, 30)[index % 2])
        for index, minute in enumerate((0, 2, 4, 20, 21))
    ]
    assert _events(gap_fragments) == []


def test_empty_missing_and_unknown_profile_inputs_fail_closed() -> None:
    for frame in (
        pl.DataFrame(),
        pl.DataFrame({"symbol": ["XUSDT"]}),
        pl.DataFrame(
            {
                "symbol": ["XUSDT"],
                "profile_name": ["actionable_density_v2"],
                "signal_time_ms": [BASE_MS],
            }
        ),
    ):
        assert _events(frame) == []
    assert _events([_row(0, profile="unknown_profile", raw_id="unknown")]) == []


def test_reentry_requires_explicit_evidence_and_respects_total_cap() -> None:
    rows = _qualifying("actionable_density_v2")
    rows.extend(
        [
            _row(16, raw_id="missing"),
            _row(18, raw_id="below", outside=29),
        ]
    )
    cfg = ActionableEventConfig(
        allow_reentry_events=True,
        min_minutes_outside_midzone_before_reentry=30,
        max_events_per_regime=2,
    )
    assert len(_events(rows, cfg=cfg)) == 1
    rows.extend(
        [
            _row(20, raw_id="eligible-a", outside=30),
            _row(22, raw_id="eligible-b", outside=31),
        ]
    )
    events = _events(rows, cfg=cfg)
    assert len(events) == 2
    assert events[0]["decision_time_ms"] == BASE_MS + 14 * MINUTE_MS
    assert events[1]["decision_time_ms"] == BASE_MS + 20 * MINUTE_MS


def test_time_fields_are_the_same_utc_decision_snapshot() -> None:
    event = _events(_qualifying("strict_actionable_v2"))[0]
    expected_ms = BASE_MS + 59 * MINUTE_MS
    expected_utc = datetime.fromtimestamp(
        expected_ms / 1000, tz=timezone.utc
    ).isoformat()
    assert event["decision_time_ms"] == event["signal_time_ms"] == expected_ms
    assert event["decision_time_utc"] == event["signal_time_utc"] == expected_utc
