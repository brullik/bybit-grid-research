# Sprint 06.2B.3 — Geometric Scenario Audit and Derived Guardrail Closure

## PM decision

The Sprint 06.2B.2 owner run and 14-member pack are operationally valid. This sprint fixes the last semantic-evidence defects before public Bybit batch integration.

This is an audit/evidence-only closure. The accepted state-machine and OHLC replay economics are frozen.

## Safety and scope

Allowed changes:

```text
src/bybit_grid/backtest/ohlc_replay/evidence.py
src/bybit_grid/backtest/ohlc_replay/scenarios.py
scripts/run_ohlc_replay_synthetic_matrix.py
scripts/make_ohlc_replay_review_pack.py
scripts/check_ohlc_replay_review_pack.py
docs/ohlc_minimal_path_replay_contract_v1.md
tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py
small updates to existing 06.2B evidence tests when required
.gitignore only if required
```

Do not change:

```text
src/bybit_grid/backtest/neutral_grid/engine.py
src/bybit_grid/backtest/neutral_grid/accounting.py
src/bybit_grid/backtest/neutral_grid/geometry.py
src/bybit_grid/backtest/ohlc_replay/models.py
src/bybit_grid/backtest/ohlc_replay/paths.py
src/bybit_grid/backtest/ohlc_replay/replay.py
src/bybit_grid/backtest/ohlc_replay/envelope.py
src/bybit_grid/backtest/ohlc_replay/audit.py
24 candle/funding price fixtures
fees, funding, fills, termination or PnL formulas
```

No Bybit calls, private APIs, live execution, Telegram, Parquet, historical backtest, parameter selection or generated binary files in the repository.

## Frozen economic counts

The revised pack must preserve:

```text
canonical scenarios = 24
fixed replay scenarios = 18
envelope scenarios = 6
risk_budget_proven_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

Ledger/cycle row counts must remain identical to the accepted 06.2B.2 run unless a test proves the existing evidence-only serialization was wrong. Any economic-count change is a stop-and-report condition.

## New evidence identifiers

Do not overwrite the accepted v2 pack.

```text
SCENARIO_VERSION = ohlc_minimal_path_scenarios_v2
RUN_ID = ohlc_minimal_v2_synthetic_audit_v3
REVIEW_PACK_SCHEMA_VERSION = ohlc_minimal_path_review_pack_v3_geometric_audit
SCENARIO_AUDIT_VERSION = ohlc_scenario_audit_v3_geometric_derived
REVIEW_PHASE = ohlc_synthetic_evidence_geometric_audit_complete
DEFAULT_PACK = pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic_audit_v3.zip
```

The OHLC replay economic contract version remains unchanged because replay semantics do not change.

Add `scenario_audit_version` to the exact manifest contract and to `scenario_audit.json`.

## Observed defect 1 — arithmetic levels are reported as canonical

The current scenario audit uses:

```python
lower + (upper - lower) * i / N
```

That is arithmetic geometry. The accepted engine uses:

```python
geometric_grid_levels_decimal(lower, upper, N).levels
```

Examples currently reported incorrectly:

```text
80..120, N=6:
reported: 80, 86.666..., 93.333..., 100, ...
actual geometric: 80, 85.593..., 91.577..., 97.979..., ...

0.008..0.012, N=4:
reported: 0.008, 0.009, 0.010, 0.011, 0.012
actual geometric: 0.008, 0.008853..., 0.009797..., 0.010843..., 0.012
```

### Task 1 — exact geometric audit

Import and use the single accepted helper:

```python
geometric_grid_levels_decimal
```

For every scenario and every assignment result:

```text
canonical_levels = exact helper output
stored state_machine_result.levels == canonical_levels
level count == N + 1
all levels strictly increasing
all levels unique
first == lower
last == upper
geometry_rounding_applied_bool == false
```

Write `canonical_levels` from the actual geometric Decimal tuple. Never independently reimplement the formula and never use linear interpolation.

Derive:

```text
canonical_levels_preserved_bool
no_level_collapse_bool
canonical_level_count
all_assignments_share_exact_geometry_bool
```

The audit must fail if one assignment has a changed level, arithmetic levels, a collapsed level, a rounded level or a different tuple.

## Observed defect 2 — guardrails are copied from expected

Current behavior can accept:

```text
scenario.expected.risk_budget_proven_bool = true
scenario_audit_ok = true
```

### Task 2 — guardrails must be derived

At `OhlcReplayScenario` construction:

- every key in `GUARDRAILS` is required;
- every guardrail value must be exact `False`;
- `True`, `0`, `1`, strings and subclasses are rejected.

Implement an independent `derive_guardrails_for_scenario(...)`.

Derive from fresh replay/envelope evidence where applicable:

```text
native_equivalence_proven_bool
native_quantity_mapping_proven_bool
native_termination_mapping_proven_bool
liquidation_modeled_bool
risk_budget_proven_bool
profitability_claims_present_bool
live_execution_present_bool
```

from the nested state-machine proof flags and audits.

Derive adapter limitations from the actual replay/envelope contract:

```text
full_intrabar_path_reconstructed_bool = false
arbitrary_intrabar_oscillation_bounded_bool = false
global_true_worst_case_proven_bool = false
global_true_best_case_proven_bool = false
```

Derive source/readiness guardrails from scenario provenance and this synthetic-only phase:

```text
real_bybit_batch_integration_proven_bool = false
funding_coverage_proven_bool = false
sufficient_for_bybit_batch_integration_bool = false
sufficient_for_parameter_selection_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

Do not read these values from `scenario.expected` when constructing `scenario_checks_by_id`. Compare the independently derived map to the frozen expected map and fail on any difference.

## Observed defect 3 — termination-prefix claim is tautological

The current expression accepts any non-negative ignored-candle count.

### Task 3 — independently prove termination prefix

For every fixed replay and every envelope assignment:

1. Reconstruct the full expected event schedule from retained candles, policies and funding observations.
2. Confirm persisted/generated events are the exact strict prefix consumed before termination.
3. Confirm no price or funding event follows the termination-triggering event.
4. Confirm state-machine ledger has exactly one valid termination trigger and at most one residual termination fill as required by the frozen engine contract.
5. Confirm `candle_count_processed` and `candles_not_processed_after_termination` reconcile to source candle count.
6. For non-terminated scenarios, confirm the entire expected schedule was consumed.

Derive:

```text
consumed_event_prefix_exact_bool
later_price_or_funding_events_absent_bool
termination_event_contract_ok
ignored_candle_count_reconciled_bool
```

Do not use `>= 0` as evidence.

## Observed defect 4 — path materiality includes the input assignment itself

The whole normalized result includes `path_policies`; therefore two different assignments can be reported as materially different even when their economics are identical.

### Task 4 — explicit economic and trace fingerprints

Add a canonical economic fingerprint that excludes source inputs and raw path-policy identity and includes at minimum:

```text
final_total_pnl_usdt
final_mark_price
signed_position
average_entry
cumulative realized position PnL
cumulative completed-cycle gross PnL
cumulative trading fees
cumulative funding PnL
completed-cycle count and canonical cycle totals
terminated_bool
termination_reason
candle_count_processed
candles_not_processed_after_termination
```

Derive:

```text
path_sensitive_bool = more than one economic fingerprint
material_path_outcome_differs_bool = path_sensitive_bool
trace_sensitive_bool = generated-event or nested-ledger fingerprints differ
```

Required semantics:

```text
scenario 04: path_sensitive=false, material=false, trace_sensitive=true
scenario 05: path_sensitive=true
scenario 06: path_sensitive=true
scenario 07: exact PnL equal, economic fingerprint equal, nested ledger differs, trace_sensitive=true
scenario 08: four assignments in exact order
scenario 21: completed cycle min=1, max=2
```

## Observed defect 5 — custom run ID does not propagate to the report

Current behavior can produce:

```text
manifest/status run_id = custom_run
report run_id = ohlc_minimal_v2_synthetic
```

### Task 5 — run provenance reconciliation

Pass `run_id` explicitly to every builder. Do not read global `RUN_ID` inside report generation when a run ID argument exists.

Require exact reconciliation across:

```text
CLI requested run ID
manifest.run_id
run status.run_id
OHLC report run_id
checker requested run ID
output directory name
```

Add a custom-run regression test. A pack with a mismatched report run ID must fail even after its report hash is recomputed.

## Task 6 — derive contract audit from evidence

Replace a purely literal success payload with a derived audit.

At minimum derive from actual artifacts/audits:

```text
closed_contiguous_1m_enforced_bool
minimal_path_policies_frozen_bool
funding_before_price_enforced_bool
funding_source_provenance_enforced_bool
strict_snapshot_identity_enforced_bool
fresh_nested_replay_enforced_bool
exact_cartesian_enumeration_enforced_bool
canonical_geometric_levels_enforced_bool
canonical_byte_identity_enforced_bool
all_scenario_audits_pass_bool
```

Include:

```text
failures: []
contract_audit_ok: true only when every required condition passes
```

The no-live posture remains separately enforced by `scripts/check_no_live_execution.py` and by false live guardrails.

## Task 7 — persisted-input-first checking

The checker must continue to:

```text
strict-parse persisted scenario inputs
reconstruct exact scenarios
fresh replay those reconstructed inputs
compare fixed results
envelopes
generated events
nested ledger
completed cycles
reports
audits
manifest and hashes
```

The scenario audit used by the checker must be derived from the reconstructed persisted scenarios and fresh results, not only from the module-global catalog.

## Task 8 — exact tests

Add `tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py` with at least:

1. 90..110/N=4 reported levels exactly equal `geometric_grid_levels_decimal`, not arithmetic 95/100/105.
2. 80..120/N=6 exact geometric tuple.
3. 0.008..0.012/N=4 exact low-price geometric tuple.
4. 49900..50100/N=20 exact tight-price geometric tuple.
5. all assignment state-machine level tuples equal canonical.
6. arithmetic-level substitution is rejected.
7. rounded-level substitution is rejected.
8. any guardrail `true` is rejected at scenario construction.
9. bool/int/string aliases for guardrails are rejected.
10. scenario audit guardrails equal derived nested proof/readiness evidence, not `expected` identity.
11. terminated scenario has exact consumed prefix and no later event.
12. injected post-termination event is rejected.
13. incorrect ignored-candle count is rejected.
14. scenario 04 economic path-insensitive but trace-sensitive.
15. scenario 07 equal economic fingerprint and differing nested ledger.
16. custom run ID appears in status, manifest and report.
17. mismatched report run ID with recomputed hash is rejected.
18. old v2 pack schema is rejected by the v3 checker.
19. contract audit false/tampered with recomputed hash is rejected.
20. no private/live/Telegram code additions.

Temporary ZIPs are allowed only inside pytest `tmp_path`. Do not commit ZIP, JSONL, database or Parquet fixtures.

## Task 9 — reports and manifest

The 14-member pack remains unchanged:

```text
review_pack_manifest.json
ohlc_replay_run_status.json
ohlc_replay_contract_audit.json
scenario_catalog.json
scenario_inputs.jsonl
fixed_replay_results.jsonl
envelope_results.jsonl
generated_replay_events.jsonl
state_machine_ledger.jsonl
completed_cycles.jsonl
scenario_audit.json
reproducibility_audit.json
ohlc_replay_report.md
risk_budget_readiness_report.md
```

Manifest exact key set must include `scenario_audit_version`. Keep self-excluded SHA policy and exactly 13 non-manifest hashes.

Reports must be generated canonically and must not contain contradictory or duplicate claims.

## Required commands in Codex environment

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_2b_persisted_ohlc_evidence.py -q
python -m pytest tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py -q
python -m pytest tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py -q
python -m pytest tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py -q
python -m pytest -q
ruff check .
```

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live audit passes
24 scenarios = 18 fixed + 6 envelope
state-machine/OHLC economic outputs unchanged
all reported levels are exact canonical geometric levels
no arithmetic geometry in scenario audit
all assignment level tuples reconcile
all guardrails independently derived and false
expected guardrail true cannot be constructed
termination prefixes independently reconciled
scenario 04 economic-insensitive/trace-sensitive
scenario 07 equal economic fingerprint/different ledger
custom run ID reconciles in every artifact
scenario_audit_version present and exact
14 members, 13 non-manifest hashes
review_pack_ok=true
risk_budget_proven_bool=false
parameter_selection_authorized_bool=false
live_authorized_bool=false
```

## Required return to PM

Return text:

```text
changed text files
full pytest output
all four focused 06.2B test outputs
Ruff output
no-live audit output
geometric-level audit summary
scenario 04 and 07 fingerprint summary
derived guardrail summary
termination-prefix summary
custom-run provenance test summary
runner JSON
builder JSON
checker JSON
risk_budget_proven_bool
parameter_selection_authorized_bool
live_authorized_bool
```

Do not create or attach binary artifacts in Codex.
