from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

import polars as pl

from bybit_grid.research.range_features import DEFAULT_LOOKBACKS
from bybit_grid.research.range_profiles import RANGE_PROFILES, RangeProfile


RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


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

    def __post_init__(self) -> None:
        if (
            type(self.lookbacks) is not tuple
            or not self.lookbacks
            or any(type(lookback) is not int or lookback <= 0 for lookback in self.lookbacks)
            or len(set(self.lookbacks)) != len(self.lookbacks)
        ):
            raise ValueError("lookbacks must be a nonempty tuple of unique positive integers")

        for name in (
            "lower_zone_pct",
            "mid_zone_pct",
            "upper_zone_pct",
            "max_zero_volume_window_pct",
        ):
            value = getattr(self, name)
            if not _is_finite_number(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite number in [0, 1]")

        if (
            not _is_finite_number(self.min_range_height_pct)
            or self.min_range_height_pct < 0.0
        ):
            raise ValueError("min_range_height_pct must be a finite nonnegative number")

        if (
            not _is_finite_number(self.min_valid_candle_pct)
            or self.min_valid_candle_pct != 1.0
        ):
            raise ValueError(
                "range-reference-fast-config-parity-v1 requires "
                "min_valid_candle_pct=1.0"
            )

        if not isinstance(self.profile_name, str) or not self.profile_name.strip():
            raise ValueError("profile_name must name a nonblank profile")


def _col(df: pl.DataFrame, *names: str) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"missing required column; tried {names}")


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    for index in range(window - 1, len(values)):
        current = values[index - window + 1 : index + 1]
        if all(math.isfinite(value) for value in current):
            out[index] = math.fsum(current) / window
    return out


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))


def _profile_from_config(config: DetectionConfig) -> RangeProfile:
    try:
        return RANGE_PROFILES[config.profile_name]
    except KeyError:
        raise ValueError(
            "profile_name must name a registered profile when no explicit profile is supplied"
        ) from None


def detect_range_candidates(
    df: pl.DataFrame,
    symbol: str,
    config: DetectionConfig | None = None,
    profile: RangeProfile | None = None,
) -> pl.DataFrame:
    cfg = DetectionConfig() if config is None else config
    selected_profile = _profile_from_config(cfg) if profile is None else profile
    if df.is_empty():
        return pl.DataFrame()

    from bybit_grid.research.range_core.adapter import arrays_from_frame, detect_ranges_core

    return detect_ranges_core(
        arrays_from_frame(df),
        symbol,
        selected_profile,
        cfg.lookbacks,
        core="numpy_fast",
        config=cfg,
    )
