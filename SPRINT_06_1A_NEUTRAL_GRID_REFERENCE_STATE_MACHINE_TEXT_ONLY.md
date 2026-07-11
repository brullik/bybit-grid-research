# Sprint 06.1A — Neutral Grid Reference State Machine Core

## PM authorization

Gate 5A is closed. The current scoring run is sufficient for state-machine engineering only.

This sprint implements a deterministic reference accounting engine for a Bybit-style Neutral Geometric Futures Grid Bot on explicitly ordered synthetic events.

It does **not** perform historical parameter selection, OHLC replay, native API calibration, liquidation modeling, live trading or profitability analysis.

## Critical repository-output rule

Codex must modify and commit **text source files only**.

Allowed committed file types:

```text
.py
.md
.toml only if strictly necessary
```

Forbidden repository changes:

```text
.zip
.parquet
.csv
database files
images
binary fixtures
.env
market data
outcome data
scoring data
generated reports
cache files
```

Do not generate or upload a review-pack ZIP in this sprint. Do not add generated artifacts to Git. Tests may create temporary files only inside pytest `tmp_path`, but this sprint should be implementable with pure in-memory tests and should not require temporary binary files.

Return to PM must be text only.

## Safety rules

- No Bybit private API calls.
- No `/v5/fgridbot/create` or `/v5/fgridbot/close` implementation.
- No ordinary order create/cancel/amend implementation.
- No position mutation API.
- No Telegram implementation.
- No mainnet/testnet/demo calls.
- No API keys or `.env` access.
- No parameter search or optimization.
- No modification of Sprint 05 scores, cost weights, fee snapshot, grains or walk-forward splits.
- Preserve `risk_budget_proven_bool=false`.
- Preserve `sufficient_for_parameter_selection_bool=false`.
- Preserve all existing tests.

## Why this sprint exists

The current Sprint 05 score is an ex-post ranking proxy. It does not account for the actual sequence of grid fills, one-way position netting, residual exposure, termination close, funding on the signed position path or total PnL.

Before any claim about EV, PnL or a 5 USDT loss cap, the project needs an auditable state machine.

## Reference-semantic posture

Use the word **reference**, not **native-equivalent**, throughout the implementation.

Required false flags in every final result:

```text
native_equivalence_proven_bool = false
native_quantity_mapping_proven_bool = false
native_termination_mapping_proven_bool = false
liquidation_modeled_bool = false
ohlc_replay_supported_bool = false
risk_budget_proven_bool = false
parameter_selection_performed_bool = false
profitability_claims_present_bool = false
live_execution_present_bool = false
```

## Two-sided termination correction

The user originally requested “close only by SL”. For a neutral grid, that is not sufficient to prove a bounded loss:

- a downward move may accumulate long exposure;
- an upward move may accumulate short exposure.

The reference model must therefore support abstract boundaries:

```text
lower_termination_price
upper_termination_price
```

Do not name the upper boundary a profit target inside the engine. It is an upper risk-termination boundary.

Potential future native mappings are outside this sprint:

```text
lower boundary -> native stop-loss candidate
upper boundary -> native TP-as-termination candidate or monitored close fallback
```

No native mapping is proven in Sprint 06.1A.

A one-sided configuration is allowed only as a diagnostic scenario and must report:

```text
two_sided_termination_configured_bool = false
risk_budget_proven_bool = false
```

## Existing code to preserve and reuse

Do not rewrite or fork Sprint 04 geometry semantics incompatibly.

Existing canonical helper:

```text
src/bybit_grid/research/outcome_core/grid_crossings.py
  geometric_grid_levels(low, high, cell_number)
```

Existing semantics:

```text
N grid cells -> N + 1 boundary prices
ratio = (upper / lower) ** (1 / N)
grid_count_semantics = native_bybit_cell_number
```

The new Decimal geometry implementation must be cross-tested against the existing helper within an explicit tolerance. Do not change the old helper in this sprint unless a failing regression proves a defect and PM scope is updated.

Do not delete the existing placeholder:

```text
src/bybit_grid/backtest/grid_simulator.py
```

## Required files

Create:

```text
docs/native_neutral_grid_reference_contract_v1.md

src/bybit_grid/backtest/neutral_grid/__init__.py
src/bybit_grid/backtest/neutral_grid/models.py
src/bybit_grid/backtest/neutral_grid/geometry.py
src/bybit_grid/backtest/neutral_grid/accounting.py
src/bybit_grid/backtest/neutral_grid/engine.py
src/bybit_grid/backtest/neutral_grid/audit.py

tests/test_sprint_06_1a_neutral_grid_state_machine.py
```

Small adjustments to existing text source files are allowed only when required for imports or safety checks.

## Task 1 — Versioned semantic contract

Write:

```text
docs/native_neutral_grid_reference_contract_v1.md
```

It must explicitly define:

1. Reference scope and all unproven native assumptions.
2. Neutral initialization with zero position.
3. Geometric levels and N-cell/N+1-level semantics.
4. Buy orders below base and sell orders above base.
5. Dynamic adjacent replacement after a fill.
6. One-way signed-position convention.
7. The distinction between:
   - grid-cycle profit;
   - position realized PnL;
   - unrealized PnL;
   - trading fees;
   - funding PnL;
   - total PnL.
8. Exact segment crossing boundaries.
9. Event ordering by `sequence_id`.
10. Funding ordering when timestamps match.
11. Lower/upper termination and residual-position close.
12. Unsupported OHLC ambiguity, liquidation and native quantity derivation.
13. Why leverage affects margin/liquidation but not the raw linear-contract PnL amount for a fixed quantity.
14. Why no result from this sprint is a profitability claim.

## Task 2 — Decimal-only accounting models

Use `decimal.Decimal` for all prices, quantities, fee rates, funding rates and PnL values.

No float is allowed inside accounting state or ledger records. Floats may appear only in compatibility tests against the existing NumPy geometry helper.

Create strict enums/dataclasses at minimum:

### Enums

```text
OrderSide: buy, sell
OrderState: active, filled, cancelled
LiquidityRole: maker, taker
PositionEffect: open_long, add_long, close_long, open_short, add_short, close_short, flip_long_to_short, flip_short_to_long, none
EventType: initialization, grid_fill, funding, termination_trigger, termination_fill
TerminationReason: lower_boundary, upper_boundary, explicit_manual_synthetic
QuantitySource: synthetic_explicit, observed_native_detail, validated_formula, unproven_derived
```

### NeutralGridConfig

Required fields:

```text
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
```

Validation:

```text
category == "linear"
symbol is non-empty
0 < lower_price < base_price < upper_price
grid_cell_number >= 2
quantity_per_grid_base > 0
leverage > 0
fee rates are finite and non-negative
slippage is finite and non-negative
lower termination, when provided, is below lower_price
upper termination, when provided, is above upper_price
```

Do not derive quantity from investment in this sprint.

### Ordered events

```text
PriceEvent:
  sequence_id: int
  time_ms: int
  price: Decimal

FundingEvent:
  sequence_id: int
  time_ms: int
  mark_price: Decimal
  funding_rate: Decimal
```

Rules:

```text
sequence_id must be unique and strictly increasing in submitted order
time_ms must be non-decreasing
same time_ms is allowed; sequence_id determines order
all numeric values must be finite
price and mark_price must be positive
```

### GridOrder

Required state:

```text
order_id
level_index
price
side
state
activation_sequence_id
filled_sequence_id
linked_open_fill_id | None
```

At most one active effective grid order may exist at one level.

### LedgerEntry

Include at minimum:

```text
ledger_event_id
sequence_id
time_ms
event_type
order_id | None
level_index | None
side | None
price
quantity_base
liquidity_role | None
signed_position_before
signed_position_after
average_entry_before
average_entry_after
position_effect
realized_position_pnl_gross_usdt
completed_grid_cycle_gross_usdt
grid_cycle_open_fee_usdt
grid_cycle_close_fee_usdt
trading_fee_usdt
funding_pnl_usdt
cumulative_realized_position_pnl_gross_usdt
cumulative_completed_grid_cycle_gross_usdt
cumulative_trading_fees_usdt
cumulative_funding_pnl_usdt
```

## Task 3 — Geometric grid

Implement Decimal geometry with high precision:

```text
level_count = N + 1
ratio = exp(ln(upper/lower) / N)
```

Requirements:

- first level exactly equals lower;
- last level exactly equals upper;
- N+1 levels;
- strictly increasing;
- equal ratios within documented Decimal tolerance;
- levels are not tick-rounded in Sprint 06.1A;
- output carries `geometry_rounding_applied_bool=false`;
- cross-test against the existing NumPy helper.

## Task 4 — Neutral initialization

Engine starts at `base_price` with:

```text
signed_position = 0
average_entry = None
realized position PnL = 0
fees = 0
funding PnL = 0
```

Initial effective order book:

```text
level < base_price  -> one BUY order
level > base_price  -> one SELL order
level == base_price -> no order
```

Initialization audit must expose:

```text
initial_position_zero_bool
buy_orders_below_base_bool
sell_orders_above_base_bool
base_level_has_no_order_bool
one_active_order_per_level_bool
constant_quantity_per_grid_bool
```

## Task 5 — Exact path-crossing policy

The engine consumes an explicitly ordered sequence of price events.

For a segment from `previous_price` to `current_price`:

### Upward

Process crossed triggers in ascending price order using:

```text
previous_price < trigger_price <= current_price
```

### Downward

Process crossed triggers in descending price order using:

```text
current_price <= trigger_price < previous_price
```

This open-start/closed-end rule prevents double filling at a segment boundary.

If several triggers share the same price, use deterministic priority documented in the contract. Termination priority must not skip grid fills that occur earlier along the actual segment path. Once termination fires, no later trigger in that segment is processed.

No OHLC interpolation is allowed in this sprint.

## Task 6 — Dynamic adjacent order replacement

Use one effective order per level.

After a BUY at level `i` fills:

```text
remove the filled BUY at i
activate or replace with one SELL at i + 1
```

After a SELL at level `i` fills:

```text
remove the filled SELL at i
activate or replace with one BUY at i - 1
```

Boundary-safe behavior is required.

Do not create duplicate quantity at a level just because an order already existed there. Replace/reclassify the effective order deterministically.

A replacement order may carry `linked_open_fill_id` only when the fill created exposure in its own direction. When the fill only closed opposite exposure, the re-armed order is unlinked and will open exposure if later filled.

## Task 7 — One-way position accounting

Signed quantity convention:

```text
long > 0
short < 0
flat == 0
BUY delta = +quantity
SELL delta = -quantity
```

Implement weighted-average one-way accounting.

A fill may:

- add to the current side;
- partially or fully close the opposite side;
- flip through zero if fill quantity exceeds the opposite position.

The accounting function must return:

```text
closed_quantity
opened_quantity
position_effect
realized_position_pnl_gross_usdt
new_signed_position
new_average_entry
```

Linear USDT formulas:

```text
closing long with sell:
  pnl = closed_qty * (sell_price - average_long_entry)

closing short with buy:
  pnl = closed_qty * (average_short_entry - buy_price)
```

A fixed quantity fill pays one trading fee exactly once:

```text
fee = fill_quantity * fill_price * selected_fee_rate
```

No leverage multiplier is applied to raw PnL or trading fee.

## Task 8 — Adjacent grid-cycle tracker

Track completed adjacent cycles separately from position accounting.

Normal cycle examples:

```text
BUY at level i opens long exposure
SELL at level i+1 closes the linked exposure

SELL at level i opens short exposure
BUY at level i-1 closes the linked exposure
```

For a linked completed cycle:

```text
long cycle gross = qty * (sell_price - buy_price)
short cycle gross = qty * (sell_price - buy_price)
cycle net = gross - opening fill fee - closing fill fee
```

Requirements:

- one open fill can complete at most one cycle;
- one close fill can complete at most one cycle;
- no fill is counted twice;
- a completed cycle must be adjacent by level index;
- a cycle stores both fill IDs;
- re-arming permits a later new cycle at the same two levels;
- cumulative grid-cycle profit is diagnostic and must not be substituted for Total PnL.

If a fill closes position but has no valid linked adjacent open fill, it affects position PnL but does not create a completed grid cycle.

## Task 9 — Funding accounting

At a FundingEvent, apply funding to the signed position that exists immediately before that event in sequence order:

```text
funding_pnl_usdt = -signed_position_qty * mark_price * funding_rate
```

Therefore, for positive funding:

```text
long pays
short receives
flat pays/receives zero
```

Funding does not change position quantity or average entry.

## Task 10 — Unrealized and total PnL identities

At any mark price:

```text
long unrealized = qty * (mark - average_entry)
short unrealized = abs(qty) * (average_entry - mark)
flat unrealized = 0
```

Required identity:

```text
realized_net_pnl =
    cumulative_realized_position_pnl_gross
  - cumulative_trading_fees
  + cumulative_funding_pnl

total_pnl = realized_net_pnl + unrealized_pnl
```

Expose an audit that recomputes the identity from the ledger rather than trusting cached totals.

## Task 11 — Termination

Treat termination boundaries as triggers on the explicit price path.

When a boundary is reached in path order:

1. Record termination trigger.
2. Stop processing later triggers.
3. Cancel every remaining active grid order.
4. Close the full residual signed position.
5. Use the configured termination fee role.
6. Apply adverse slippage:

```text
closing long by SELL:
  execution_price = trigger_price * (1 - slippage_bps / 10000)

closing short by BUY:
  execution_price = trigger_price * (1 + slippage_bps / 10000)
```

7. Charge the termination fill fee once.
8. End flat.
9. Reject all subsequent events.

If already flat, termination must not invent a fill fee.

Expose:

```text
termination_reason
termination_trigger_price
termination_execution_price | None
residual_quantity_closed
termination_trading_fee_usdt
termination_slippage_cost_usdt
all_orders_cancelled_bool
position_flat_after_termination_bool
```

No liquidation logic is allowed in this sprint.

## Task 12 — Invariant audit

Implement an audit function that fails closed on at least:

```text
duplicate ledger_event_id
duplicate fill ID
duplicate completed-cycle pairing
more than one active order at a level
active order with invalid side for its level/state
position quantity not reconciled to fill deltas
fee total not reconciled to fill fees
funding total not reconciled to funding events
realized PnL not reconciled to accounting events
total PnL identity mismatch
terminated result not flat
active orders remaining after termination
event accepted after termination
non-Decimal accounting values
```

Audit output is an in-memory dataclass/dict in this sprint. Do not write generated audit JSON to the repository.

## Task 13 — Required tests

Create a single focused test file with small synthetic paths. At minimum cover:

1. N cells produce N+1 levels.
2. Decimal geometry is strictly increasing and endpoint exact.
3. Decimal geometry agrees with existing NumPy helper within tolerance.
4. Neutral initialization starts flat.
5. Buys are below base; sells are above base.
6. No order exists exactly at base.
7. Quantity per grid is constant.
8. One BUY fill opens a long.
9. Adjacent SELL closes that long and completes one cycle.
10. One SELL fill opens a short.
11. Adjacent BUY closes that short and completes one cycle.
12. Long-cycle gross and net fee math are exact.
13. Short-cycle gross and net fee math are exact.
14. Trading fee is charged once per fill.
15. Multiple downward fills accumulate long quantity.
16. Multiple upward fills accumulate short quantity.
17. A reversal closes exposure without double-counting fills.
18. A re-armed level can complete a second cycle.
19. Multi-level upward crossing processes low-to-high.
20. Multi-level downward crossing processes high-to-low.
21. Segment boundary does not fill the same order twice.
22. Duplicate sequence IDs are rejected.
23. Decreasing sequence IDs are rejected.
24. Decreasing timestamps are rejected.
25. Same timestamp with increasing sequence IDs is accepted.
26. Positive funding charges long.
27. Positive funding credits short.
28. Funding while flat is zero.
29. Funding ordering follows sequence ID at the same timestamp.
30. Lower termination closes residual long and ends flat.
31. Upper termination closes residual short and ends flat.
32. Termination fee/slippage is applied exactly once.
33. Flat termination charges no synthetic close fee.
34. All orders are cancelled after termination.
35. Events after termination are rejected.
36. Realized-net and total-PnL identities reconcile.
37. One-sided termination reports no two-sided bound.
38. All proof/readiness flags remain false as required.
39. No live/private API implementation is introduced.
40. Full existing test suite remains green.

Use explicit Decimal strings in expected values. Do not weaken exact assertions into broad floating tolerances.

## Task 14 — Code quality

- Type hints on public functions.
- No monolithic module.
- No hidden global mutable state.
- Stable deterministic IDs derived from simulation-local counters or canonical input fields.
- Helpful exceptions with context.
- No silent coercion of invalid strings, NaN or infinity.
- No swallowed exceptions.
- No network access in tests.
- Keep Ruff clean.

## Required commands

Run:

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_1a_neutral_grid_state_machine.py -q
python -m pytest -q
ruff check .
git diff --check
git status --short
```

## Acceptance criteria

```text
all existing tests pass
all Sprint 06.1A tests pass
ruff passes
no-live audit passes
only text source/test/documentation files changed
no generated or binary files committed
reference contract is versioned
Decimal accounting only
N cells -> N+1 levels
initial signed position = 0
one effective active order per level
adjacent order replacement is deterministic
one-way position accounting reconciles
grid cycles cannot double count fills
fees are charged exactly once per fill
funding sign and ordering are correct
lower and upper termination are supported
terminated simulations end flat
ledger/accounting audit passes
native_equivalence_proven_bool = false
native_quantity_mapping_proven_bool = false
native_termination_mapping_proven_bool = false
liquidation_modeled_bool = false
ohlc_replay_supported_bool = false
risk_budget_proven_bool = false
parameter_selection_performed_bool = false
profitability_claims_present_bool = false
live_execution_present_bool = false
```

## Required Codex return — text only

Return:

```text
commit hash
changed text files
git diff --stat
full pytest output
focused Sprint 06.1A test output
ruff output
no-live audit output
git diff --check output
git status --short output
state-machine semantic summary
initial order-book summary
one-way position-accounting summary
adjacent-cycle pairing summary
funding accounting summary
termination accounting summary
invariant audit summary
all proof/readiness flag values
known native-equivalence unknowns
```

Do not upload, create or commit ZIP, Parquet, CSV, database, image or other binary files.
