from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RangeProfile:
    name: str
    range_height_pct_min: float = 0.0001
    range_height_pct_max: float = 1.0
    range_height_atr_min: float = 0.0
    range_height_atr_max: float = 1_000_000.0
    min_midline_cross_count: int = 0
    min_touches_lower_zone: int = 1
    min_touches_upper_zone: int = 1
    max_abs_slope_pct_per_window: float = 1.0
    max_zero_volume_window_pct: float = 0.05
    require_current_middle_zone: bool = True
    require_lower_upper_entries: bool = True


RANGE_PROFILES: dict[str, RangeProfile] = {
    "broad_diagnostic": RangeProfile(
        name="broad_diagnostic",
        range_height_pct_min=0.0001,
        range_height_pct_max=1.0,
        range_height_atr_min=0.0,
        range_height_atr_max=1_000_000.0,
        min_midline_cross_count=0,
        min_touches_lower_zone=1,
        min_touches_upper_zone=1,
        max_abs_slope_pct_per_window=0.05,
        max_zero_volume_window_pct=0.05,
    ),
    "balanced_research": RangeProfile(
        name="balanced_research",
        range_height_pct_min=0.001,
        range_height_pct_max=0.10,
        range_height_atr_min=2.0,
        range_height_atr_max=80.0,
        min_midline_cross_count=2,
        min_touches_lower_zone=1,
        min_touches_upper_zone=1,
        max_abs_slope_pct_per_window=0.015,
        max_zero_volume_window_pct=0.05,
    ),
    "strict_research": RangeProfile(
        name="strict_research",
        range_height_pct_min=0.002,
        range_height_pct_max=0.07,
        range_height_atr_min=3.0,
        range_height_atr_max=50.0,
        min_midline_cross_count=3,
        min_touches_lower_zone=2,
        min_touches_upper_zone=2,
        max_abs_slope_pct_per_window=0.010,
        max_zero_volume_window_pct=0.02,
    ),
}


def resolve_profiles(profile: str) -> tuple[RangeProfile, ...]:
    if profile == "all":
        return tuple(RANGE_PROFILES.values())
    return (RANGE_PROFILES[profile],)
