from __future__ import annotations

import json

import numpy as np

GRID_LEVELS_SERIALIZATION_VERSION = "float64_roundtrip_v1"


def geometric_grid_levels(low: float, high: float, cell_number: int) -> np.ndarray:
    """Return N+1 native-grid boundary levels for N geometric cells."""
    if cell_number < 2:
        raise ValueError("cell_number must be >= 2")
    if low <= 0:
        raise ValueError("low must be > 0 for geometric grid levels")
    if high <= low:
        raise ValueError("high must be greater than low for geometric grid levels")
    ratio = (high / low) ** (1.0 / cell_number)
    levels = low * np.power(ratio, np.arange(cell_number + 1, dtype=float))
    levels[0] = low
    levels[-1] = high
    if levels.size != cell_number + 1 or not np.all(np.diff(levels) > 0):
        raise ValueError("geometric grid levels must be strictly increasing")
    return levels.astype(float)


def levels_json(levels: np.ndarray) -> str:
    values = [float(x) for x in levels]
    return json.dumps(values, separators=(",", ":"), allow_nan=False)


def count_level_crossings(closes: np.ndarray, levels: np.ndarray) -> int:
    if closes.size < 2 or levels.size == 0:
        return 0
    prev = closes[:-1]
    cur = closes[1:]
    lo = np.minimum(prev, cur)
    hi = np.maximum(prev, cur)
    moved = cur != prev
    count = 0
    for level in levels:
        count += int(np.sum(moved & (lo < level) & (hi >= level)))
    return count


def count_midline_crossings(closes: np.ndarray, mid: float) -> int:
    return count_level_crossings(closes, np.array([mid], dtype=float))


def count_intrabar_level_touches(lows: np.ndarray, highs: np.ndarray, levels: np.ndarray) -> int:
    if lows.size == 0 or highs.size == 0 or levels.size == 0:
        return 0
    count = 0
    for lo, hi in zip(lows, highs, strict=False):
        count += int(np.sum((levels >= lo) & (levels <= hi)))
    return count


def count_unique_intrabar_levels_touched(lows: np.ndarray, highs: np.ndarray, levels: np.ndarray) -> int:
    if lows.size == 0 or highs.size == 0 or levels.size == 0:
        return 0
    touched = np.zeros(levels.shape, dtype=bool)
    for lo, hi in zip(lows, highs, strict=False):
        touched |= (levels >= lo) & (levels <= hi)
    return int(np.sum(touched))
