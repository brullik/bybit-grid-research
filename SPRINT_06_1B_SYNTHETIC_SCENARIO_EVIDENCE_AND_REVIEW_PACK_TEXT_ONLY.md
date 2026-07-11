# Sprint 06.1B — Synthetic Scenario Evidence, Replay Audit, and Text Review Pack

## PM decision

Sprint 06.1A.2 core geometry/accounting is accepted for progression. Gate 6A remains open until this sprint produces deterministic input-event evidence, exact replay reconciliation, hardened result audits, and a verified review pack.

This is the final synthetic state-machine evidence sprint. Do not split the listed mandatory audit fixes into another preliminary micro-sprint.

## Critical Codex artifact rule

Codex may add or modify only text source files:

```text
.py
.md
```

Do not add, modify, upload, or commit:

```text
.zip
.parquet
.csv
.json generated artifacts
.jsonl generated artifacts
.duckdb
.db
.sqlite
pickle/numpy binaries
images
PDFs
market data
owner logs
```

The implementation may contain scripts that generate JSON/JSONL/Markdown and a ZIP when the owner runs them locally. Do not run those scripts to create repository artifacts in the Codex return. Temporary ZIP/JSON files created only inside pytest `tmp_path` are allowed and must not be committed.

Return code and test results as text only.

## Safety and scope

- No Bybit private API calls.
- No create/close/order/cancel/position execution.
- No Telegram.
- No OHLC replay.
- No historical market-data run.
- No parameter optimization or selection.
- No profitability, EV, ROI, or loss-cap claim.
- No native equivalence claim.
- Preserve all false proof/readiness flags.
- Synthetic PnL is diagnostic accounting evidence only.

## Task 0 — Close the remaining core-audit defects

Complete these before building the scenario matrix.

### 0.1 Reserve sequence 0 for initialization

Choose and document one unambiguous contract:

```text
activation_sequence_id = 0 is reserved for initialization
all external PriceEvent/FundingEvent/manual-termination sequence_id values must be >= 1
```

Update:

- `PriceEvent` validation;
- `FundingEvent` validation;
- `terminate_now()` guard;
- contract documentation;
- tests.

Do not silently coerce zero to one.

### 0.2 Exact active-order bijection

The audit must require:

```text
IDs of all_orders rows with state=active
== IDs represented by active_orders values
```

Also require:

- exactly one active order per level;
- active mapping key equals order level index;
- no hidden active order in `all_orders`;
- no active mapping row absent from `all_orders`;
- terminated result has no active order in either representation;
- non-bool integer level indices;
- valid non-empty order IDs;
- valid state/side enum types.

### 0.3 Linked-open-fill provenance

For every non-null `GridOrder.linked_open_fill_id`, require:

- referenced ledger row exists;
- referenced row is a grid fill;
- referenced fill occurred no later than order activation;
- activation sequence equals referenced fill sequence for replacement orders;
- order side is opposite referenced fill side;
- order level is exactly the expected adjacent level;
- referenced fill opened or added exposure in its own direction;
- linked ID cannot point to funding, termination, missing, later, same-side, non-adjacent, or already invalid evidence.

Tampering the active mapping and the matching `all_orders` row consistently must still fail.

### 0.4 Exact completed-cycle provenance

For each `CompletedGridCycle`, reconcile:

```text
open_level_index == open ledger level_index
close_level_index == close ledger level_index
open/close IDs are grid fills
open row precedes close row
opposite sides
adjacent levels
same quantity
cycle gross/fees/net exact
```

Also reconcile the close ledger row's:

```text
completed_grid_cycle_gross_usdt
grid_cycle_open_fee_usdt
grid_cycle_close_fee_usdt
```

to the cycle object, and require zero cycle fields on grid-fill rows that do not close a cycle.

### 0.5 Exact termination contract

For terminated results require:

- `termination_reason` is exactly a `TerminationReason`, never null/string/unknown;
- exactly one termination trigger;
- trigger ledger row has `PositionEffect.none` and all non-applicable fields zero/null;
- boundary reason matches configured boundary and trigger price;
- manual reason has a finite positive trigger;
- all orders are filled or cancelled; none remain active;
- termination fill, when required, is the final ledger row;
- trigger and termination fill share the terminating sequence/time;
- residual quantity equals absolute pre-close position;
- side closes the pre-close signed position;
- execution price, taker/maker role, fee, and slippage reconcile exactly;
- final signed position is zero and average entry is null.

For flat termination require exactly:

```text
residual_quantity_closed = 0
termination_execution_price = null
termination_trading_fee_usdt = 0
termination_slippage_cost_usdt = 0
no termination_fill ledger row
```

For nonterminated results require the default empty `TerminationSummary` and no trigger/fill rows.

### 0.6 Audit must always fail closed, never traceback

`audit_simulation_result()` must return a failed `AuditResult` for malformed/tampered snapshots instead of raising uncaught exceptions from:

- invalid level index;
- missing/mixed order ID types;
- malformed enums;
- invalid Decimal values;
- malformed termination fields;
- bad cycle references;
- unexpected ledger structures.

Do not hide programming errors in the engine runner; this fail-closed rule applies to the public audit boundary.

## Task 1 — Add explicit synthetic scenario definitions

Add text source modules under:

```text
src/bybit_grid/backtest/neutral_grid/
```

Suggested files:

```text
scenarios.py
serialization.py
scenario_audit.py
```

Use strict dataclasses/enums and Decimal-only accounting fields.

### ScenarioDefinition

At minimum:

```text
scenario_id: str
scenario_version: str
config: NeutralGridConfig
actions: tuple[ScenarioAction, ...]
description: str
expected_termination_reason: TerminationReason | None
```

### ScenarioAction

Support exactly:

```text
PriceEvent
FundingEvent
ManualTerminationAction
```

Add a strict `ManualTerminationAction` with:

```text
sequence_id >= 1
time_ms >= 0
trigger_price finite positive Decimal
```

The normal engine `process()` must continue to accept only `PriceEvent | FundingEvent`. The scenario runner dispatches manual action to `terminate_now()`.

### Canonical serialization

Implement deterministic serialization:

- Decimals serialized as exact strings;
- enums serialized by `.value`;
- stable key ordering;
- UTF-8;
- newline policy fixed;
- no timestamps, random UUIDs, machine paths, Python object reprs, or environment-specific fields;
- deterministic scenario input SHA-256.

## Task 2 — Canonical synthetic matrix

Create a frozen catalog with exactly these 33 scenario IDs:

```text
01_initial_exact_base
02_initial_between_levels
03_low_price_initial
04_tight_high_price_initial
05_single_long_open
06_single_short_open
07_single_long_cycle
08_single_short_cycle
09_double_long_cycle_rearm
10_double_short_cycle_rearm
11_accumulate_two_long
12_accumulate_two_short
13_long_partial_rebound
14_short_partial_rebound
15_full_range_down_then_up
16_full_range_up_then_down
17_flat_positive_funding
18_long_positive_funding
19_short_positive_funding
20_long_negative_funding
21_short_negative_funding
22_lower_termination_residual_long
23_upper_termination_residual_short
24_manual_flat_termination
25_manual_long_termination
26_manual_short_termination
27_repeated_same_price_no_double_fill
28_same_timestamp_price_then_funding
29_same_timestamp_funding_then_price
30_lower_only_termination_guardrail
31_upper_only_termination_guardrail
32_low_price_long_cycle
33_tight_high_price_short_cycle
```

Required config coverage:

- base exactly equal to canonical grid level;
- base strictly between canonical levels;
- low-price range around 0.08–0.12;
- tight high-price range around 9998–10002;
- two-sided termination;
- lower-only termination;
- upper-only termination;
- positive and negative funding;
- same timestamp with sequence-defined ordering.

All action sequence IDs start at 1 and increase strictly. Times are non-decreasing.

Do not use random scenarios in the canonical evidence pack. Random/property-style tests may be used separately with a fixed seed.

## Task 3 — Replay and exact result reconciliation

Implement a scenario replay function that:

1. creates a fresh engine from the serialized scenario config;
2. dispatches each action in order;
3. returns the detached `SimulationResult`;
4. runs the hardened result audit;
5. serializes the complete result deterministically.

Implement an independent scenario evidence audit that compares:

```text
stored scenario input
freshly deserialized scenario input
fresh replay result
stored normalized result
```

Require exact equality for:

- config;
- canonical levels;
- active and all orders;
- ledger rows and order;
- cycles;
- position and average entry;
- all cumulative PnL fields;
- termination summary;
- initialization audit;
- proof flags;
- rejected-event counter;
- geometry rounding flag.

Pack-level fields:

```text
input_event_evidence_complete_bool = true
all_scenarios_replay_match_bool = true
all_result_audits_pass_bool = true
canonical_scenario_count = 33
```

Do not change the engine result flag `event_path_completeness_proven_bool`; it remains false because a standalone result does not contain its input path. The separate scenario-evidence audit proves completeness only for the packaged synthetic scenarios.

## Task 4 — Owner-side runner with atomic status

Add:

```text
scripts/run_neutral_grid_synthetic_matrix.py
```

CLI:

```text
--run-id neutral_sm_v1_synthetic
--output-root data/processed/state_machine_runs
--report-root reports/state_machine_runs
```

The script is not run by Codex for committed artifacts.

Atomic lifecycle:

```text
building -> complete
building -> failed
```

`complete` may be written only after every required artifact exists, parses, and passes internal checks. On exception write `failed` with stable error type/summary, then exit nonzero. Do not leave stale complete state.

Use output directory:

```text
data/processed/state_machine_runs/<run_id>/
```

Generated artifacts, all text:

```text
state_machine_run_status.json
state_machine_contract_audit.json
scenario_catalog.json
scenario_inputs.jsonl
scenario_results.jsonl
ledger_events.jsonl
completed_cycles.jsonl
scenario_audit.json
reproducibility_audit.json
```

Reports:

```text
reports/state_machine_runs/<run_id>/synthetic_scenario_report.md
reports/state_machine_runs/<run_id>/risk_budget_readiness_report.md
```

No Parquet is needed in this sprint.

## Task 5 — Required artifact semantics

### state_machine_run_status.json

Require:

```text
schema_version = neutral_grid_state_machine_run_status_v1
run_id
status = complete
canonical_scenario_count = 33
completed_scenario_count = 33
failed_scenario_count = 0
state_machine_contract_version = native_neutral_grid_reference_contract_v1
```

### state_machine_contract_audit.json

Require at least:

```text
contract_audit_ok = true
canonical_geometry_exact_bool = true
sequence_zero_reserved_bool = true
active_order_bijection_enforced_bool = true
linked_fill_provenance_enforced_bool = true
cycle_provenance_enforced_bool = true
termination_contract_enforced_bool = true
audit_fail_closed_bool = true
no_live_execution_bool = true
```

### scenario_audit.json

Require:

```text
scenario_audit_ok = true
canonical_scenario_count = 33
all_scenarios_replay_match_bool = true
all_result_audits_pass_bool = true
input_event_evidence_complete_bool = true
scenario_ids_unique_bool = true
scenario_input_hashes_unique_bool = true
ledger_ids_unique_within_scenario_bool = true
order_ids_unique_within_scenario_bool = true
cycle_ids_unique_within_scenario_bool = true
all_terminated_scenarios_flat_bool = true
all_nonterminated_scenarios_have_empty_termination_summary_bool = true
```

### reproducibility_audit.json

Require:

```text
reproducibility_audit_ok = true
canonical_serialization_version = neutral_grid_canonical_json_v1
same_inputs_same_bytes_bool = true
same_inputs_same_hashes_bool = true
machine_specific_fields_present_bool = false
wall_clock_fields_present_bool = false
```

### risk_budget_readiness_report.md

Must state explicitly:

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
sufficient_for_ohlc_replay_engineering_bool = true
```

Synthetic loss/PnL values may be reported as diagnostics but must not be described as an actual Bybit loss cap, EV, expected return, or profitability.

## Task 6 — Text review-pack builder and checker

Add:

```text
scripts/make_state_machine_review_pack.py
scripts/check_state_machine_review_pack.py
```

Default pack:

```text
pm_review_pack_state_machine_neutral_sm_v1_synthetic.zip
```

Codex must not create or commit this ZIP. The owner will run the builder locally.

Exact review-pack member set, 12 unique members:

```text
review_pack_manifest.json
state_machine_run_status.json
state_machine_contract_audit.json
scenario_catalog.json
scenario_inputs.jsonl
scenario_results.jsonl
ledger_events.jsonl
completed_cycles.jsonl
scenario_audit.json
reproducibility_audit.json
synthetic_scenario_report.md
risk_budget_readiness_report.md
```

Manifest:

```text
review_pack_schema_version = neutral_grid_state_machine_review_pack_v1
manifest_hash_policy = self_excluded_v1
review_phase = synthetic_state_machine_evidence_complete
run_id = requested run ID
state_machine_contract_version = native_neutral_grid_reference_contract_v1
canonical_serialization_version = neutral_grid_canonical_json_v1
canonical_scenario_count = 33
risk_budget_proven_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
members = exact 12-member list
sha256 = exact mapping for 11 non-manifest members
```

Checker must:

- print strict JSON and no traceback for expected operator failures;
- reject missing ZIP;
- reject missing/extra/duplicate members;
- reject absolute/path-traversal/forbidden paths;
- require no manifest self-hash;
- require exact hash-key set and matching hashes;
- validate all run/audit/report guardrails;
- reconcile run ID, versions, count, scenario IDs, and false risk/live/selection claims across artifacts;
- parse every JSONL line;
- verify row counts and scenario coverage;
- independently recompute scenario input hashes;
- reject any tampered text artifact.

Successful output includes:

```text
review_pack_ok = true
member_count = 12
hashes_verified = 11
canonical_scenario_count = 33
risk_budget_proven_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

## Task 7 — Tests

Add a focused file such as:

```text
tests/test_sprint_06_1b_synthetic_scenario_evidence.py
```

Required regression coverage:

### Core closure

1. PriceEvent sequence 0 rejected.
2. FundingEvent sequence 0 rejected.
3. Manual termination sequence 0 rejected without mutation.
4. Missing active mapping entry rejected.
5. Hidden active `all_orders` row rejected.
6. Consistently tampered linked-open ID rejected.
7. Linked ID to funding/termination/later/same-side/non-adjacent fill rejected.
8. Tampered cycle open/close level fields rejected.
9. Cycle fields on wrong ledger row rejected.
10. Terminated reason null/string/wrong enum rejected.
11. Hidden active order after termination rejected.
12. Flat termination fabricated execution price/fee/slippage rejected.
13. Invalid level index and malformed order ID return failed audit without traceback.

### Scenario matrix and replay

14. Exact 33 scenario IDs and no extras.
15. All action sequences start at 1 and are strictly increasing.
16. All scenarios replay and result-audit successfully.
17. Low-price and tight-range scenarios keep exact canonical levels.
18. Same-timestamp ordering produces the documented distinct funding result.
19. Repeated same-price event creates no duplicate fill.
20. All termination scenarios end flat.
21. One-sided scenarios keep risk proof false.
22. Input-event tamper changes hash and fails replay audit.
23. Stored result tamper fails exact replay comparison.
24. Deterministic serialization is byte-identical across two temp roots.

### Status and review pack

25. Successful temp run reaches complete only after all artifacts exist.
26. Deliberate scenario failure writes failed and never complete.
27. Pack builder rejects building/failed status.
28. Pack builder rejects missing required artifact.
29. Checker accepts the valid tiny/canonical temp pack.
30. Checker rejects each member tamper by hash.
31. Checker rejects manifest semantic tamper without relying on self-hash.
32. Checker rejects duplicate/extra/path-traversal member.
33. Missing ZIP returns strict JSON without traceback.
34. No live/private API/Telegram additions.

Temporary generated files and ZIPs must live only under pytest `tmp_path`.

## Required Codex commands

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_1a_neutral_grid_state_machine.py -q
python -m pytest tests/test_sprint_06_1a_1_state_machine_hardening.py -q
python -m pytest tests/test_sprint_06_1a_2_canonical_geometry_and_audit_closure.py -q
python -m pytest tests/test_sprint_06_1b_synthetic_scenario_evidence.py -q
python -m pytest -q
ruff check .
git diff --check
```

If Git is unavailable in the Codex environment, report that fact rather than fabricating output.

Do not run the owner artifact-generation commands in the repository working tree.

## Acceptance criteria for code return

```text
all tests passed
Ruff passed
no-live audit passed
sequence zero reserved
active-order bijection enforced
linked-fill provenance enforced
cycle provenance enforced
termination contract enforced
audit fail-closed on malformed snapshots
exact 33-scenario frozen catalog
canonical deterministic serialization
exact replay reconciliation implemented
atomic run status implemented
12-member review-pack builder/checker implemented
all native/risk/selection/profit/live flags remain false
no generated/binary files committed
```

## Required Codex return — text only

```text
commit hash
changed text files
git diff --stat
full pytest output
06.1A focused output
06.1A.1 focused output
06.1A.2 focused output
06.1B focused output
Ruff output
no-live audit output
numeric environment output
pip check output
git diff --check output
git status --short output
sequence-zero contract summary
active-order bijection summary
linked-fill provenance summary
cycle provenance summary
termination contract summary
scenario catalog summary
replay reconciliation summary
deterministic serialization summary
status lifecycle summary
review-pack builder/checker test summary
all proof/readiness flag values
known remaining native-equivalence unknowns
```

Do not return or upload ZIP/JSON/JSONL/generated reports from Codex.
