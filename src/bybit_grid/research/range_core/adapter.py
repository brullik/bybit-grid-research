from __future__ import annotations

from pathlib import Path

import polars as pl

from bybit_grid.research.range_core.models import RangeInputArrays
from bybit_grid.research.range_detector import DetectionConfig
from bybit_grid.research.range_profiles import RangeProfile


RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"


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


def numpy_is_project_shadow(numpy_file: Path, project_root: Path) -> bool:
    project_numpy_dir = (project_root / "numpy").resolve()
    project_numpy_file = (project_root / "numpy.py").resolve()
    numpy_file = numpy_file.resolve()
    return numpy_file == project_numpy_file or numpy_file.is_relative_to(project_numpy_dir)


def _import_real_numpy_for_fast_core():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "numpy_fast requires real numpy. Install dependencies with: python -m pip install -e .[dev]"
        ) from exc
    project_root = Path(__file__).resolve().parents[4]
    numpy_file = Path(getattr(np, "__file__", "")).resolve()
    if not getattr(np, "__version__", None) or numpy_is_project_shadow(numpy_file, project_root):
        raise ModuleNotFoundError(
            "numpy_fast requires real numpy. Install dependencies with: python -m pip install -e .[dev]"
        )
    return np


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


def _resolve_config(
    lookbacks: tuple[int, ...],
    config: DetectionConfig | None,
) -> DetectionConfig:
    if config is None:
        return DetectionConfig(lookbacks=lookbacks)
    if config.lookbacks != lookbacks:
        raise ValueError("config.lookbacks must exactly match positional lookbacks")
    return config


def detect_ranges_core_with_funnel(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    core: str = "numpy_fast",
    config: DetectionConfig | None = None,
) -> tuple[pl.DataFrame, dict[str, int]]:
    cfg = _resolve_config(lookbacks, config)
    if core in {"numpy_fast", "numba_optional"}:
        _import_real_numpy_for_fast_core()
        from bybit_grid.research.range_core.numpy_fast import detect_ranges

        return detect_ranges(arrays, symbol, profile, lookbacks, config=cfg)
    from bybit_grid.research.range_core.python_reference import (
        detect_from_frame_with_funnel,
    )

    return detect_from_frame_with_funnel(_frame_from_arrays(arrays), symbol, cfg, profile)


def detect_ranges_core(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    core: str = "numpy_fast",
    config: DetectionConfig | None = None,
) -> pl.DataFrame:
    return detect_ranges_core_with_funnel(
        arrays,
        symbol,
        profile,
        lookbacks,
        core=core,
        config=config,
    )[0]
