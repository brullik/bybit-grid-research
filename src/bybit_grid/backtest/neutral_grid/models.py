from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

ZERO = Decimal("0")


class OrderSide(Enum):
    buy = "buy"
    sell = "sell"


class OrderState(Enum):
    active = "active"
    filled = "filled"
    cancelled = "cancelled"


class LiquidityRole(Enum):
    maker = "maker"
    taker = "taker"


class PositionEffect(Enum):
    open_long = "open_long"
    add_long = "add_long"
    close_long = "close_long"
    open_short = "open_short"
    add_short = "add_short"
    close_short = "close_short"
    flip_long_to_short = "flip_long_to_short"
    flip_short_to_long = "flip_short_to_long"
    none = "none"


class EventType(Enum):
    initialization = "initialization"
    grid_fill = "grid_fill"
    funding = "funding"
    termination_trigger = "termination_trigger"
    termination_fill = "termination_fill"


class TerminationReason(Enum):
    lower_boundary = "lower_boundary"
    upper_boundary = "upper_boundary"
    explicit_manual_synthetic = "explicit_manual_synthetic"


class QuantitySource(Enum):
    synthetic_explicit = "synthetic_explicit"
    observed_native_detail = "observed_native_detail"
    validated_formula = "validated_formula"
    unproven_derived = "unproven_derived"


def _finite_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")


@dataclass(frozen=True)
class NeutralGridConfig:
    category: str
    symbol: str
    lower_price: Decimal
    upper_price: Decimal
    base_price: Decimal
    grid_cell_number: int
    quantity_per_grid_base: Decimal
    quantity_source: QuantitySource
    leverage: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    grid_fill_liquidity_role: LiquidityRole
    termination_liquidity_role: LiquidityRole
    termination_slippage_bps: Decimal
    lower_termination_price: Decimal | None
    upper_termination_price: Decimal | None

    def __post_init__(self) -> None:
        if self.category != "linear":
            raise ValueError("category must be linear")
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        for n in (
            "lower_price",
            "upper_price",
            "base_price",
            "quantity_per_grid_base",
            "leverage",
            "maker_fee_rate",
            "taker_fee_rate",
            "termination_slippage_bps",
        ):
            _finite_decimal(getattr(self, n), n)
        if not (ZERO < self.lower_price < self.base_price < self.upper_price):
            raise ValueError("requires 0 < lower_price < base_price < upper_price")
        if self.grid_cell_number < 2:
            raise ValueError("grid_cell_number must be >= 2")
        if self.quantity_per_grid_base <= ZERO or self.leverage <= ZERO:
            raise ValueError("quantity_per_grid_base and leverage must be > 0")
        if (
            self.maker_fee_rate < ZERO
            or self.taker_fee_rate < ZERO
            or self.termination_slippage_bps < ZERO
        ):
            raise ValueError("fee rates and slippage must be non-negative")
        if self.lower_termination_price is not None:
            _finite_decimal(self.lower_termination_price, "lower_termination_price")
            if self.lower_termination_price >= self.lower_price:
                raise ValueError("lower termination must be below lower_price")
        if self.upper_termination_price is not None:
            _finite_decimal(self.upper_termination_price, "upper_termination_price")
            if self.upper_termination_price <= self.upper_price:
                raise ValueError("upper termination must be above upper_price")


@dataclass(frozen=True)
class PriceEvent:
    sequence_id: int
    time_ms: int
    price: Decimal

    def __post_init__(self) -> None:
        _finite_decimal(self.price, "price")
        if self.price <= ZERO:
            raise ValueError("price must be positive")


@dataclass(frozen=True)
class FundingEvent:
    sequence_id: int
    time_ms: int
    mark_price: Decimal
    funding_rate: Decimal

    def __post_init__(self) -> None:
        _finite_decimal(self.mark_price, "mark_price")
        _finite_decimal(self.funding_rate, "funding_rate")
        if self.mark_price <= ZERO:
            raise ValueError("mark_price must be positive")


@dataclass
class GridOrder:
    order_id: str
    level_index: int
    price: Decimal
    side: OrderSide
    state: OrderState
    activation_sequence_id: int
    filled_sequence_id: int | None = None
    linked_open_fill_id: str | None = None


@dataclass(frozen=True)
class LedgerEntry:
    ledger_event_id: str
    sequence_id: int
    time_ms: int
    event_type: EventType
    order_id: str | None
    level_index: int | None
    side: OrderSide | None
    price: Decimal
    quantity_base: Decimal
    liquidity_role: LiquidityRole | None
    signed_position_before: Decimal
    signed_position_after: Decimal
    average_entry_before: Decimal | None
    average_entry_after: Decimal | None
    position_effect: PositionEffect
    realized_position_pnl_gross_usdt: Decimal
    completed_grid_cycle_gross_usdt: Decimal
    grid_cycle_open_fee_usdt: Decimal
    grid_cycle_close_fee_usdt: Decimal
    trading_fee_usdt: Decimal
    funding_pnl_usdt: Decimal
    cumulative_realized_position_pnl_gross_usdt: Decimal
    cumulative_completed_grid_cycle_gross_usdt: Decimal
    cumulative_trading_fees_usdt: Decimal
    cumulative_funding_pnl_usdt: Decimal


@dataclass(frozen=True)
class CompletedGridCycle:
    cycle_id: str
    open_fill_id: str
    close_fill_id: str
    open_level_index: int
    close_level_index: int
    gross_usdt: Decimal
    open_fee_usdt: Decimal
    close_fee_usdt: Decimal
    net_usdt: Decimal


@dataclass(frozen=True)
class TerminationSummary:
    termination_reason: TerminationReason | None = None
    termination_trigger_price: Decimal | None = None
    termination_execution_price: Decimal | None = None
    residual_quantity_closed: Decimal = ZERO
    termination_trading_fee_usdt: Decimal = ZERO
    termination_slippage_cost_usdt: Decimal = ZERO
    all_orders_cancelled_bool: bool = False
    position_flat_after_termination_bool: bool = False


@dataclass(frozen=True)
class SimulationResult:
    config: NeutralGridConfig
    levels: tuple[Decimal, ...]
    active_orders: dict[int, GridOrder]
    all_orders: list[GridOrder]
    ledger: list[LedgerEntry]
    completed_cycles: list[CompletedGridCycle]
    signed_position: Decimal
    average_entry: Decimal | None
    cumulative_realized_position_pnl_gross_usdt: Decimal
    cumulative_completed_grid_cycle_gross_usdt: Decimal
    cumulative_trading_fees_usdt: Decimal
    cumulative_funding_pnl_usdt: Decimal
    last_price: Decimal
    terminated_bool: bool
    termination: TerminationSummary
    initialization_audit: dict[str, bool]
    proof_flags: dict[str, bool]
    events_rejected_after_termination_count: int = 0
    geometry_rounding_applied_bool: bool = False

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        _finite_decimal(mark_price, "mark_price")
        if self.signed_position == ZERO or self.average_entry is None:
            return ZERO
        if self.signed_position > ZERO:
            return self.signed_position * (mark_price - self.average_entry)
        return abs(self.signed_position) * (self.average_entry - mark_price)

    def realized_net_pnl(self) -> Decimal:
        return (
            self.cumulative_realized_position_pnl_gross_usdt
            - self.cumulative_trading_fees_usdt
            + self.cumulative_funding_pnl_usdt
        )

    def total_pnl(self, mark_price: Decimal) -> Decimal:
        return self.realized_net_pnl() + self.unrealized_pnl(mark_price)
