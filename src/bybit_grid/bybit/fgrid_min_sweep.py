from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload

DEFAULT_INIT_MARGIN = Decimal("100")
FALLBACK_INIT_MARGIN = Decimal("500")
LEVERAGE_LADDER = [1, 3, 10, 25, 50, 100]


@dataclass(frozen=True)
class SweepProfile:
    profile_name: str
    range_width_pct: Decimal
    cell_number: int
    leverage: int
    stop_loss_mult: Decimal
    init_margin: Decimal = DEFAULT_INIT_MARGIN


def leverage_probe_values(max_leverage: Any) -> list[int]:
    try:
        max_lev = Decimal(str(max_leverage))
    except Exception:
        max_lev = Decimal("1")
    values = [x for x in LEVERAGE_LADDER if Decimal(x) <= max_lev]
    return values or [1]


def _profile_payload(
    symbol: str, last_price: Any, tick_size: Any, profile: SweepProfile
) -> tuple[dict[str, Any], dict[str, Any]]:
    width = profile.range_width_pct
    lower = Decimal("1") - (width / 2)
    upper = Decimal("1") + (width / 2)
    stop_loss = lower * profile.stop_loss_mult
    payload = build_fgrid_validate_payload(
        symbol,
        Decimal(str(last_price)),
        Decimal(str(tick_size)),
        leverage=profile.leverage,
        cell_number=profile.cell_number,
        init_margin=profile.init_margin,
        lower_mult=lower,
        upper_mult=upper,
        stop_loss_mult=stop_loss,
    )
    meta = {
        "symbol": symbol,
        "profile_name": profile.profile_name,
        "lastPrice": float(last_price),
        "tickSize": str(tick_size),
        "range_width_pct": float(width),
        "min_price": float(payload["min_price"]),
        "max_price": float(payload["max_price"]),
        "stop_loss_price": float(payload["stop_loss_price"]),
        "cell_number_requested": profile.cell_number,
        "leverage_requested": profile.leverage,
        "init_margin_requested": float(profile.init_margin),
        "stop_loss_mult": float(profile.stop_loss_mult),
    }
    return payload, meta


def build_min_sweep_candidates(
    symbol: str,
    last_price: Any,
    tick_size: Any,
    max_leverage: Any = 1,
    max_profiles_per_symbol: int = 12,
    absolute_max_profiles_per_symbol: int = 24,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    cap = min(max_profiles_per_symbol, absolute_max_profiles_per_symbol)
    ladder = leverage_probe_values(max_leverage)
    high = ladder[-1]
    profiles = [
        SweepProfile("ultra_min_1", Decimal("0.01"), 2, high, Decimal("0.98")),
        SweepProfile("ultra_min_2", Decimal("0.02"), 2, high, Decimal("0.98")),
        SweepProfile("min_cells_high_lev", Decimal("0.05"), 2, high, Decimal("0.95")),
        SweepProfile("small_grid_high_lev", Decimal("0.05"), 5, high, Decimal("0.95")),
        SweepProfile("baseline_high_lev", Decimal("0.10"), 10, high, Decimal("0.95")),
        SweepProfile("baseline_low_lev", Decimal("0.10"), 10, 1, Decimal("0.95")),
    ]
    for lev in ladder:
        profiles.append(SweepProfile(f"ladder_lev_{lev}", Decimal("0.05"), 2, lev, Decimal("0.95")))
    seen: set[tuple[Any, ...]] = set()
    out = []
    for profile in profiles:
        key = (
            profile.range_width_pct,
            profile.cell_number,
            profile.leverage,
            profile.stop_loss_mult,
            profile.init_margin,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(_profile_payload(symbol, last_price, tick_size, profile))
        if len(out) >= cap:
            break
    return out


def should_stop_symbol(
    rows: list[dict[str, Any]], threshold: Decimal = Decimal("5"), exhaustive: bool = False
) -> bool:
    if exhaustive:
        return False
    mins = [Decimal(str(r["investment_min"])) for r in rows if r.get("investment_min") is not None]
    if mins and min(mins) <= threshold:
        return True
    return len(rows) >= 3 and mins and min(mins) > Decimal("500")


def progress_line(
    done: int,
    total: int,
    start: float,
    best_5usdt_symbols: int = 0,
    errors: int = 0,
    skipped_resume: int = 0,
) -> str:
    elapsed = max(time.monotonic() - start, 1e-9)
    rps = done / elapsed
    remaining = max(total - done, 0)
    eta = int(remaining / rps) if rps > 0 else 0
    pct = (done / total * 100) if total else 100.0
    return f"progress done={done} total={total} pct={pct:.1f} rps={rps:.1f} eta_sec={eta} best_5usdt_symbols={best_5usdt_symbols} errors={errors} skipped_resume={skipped_resume}"
