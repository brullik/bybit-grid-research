from __future__ import annotations

from dataclasses import dataclass

import math
import polars as pl

from bybit_grid.research.range_features import DEFAULT_LOOKBACKS
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile


@dataclass(frozen=True)
class DetectionConfig:
    lookbacks: tuple[int, ...] = DEFAULT_LOOKBACKS
    lower_zone_pct: float = 0.20
    mid_zone_pct: float = 0.30
    upper_zone_pct: float = 0.20
    min_valid_candle_pct: float = 1.0
    max_zero_volume_window_pct: float = 0.05
    min_range_height_pct: float = 0.0001
    profile_name: str = "broad_diagnostic"


def _col(df: pl.DataFrame, *names: str) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"missing required column; tried {names}")


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    total = 0.0
    for i, val in enumerate(values):
        total += val
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def detect_range_candidates(
    df: pl.DataFrame, symbol: str, config: DetectionConfig | None = None, profile: RangeProfile | None = None
) -> pl.DataFrame:
    cfg = config or DetectionConfig()
    prof = profile or RANGE_PROFILES.get(cfg.profile_name, RANGE_PROFILES["broad_diagnostic"])
    if df.is_empty():
        return pl.DataFrame()
    from bybit_grid.research.range_core.adapter import arrays_from_frame, detect_ranges_core

    return detect_ranges_core(arrays_from_frame(df), symbol, prof, cfg.lookbacks, core="numpy_fast")
# mandatory-red-probe: p0-range-reference-fast-config-parity; intentionally inert
