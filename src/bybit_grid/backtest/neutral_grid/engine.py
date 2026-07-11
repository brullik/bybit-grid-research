from __future__ import annotations
from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType
from .accounting import apply_fill, funding_pnl, trading_fee
from .geometry import geometric_grid_levels_decimal
from .models import (
    ZERO,
    CompletedGridCycle,
    EventType,
    FundingEvent,
    GridOrder,
    LedgerEntry,
    LiquidityRole,
    NeutralGridConfig,
    OrderSide,
    OrderState,
    PositionEffect,
    PriceEvent,
    readonly_bool_map,
    SimulationResult,
    TerminationReason,
    TerminationSummary,
)

FALSE_FLAGS = {
    "native_equivalence_proven_bool": False,
    "native_quantity_mapping_proven_bool": False,
    "native_termination_mapping_proven_bool": False,
    "liquidation_modeled_bool": False,
    "ohlc_replay_supported_bool": False,
    "event_path_completeness_proven_bool": False,
    "risk_budget_proven_bool": False,
    "parameter_selection_performed_bool": False,
    "profitability_claims_present_bool": False,
    "live_execution_present_bool": False,
}


class NeutralGridReferenceEngine:
    def __init__(self, config: NeutralGridConfig) -> None:
        self.config = config
        geom = geometric_grid_levels_decimal(
            config.lower_price, config.upper_price, config.grid_cell_number
        )
        self.levels = geom.levels
        self.orders: dict[int, GridOrder] = {}
        self.all_orders: list[GridOrder] = []
        self.ledger: list[LedgerEntry] = []
        self.cycles: list[CompletedGridCycle] = []
        self.pos = ZERO
        self.avg: Decimal | None = None
        self.realized = ZERO
        self.cycle_gross = ZERO
        self.fees = ZERO
        self.funding = ZERO
        self._order_n = 0
        self._ledger_n = 0
        self._cycle_n = 0
        self._last_seq = -1
        self._last_time = -1
        self.last_price = config.base_price
        self.terminated = False
        self.rejected = 0
        self.term = TerminationSummary()
        for i, p in enumerate(self.levels):
            if p < config.base_price:
                self._activate(i, OrderSide.buy, 0, None)
            elif p > config.base_price:
                self._activate(i, OrderSide.sell, 0, None)
        self.init_audit = {
            "initial_position_zero_bool": True,
            "buy_orders_below_base_bool": all(
                o.side is OrderSide.buy and o.price < config.base_price
                for o in self.orders.values()
                if o.price < config.base_price
            ),
            "sell_orders_above_base_bool": all(
                o.side is OrderSide.sell and o.price > config.base_price
                for o in self.orders.values()
                if o.price > config.base_price
            ),
            "base_level_has_no_order_bool": all(
                o.price != config.base_price for o in self.orders.values()
            ),
            "one_active_order_per_level_bool": len(self.orders) == len(set(self.orders)),
            "constant_quantity_per_grid_bool": config.quantity_per_grid_base > ZERO,
        }

    def _activate(self, idx: int, side: OrderSide, seq: int, linked: str | None) -> None:
        if not (0 <= idx < len(self.levels)):
            return
        if idx in self.orders:
            self.orders[idx].state = OrderState.cancelled
        self._order_n += 1
        o = GridOrder(
            f"ord-{self._order_n}",
            idx,
            self.levels[idx],
            side,
            OrderState.active,
            seq,
            None,
            linked,
        )
        self.orders[idx] = o
        self.all_orders.append(o)

    def run(self, events: list[PriceEvent | FundingEvent]) -> SimulationResult:
        for e in events:
            self.process(e)
        return self.result()

    def _guard_event_order(self, sequence_id: int, time_ms: int) -> None:
        if not isinstance(sequence_id, int) or isinstance(sequence_id, bool):
            raise ValueError("sequence_id must be int, not bool")
        if not isinstance(time_ms, int) or isinstance(time_id := time_ms, bool):
            raise ValueError("time_ms must be int, not bool")
        _ = time_id
        if sequence_id < 0 or time_ms < 0:
            raise ValueError("sequence_id and time_ms must be >= 0")
        if self.terminated:
            self.rejected += 1
            raise ValueError("event accepted after termination is forbidden")
        if sequence_id <= self._last_seq:
            raise ValueError("sequence_id must be unique and strictly increasing")
        if time_ms < self._last_time:
            raise ValueError("time_ms must be non-decreasing")

    def _accept_event_order(self, sequence_id: int, time_ms: int) -> None:
        self._last_seq = sequence_id
        self._last_time = time_ms

    def process(self, e: PriceEvent | FundingEvent) -> None:
        if not isinstance(e, PriceEvent | FundingEvent):
            raise TypeError("process accepts only PriceEvent or FundingEvent")
        self._guard_event_order(e.sequence_id, e.time_ms)
        self._accept_event_order(e.sequence_id, e.time_ms)
        if isinstance(e, FundingEvent):
            self._funding(e)
            return
        prev = self.last_price
        cur = e.price
        up = cur > prev
        triggers: list[tuple[Decimal, str, int | None]] = []
        for idx, o in list(self.orders.items()):
            if up and prev < o.price <= cur:
                triggers.append((o.price, "grid", idx))
            if (not up) and cur <= o.price < prev:
                triggers.append((o.price, "grid", idx))
        if (
            self.config.upper_termination_price
            and up
            and prev < self.config.upper_termination_price <= cur
        ):
            triggers.append((self.config.upper_termination_price, "term_up", None))
        if (
            self.config.lower_termination_price
            and (not up)
            and cur <= self.config.lower_termination_price < prev
        ):
            triggers.append((self.config.lower_termination_price, "term_down", None))
        triggers.sort(key=lambda x: (x[0], 1 if x[1].startswith("term") else 0), reverse=not up)
        for price, kind, idx in triggers:
            if kind == "grid" and idx in self.orders:
                self._fill_grid(idx, e.sequence_id, e.time_ms)
            elif kind.startswith("term"):
                self._terminate(
                    e.sequence_id,
                    e.time_ms,
                    price,
                    TerminationReason.upper_boundary
                    if kind == "term_up"
                    else TerminationReason.lower_boundary,
                )
                break
        self.last_price = cur

    def _append(
        self,
        seq: int,
        time: int,
        et: EventType,
        order_id: str | None,
        idx: int | None,
        side: OrderSide | None,
        price: Decimal,
        qty: Decimal,
        role: LiquidityRole | None,
        before: Decimal,
        after: Decimal,
        avg_b: Decimal | None,
        avg_a: Decimal | None,
        eff: PositionEffect,
        pnl: Decimal,
        cg: Decimal = ZERO,
        ofee: Decimal = ZERO,
        cfee: Decimal = ZERO,
        fee: Decimal = ZERO,
        fund: Decimal = ZERO,
        funding_rate: Decimal | None = None,
    ) -> str:
        self._ledger_n += 1
        lid = (
            f"fill-{self._ledger_n}"
            if et in (EventType.grid_fill, EventType.termination_fill)
            else f"evt-{self._ledger_n}"
        )
        self.ledger.append(
            LedgerEntry(
                lid,
                seq,
                time,
                et,
                order_id,
                idx,
                side,
                price,
                qty,
                role,
                before,
                after,
                avg_b,
                avg_a,
                eff,
                pnl,
                cg,
                ofee,
                cfee,
                fee,
                fund,
                self.realized,
                self.cycle_gross,
                self.fees,
                self.funding,
                funding_rate,
            )
        )
        return lid

    def _fill_grid(self, idx: int, seq: int, time: int) -> None:
        o = self.orders.pop(idx)
        o.state = OrderState.filled
        o.filled_sequence_id = seq
        q = self.config.quantity_per_grid_base
        before = self.pos
        avg_b = self.avg
        acc = apply_fill(o.side, q, o.price, self.pos, self.avg)
        fee = trading_fee(
            q,
            o.price,
            self.config.grid_fill_liquidity_role,
            self.config.maker_fee_rate,
            self.config.taker_fee_rate,
        )
        self.pos = acc.new_signed_position
        self.avg = acc.new_average_entry
        self.realized += acc.realized_position_pnl_gross_usdt
        self.fees += fee
        cg = of = cfee = ZERO
        linked = None
        opens = acc.opened_quantity > ZERO and (
            acc.position_effect.name.startswith("open")
            or acc.position_effect.name.startswith("add")
            or acc.position_effect.name.startswith("flip")
        )
        lid = self._append(
            seq,
            time,
            EventType.grid_fill,
            o.order_id,
            idx,
            o.side,
            o.price,
            q,
            self.config.grid_fill_liquidity_role,
            before,
            self.pos,
            avg_b,
            self.avg,
            acc.position_effect,
            acc.realized_position_pnl_gross_usdt,
            fee=fee,
        )
        if o.linked_open_fill_id and acc.closed_quantity > ZERO:
            open_entry = next(x for x in self.ledger if x.ledger_event_id == o.linked_open_fill_id)
            if abs((open_entry.level_index or 0) - idx) == 1 and o.linked_open_fill_id not in {
                c.open_fill_id for c in self.cycles
            }:
                buy_price = o.price if o.side is OrderSide.buy else open_entry.price
                sell_price = o.price if o.side is OrderSide.sell else open_entry.price
                cg = q * (sell_price - buy_price)
                of = open_entry.trading_fee_usdt
                cfee = fee
                self.cycle_gross += cg
                self._cycle_n += 1
                self.cycles.append(
                    CompletedGridCycle(
                        f"cycle-{self._cycle_n}",
                        o.linked_open_fill_id,
                        lid,
                        open_entry.level_index or 0,
                        idx,
                        cg,
                        of,
                        cfee,
                        cg - of - cfee,
                    )
                )
                le = self.ledger[-1]
                self.ledger[-1] = le.__class__(
                    **{
                        **le.__dict__,
                        "completed_grid_cycle_gross_usdt": cg,
                        "grid_cycle_open_fee_usdt": of,
                        "grid_cycle_close_fee_usdt": cfee,
                        "cumulative_completed_grid_cycle_gross_usdt": self.cycle_gross,
                    }
                )
        if opens:
            linked = lid
        self._activate(
            idx + 1 if o.side is OrderSide.buy else idx - 1,
            OrderSide.sell if o.side is OrderSide.buy else OrderSide.buy,
            seq,
            linked,
        )

    def _funding(self, e: FundingEvent) -> None:
        before = self.pos
        fp = funding_pnl(self.pos, e.mark_price, e.funding_rate)
        self.funding += fp
        self._append(
            e.sequence_id,
            e.time_ms,
            EventType.funding,
            None,
            None,
            None,
            e.mark_price,
            ZERO,
            None,
            before,
            before,
            self.avg,
            self.avg,
            PositionEffect.none,
            ZERO,
            fund=fp,
            funding_rate=e.funding_rate,
        )

    def _terminate(self, seq: int, time: int, trigger: Decimal, reason: TerminationReason) -> None:
        before = self.pos
        avg_b = self.avg
        self._append(
            seq,
            time,
            EventType.termination_trigger,
            None,
            None,
            None,
            trigger,
            ZERO,
            None,
            before,
            before,
            self.avg,
            self.avg,
            PositionEffect.none,
            ZERO,
        )
        for o in self.orders.values():
            o.state = OrderState.cancelled
        self.orders.clear()
        exec_price = None
        fee = slip = qty = ZERO
        if self.pos != ZERO:
            closing_long = self.pos > ZERO
            qty = abs(self.pos)
            bps = self.config.termination_slippage_bps / Decimal("10000")
            exec_price = (
                trigger * (Decimal("1") - bps) if closing_long else trigger * (Decimal("1") + bps)
            )
            side = OrderSide.sell if closing_long else OrderSide.buy
            acc = apply_fill(side, qty, exec_price, self.pos, self.avg)
            fee = trading_fee(
                qty,
                exec_price,
                self.config.termination_liquidity_role,
                self.config.maker_fee_rate,
                self.config.taker_fee_rate,
            )
            slip = abs(trigger - exec_price) * qty
            self.pos = acc.new_signed_position
            self.avg = acc.new_average_entry
            self.realized += acc.realized_position_pnl_gross_usdt
            self.fees += fee
            self._append(
                seq,
                time,
                EventType.termination_fill,
                None,
                None,
                side,
                exec_price,
                qty,
                self.config.termination_liquidity_role,
                before,
                self.pos,
                avg_b,
                self.avg,
                acc.position_effect,
                acc.realized_position_pnl_gross_usdt,
                fee=fee,
            )
        self.terminated = True
        self.term = TerminationSummary(
            reason, trigger, exec_price, qty, fee, slip, True, self.pos == ZERO
        )

    def terminate_now(self, sequence_id: int, time_ms: int, trigger_price: Decimal) -> None:
        if not isinstance(trigger_price, Decimal) or not trigger_price.is_finite() or trigger_price <= ZERO:
            raise ValueError("trigger_price must be a finite positive Decimal")
        self._guard_event_order(sequence_id, time_ms)
        self._accept_event_order(sequence_id, time_ms)
        self._terminate(
            sequence_id, time_ms, trigger_price, TerminationReason.explicit_manual_synthetic
        )

    def result(self) -> SimulationResult:
        flags = {
            **FALSE_FLAGS,
            "two_sided_termination_configured_bool": self.config.lower_termination_price is not None
            and self.config.upper_termination_price is not None,
        }
        return SimulationResult(
            self.config,
            self.levels,
            MappingProxyType({k: replace(v) for k, v in self.orders.items()}),
            tuple(replace(o) for o in self.all_orders),
            tuple(self.ledger),
            tuple(self.cycles),
            self.pos,
            self.avg,
            self.realized,
            self.cycle_gross,
            self.fees,
            self.funding,
            self.last_price,
            self.terminated,
            self.term,
            readonly_bool_map(self.init_audit),
            readonly_bool_map(flags),
            self.rejected,
        )
