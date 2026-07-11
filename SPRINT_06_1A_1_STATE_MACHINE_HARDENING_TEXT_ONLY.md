# Sprint 06.1A.1 — State-Machine Hardening and Independent Ledger Audit

## PM decision

The Sprint 06.1A reference core is directionally accepted, but Gate 6A remains **HOLD** until this hardening sprint is complete.

This is one consolidated correctness sprint. Do not split it into separate micro-fixes. It closes the concrete defects found during independent PM review before any synthetic scenario pack, OHLC replay, risk-envelope work or parameter selection begins.

## Critical text-only repository rule

Codex may modify and commit text files only.

Allowed committed types:

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
.json generated artifacts
databases
images
binary fixtures
.env
market data
outcome/scoring data
generated reports
cache files
```

Do not create or upload a review-pack ZIP. Tests may use in-memory objects and pytest `tmp_path`, but no generated artifact is required in this sprint.

## Safety and scope

- No Bybit private API calls.
- No create/close/order/cancel/amend/position API implementation.
- No Telegram.
- No mainnet, testnet or demo calls.
- No `.env` or API keys.
- No historical OHLC replay.
- No native quantity derivation.
- No liquidation model.
- No risk-budget proof.
- No parameter search, ranking change or profitability claim.
- Do not modify Sprint 05 scoring, fees, grains or walk-forward results.
- Preserve every required proof/readiness flag as false.

## Independently reproduced defects

### D1 — `terminate_now()` accepts an event after termination

Current behavior permits:

```python
engine.terminate_now(1, 1, Decimal("100"))
engine.terminate_now(2, 2, Decimal("100"))  # currently accepted
```

This violates the contract that no event is accepted after termination.

### D2 — `SimulationResult` aliases mutable engine state

A result snapshot currently shares mutable `GridOrder` objects and the `all_orders` list with the running engine. Processing another event mutates an earlier result. Clearing `result.all_orders` can also clear the engine's internal order history.

A result must be a detached snapshot. External mutation of a returned result must never mutate the engine or a later result.

### D3 — The audit does not independently replay accounting

The current audit sums selected cached ledger fields, but it does not independently rebuild:

```text
signed position
weighted average entry
position effect
realized PnL per fill
fee per fill
funding per event
cumulative fields after every event
final average entry
completed-cycle totals
```

Consequently, a tampered `SimulationResult.average_entry` or `cumulative_completed_grid_cycle_gross_usdt` can still pass the audit. The Total-PnL identity is currently partly tautological because both sides use the same cached result methods.

### D4 — Strict runtime type validation is incomplete

Examples currently accepted:

```python
grid_fill_liquidity_role="maker"  # plain string
PriceEvent(sequence_id=1.5, ...)
PriceEvent(sequence_id=True, ...)
PriceEvent(time_ms=-1, ...)
```

A plain string role can silently route through the taker branch because `selected_fee_rate()` treats every non-maker enum value as taker.

### D5 — Manual trigger input is not fully validated

`terminate_now()` must reject non-Decimal, non-finite and non-positive trigger prices and must enforce the same sequence/time contract as normal events.

## Task 1 — Strict validation helpers

Update `models.py` and `accounting.py` with explicit runtime validation. Type annotations alone are insufficient.

### NeutralGridConfig

Require:

```text
category is exactly str "linear"
symbol is str and symbol.strip() is non-empty
grid_cell_number is int but not bool, and >= 2
quantity_source is QuantitySource
grid_fill_liquidity_role is LiquidityRole
termination_liquidity_role is LiquidityRole
all accounting numerics are finite Decimal, never int/float/string/bool
0 < lower < base < upper
quantity > 0
leverage > 0
fees/slippage >= 0
lower termination < lower when present
upper termination > upper when present
```

Do not silently strip/coerce invalid values. Reject them.

### PriceEvent and FundingEvent

Require:

```text
sequence_id is int, not bool, and >= 0
time_ms is int, not bool, and >= 0
price/mark_price/funding_rate are finite Decimal
price/mark_price > 0
```

### Accounting functions

`selected_fee_rate()` must explicitly handle:

```text
LiquidityRole.maker
LiquidityRole.taker
```

and raise for anything else. Do not use an unconditional `else -> taker` fallback.

`apply_fill()`, `trading_fee()` and `funding_pnl()` must reject invalid numeric types/non-finite values and inconsistent position state, including:

```text
nonzero position with average_entry=None
flat position with non-None average_entry
average_entry <= 0 when present
quantity <= 0
price/mark_price <= 0
negative fee rates
```

Funding rate may be positive, zero or negative but must be finite Decimal.

## Task 2 — Make all termination paths fail closed

Create one shared event-order guard used by both `process()` and `terminate_now()`.

Requirements:

```text
already terminated -> reject without mutating sequence/time/ledger/state
sequence_id must be strictly increasing
same sequence ID rejected
decreasing sequence ID rejected
time_ms must be non-decreasing
trigger_price must be finite positive Decimal
```

After a rejected event, all engine state except an optional rejected-attempt counter must remain unchanged.

Add tests for:

```text
second terminate_now rejected
process after terminate_now rejected
terminate_now after boundary termination rejected
bad manual trigger type/NaN/infinity/zero/negative rejected
rejected termination leaves ledger and termination summary unchanged
```

## Task 3 — Return detached result snapshots

`result()` must return a snapshot that does not alias engine-owned mutable structures.

At minimum detach:

```text
active_orders and GridOrder values
all_orders and GridOrder values
ledger container
completed_cycles container
initialization_audit
proof_flags
```

Preferred public snapshot shape:

```text
active_orders: read-only mapping or detached dict
all_orders: tuple
ledger: tuple
completed_cycles: tuple
initialization_audit: read-only mapping or detached dict
proof_flags: read-only mapping or detached dict
```

A fully frozen snapshot model is acceptable. Internal engine order objects may remain mutable, but they must never be exposed by reference.

Required tests:

1. Capture `r1 = engine.result()`.
2. Process another event.
3. Prove `r1` did not change.
4. Mutate any mutable container in `r1` when the API permits it.
5. Prove engine state and `r2 = engine.result()` did not change.

If public containers become immutable, assert mutation raises instead.

## Task 4 — Implement independent ledger replay audit

Refactor `audit_simulation_result()` so it independently replays the ledger from a canonical zero state instead of trusting result caches.

Replay state:

```text
position = 0
average_entry = None
realized_position_pnl_gross = 0
trading_fees = 0
funding_pnl = 0
completed_grid_cycle_gross = 0
```

For every ledger event, verify all applicable fields.

### Grid fill / termination fill

Recompute using the accounting helper:

```text
signed_position_before
average_entry_before
closed/opened quantity effect
position_effect
realized_position_pnl_gross_usdt
signed_position_after
average_entry_after
liquidity role
trading_fee_usdt
```

Expected liquidity role:

```text
grid_fill -> config.grid_fill_liquidity_role
termination_fill -> config.termination_liquidity_role
```

### Funding event

Verify:

```text
quantity == 0
side is None
position and average entry unchanged
funding_pnl == -position_before * mark_price * funding_rate
```

The current LedgerEntry does not carry funding rate. Add the minimum explicit immutable source field required to replay funding exactly, for example:

```text
funding_rate: Decimal | None
```

Do not infer it from the resulting amount.

### Termination trigger

Verify no position, average-entry, fee, realized-PnL or funding mutation.

### Every ledger row

Verify cumulative fields equal the independently accumulated totals immediately after that event.

### Final result

Verify independently replayed values equal:

```text
result.signed_position
result.average_entry
result.cumulative_realized_position_pnl_gross_usdt
result.cumulative_trading_fees_usdt
result.cumulative_funding_pnl_usdt
```

For open results, independently compute unrealized PnL from replayed position/average entry and the supplied positive finite Decimal mark.

For terminated results, independently prove the final position is flat and unrealized PnL is zero.

Set `total_pnl_identity_recomputed_bool=true` only when the independent replay and identity checks actually pass. Otherwise it must be false.

## Task 5 — Independently audit completed grid cycles

For every `CompletedGridCycle`, verify:

```text
cycle_id unique
open_fill_id unique across cycles
close_fill_id unique across cycles
open and close entries exist
both are grid_fill events
open and close sides are opposite
level indices are adjacent
open occurs before close in ledger order
quantity is exactly equal on both fills
cycle gross recomputed from prices and quantity
open fee equals opening ledger fee
close fee equals closing ledger fee
cycle net == gross - open fee - close fee
matching close ledger cycle fields agree
```

Verify:

```text
sum(cycle.gross_usdt) == result.cumulative_completed_grid_cycle_gross_usdt
sum(ledger completed_grid_cycle_gross_usdt) == same total
```

The audit must reject tampering of cycle gross, fee, net, IDs, ordering or cached cumulative cycle totals.

## Task 6 — Audit order state and result guardrails

Audit at minimum:

```text
all order_id values unique
active-order mapping key == order.level_index
active order state == active
active order price == result.levels[level_index]
active level within bounds
at most one active order per level
all_orders contains every active order exactly once
filled orders have filled_sequence_id
active/cancelled orders have no impossible filled state
terminated result has no active orders
termination summary says all orders cancelled and position flat
termination fill count is 0 when residual quantity is zero, otherwise exactly 1
termination fee/slippage summary reconciles to termination fill and trigger
```

Do not subtract `termination_slippage_cost_usdt` a second time from Total PnL. The adverse execution price already embeds that cost. Document this explicitly in the contract.

Audit exact proof/readiness guardrails:

```text
native_equivalence_proven_bool == false
native_quantity_mapping_proven_bool == false
native_termination_mapping_proven_bool == false
liquidation_modeled_bool == false
ohlc_replay_supported_bool == false
risk_budget_proven_bool == false
parameter_selection_performed_bool == false
profitability_claims_present_bool == false
live_execution_present_bool == false
two_sided_termination_configured_bool matches config
```

Recompute and verify initialization-audit booleans rather than trusting their cached values.

## Task 7 — Geometry closure

Validate every one of the N adjacent ratios, including the final interval ending at the exact upper endpoint.

Requirements:

```text
N+1 levels
exact lower/upper endpoints
strict increase
all N ratios agree with the stored ratio within an explicit high-precision Decimal tolerance
ratio_tolerance is actually used by validation/tests
```

Do not add tick rounding.

## Task 8 — Expand the semantic contract

Update:

```text
docs/native_neutral_grid_reference_contract_v1.md
```

Add explicit sections for:

```text
strict input types
result snapshot detachment
independent ledger replay audit
funding-rate provenance in ledger
cycle reconciliation
termination slippage diagnostic (not double-subtracted)
post-termination rejection for process and terminate_now
proof-flag audit
```

Preserve the reference-only and non-profitability posture.

## Task 9 — Regression tests

Extend the focused test file or add:

```text
tests/test_sprint_06_1a_1_state_machine_hardening.py
```

At minimum include separate tests for:

1. Plain-string maker/taker role rejected.
2. Non-enum quantity source rejected.
3. Float/int/string accounting values rejected where Decimal is required.
4. Bool/fractional/negative sequence ID rejected.
5. Negative/non-int time rejected.
6. Invalid average-entry state rejected.
7. `selected_fee_rate()` has no fallback.
8. Second `terminate_now()` rejected.
9. `terminate_now()` after boundary termination rejected.
10. Invalid manual trigger prices rejected.
11. Rejected event leaves state unchanged.
12. Earlier result snapshot is unchanged after later processing.
13. External result-container mutation cannot mutate engine.
14. Tampered result average entry fails audit.
15. Tampered per-ledger before/after position fails audit.
16. Tampered per-ledger average entry fails audit.
17. Tampered position effect fails audit.
18. Tampered fill fee fails audit.
19. Tampered funding rate or funding PnL fails audit.
20. Tampered cumulative ledger fields fail audit.
21. Tampered final fee/funding/realized totals fail audit.
22. Tampered cycle gross/net/fee/IDs fail audit.
23. Tampered cached cumulative cycle gross fails audit.
24. Tampered proof flag fails audit.
25. Tampered initialization flag fails audit.
26. Tampered termination summary fails audit.
27. All N geometry ratios, including the last, pass tolerance.
28. A deliberately altered final level ratio fails geometry validation/audit.
29. Existing valid long/short/funding/termination scenarios still pass.
30. No live/private API surface is introduced.

Use `dataclasses.replace()` and detached copies to build deliberate tamper fixtures. Do not mutate the engine as part of an audit test unless the test is specifically for snapshot isolation.

## Required commands in the Codex environment

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_1a_neutral_grid_state_machine.py -q
python -m pytest tests/test_sprint_06_1a_1_state_machine_hardening.py -q
python -m pytest -q
ruff check .
git diff --check
git status --short
```

If the new tests are added to the existing focused file instead, replace the second focused command with the actual path and report it precisely.

## Acceptance criteria

```text
all existing tests pass
all 06.1A and 06.1A.1 tests pass
ruff passes
no-live audit passes
only text files changed
no binary/generated artifacts committed
strict enum/int/Decimal validation implemented
selected_fee_rate has no implicit fallback
all termination entry points reject post-termination events
result snapshots do not alias engine state
ledger audit independently replays position and average entry
funding is replayable from explicit ledger provenance
all cumulative fields reconcile after every event
cycle accounting independently reconciles
termination summary independently reconciles
all required proof flags are audited false
all N geometry ratios are validated
native equivalence remains unproven
risk budget remains unproven
no parameter selection or profitability claim
```

## Required Codex return — text only

Return exactly:

```text
commit hash
changed text files
git diff --stat
full pytest output
06.1A focused test output
06.1A.1 focused test output
ruff output
no-live audit output
numeric environment output
pip check output
git diff --check output
git status --short output
strict-validation summary
snapshot-isolation summary
independent-ledger-replay summary
cycle-audit summary
termination-guard summary
adversarial tamper-test summary
all proof/readiness flag values
known remaining native-equivalence unknowns
```

Do not ask Codex to create, commit or upload ZIP, Parquet, CSV, JSON reports or any other binary/generated artifact.
