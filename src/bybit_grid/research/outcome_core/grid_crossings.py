from __future__ import annotations

import json

import numpy as np


def geometric_grid_levels(low: float, high: float, grid_count: int) -> np.ndarray:
    if grid_count < 2:
        raise ValueError("grid_count must be >= 2")
    if low <= 0 or high <= 0 or high <= low:
        return np.linspace(low, high, grid_count, dtype=float)
    return np.geomspace(low, high, grid_count, dtype=float)


def levels_json(levels: np.ndarray) -> str:
    return json.dumps([round(float(x), 10) for x in levels.tolist()], separators=(",", ":"))


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
