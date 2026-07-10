from __future__ import annotations

import math
from dataclasses import dataclass

ATR_SOURCE_DIRECT = "direct_event_atr_14"
ATR_SOURCE_DERIVED = "derived_range_height_over_ratio"
ATR_SOURCE_INVALID = "missing_or_invalid"


@dataclass(frozen=True)
class SlProxy:
    atr_14_abs_used: float | None
    atr_rel_14_used: float | None
    atr_value_source: str
    sl_atr_buffer: float
    lower_sl_price: float | None
    upper_sl_price: float | None
    sl_distance_lower_abs: float | None
    sl_distance_upper_abs: float | None
    sl_distance_lower_pct: float | None
    sl_distance_upper_pct: float | None
    sl_proxy_valid_bool: bool
    sl_proxy_invalid_reason: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _finite_positive(value: object) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and x > 0


def compute_sl_proxy(event: dict, range_low: float, range_high: float, sl_atr_buffer: float) -> SlProxy:
    range_height_abs = range_high - range_low
    if not (math.isfinite(range_low) and math.isfinite(range_high) and range_low > 0 and range_high > range_low):
        return _invalid(sl_atr_buffer, "invalid_range")

    derived: float | None = None
    ratio = event.get("range_height_atr_14")
    if _finite_positive(ratio) and range_height_abs > 0:
        derived = range_height_abs / float(ratio)

    direct = None
    for key in ("atr_14", "atr_14_abs"):
        if _finite_positive(event.get(key)):
            direct = float(event[key])
            break

    if direct is not None:
        atr_abs = direct
        source = ATR_SOURCE_DIRECT
        reason = ""
        if derived is not None and not math.isclose(direct, derived, rel_tol=1e-6, abs_tol=1e-12):
            reason = "direct_derived_atr_mismatch"
    elif derived is not None:
        atr_abs = derived
        source = ATR_SOURCE_DERIVED
        reason = ""
    else:
        return _invalid(sl_atr_buffer, "missing_or_invalid_atr")

    if not _finite_positive(atr_abs):
        return _invalid(sl_atr_buffer, "missing_or_invalid_atr")
    buf = float(sl_atr_buffer)
    if not math.isfinite(buf) or buf < 0:
        return _invalid(sl_atr_buffer, "invalid_sl_atr_buffer")
    lower = range_low - buf * atr_abs
    upper = range_high + buf * atr_abs
    lower_abs = range_low - lower
    upper_abs = upper - range_high
    atr_rel = atr_abs / range_low * 100 if range_low else None
    return SlProxy(
        atr_abs, atr_rel, source, buf, lower, upper, lower_abs, upper_abs,
        lower_abs / range_low * 100 if range_low else None,
        upper_abs / range_high * 100 if range_high else None,
        True, reason,
    )


def _invalid(sl_atr_buffer: float, reason: str) -> SlProxy:
    return SlProxy(None, None, ATR_SOURCE_INVALID, float(sl_atr_buffer), None, None, None, None, None, None, False, reason)
