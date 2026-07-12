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

## Sprint 06.1B sequence-zero and synthetic evidence contract

`activation_sequence_id = 0` is reserved exclusively for initialization orders created by the reference engine constructor. All external `PriceEvent`, `FundingEvent`, and explicit manual synthetic termination inputs must provide `sequence_id >= 1`; zero is rejected and is never silently coerced.

The public audit boundary fails closed for malformed result snapshots. It returns a failed audit result rather than allowing expected tamper classes such as malformed order IDs, invalid level indices, bad enum values, invalid Decimal values, malformed termination fields, bad cycle references, or unexpected ledger structures to traceback.

The synthetic scenario evidence catalog is deterministic and input-event complete for the packaged 33 canonical synthetic scenarios only. This separate pack-level evidence does not change standalone result proof flags: `event_path_completeness_proven_bool`, native equivalence, native quantity mapping, native termination mapping, liquidation modeling, OHLC replay support, risk-budget proof, parameter-selection authorization, profitability claims, and live-execution flags remain false.

## Sprint 06.1B.2 evidence contract closure

The state-machine economic semantics above remain unchanged. Sprint 06.1B.2 corrects only the frozen synthetic scenario catalog and review-pack evidence contract.

### Scenario catalog v2

The corrected scenario catalog version is `neutral_grid_synthetic_scenario_v2`. The `01_initial_exact_base` scenario now derives its grid levels with `geometric_grid_levels_decimal(Decimal("80"), Decimal("125"), 4)` and uses the generated canonical Decimal level at index `2` as `base_price`. It does not use a rounded literal such as `Decimal("100")`, and it does not snap or quantize the generated level. The exact-base scenario must have exactly one canonical level equal to the base, no initialization order at that level, BUY initialization orders below that level, SELL initialization orders above that level, and exactly `N` active initialization orders for `N` grid cells.

The `02_initial_between_levels` scenario remains a between-level scenario: its base price is not a canonical level, its canonical grid levels are unchanged, and initialization orders are derived strictly from canonical levels below and above the base. Low-price and tight-high-price catalog scenarios continue to preserve their canonical generated levels.

### Evidence pack v2 identifiers

Corrected synthetic evidence uses these identifiers:

- `RUN_ID = neutral_sm_v1_synthetic_v2`
- `SCENARIO_VERSION = neutral_grid_synthetic_scenario_v2`
- `REVIEW_PACK_SCHEMA_VERSION = neutral_grid_state_machine_review_pack_v2`
- `DEFAULT_PACK = pm_review_pack_state_machine_neutral_sm_v1_synthetic_v2.zip`

The state-machine contract version remains `native_neutral_grid_reference_contract_v1`, canonical serialization remains `neutral_grid_canonical_json_v1`, and the manifest hash policy remains `self_excluded_v1`.

### Canonical persisted bytes and duplicate-key rejection

Evidence v2 requires persisted JSON and JSONL bytes to be canonical, not merely semantically equivalent after parsing. The checker and builder reject non-canonical JSON whitespace, non-canonical JSON key ordering, JSONL blank lines, missing final JSONL newlines, extra JSONL rows or fields, and any payload whose bytes differ from the canonical serialization of the parsed object or expected rows.

All JSON documents and JSONL rows are parsed with duplicate-key rejection. Standard last-value JSON parsing is not sufficient for review evidence. Duplicate keys in `review_pack_manifest.json`, any JSON artifact, or any JSONL row fail validation.

### Exact self-excluded manifest contract

Because the manifest is self-excluded from its own `sha256` map, evidence v2 requires the manifest to contain exactly these keys and no others:

```text
review_pack_schema_version
manifest_hash_policy
review_phase
run_id
state_machine_contract_version
canonical_serialization_version
scenario_version
canonical_scenario_count
risk_budget_proven_bool
parameter_selection_authorized_bool
live_authorized_bool
members
sha256
```

Missing keys, extra keys, wrong types, wrong values, a self-hash entry, or a `sha256` key set other than the exact 11 non-manifest members fail validation. The manifest bytes must also equal the canonical JSON serialization of the parsed manifest.

### Canonical reports

The synthetic scenario report and risk budget readiness report are exact canonical evidence bytes. They are not substring-validated prose. Runner, builder, and checker use the same report builders, so duplicate guardrail lines, contradictory true/false lines, omitted lines, extra live/profitability claims, unexpected trailing text, or altered counts fail validation after rehashing.

### Preserved false guardrails

All native/risk/live guardrails remain false unless explicitly proven by a later approved sprint:

```text
native_equivalence_proven_bool = false
native_quantity_mapping_proven_bool = false
native_termination_mapping_proven_bool = false
liquidation_modeled_bool = false
ohlc_replay_supported_bool = false
risk_budget_proven_bool = false
sufficient_for_parameter_selection_bool = false
profitability_claims_present_bool = false
live_execution_present_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```
