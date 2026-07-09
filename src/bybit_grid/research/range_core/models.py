from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RangeInputArrays:
    open_time_ms: Any
    open: Any
    high: Any
    low: Any
    close: Any
    volume: Any
    turnover: Any | None = None

    def contiguous(self) -> "RangeInputArrays":
        try:
            import numpy as np
        except ModuleNotFoundError:
            return self
        return RangeInputArrays(
            open_time_ms=np.ascontiguousarray(self.open_time_ms, dtype=np.int64),
            open=np.ascontiguousarray(self.open, dtype=np.float64),
            high=np.ascontiguousarray(self.high, dtype=np.float64),
            low=np.ascontiguousarray(self.low, dtype=np.float64),
            close=np.ascontiguousarray(self.close, dtype=np.float64),
            volume=np.ascontiguousarray(self.volume, dtype=np.float64),
            turnover=None if self.turnover is None else np.ascontiguousarray(self.turnover, dtype=np.float64),
        )

FUNNEL_KEYS = (
    "total_window_positions", "insufficient_history_rejection_count", "missing_window_rejection_count",
    "duplicate_timestamp_rejection_count", "bad_ohlc_window_rejection_count", "zero_volume_window_rejection_count",
    "range_height_rejection_count", "middle_zone_rejection_count", "lower_upper_entry_rejection_count",
    "midline_cross_rejection_count", "touch_count_rejection_count", "slope_rejection_count",
    "range_atr_rejection_count", "quality_score_rejection_count", "raw_candidate_pass_count",
)

def empty_funnel() -> dict[str, int]:
    return {k: 0 for k in FUNNEL_KEYS}
