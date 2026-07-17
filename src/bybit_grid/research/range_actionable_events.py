from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import groupby
from typing import Any

import polars as pl

from bybit_grid.research.range_features import ONE_MINUTE_MS
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile
from bybit_grid.research.range_regime_coalescer import (
    RegimeCoalesceConfig,
    add_actionable_cluster_id,
    coalesce_range_regimes,
)


RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT = "range-actionable-prefix-invariance-v1"


@dataclass(frozen=True)
class ActionableEventConfig:
    allow_reentry_events: bool = False
    min_minutes_outside_midzone_before_reentry: int = 30
    max_events_per_regime: int = 1


@dataclass(frozen=True)
class _PrefixSnapshot:
    decision_time_ms: int
    regime_duration_minutes: int
    raw_candidates_in_regime: int
    lookbacks_observed: str
    candidate: dict[str, object]


def stable_action_event_id(
    regime_id: str,
    signal_time_ms: int,
    raw_candidate_id: str,
) -> str:
    material = (
        f"{RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT}|{regime_id}|"
        f"{int(signal_time_ms)}|{raw_candidate_id}"
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def add_range_quality_score(raw: pl.DataFrame) -> pl.DataFrame:
    if raw.is_empty() or "range_quality_score" in raw.columns:
        return raw
    lower = (
        pl.col("touches_lower_zone")
        if "touches_lower_zone" in raw.columns
        else pl.lit(0)
    )
    upper = (
        pl.col("touches_upper_zone")
        if "touches_upper_zone" in raw.columns
        else pl.lit(0)
    )
    crosses = (
        pl.col("midline_crosses") if "midline_crosses" in raw.columns else pl.lit(0)
    )
    height_atr = (
        pl.col("range_height_atr_14").fill_null(0.0)
        if "range_height_atr_14" in raw.columns
        else pl.lit(0.0)
    )
    amp = (
        pl.col("amplitude_score").fill_null(pl.col("range_height_pct"))
        if "amplitude_score" in raw.columns
        else pl.col("range_height_pct")
    )
    zero = (
        pl.col("zero_volume_candles_in_window")
        if "zero_volume_candles_in_window" in raw.columns
        else pl.lit(0)
    )
    valid = (
        pl.col("valid_candles_in_window")
        if "valid_candles_in_window" in raw.columns
        else pl.col("lookback_minutes")
    )
    slope_proxy = (
        (
            (
                pl.col("time_since_last_lower_touch_minutes").fill_null(0)
                - pl.col("time_since_last_upper_touch_minutes").fill_null(0)
            ).abs()
            / pl.col("lookback_minutes").clip(lower_bound=1)
        )
        if "time_since_last_lower_touch_minutes" in raw.columns
        else pl.lit(0.0)
    )
    return raw.with_columns(
        (
            amp * 100.0
            + crosses.clip(upper_bound=20) / 4.0
            + pl.min_horizontal(lower, upper).clip(upper_bound=10) / 2.0
            + height_atr.clip(upper_bound=50) / 10.0
            + (1.0 - slope_proxy).clip(lower_bound=0.0)
            - (zero / valid.clip(lower_bound=1)) * 10.0
        ).alias("range_quality_score"),
        height_atr.alias("path_length_over_range"),
        (1.0 - slope_proxy).clip(lower_bound=0.0).alias("horizontal_score"),
    )


def _finite_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, Decimal)):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default


def _raw_id(row: dict[str, object]) -> str:
    value = row.get("raw_candidate_id")
    return str(value) if value is not None else ""


def _candidate_rank(row: dict[str, object]) -> tuple[float, int, int, str]:
    return (
        -_finite_float(row.get("range_quality_score"), default=float("-inf")),
        -_int_value(row.get("midline_crosses")),
        -_int_value(row.get("lookback_minutes")),
        _raw_id(row),
    )


def _ordered_rows(part: pl.DataFrame) -> list[dict[str, object]]:
    return sorted(
        part.to_dicts(),
        key=lambda row: (
            _int_value(row.get("signal_time_ms")),
            *_candidate_rank(row),
        ),
    )


def _lookbacks(rows: list[dict[str, object]]) -> str:
    values = sorted({_int_value(row.get("lookback_minutes")) for row in rows})
    return ",".join(str(value) for value in values)


def _snapshot(
    prefix: list[dict[str, object]],
    timestamp_rows: list[dict[str, object]],
    first_seen_ms: int,
) -> _PrefixSnapshot:
    decision_time_ms = _int_value(timestamp_rows[0].get("signal_time_ms"))
    candidate = min(timestamp_rows, key=_candidate_rank)
    return _PrefixSnapshot(
        decision_time_ms=decision_time_ms,
        regime_duration_minutes=(decision_time_ms - first_seen_ms) // ONE_MINUTE_MS + 1,
        raw_candidates_in_regime=len(prefix),
        lookbacks_observed=_lookbacks(prefix),
        candidate=candidate,
    )


def _qualification_snapshot(
    ordered: list[dict[str, object]],
    profile: RangeProfile,
) -> _PrefixSnapshot | None:
    if not ordered:
        return None
    first_seen_ms = _int_value(ordered[0].get("signal_time_ms"))
    prefix: list[dict[str, object]] = []
    for _, group in groupby(
        ordered,
        key=lambda row: _int_value(row.get("signal_time_ms")),
    ):
        timestamp_rows = list(group)
        prefix.extend(timestamp_rows)
        snapshot = _snapshot(prefix, timestamp_rows, first_seen_ms)
        unique_lookbacks = len(snapshot.lookbacks_observed.split(","))
        if (
            snapshot.regime_duration_minutes >= profile.min_regime_duration_minutes
            and snapshot.raw_candidates_in_regime
            >= profile.min_raw_candidates_in_regime
            and unique_lookbacks >= profile.min_unique_lookbacks_in_regime
        ):
            return snapshot
    return None


def _explicit_reentry_evidence(row: dict[str, object], minimum_minutes: int) -> bool:
    value = row.get("minutes_outside_midzone_before_reentry")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    minutes = float(value)
    return math.isfinite(minutes) and minutes >= max(0, minimum_minutes)


def _required_number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        return None
    return number


def _valid_candidate_row(row: dict[str, object], id_column: str) -> bool:
    symbol = row.get("symbol")
    profile = row.get("profile_name")
    raw_id = row.get(id_column)
    if not isinstance(symbol, str) or not symbol.strip():
        return False
    if not isinstance(profile, str) or not profile.strip():
        return False
    if not isinstance(raw_id, str) or not raw_id.strip():
        return False

    signal = _required_number(row.get("signal_time_ms"))
    lookback = _required_number(row.get("lookback_minutes"), positive=True)
    low = _required_number(row.get("range_low"), positive=True)
    high = _required_number(row.get("range_high"), positive=True)
    middle = _required_number(row.get("range_mid"), positive=True)
    close = _required_number(row.get("current_close"), positive=True)
    height_pct = _required_number(row.get("range_height_pct"), positive=True)
    if None in (signal, lookback, low, high, middle, close, height_pct):
        return False
    assert signal is not None
    assert lookback is not None
    assert low is not None
    assert high is not None
    assert middle is not None
    assert close is not None
    if signal < 0.0 or not signal.is_integer() or not lookback.is_integer():
        return False
    return low < middle < high and low <= close <= high


def _candidate_batch_key(
    row: dict[str, object],
) -> tuple[str, str, int] | None:
    symbol = row.get("symbol")
    profile = row.get("profile_name")
    signal = _required_number(row.get("signal_time_ms"))
    if (
        not isinstance(symbol, str)
        or not symbol.strip()
        or not isinstance(profile, str)
        or not profile.strip()
        or signal is None
        or signal < 0.0
        or not signal.is_integer()
    ):
        return None
    return symbol, profile, int(signal)


def _validated_candidates(raw: pl.DataFrame) -> pl.DataFrame:
    required = {
        "symbol",
        "profile_name",
        "signal_time_ms",
        "lookback_minutes",
        "range_low",
        "range_high",
        "range_mid",
        "current_close",
        "range_height_pct",
    }
    if not required.issubset(raw.columns):
        return pl.DataFrame()
    if "raw_candidate_id" in raw.columns:
        id_column = "raw_candidate_id"
    elif "candidate_id" in raw.columns:
        id_column = "candidate_id"
    else:
        return pl.DataFrame()

    rows = raw.to_dicts()
    batch_keys = [_candidate_batch_key(row) for row in rows]

    poisoned_batches: set[tuple[str, str, int]] = set()
    identities: dict[tuple[str, str, int], dict[str, dict[str, object]]] = {}
    first_occurrence: list[bool] = []
    row_validity: list[bool] = []
    for row, batch_key in zip(rows, batch_keys, strict=True):
        if batch_key is None:
            row_validity.append(False)
            first_occurrence.append(False)
            continue
        valid = _valid_candidate_row(row, id_column)
        row_validity.append(valid)
        if not valid:
            poisoned_batches.add(batch_key)
            first_occurrence.append(False)
            continue

        raw_id = str(row[id_column])
        seen = identities.setdefault(batch_key, {})
        previous = seen.get(raw_id)
        if previous is None:
            seen[raw_id] = row
            first_occurrence.append(True)
        elif previous == row:
            first_occurrence.append(False)
        else:
            poisoned_batches.add(batch_key)
            first_occurrence.append(False)

    mask = [
        valid and first and key not in poisoned_batches
        for valid, first, key in zip(
            row_validity,
            first_occurrence,
            batch_keys,
            strict=True,
        )
    ]
    if not any(mask):
        return pl.DataFrame()
    return raw.filter(pl.Series("valid_candidate", mask))


def _event_snapshots(
    ordered: list[dict[str, object]],
    primary: _PrefixSnapshot,
    event_cfg: ActionableEventConfig,
) -> list[_PrefixSnapshot]:
    snapshots = [primary]
    limit = max(1, event_cfg.max_events_per_regime)
    if not event_cfg.allow_reentry_events or limit == 1:
        return snapshots

    first_seen_ms = _int_value(ordered[0].get("signal_time_ms"))
    prefix: list[dict[str, object]] = []
    for timestamp, group in groupby(
        ordered,
        key=lambda row: _int_value(row.get("signal_time_ms")),
    ):
        timestamp_rows = list(group)
        prefix.extend(timestamp_rows)
        if timestamp <= primary.decision_time_ms:
            continue
        eligible = [
            row
            for row in timestamp_rows
            if _explicit_reentry_evidence(
                row,
                event_cfg.min_minutes_outside_midzone_before_reentry,
            )
        ]
        if not eligible:
            continue
        snapshots.append(_snapshot(prefix, eligible, first_seen_ms))
        if len(snapshots) >= limit:
            break
    return snapshots


def _event_row(
    regime_id: str,
    snapshot: _PrefixSnapshot,
) -> dict[str, object]:
    candidate = snapshot.candidate
    raw_id = _raw_id(candidate)
    decision_time_ms = snapshot.decision_time_ms
    decision_time_utc = datetime.fromtimestamp(
        decision_time_ms / 1000,
        tz=timezone.utc,
    ).isoformat()
    return {
        "range_action_event_id": stable_action_event_id(
            regime_id,
            decision_time_ms,
            raw_id,
        ),
        "actionable_event_semantics_version": RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT,
        "range_regime_id": regime_id,
        "symbol": candidate["symbol"],
        "profile_name": candidate["profile_name"],
        "decision_time_ms": decision_time_ms,
        "decision_time_utc": decision_time_utc,
        "signal_time_ms": decision_time_ms,
        "signal_time_utc": decision_time_utc,
        "regime_duration_minutes": snapshot.regime_duration_minutes,
        "best_lookback_minutes": _int_value(candidate.get("lookback_minutes")),
        "lookbacks_observed": snapshot.lookbacks_observed,
        "raw_candidates_in_regime": snapshot.raw_candidates_in_regime,
        "raw_candidate_id": raw_id,
        "range_low": candidate["range_low"],
        "range_high": candidate["range_high"],
        "range_mid": candidate["range_mid"],
        "range_height_pct": candidate.get("range_height_pct"),
        "range_height_atr_14": candidate.get("range_height_atr_14"),
        "current_position_in_range": candidate.get("current_position_in_range"),
        "midline_crosses": candidate.get("midline_crosses"),
        "min_touches_lower_zone": candidate.get("touches_lower_zone"),
        "min_touches_upper_zone": candidate.get("touches_upper_zone"),
        "amplitude_score": candidate.get("amplitude_score"),
        "path_length_over_range": candidate.get("path_length_over_range"),
        "horizontal_score": candidate.get("horizontal_score"),
        "range_quality_score": candidate.get("range_quality_score"),
        "data_quality_ok": candidate.get("data_quality_ok", True),
        "zero_volume_candles_in_window": candidate.get(
            "zero_volume_candles_in_window",
            0,
        ),
        "missing_candles_in_window": candidate.get("missing_candles_in_window", 0),
        "bad_ohlc_in_window": candidate.get("bad_ohlc_in_window", 0),
        "fgrid_investment_min": candidate.get("fgrid_investment_min"),
        "min_investment_feasible_at_5usdt": candidate.get(
            "min_investment_feasible_at_5usdt"
        ),
    }


def _regime_part(df: pl.DataFrame, regime: dict[str, Any]) -> pl.DataFrame:
    return df.filter(
        (pl.col("symbol") == regime["symbol"])
        & (pl.col("profile_name") == regime["profile_name"])
        & (pl.col("range_cluster_id") == regime["range_cluster_id"])
        & (pl.col("signal_time_ms") >= regime["first_seen_time_ms"])
        & (pl.col("signal_time_ms") <= regime["last_seen_time_ms"])
    )


def build_actionable_events(
    raw: pl.DataFrame,
    regime_cfg: RegimeCoalesceConfig | None = None,
    event_cfg: ActionableEventConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    event_cfg = event_cfg or ActionableEventConfig()
    if raw.is_empty():
        return pl.DataFrame(), pl.DataFrame()

    validated = _validated_candidates(raw)
    if validated.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    df = add_range_quality_score(add_actionable_cluster_id(validated, regime_cfg))
    if "raw_candidate_id" not in df.columns:
        df = df.with_columns(pl.col("candidate_id").alias("raw_candidate_id"))
    all_regimes = coalesce_range_regimes(df, regime_cfg)

    keep_ids: list[str] = []
    rows: list[dict[str, object]] = []
    for regime in all_regimes.to_dicts():
        profile = RANGE_PROFILES.get(str(regime.get("profile_name", "")))
        if profile is None:
            continue
        regime_id = str(regime["range_regime_id"])
        ordered = _ordered_rows(_regime_part(df, regime))
        primary = _qualification_snapshot(ordered, profile)
        if primary is None:
            continue
        keep_ids.append(regime_id)
        rows.extend(
            _event_row(regime_id, snapshot)
            for snapshot in _event_snapshots(ordered, primary, event_cfg)
        )

    regimes = (
        all_regimes.filter(pl.col("range_regime_id").is_in(keep_ids))
        if keep_ids
        else pl.DataFrame()
    )
    events = (
        pl.DataFrame(rows).sort(
            [
                "symbol",
                "profile_name",
                "signal_time_ms",
                "range_action_event_id",
            ]
        )
        if rows
        else pl.DataFrame()
    )
    return regimes, events
