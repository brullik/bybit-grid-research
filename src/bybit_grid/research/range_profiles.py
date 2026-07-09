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
    min_path_length_over_range: float = 0.0
    min_range_quality_score: float = 0.0


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
    "actionable_research": RangeProfile(
        name="actionable_research",
        range_height_pct_min=0.0015,
        range_height_pct_max=0.08,
        range_height_atr_min=3.0,
        range_height_atr_max=50.0,
        min_midline_cross_count=4,
        min_touches_lower_zone=2,
        min_touches_upper_zone=2,
        max_abs_slope_pct_per_window=0.008,
        max_zero_volume_window_pct=0.02,
        min_path_length_over_range=3.0,
        min_range_quality_score=1.0,
    ),
    "strict_actionable": RangeProfile(
        name="strict_actionable",
        range_height_pct_min=0.002,
        range_height_pct_max=0.06,
        range_height_atr_min=4.0,
        range_height_atr_max=35.0,
        min_midline_cross_count=5,
        min_touches_lower_zone=2,
        min_touches_upper_zone=2,
        max_abs_slope_pct_per_window=0.005,
        max_zero_volume_window_pct=0.01,
        min_path_length_over_range=4.0,
        min_range_quality_score=1.5,
    ),
}


def resolve_profiles(profile: str) -> tuple[RangeProfile, ...]:
    if profile == "all":
        return tuple(RANGE_PROFILES.values())
    return (RANGE_PROFILES[profile],)
