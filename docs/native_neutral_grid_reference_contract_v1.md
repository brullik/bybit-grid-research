# Native Neutral Grid Reference Contract v1

Sprint 06.1A defines a deterministic **reference** state machine for synthetic, explicitly ordered events. It proves no native equivalence: native quantity mapping, termination mapping, liquidation behavior, API behavior, OHLC replay, risk budget, parameter selection, live execution, and profitability remain unproven and out of scope.

The reference starts neutral at `base_price` with zero signed position, no average entry, zero realized PnL, zero fees, and zero funding PnL. A geometric grid uses N cells and N+1 boundary levels with ratio `exp(ln(upper/lower)/N)`. Levels below base have buy orders, levels above base have sell orders, and a level exactly at base has no order.

After a buy fill at level `i`, the filled buy is removed and one sell at `i+1` is activated or replaces the existing effective order. After a sell fill at `i`, one buy at `i-1` is activated or replaces the existing effective order. There is one effective active order per level. Replacement links to an open fill only when that fill opened exposure in its own direction.

The signed one-way convention is long `> 0`, short `< 0`, flat `== 0`; buy deltas are positive and sell deltas are negative. Weighted-average accounting distinguishes position realized PnL from diagnostic grid-cycle profit. Grid-cycle profit is completed adjacent open/close pair gross and net of the two fill fees. Position realized PnL is generated only by closing exposure. Unrealized PnL marks the residual position. Trading fees are charged once per fill. Funding PnL is `-signed_position_qty * mark_price * funding_rate`. Total PnL equals realized position gross minus trading fees plus funding plus unrealized PnL.

Events are consumed in submitted order and must have strictly increasing unique `sequence_id`; `time_ms` is non-decreasing. Same timestamps are allowed and funding ordering follows `sequence_id`.

For a price segment, upward crossings process triggers in ascending price order using `previous_price < trigger_price <= current_price`; downward crossings process descending order using `current_price <= trigger_price < previous_price`. This open-start/closed-end policy prevents boundary double fills. If grid and termination triggers share a price, grid fills have deterministic priority at that price, while termination never skips earlier triggers along the path. No OHLC interpolation is supported.

Lower and upper termination prices are abstract risk-termination boundaries. On trigger, the reference records a trigger, cancels active orders, closes the full residual position with configured termination liquidity and adverse slippage, charges at most one termination close fee, and ends flat. A flat termination does not invent a close fee. The upper boundary is not named a profit target. Liquidation is unsupported.

Leverage affects margin and liquidation mechanics, but for a fixed linear-contract quantity it does not multiply raw PnL or trading fees: PnL is quantity times price difference and fee is quantity times fill price times fee rate.

No Sprint 06.1A result is a profitability claim because it uses synthetic explicit events, no historical parameter selection, no OHLC replay, no native calibration, no liquidation model, and all proof/readiness flags remain false.
