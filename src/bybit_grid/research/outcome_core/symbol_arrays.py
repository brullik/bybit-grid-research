from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl


@dataclass(frozen=True)
class OutcomeSymbolArrays:
    time_ms: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    mark_time_ms: np.ndarray
    mark_close: np.ndarray
    funding_time_ms: np.ndarray
    funding_rate: np.ndarray
    bad_ohlc_prefix: np.ndarray
    zero_volume_prefix: np.ndarray


def _time_col(df: pl.DataFrame) -> str:
    return "open_time_ms" if "open_time_ms" in df.columns else "start_time_ms"


def _sorted_arrays(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if df.is_empty():
        zf = np.array([], dtype=float)
        return np.array([], dtype=np.int64), zf, zf, zf, zf, zf
    tcol = _time_col(df)
    d = df.sort(tcol)
    return (
        d[tcol].cast(pl.Int64).to_numpy(),
        d["open"].cast(pl.Float64).to_numpy() if "open" in d.columns else np.array([], dtype=float),
        d["high"].cast(pl.Float64).to_numpy() if "high" in d.columns else np.array([], dtype=float),
        d["low"].cast(pl.Float64).to_numpy() if "low" in d.columns else np.array([], dtype=float),
        d["close"].cast(pl.Float64).to_numpy() if "close" in d.columns else np.array([], dtype=float),
        d["volume"].cast(pl.Float64).to_numpy() if "volume" in d.columns else np.array([], dtype=float),
    )


def build_symbol_arrays(klines: pl.DataFrame, mark_klines: pl.DataFrame, funding: pl.DataFrame) -> OutcomeSymbolArrays:
    time_ms, opens, highs, lows, closes, volume = _sorted_arrays(klines)
    bad = ((highs < lows) | (opens <= 0) | (closes <= 0)).astype(np.int64) if highs.size else np.array([], dtype=np.int64)
    zero = (volume <= 0).astype(np.int64) if volume.size else np.array([], dtype=np.int64)
    mark_time = np.array([], dtype=np.int64)
    mark_close = np.array([], dtype=float)
    if not mark_klines.is_empty():
        mt = _time_col(mark_klines)
        m = mark_klines.sort(mt)
        mark_time = m[mt].cast(pl.Int64).to_numpy()
        mark_close = m["close"].cast(pl.Float64).to_numpy() if "close" in m.columns else np.array([], dtype=float)
    funding_time = np.array([], dtype=np.int64)
    funding_rate = np.array([], dtype=float)
    if not funding.is_empty():
        ft = "funding_time_ms" if "funding_time_ms" in funding.columns else _time_col(funding)
        fr = "funding_rate" if "funding_rate" in funding.columns else ("rate" if "rate" in funding.columns else None)
        f = funding.sort(ft)
        funding_time = f[ft].cast(pl.Int64).to_numpy()
        funding_rate = f[fr].cast(pl.Float64).to_numpy() if fr else np.array([], dtype=float)
    return OutcomeSymbolArrays(
        time_ms=time_ms,
        open=opens,
        high=highs,
        low=lows,
        close=closes,
        volume=volume,
        mark_time_ms=mark_time,
        mark_close=mark_close,
        funding_time_ms=funding_time,
        funding_rate=funding_rate,
        bad_ohlc_prefix=np.concatenate(([0], np.cumsum(bad))),
        zero_volume_prefix=np.concatenate(([0], np.cumsum(zero))),
    )
