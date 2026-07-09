from __future__ import annotations

import polars as pl

from bybit_grid.research.range_core.models import RangeInputArrays, empty_funnel
from bybit_grid.research.range_profiles import RangeProfile


def _col(df: pl.DataFrame, *names: str) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"missing required column; tried {names}")


def arrays_from_frame(df: pl.DataFrame) -> RangeInputArrays:
    ts = _col(df, "open_time_ms", "start_time_ms", "timestamp_ms")
    op = _col(df, "open", "open_price")
    hi = _col(df, "high", "high_price")
    lo = _col(df, "low", "low_price")
    cl = _col(df, "close", "close_price")
    vol = "volume" if "volume" in df.columns else None
    turn = "turnover" if "turnover" in df.columns else ("turnover_usdt" if "turnover_usdt" in df.columns else None)
    try:
        import numpy as np
    except ModuleNotFoundError:
        return RangeInputArrays(
            df[ts].to_list(),
            df[op].to_list(),
            df[hi].to_list(),
            df[lo].to_list(),
            df[cl].to_list(),
            df[vol].to_list() if vol else [1.0] * df.height,
            df[turn].to_list() if turn else None,
        )
    return RangeInputArrays(
        df[ts].to_numpy().astype(np.int64, copy=False),
        df[op].to_numpy().astype(np.float64, copy=False),
        df[hi].to_numpy().astype(np.float64, copy=False),
        df[lo].to_numpy().astype(np.float64, copy=False),
        df[cl].to_numpy().astype(np.float64, copy=False),
        df[vol].to_numpy().astype(np.float64, copy=False) if vol else np.ones(df.height, dtype=np.float64),
        df[turn].to_numpy().astype(np.float64, copy=False) if turn else None,
    )


def _frame_from_arrays(a: RangeInputArrays) -> pl.DataFrame:
    data = {
        "open_time_ms": list(a.open_time_ms),
        "open": list(a.open),
        "high": list(a.high),
        "low": list(a.low),
        "close": list(a.close),
        "volume": list(a.volume),
    }
    if a.turnover is not None:
        data["turnover"] = list(a.turnover)
    return pl.DataFrame(data)


def detect_ranges_core_with_funnel(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    core: str = "numpy_fast",
) -> tuple[pl.DataFrame, dict[str, int]]:
    try:
        if core in {"numpy_fast", "numba_optional"}:
            from bybit_grid.research.range_core.numpy_fast import detect_ranges

            return detect_ranges(arrays, symbol, profile, lookbacks)
    except ModuleNotFoundError as exc:
        if exc.name != "numpy":
            raise
    from bybit_grid.research.range_detector import DetectionConfig
    from bybit_grid.research.range_core.python_reference import detect_from_frame

    out = detect_from_frame(_frame_from_arrays(arrays), symbol, DetectionConfig(lookbacks=lookbacks), profile)
    funnel = empty_funnel()
    funnel["total_window_positions"] = sum(max(0, len(arrays.open_time_ms) - lb + 1) for lb in lookbacks)
    funnel["range_height_rejection_count"] = max(0, funnel["total_window_positions"] - out.height)
    funnel["raw_candidate_pass_count"] = out.height
    return out, funnel


def detect_ranges_core(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    core: str = "numpy_fast",
) -> pl.DataFrame:
    return detect_ranges_core_with_funnel(arrays, symbol, profile, lookbacks, core=core)[0]
