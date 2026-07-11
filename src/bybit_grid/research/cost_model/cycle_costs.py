from __future__ import annotations

from bybit_grid.research.cost_model.models import CostScenario, FeeRate


def _select_fee(rate: FeeRate, source: str) -> float:
    if source == "maker":
        return rate.maker_fee_rate
    if source == "taker":
        return rate.taker_fee_rate
    raise ValueError(f"unsupported fee source: {source}")


def geometric_cycle_costs(grid_interval_ratio: float, fee_rate: FeeRate, scenario: CostScenario) -> dict[str, object]:
    """Return per-unit-entry-notional cycle economics.

    Long normalization: buy at P and sell at P*r. Fees are measured against initial
    buy notional P, so the exit fee is multiplied by r.

    Short normalization: sell at P*r then buy back at P. Returns are measured
    against initial short-sale notional P*r, so gross return is (r-1)/r and the
    buy-back fee is divided by r. This is deliberately reported separately from
    the long calculation because the notional denominator differs.
    """
    if grid_interval_ratio <= 1:
        raise ValueError("grid_interval_ratio must be greater than 1")
    buy_fee = _select_fee(fee_rate, scenario.entry_fee_source)
    sell_fee = _select_fee(fee_rate, scenario.exit_fee_source)
    slip = scenario.slippage_bps_per_market_leg / 10_000

    gross_long = grid_interval_ratio - 1
    fee_long = buy_fee + sell_fee * grid_interval_ratio + (2 * slip)
    net_long = gross_long - fee_long

    gross_short = (grid_interval_ratio - 1) / grid_interval_ratio
    fee_short = sell_fee + (buy_fee / grid_interval_ratio) + (2 * slip)
    net_short = gross_short - fee_short

    approx_fee_bps = (buy_fee + sell_fee + 2 * slip) * 10_000
    interval_bps = (grid_interval_ratio - 1) * 10_000
    return {
        "grid_interval_ratio": grid_interval_ratio,
        "grid_interval_bps": interval_bps,
        "round_trip_fee_bps_approx": approx_fee_bps,
        "net_cycle_return_long_bps": net_long * 10_000,
        "net_cycle_return_short_bps": net_short * 10_000,
        "fee_break_even_long_bool": net_long > 0,
        "fee_break_even_short_bool": net_short > 0,
        "fee_efficiency_ratio_long": (net_long / gross_long) if gross_long else None,
        "fee_efficiency_ratio_short": (net_short / gross_short) if gross_short else None,
        "cost_assumption_id": f"cost_v1:{scenario.name}:{fee_rate.symbol}",
        "fee_snapshot_id": fee_rate.fee_snapshot_id,
        "fee_source": fee_rate.fee_source,
        "cost_scenario": scenario.name,
        "symbol": fee_rate.symbol,
    }
