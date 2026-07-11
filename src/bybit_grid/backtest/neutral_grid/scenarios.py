from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TypeAlias

from .engine import NeutralGridReferenceEngine
from .models import (
    FundingEvent,
    LiquidityRole,
    NeutralGridConfig,
    PriceEvent,
    QuantitySource,
    SimulationResult,
    TerminationReason,
    ZERO,
    _finite_decimal,
    _non_bool_int,
)

SCENARIO_VERSION = "neutral_grid_synthetic_scenario_v1"


@dataclass(frozen=True)
class ManualTerminationAction:
    sequence_id: int
    time_ms: int
    trigger_price: Decimal

    def __post_init__(self) -> None:
        _non_bool_int(self.sequence_id, "sequence_id")
        _non_bool_int(self.time_ms, "time_ms")
        if self.sequence_id < 1 or self.time_ms < 0:
            raise ValueError("sequence_id must be >= 1 and time_ms must be >= 0")
        _finite_decimal(self.trigger_price, "trigger_price")
        if self.trigger_price <= ZERO:
            raise ValueError("trigger_price must be positive")


ScenarioAction: TypeAlias = PriceEvent | FundingEvent | ManualTerminationAction


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    scenario_version: str
    config: NeutralGridConfig
    actions: tuple[ScenarioAction, ...]
    description: str
    expected_termination_reason: TerminationReason | None


D = Decimal


def cfg(
    lower="80", upper="120", base="100", cells=4, lower_term="70", upper_term="130"
) -> NeutralGridConfig:
    return NeutralGridConfig(
        "linear",
        "BTCUSDT",
        D(lower),
        D(upper),
        D(base),
        cells,
        D("1"),
        QuantitySource.synthetic_explicit,
        D("1"),
        D("0.001"),
        D("0.002"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("10"),
        D(lower_term) if lower_term is not None else None,
        D(upper_term) if upper_term is not None else None,
    )


def p(seq: int, price: str, time: int | None = None) -> PriceEvent:
    return PriceEvent(seq, seq if time is None else time, D(price))


def f(seq: int, rate: str, mark="100", time: int | None = None) -> FundingEvent:
    return FundingEvent(seq, seq if time is None else time, D(mark), D(rate))


def m(seq: int, price: str, time: int | None = None) -> ManualTerminationAction:
    return ManualTerminationAction(seq, seq if time is None else time, D(price))


SCENARIO_IDS = (
    "01_initial_exact_base",
    "02_initial_between_levels",
    "03_low_price_initial",
    "04_tight_high_price_initial",
    "05_single_long_open",
    "06_single_short_open",
    "07_single_long_cycle",
    "08_single_short_cycle",
    "09_double_long_cycle_rearm",
    "10_double_short_cycle_rearm",
    "11_accumulate_two_long",
    "12_accumulate_two_short",
    "13_long_partial_rebound",
    "14_short_partial_rebound",
    "15_full_range_down_then_up",
    "16_full_range_up_then_down",
    "17_flat_positive_funding",
    "18_long_positive_funding",
    "19_short_positive_funding",
    "20_long_negative_funding",
    "21_short_negative_funding",
    "22_lower_termination_residual_long",
    "23_upper_termination_residual_short",
    "24_manual_flat_termination",
    "25_manual_long_termination",
    "26_manual_short_termination",
    "27_repeated_same_price_no_double_fill",
    "28_same_timestamp_price_then_funding",
    "29_same_timestamp_funding_then_price",
    "30_lower_only_termination_guardrail",
    "31_upper_only_termination_guardrail",
    "32_low_price_long_cycle",
    "33_tight_high_price_short_cycle",
)


def canonical_scenarios() -> tuple[ScenarioDefinition, ...]:
    exact = cfg(upper="125", base="100")
    low = cfg(lower="0.08", upper="0.12", base="0.10", lower_term="0.07", upper_term="0.13")
    tight = cfg(
        lower="9998", upper="10002", base="10000", cells=8, lower_term="9997", upper_term="10003"
    )
    rows = [
        (SCENARIO_IDS[0], exact, (), None),
        (SCENARIO_IDS[1], cfg(), (), None),
        (SCENARIO_IDS[2], low, (), None),
        (SCENARIO_IDS[3], tight, (), None),
        (SCENARIO_IDS[4], cfg(), (p(1, "90"),), None),
        (SCENARIO_IDS[5], cfg(), (p(1, "110"),), None),
        (SCENARIO_IDS[6], cfg(), (p(1, "80"), p(2, "100")), None),
        (SCENARIO_IDS[7], cfg(), (p(1, "120"), p(2, "100")), None),
        (SCENARIO_IDS[8], cfg(), (p(1, "80"), p(2, "100"), p(3, "80"), p(4, "100")), None),
        (SCENARIO_IDS[9], cfg(), (p(1, "120"), p(2, "100"), p(3, "120"), p(4, "100")), None),
        (SCENARIO_IDS[10], cfg(), (p(1, "80"),), None),
        (SCENARIO_IDS[11], cfg(), (p(1, "120"),), None),
        (SCENARIO_IDS[12], cfg(), (p(1, "80"), p(2, "90")), None),
        (SCENARIO_IDS[13], cfg(), (p(1, "120"), p(2, "110")), None),
        (SCENARIO_IDS[14], cfg(), (p(1, "80"), p(2, "120")), None),
        (SCENARIO_IDS[15], cfg(), (p(1, "120"), p(2, "80")), None),
        (SCENARIO_IDS[16], cfg(), (f(1, "0.01"),), None),
        (SCENARIO_IDS[17], cfg(), (p(1, "80"), f(2, "0.01")), None),
        (SCENARIO_IDS[18], cfg(), (p(1, "120"), f(2, "0.01")), None),
        (SCENARIO_IDS[19], cfg(), (p(1, "80"), f(2, "-0.01")), None),
        (SCENARIO_IDS[20], cfg(), (p(1, "120"), f(2, "-0.01")), None),
        (SCENARIO_IDS[21], cfg(), (p(1, "80"), p(2, "69")), TerminationReason.lower_boundary),
        (SCENARIO_IDS[22], cfg(), (p(1, "120"), p(2, "131")), TerminationReason.upper_boundary),
        (SCENARIO_IDS[23], cfg(), (m(1, "100"),), TerminationReason.explicit_manual_synthetic),
        (
            SCENARIO_IDS[24],
            cfg(),
            (p(1, "80"), m(2, "90")),
            TerminationReason.explicit_manual_synthetic,
        ),
        (
            SCENARIO_IDS[25],
            cfg(),
            (p(1, "120"), m(2, "110")),
            TerminationReason.explicit_manual_synthetic,
        ),
        (SCENARIO_IDS[26], cfg(), (p(1, "90"), p(2, "90"), p(3, "90")), None),
        (SCENARIO_IDS[27], cfg(), (p(1, "80", 10), f(2, "0.01", time=10)), None),
        (SCENARIO_IDS[28], cfg(), (f(1, "0.01", time=10), p(2, "80", 10)), None),
        (
            SCENARIO_IDS[29],
            cfg(lower_term="70", upper_term=None),
            (p(1, "69"),),
            TerminationReason.lower_boundary,
        ),
        (
            SCENARIO_IDS[30],
            cfg(lower_term=None, upper_term="130"),
            (p(1, "131"),),
            TerminationReason.upper_boundary,
        ),
        (SCENARIO_IDS[31], low, (p(1, "0.08"), p(2, "0.10")), None),
        (SCENARIO_IDS[32], tight, (p(1, "10002"), p(2, "10000")), None),
    ]
    return tuple(
        ScenarioDefinition(i, SCENARIO_VERSION, c, a, i.replace("_", " "), r) for i, c, a, r in rows
    )


def replay_scenario(s: ScenarioDefinition) -> SimulationResult:
    e = NeutralGridReferenceEngine(s.config)
    for a in s.actions:
        if isinstance(a, ManualTerminationAction):
            e.terminate_now(a.sequence_id, a.time_ms, a.trigger_price)
        else:
            e.process(a)
    return e.result()
