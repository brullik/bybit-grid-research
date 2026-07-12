from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from decimal import Decimal as D
from enum import Enum

from bybit_grid.backtest.neutral_grid.models import LiquidityRole, NeutralGridConfig, QuantitySource

from .models import (
    CandleSource,
    FundingMarkPriceSource,
    FundingObservation,
    FundingRateSource,
    MinimalPathPolicy,
    OhlcCandle1m,
)

OHLC_REPLAY_CONTRACT_VERSION = "ohlc_minimal_path_replay_contract_v2"
SCENARIO_VERSION = "ohlc_minimal_path_scenarios_v2"
RUN_ID = "ohlc_minimal_v2_synthetic"
REVIEW_PACK_SCHEMA_VERSION = "ohlc_minimal_path_review_pack_v2_semantic_replay"
MANIFEST_HASH_POLICY = "self_excluded_v1"
EVIDENCE_TYPE_CONTRACT_VERSION = "strict_json_type_identity_v1"
CANONICAL_SERIALIZATION_VERSION = "neutral_grid_canonical_json_v1"
REVIEW_PHASE = "ohlc_synthetic_evidence_complete"
DEFAULT_PACK = "pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic.zip"
CANONICAL_SCENARIO_COUNT = 24

GUARDRAILS = {
    "native_equivalence_proven_bool": False,
    "native_quantity_mapping_proven_bool": False,
    "native_termination_mapping_proven_bool": False,
    "liquidation_modeled_bool": False,
    "real_bybit_batch_integration_proven_bool": False,
    "funding_coverage_proven_bool": False,
    "full_intrabar_path_reconstructed_bool": False,
    "arbitrary_intrabar_oscillation_bounded_bool": False,
    "global_true_worst_case_proven_bool": False,
    "global_true_best_case_proven_bool": False,
    "risk_budget_proven_bool": False,
    "sufficient_for_parameter_selection_bool": False,
    "parameter_selection_authorized_bool": False,
    "profitability_claims_present_bool": False,
    "live_execution_present_bool": False,
    "live_authorized_bool": False,
    "sufficient_for_bybit_batch_integration_bool": False,
}

SCENARIO_IDS = (
    "01_flat_no_ambiguity",
    "02_open_equals_high_duplicate_node",
    "03_low_equals_close_duplicate_node",
    "04_single_candle_path_insensitive",
    "05_single_candle_path_sensitive_long",
    "06_single_candle_path_sensitive_short",
    "07_equal_pnl_different_nested_ledger",
    "08_two_candle_four_assignments",
    "09_gap_up_preserved",
    "10_gap_down_preserved",
    "11_low_price_grid",
    "12_tight_high_price_grid",
    "13_positive_funding_long",
    "14_positive_funding_short",
    "15_negative_funding_long",
    "16_flat_position_funding_zero",
    "17_two_funding_boundaries",
    "18_lower_termination_first_candle",
    "19_upper_termination_first_candle",
    "20_termination_ignores_later_candles",
    "21_cycle_count_envelope_one_to_two",
    "22_bybit_source_enum_contract",
    "23_lower_only_termination_guardrail",
    "24_upper_only_termination_guardrail",
)


class ScenarioMode(Enum):
    fixed_replay = "fixed_replay"
    ambiguity_envelope = "ambiguity_envelope"


@dataclass(frozen=True)
class OhlcReplayScenario:
    scenario_id: str
    scenario_version: str
    mode: ScenarioMode
    config: NeutralGridConfig
    entry_time_ms: int
    candles: tuple[OhlcCandle1m, ...]
    funding_observations: tuple[FundingObservation, ...]
    path_policies: tuple[MinimalPathPolicy, ...] | None
    max_exact_ambiguous_candles: int | None
    expected: MappingProxyType

    def __post_init__(self) -> None:
        from bybit_grid.backtest.neutral_grid.serialization import canonical_json_bytes

        if type(self.scenario_id) is not str or self.scenario_id.strip() == "" or self.scenario_id != self.scenario_id.strip():
            raise ValueError("scenario_id must be stripped non-empty str")
        if type(self.scenario_version) is not str:
            raise ValueError("scenario_version must be exact str")
        if type(self.mode) is not ScenarioMode:
            raise ValueError("mode must be ScenarioMode")
        if type(self.config) is not NeutralGridConfig:
            raise ValueError("config must be exact NeutralGridConfig")
        if type(self.entry_time_ms) is not int or isinstance(self.entry_time_ms, bool):
            raise ValueError("entry_time_ms must be exact int")
        if type(self.candles) is not tuple or any(type(x) is not OhlcCandle1m for x in self.candles):
            raise ValueError("candles must be tuple of exact OhlcCandle1m")
        if type(self.funding_observations) is not tuple or any(type(x) is not FundingObservation for x in self.funding_observations):
            raise ValueError("funding_observations must be tuple of exact FundingObservation")
        if self.mode is ScenarioMode.fixed_replay:
            if type(self.path_policies) is not tuple or len(self.path_policies) != len(self.candles) or any(type(x) is not MinimalPathPolicy for x in self.path_policies):
                raise ValueError("fixed_replay requires exact path policy tuple per candle")
            if self.max_exact_ambiguous_candles is not None:
                raise ValueError("fixed_replay cap must be None")
        elif self.mode is ScenarioMode.ambiguity_envelope:
            if self.path_policies is not None:
                raise ValueError("ambiguity_envelope path policies must be None")
            if type(self.max_exact_ambiguous_candles) is not int or isinstance(self.max_exact_ambiguous_candles, bool) or self.max_exact_ambiguous_candles < 0:
                raise ValueError("ambiguity_envelope cap must be exact non-negative int")
        if type(self.expected) is not MappingProxyType:
            raise ValueError("expected must be immutable MappingProxyType")
        canonical_json_bytes(dict(self.expected))


def cfg(
    sym="BTCUSDT", low="90", high="110", base="100", cells=4, qty="0.01", lo_term=None, hi_term=None
):
    return NeutralGridConfig(
        "linear",
        sym,
        D(low),
        D(high),
        D(base),
        cells,
        D(qty),
        QuantitySource.synthetic_explicit,
        D("1"),
        D("0.0001"),
        D("0.0002"),
        LiquidityRole.maker,
        LiquidityRole.taker,
        D("5"),
        D(lo_term) if lo_term else None,
        D(hi_term) if hi_term else None,
    )


def c(t, o="100", h="105", low="95", cl="100", sym="BTCUSDT", source=CandleSource.synthetic_1m):
    return OhlcCandle1m("linear", sym, t, D(o), D(h), D(low), D(cl), True, source)


def f(
    t,
    rate="0.001",
    mark="100",
    sym="BTCUSDT",
    rs=FundingRateSource.synthetic,
    ms=FundingMarkPriceSource.synthetic,
):
    return FundingObservation("linear", sym, t, D(rate), D(mark), rs, ms)


def fixed(
    i, candles, pol=MinimalPathPolicy.open_high_low_close, *, config=None, funding=(), expected=None
):
    ps = (pol,) * len(candles) if isinstance(pol, MinimalPathPolicy) else tuple(pol)
    return OhlcReplayScenario(
        SCENARIO_IDS[i - 1],
        SCENARIO_VERSION,
        ScenarioMode.fixed_replay,
        config or cfg(),
        60000,
        tuple(candles),
        tuple(funding),
        ps,
        None,
        MappingProxyType({**GUARDRAILS, **(expected or {})}),
    )


def env(i, candles, *, config=None, funding=(), cap=12, expected=None):
    return OhlcReplayScenario(
        SCENARIO_IDS[i - 1],
        SCENARIO_VERSION,
        ScenarioMode.ambiguity_envelope,
        config or cfg(),
        60000,
        tuple(candles),
        tuple(funding),
        None,
        cap,
        MappingProxyType({**GUARDRAILS, **(expected or {})}),
    )


def build_scenario_catalog() -> tuple[OhlcReplayScenario, ...]:
    return (
        fixed(1, (c(60000, "100", "100", "100", "100"),)),
        fixed(2, (c(60000, "105", "105", "95", "100"),)),
        fixed(3, (c(60000, "100", "105", "95", "95"),)),
        env(4, (c(60000, "100", "102", "98", "100"),), expected={"path_sensitive_bool": False, "exact_assignment_count": 2}),
        env(5, (c(60000, "92", "96", "90", "92"),), expected={"path_sensitive_bool": True}),
        env(6, (c(60000, "100", "110", "100", "110"),), expected={"path_sensitive_bool": True}),
        env(
            7,
            (c(60000, "94", "96", "82", "92"),),
            config=cfg(low="80", high="120", base="100", cells=6, qty="0.01"),
            expected={"equal_top_level_pnl_different_nested_ledger_bool": True},
        ),
        env(
            8,
            (c(60000, "100", "108", "92", "100"), c(120000, "100", "108", "92", "100")),
            expected={"exact_assignment_count": 4},
        ),
        fixed(9, (c(60000, "100", "103", "97", "102"), c(120000, "106", "108", "104", "107"))),
        fixed(10, (c(60000, "100", "103", "97", "98"), c(120000, "94", "96", "92", "93"))),
        fixed(
            11,
            (c(60000, "0.010", "0.011", "0.009", "0.010"),),
            config=cfg(low="0.008", high="0.012", base="0.010", qty="10"),
        ),
        fixed(
            12,
            (c(60000, "50000", "50010", "49990", "50000"),),
            config=cfg(low="49900", high="50100", base="50000", cells=20, qty="0.001"),
        ),
        fixed(13, (c(60000, "100", "100", "98", "98"), c(120000, "98", "98", "98", "98")), funding=(f(120000, "0.001", "98"),), expected={"funding_pnl_sign": "negative"}),
        fixed(14, (c(60000, "100", "106", "100", "106"), c(120000, "106", "106", "106", "106")), pol=MinimalPathPolicy.open_low_high_close, funding=(f(120000, "0.001", "106"),), expected={"funding_pnl_sign": "positive"}),
        fixed(15, (c(60000, "100", "100", "98", "98"), c(120000, "98", "98", "98", "98")), funding=(f(120000, "-0.001", "98"),), expected={"funding_pnl_sign": "positive"}),
        fixed(
            16,
            (c(60000, "100", "100", "100", "100"), c(120000, "100", "100", "100", "100")),
            funding=(f(120000, "0.001"),),
        ),
        fixed(
            17, (c(60000, "100", "100", "98", "98"), c(120000, "98", "106", "98", "106"), c(180000, "106", "106", "106", "106")), funding=(f(120000, "0.001", "98"), f(180000, "-0.001", "106"))
        ),
        fixed(18, (c(60000, "100", "105", "80", "90"),), config=cfg(lo_term="85")),
        fixed(19, (c(60000, "100", "120", "95", "110"),), config=cfg(hi_term="115")),
        fixed(
            20,
            (c(60000, "100", "120", "80", "90"), c(120000)),
            config=cfg(lo_term="85", hi_term="115"),
        ),
        env(
            21,
            (c(60000, "98", "115", "96", "107.4"),),
            config=cfg(low="80", high="120", base="100", cells=6, qty="0.01"),
            expected={"completed_cycle_count_min": 1, "completed_cycle_count_max": 2},
        ),
        fixed(
            22,
            (
                c(60000, source=CandleSource.bybit_trade_kline_1m),
                c(120000, source=CandleSource.bybit_trade_kline_1m),
            ),
            funding=(
                f(
                    120000,
                    rs=FundingRateSource.bybit_funding_history,
                    ms=FundingMarkPriceSource.bybit_mark_price_kline_1m,
                ),
            ),
            expected={"synthetic_fixture_of_source_contract_bool": True},
        ),
        fixed(23, (c(60000, "100", "105", "80", "90"),), config=cfg(lo_term="85")),
        fixed(24, (c(60000, "100", "120", "95", "110"),), config=cfg(hi_term="115")),
    )


SCENARIO_CATALOG = build_scenario_catalog()
