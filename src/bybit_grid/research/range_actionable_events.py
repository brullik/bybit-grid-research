from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import polars as pl

from bybit_grid.research.range_profiles import RANGE_PROFILES
from bybit_grid.research.range_regime_coalescer import RegimeCoalesceConfig, add_actionable_cluster_id, coalesce_range_regimes


@dataclass(frozen=True)
class ActionableEventConfig:
    allow_reentry_events: bool = False
    min_minutes_outside_midzone_before_reentry: int = 30
    max_events_per_regime: int = 1


def stable_action_event_id(regime_id: str, signal_time_ms: int, raw_candidate_id: str) -> str:
    return hashlib.sha256(f"{regime_id}|{int(signal_time_ms)}|{raw_candidate_id}".encode()).hexdigest()[:32]


def add_range_quality_score(raw: pl.DataFrame) -> pl.DataFrame:
    if raw.is_empty() or "range_quality_score" in raw.columns:
        return raw
    lower = pl.col("touches_lower_zone") if "touches_lower_zone" in raw.columns else pl.lit(0)
    upper = pl.col("touches_upper_zone") if "touches_upper_zone" in raw.columns else pl.lit(0)
    crosses = pl.col("midline_crosses") if "midline_crosses" in raw.columns else pl.lit(0)
    height_atr = pl.col("range_height_atr_14").fill_null(0.0) if "range_height_atr_14" in raw.columns else pl.lit(0.0)
    amp = pl.col("amplitude_score").fill_null(pl.col("range_height_pct")) if "amplitude_score" in raw.columns else pl.col("range_height_pct")
    zero = pl.col("zero_volume_candles_in_window") if "zero_volume_candles_in_window" in raw.columns else pl.lit(0)
    valid = pl.col("valid_candles_in_window") if "valid_candles_in_window" in raw.columns else pl.col("lookback_minutes")
    slope_proxy = ((pl.col("time_since_last_lower_touch_minutes").fill_null(0) - pl.col("time_since_last_upper_touch_minutes").fill_null(0)).abs() / pl.col("lookback_minutes").clip(lower_bound=1)) if "time_since_last_lower_touch_minutes" in raw.columns else pl.lit(0.0)
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


def build_actionable_events(raw: pl.DataFrame, regime_cfg: RegimeCoalesceConfig | None = None, event_cfg: ActionableEventConfig | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    event_cfg = event_cfg or ActionableEventConfig()
    if raw.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    df = add_range_quality_score(add_actionable_cluster_id(raw, regime_cfg))
    if "raw_candidate_id" not in df.columns:
        df = df.with_columns(pl.col("candidate_id").alias("raw_candidate_id"))
    regimes = coalesce_range_regimes(df, regime_cfg)
    if not regimes.is_empty():
        keep_ids: list[str] = []
        for reg in regimes.to_dicts():
            prof = RANGE_PROFILES.get(str(reg.get("profile_name", "")))
            if prof is None:
                keep_ids.append(str(reg["range_regime_id"]))
                continue
            unique_lookbacks = len([x for x in str(reg.get("lookbacks_observed") or "").split(",") if x])
            if (
                int(reg.get("regime_duration_minutes") or 0) >= prof.min_regime_duration_minutes
                and int(reg.get("raw_candidates_in_regime") or 0) >= prof.min_raw_candidates_in_regime
                and unique_lookbacks >= prof.min_unique_lookbacks_in_regime
            ):
                keep_ids.append(str(reg["range_regime_id"]))
        regimes = regimes.filter(pl.col("range_regime_id").is_in(keep_ids)) if keep_ids else pl.DataFrame()
    rows: list[dict[str, object]] = []
    for reg in regimes.to_dicts():
        part = df.filter((pl.col("symbol") == reg["symbol"]) & (pl.col("profile_name") == reg["profile_name"]) & (pl.col("range_cluster_id") == reg["range_cluster_id"]) & (pl.col("signal_time_ms") >= reg["first_seen_time_ms"]) & (pl.col("signal_time_ms") <= reg["last_seen_time_ms"]))
        ordered = part.sort(["signal_time_ms", "range_quality_score"], descending=[False, True]).to_dicts()
        emit = ordered[:1] if not event_cfg.allow_reentry_events else ordered[: max(1, event_cfg.max_events_per_regime)]
        for cand in emit:
            raw_id = str(cand.get("raw_candidate_id") or cand.get("candidate_id"))
            ts = int(cand["signal_time_ms"])
            rows.append({
                "range_action_event_id": stable_action_event_id(str(reg["range_regime_id"]), ts, raw_id),
                "range_regime_id": reg["range_regime_id"],
                "symbol": cand["symbol"], "profile_name": cand["profile_name"],
                "signal_time_ms": ts,
                "signal_time_utc": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                "best_lookback_minutes": int(cand["lookback_minutes"]),
                "lookbacks_observed": reg["lookbacks_observed"],
                "raw_candidates_in_regime": reg["raw_candidates_in_regime"],
                "raw_candidate_id": raw_id,
                "range_low": cand["range_low"], "range_high": cand["range_high"], "range_mid": cand["range_mid"],
                "range_height_pct": cand.get("range_height_pct"), "range_height_atr_14": cand.get("range_height_atr_14"),
                "current_position_in_range": cand.get("current_position_in_range"),
                "midline_crosses": cand.get("midline_crosses"),
                "min_touches_lower_zone": cand.get("touches_lower_zone"),
                "min_touches_upper_zone": cand.get("touches_upper_zone"),
                "amplitude_score": cand.get("amplitude_score"),
                "path_length_over_range": cand.get("path_length_over_range"),
                "horizontal_score": cand.get("horizontal_score"),
                "range_quality_score": cand.get("range_quality_score"),
                "data_quality_ok": cand.get("data_quality_ok", True),
                "zero_volume_candles_in_window": cand.get("zero_volume_candles_in_window", 0),
                "missing_candles_in_window": cand.get("missing_candles_in_window", 0),
                "bad_ohlc_in_window": cand.get("bad_ohlc_in_window", 0),
                "fgrid_investment_min": cand.get("fgrid_investment_min"),
                "min_investment_feasible_at_5usdt": cand.get("min_investment_feasible_at_5usdt"),
            })
    return regimes, pl.DataFrame(rows).sort(["symbol", "profile_name", "signal_time_ms"]) if rows else pl.DataFrame()
