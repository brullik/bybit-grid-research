# Sprint 06.1A.2 — Canonical Geometry and Audit Closure

## PM decision

Sprint 06.1A.1 materially improved the reference engine, but Gate 6A remains **HOLD**. Independent adversarial review found four blocking correctness defects that are not covered by the current 206-test suite:

1. the engine alters canonical geometric levels with an absolute `Decimal("3")` base-price snap;
2. the geometry validator accepts materially non-geometric levels;
3. a valid intermediate engine state can fail its own audit because initialization is re-derived from the current order book;
4. termination/order/event provenance tampering is not fully rejected, and `process()` accepts duck-typed non-event objects.

This is the final reference-core closure before Sprint 06.1B. Fix all listed defects in one text-only commit. Do not implement scenario packs, OHLC replay, parameter selection, risk proof, native API calls, or live execution.

## Text-only and safety rules

Codex may modify or add only source, test, and Markdown files.

Do not create, modify, upload, or commit:

```text
*.zip
*.parquet
*.csv
*.duckdb
*.db
*.sqlite
*.pickle
*.npy
*.npz
*.png
*.pdf
.env
market data
review packs
generated run artifacts
```

Also prohibited:

```text
Bybit private API calls
order/grid create or close
position mutation outside the synthetic reference engine
Telegram
OHLC replay
liquidation claims
quantity calibration
parameter optimization
profitability/EV/ROI claims
risk_budget_proven_bool=true
native_equivalence_proven_bool=true
```

Preserve all existing non-readiness guardrails.

## Reproduced defects

### Defect A — arbitrary base-price snapping changes the grid

For:

```text
lower=80
upper=120
base=100
N=4
```

canonical geometric levels include approximately:

```text
80
88.534553576...
97.979589711...
108.432240433...
120
```

The current engine replaces `97.979589711...` with `100` because it is within an absolute distance of `3`. This mutates the canonical geometry while the audit still accepts it.

For a low-priced instrument:

```text
lower=0.08
upper=0.12
base=0.10
N=4
```

all five levels currently collapse to `0.10`, leaving zero active grid orders.

### Defect B — geometry validation is too permissive

The current validator accepts:

```python
(Decimal("80"), Decimal("90"), Decimal("100"), Decimal("110"), Decimal("120"))
```

as a geometric 4-cell grid between 80 and 120 because `ratio_tolerance=0.03` is too large and absolute.

### Defect C — valid intermediate state fails audit

After a monotonic move that fills two lower buy levels, linked close sells legitimately exist below `base_price`. The audit recomputes initialization flags from the **current** active order book and reports:

```text
initialization flag buy_orders_below_base_bool mismatch
```

Initialization evidence must be checked against initial orders, not current replacement orders.

### Defect D — incomplete provenance/type rejection

The current audit accepts at least these tampered results:

```text
termination_reason changed from lower_boundary to upper_boundary
termination-trigger ledger price changed independently of the summary
ledger sequence_id/time_ms changed
ledger order_id changed to a nonexistent order
all_orders price/side/activation sequence changed
extra proof flag with value true
```

The engine also accepts an arbitrary duck-typed object with `sequence_id`, `time_ms`, and `price` as though it were a `PriceEvent`.

## Task 1 — Preserve canonical geometric levels exactly

In `NeutralGridReferenceEngine.__init__`:

```text
self.levels must be the canonical levels returned by geometric_grid_levels_decimal()
```

Remove every absolute/relative base-price snap. Do not replace a nearby level with `base_price`.

Initialization rule:

```text
level < base_price  -> BUY
level > base_price  -> SELL
level == base_price -> no order
```

Equality is exact Decimal equality in reference v1. Tick-size rounding belongs to a future sprint.

Required invariants:

```text
levels[0] == lower_price
levels[-1] == upper_price
len(levels) == N + 1
strictly increasing
engine levels == canonical geometry levels
geometry_rounding_applied_bool == false
```

Add regression tests for:

1. `80 / 120 / base 100 / N=4` — no level is replaced by 100;
2. `0.08 / 0.12 / base 0.10 / N=4` — five increasing levels and nonempty order book;
3. a high-priced tight range, for example `9998 / 10002 / base 10000 / N=8`;
4. a case where base is exactly a canonical level — that exact level has no order;
5. a case where base lies between levels — no level is moved to base.

## Task 2 — Make geometry validation fail closed

Update `geometric_grid_levels_decimal()` and `validate_grid_geometry()`.

Strict input requirements:

```text
lower and upper are finite Decimal values
0 < lower < upper
cell_number is int, not bool
cell_number >= 2
levels is a tuple of finite positive Decimal values
```

Reference v1 applies no tick rounding. Therefore the validator must compare all `N+1` levels to the canonical generated levels using either:

```text
exact equality
```

or a documented extremely tight Decimal relative/absolute tolerance suitable only for deterministic Decimal serialization. A tolerance such as `0.03` is prohibited.

It must reject:

```python
(Decimal("80"), Decimal("90"), Decimal("100"), Decimal("110"), Decimal("120"))
```

for the 80–120, N=4 geometric grid.

Also reject NaN, Infinity, float/int price inputs, bool/float cell counts, duplicate levels, altered endpoints, and any altered interior level outside the documented tiny tolerance.

## Task 3 — Complete strict config validation

Keep existing strict enum/Decimal validation and add:

```text
lower_termination_price, when present, is finite and > 0
lower_termination_price < lower_price
upper_termination_price, when present, is finite and > upper_price
0 <= termination_slippage_bps < 10000
```

The `< 10000` rule prevents a non-positive adverse execution price when closing a long position.

Invalid config construction must raise `ValueError` before the engine is created.

## Task 4 — Reject noncanonical event objects before state mutation

`process()` must accept only:

```text
PriceEvent
FundingEvent
```

Do not accept duck-typed objects. A wrong object type must raise `ValueError` or `TypeError` before changing:

```text
_last_seq
_last_time
last_price
orders/all_orders
ledger/cycles
position/average entry
fees/funding/realized totals
termination state
```

`terminate_now()` must retain the same fail-closed behavior for invalid sequence, time, trigger price, order, and post-termination calls.

Add a snapshot helper in tests to prove state is unchanged after every invalid input.

## Task 5 — Audit initialization from initial-order evidence

Do not derive initialization semantics from the current active order book.

Use the canonical levels plus orders whose `activation_sequence_id == 0` to independently verify the initial book.

Require exactly one initial order for every canonical level except a level exactly equal to base:

```text
below base -> BUY
above base -> SELL
at base    -> absent
```

Require:

```text
unique initial order IDs
unique initial level indices
correct level_index/price/side
state may later be active, filled, or cancelled
constant configured quantity per grid
initialization_audit exact key set and boolean values
```

A valid audit must continue to pass:

```text
at initialization
after one fill
after multiple same-direction fills
after a reversal
after funding
after termination
```

## Task 6 — Strengthen ledger and order provenance reconciliation

The auditor must continue replaying Decimal accounting independently and additionally validate metadata/provenance.

### Ledger ordering

Require:

```text
ledger_event_id unique
sequence_id is non-negative int, not bool
time_ms is non-negative int, not bool
ledger sequence_id is non-decreasing
ledger time_ms is non-decreasing
rows sharing one sequence_id share one time_ms
sequence groups are strictly increasing
```

Multiple ledger rows may share one accepted event sequence, for example termination trigger plus termination fill.

### Grid-fill provenance

For every `grid_fill` ledger row require:

```text
order_id exists in all_orders
referenced order state == filled
order filled_sequence_id == ledger sequence_id
order level_index == ledger level_index
order price == ledger price == levels[level_index]
order side == ledger side
quantity_base == config.quantity_per_grid_base
liquidity_role == config.grid_fill_liquidity_role
```

Every filled grid order must map to exactly one grid-fill ledger row. No grid-fill row may reference a missing order.

### all_orders/current active-order consistency

Require every order to have:

```text
unique non-empty order_id
valid level_index
price == levels[level_index]
OrderSide enum
OrderState enum
non-negative integer activation_sequence_id
filled state iff filled_sequence_id is present
activation_sequence_id <= filled_sequence_id when filled
```

For each active-order mapping entry, compare the full snapshot fields to the corresponding `all_orders` item, not only its ID.

Validate linked open-fill IDs when present:

```text
refer to an earlier grid fill
opposite side
adjacent level
correct order/fill chronology
not reused by multiple completed cycles
```

### Event-type field contracts

Require exact zero/None semantics for funding and termination-trigger rows. Reject stray order IDs, sides, quantities, liquidity roles, fees, funding, realized PnL, cycle fields, or position mutations where the event type does not permit them.

## Task 7 — Strengthen termination reconciliation

For a terminated result require exactly one termination-trigger ledger row.

Reconcile:

```text
summary trigger price == trigger ledger price
summary reason == actual trigger type
lower_boundary -> configured lower boundary exists and equals trigger price
upper_boundary -> configured upper boundary exists and equals trigger price
explicit_manual_synthetic -> positive explicit trigger
```

For residual exposure:

```text
exactly one termination_fill
side closes the pre-fill signed position
quantity equals absolute residual position
execution price equals adverse-slippage formula
fee equals configured termination fee formula
slippage diagnostic equals abs(trigger - execution) * quantity
result ends flat with average_entry=None
```

For flat termination:

```text
no termination_fill
zero residual quantity
zero termination fee
zero slippage diagnostic
```

For a nonterminated result require zero termination-trigger and zero termination-fill ledger rows and an empty/default termination summary.

Add explicit tamper tests for reason, trigger ledger price, summary trigger, execution price, side, residual quantity, fee, slippage, and trigger/fill counts.

## Task 8 — Exact proof/readiness and audit metadata contracts

Require the proof flag key set to be exact, with no missing or extra keys.

All existing native/risk/selection/profitability/live flags remain false. The two-sided flag must exactly match config.

Add and preserve this explicit false flag if it does not already exist:

```text
event_path_completeness_proven_bool = false
```

Reason: the current core audit proves emitted-ledger accounting and order provenance, but full input-path completeness will be proven in Sprint 06.1B by persisting scenario inputs and replaying them.

Require:

```text
geometry_rounding_applied_bool == false
events_rejected_after_termination_count is int, not bool, and >= 0
initialization_audit exact key set
proof_flags exact key set
```

Update the reference contract to state precisely what the core audit does and does not prove.

## Task 9 — Required regression tests

Add a new focused file:

```text
tests/test_sprint_06_1a_2_canonical_geometry_and_audit_closure.py
```

At minimum cover:

1. canonical levels are not snapped to base;
2. low-price grid does not collapse;
3. tight high-price grid does not collapse;
4. exact-base-level order absence;
5. base-between-levels leaves levels unchanged;
6. arithmetic/non-geometric levels rejected;
7. altered interior level rejected;
8. NaN/Infinity/wrong geometry types rejected;
9. invalid lower termination rejected;
10. slippage `>=10000` rejected;
11. duck-typed event rejected without state mutation;
12. audit passes after every prefix of a multi-fill valid path;
13. audit passes with valid linked sells below base and linked buys above base;
14. ledger sequence/time tamper rejected;
15. missing ledger order ID rejected;
16. all_orders price/side/activation tamper rejected;
17. active-order/all-order mismatch rejected;
18. termination reason tamper rejected;
19. termination-trigger ledger price tamper rejected;
20. termination execution/side/fee/slippage tamper rejected;
21. extra/missing proof flag rejected;
22. negative/bool rejected-event counter rejected;
23. geometry_rounding_applied_bool=true rejected;
24. existing 06.1A and 06.1A.1 tests remain green;
25. no live/private API/Telegram/binary additions.

Include a deterministic prefix-audit matrix over at least these paths:

```text
base -> lower internal levels -> partial rebound
base -> upper internal levels -> partial rebound
multiple full adjacent cycles
funding between fills
lower termination
upper termination
flat manual termination
```

Every valid prefix must audit successfully.

## Task 10 — Do not overclaim

After this sprint the following must still be false:

```text
native_equivalence_proven_bool
native_quantity_mapping_proven_bool
native_termination_mapping_proven_bool
liquidation_modeled_bool
ohlc_replay_supported_bool
event_path_completeness_proven_bool
risk_budget_proven_bool
parameter_selection_performed_bool
profitability_claims_present_bool
live_execution_present_bool
```

Sprint 06.1A.2 closes reference-core geometry and accounting audit correctness only.

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_1a_neutral_grid_state_machine.py -q
python -m pytest tests/test_sprint_06_1a_1_state_machine_hardening.py -q
python -m pytest tests/test_sprint_06_1a_2_canonical_geometry_and_audit_closure.py -q
python -m pytest -q
ruff check .
git diff --check
git status --short
```

Codex must not generate a ZIP or any binary artifact.

## Acceptance criteria

```text
all tests pass
ruff passes
no-live audit passes
canonical engine levels exactly match canonical geometry
no base-price snapping exists
low-price and tight-range grids remain strictly increasing
non-geometric tuple is rejected
valid intermediate states audit successfully
wrong event object is rejected without mutation
ledger/order provenance tampering is rejected
termination reason/trigger/fill tampering is rejected
proof/init flag key sets are exact
no binaries or generated artifacts added
all non-readiness flags remain false
```

## Required text return to PM

Return only text containing:

```text
commit hash
changed text files
git diff --stat
full pytest output
06.1A focused output
06.1A.1 focused output
06.1A.2 focused output
ruff output
no-live audit output
numeric environment output
pip check output
git diff --check output
git status --short output
canonical-geometry fix summary
low-price/tight-range test summary
initialization-audit fix summary
ledger/order provenance summary
termination reconciliation summary
event-type fail-closed summary
proof/readiness flag values
known remaining native-equivalence unknowns
```
