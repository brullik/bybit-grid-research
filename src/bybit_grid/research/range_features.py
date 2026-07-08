from __future__ import annotations

ONE_MINUTE_MS = 60_000
DEFAULT_LOOKBACKS = (30, 60, 120, 240, 480, 720, 1440)


def stable_candidate_id(symbol: str, signal_time_ms: int, lookback_minutes: int) -> str:
    return f"{symbol}:{int(signal_time_ms)}:{int(lookback_minutes)}"
