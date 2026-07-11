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

## Sprint 06.1A.1 hardening contract additions

### Strict input types
All reference-core runtime inputs use explicit validation in addition to type annotations. Decimal accounting inputs must be finite `Decimal` instances, never `int`, `float`, `str`, or `bool`. Sequence and time fields must be non-boolean integers greater than or equal to zero. Quantity source and liquidity roles must be their declared enums; plain strings are rejected rather than coerced.

### Result snapshot detachment
`SimulationResult` is a detached read snapshot. Active-order, all-order, ledger, completed-cycle, initialization-audit, and proof-flag containers returned to callers must not expose engine-owned mutable containers by reference. External mutation attempts must not mutate the engine or any later result snapshot.

### Independent ledger replay audit
The audit replays ledger rows from canonical zero accounting state instead of trusting cached result totals. It independently reconstructs signed position, weighted average entry, fill position effect, realized gross position PnL, trading fees, funding PnL, cumulative fields after every event, final average entry, and total-PnL identity. The `total_pnl_identity_recomputed_bool` flag is true only when the independent replay and identity checks pass.

### Funding-rate provenance in ledger
Funding ledger rows carry the source `funding_rate` used to compute funding PnL. The audit uses this explicit provenance and the pre-event position and mark price to recompute funding exactly; it does not infer the rate from cached funding amounts.

### Cycle reconciliation
Completed grid cycles are independently reconciled to their opening and closing grid-fill ledger rows. Cycle IDs and fill IDs must be unique, open and close fills must be opposite adjacent grid fills in ledger order with equal quantity, and gross/net/fee fields must recompute from ledger prices, quantities, and fees.

### Termination slippage diagnostic
Termination slippage cost is a diagnostic reconciliation field. It is not subtracted a second time from total PnL because adverse termination execution price already embeds the slippage effect in realized position PnL.

### Post-termination rejection
Both normal `process()` events and explicit `terminate_now()` events are rejected after termination. Rejected post-termination events must not mutate accepted sequence/time state, ledger rows, order state, position state, or termination summary, apart from the optional rejected-attempt counter.

### Proof-flag audit
Audit guardrails require all native-equivalence, native quantity mapping, native termination mapping, liquidation, OHLC replay, risk-budget, parameter-selection, profitability-claim, and live-execution readiness flags to remain false. The two-sided termination flag must exactly reflect whether both lower and upper termination prices are configured.

## Sprint 06.1A.2 canonical geometry and audit closure

Reference v1 preserves canonical Decimal geometric levels exactly as returned by `geometric_grid_levels_decimal(lower, upper, cell_number)`. It does not snap, round, tick-adjust, or otherwise move any level toward `base_price`; tick-size behavior is out of scope for a later sprint. Initialization places a buy below base, a sell above base, and no order only when a canonical level is exactly equal to base by Decimal equality.

Geometry validation fails closed: bounds and levels must be finite positive `Decimal` values, `cell_number` must be a non-boolean integer of at least two, and the supplied `N+1` levels must exactly match the canonical generated tuple. Arithmetic grids, duplicate levels, altered endpoints, altered interior levels, NaN, Infinity, non-Decimal prices, and bool/float cell counts are rejected.

The core audit verifies emitted-ledger accounting, canonical order provenance, active-order/all-order consistency, initialization evidence from activation-sequence-zero orders, termination trigger/fill reconciliation, exact proof-flag keys, exact initialization-audit keys, and false non-readiness flags. It does not prove full input-path completeness, native API equivalence, native quantity mapping, native termination mapping, liquidation behavior, OHLC replay, risk-budget suitability, parameter selection, profitability, or live execution. Therefore `event_path_completeness_proven_bool` and all other non-readiness flags remain false.
