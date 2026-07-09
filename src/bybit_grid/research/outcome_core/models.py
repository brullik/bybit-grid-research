from __future__ import annotations

from dataclasses import dataclass

DEFAULT_HORIZONS_MINUTES = [60, 240, 720, 1440, 2880]
DEFAULT_GRID_COUNTS = [5, 10, 20]
DEFAULT_SL_ATR_BUFFERS = [0.0, 0.5, 1.0]


@dataclass(frozen=True)
class OutcomePlan:
    range_run_id: str
    outcome_run_id: str
    events: int
    horizons: list[int]
    grid_counts: list[int]
    sl_atr_buffers: list[float]

    @property
    def planned_rows(self) -> int:
        return self.events * len(self.horizons) * len(self.grid_counts) * len(self.sl_atr_buffers)
