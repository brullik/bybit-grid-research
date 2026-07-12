# Sprint 06.2B.3.1 — Independent Evidence Truthfulness Closure

## PM decision

Sprint 06.2B.3 fixed geometric reporting and path fingerprints. Its focused test passes. Before the owner evidence pack is accepted, three remaining evidence claims must become genuinely derived:

1. proof/readiness guardrails;
2. contract audit conditions;
3. termination-prefix evidence.

This is the final evidence-only closure before public Bybit batch integration. Do not change the frozen state-machine or OHLC replay economics.

## Safety and allowed scope

Allowed text-file changes:

```text
src/bybit_grid/backtest/ohlc_replay/evidence.py
src/bybit_grid/backtest/ohlc_replay/scenarios.py
scripts/run_ohlc_replay_synthetic_matrix.py
scripts/make_ohlc_replay_review_pack.py
scripts/check_ohlc_replay_review_pack.py
docs/ohlc_minimal_path_replay_contract_v1.md
tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py
tests/test_sprint_06_2b_3_1_independent_evidence_truthfulness.py
small updates to existing 06.2B evidence tests only when required
.gitignore only if required
```

Forbidden changes:

```text
src/bybit_grid/backtest/neutral_grid/engine.py
src/bybit_grid/backtest/neutral_grid/accounting.py
src/bybit_grid/backtest/neutral_grid/geometry.py
src/bybit_grid/backtest/ohlc_replay/models.py
src/bybit_grid/backtest/ohlc_replay/paths.py
src/bybit_grid/backtest/ohlc_replay/replay.py
src/bybit_grid/backtest/ohlc_replay/envelope.py
src/bybit_grid/backtest/ohlc_replay/audit.py
24 scenario price/funding fixtures
fees, funding, fills, termination, PnL or path formulas
```

No Bybit calls, private APIs, live execution, Telegram, historical data, Parquet, parameter selection or committed generated artifacts.

## Frozen economic contract

Preserve exactly:

```text
scenario_version = ohlc_minimal_path_scenarios_v2
canonical scenarios = 24
fixed replay scenarios = 18
envelope scenarios = 6
scenario IDs and all candle/funding/config fixtures unchanged
risk_budget_proven_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

Do not change accepted ledger/cycle/PnL outputs.

## New evidence identifiers

Because evidence semantics change, do not overwrite v3:

```text
RUN_ID = ohlc_minimal_v2_synthetic_audit_v4
REVIEW_PACK_SCHEMA_VERSION = ohlc_minimal_path_review_pack_v4_independent_evidence
SCENARIO_AUDIT_VERSION = ohlc_scenario_audit_v4_independent_derived
CONTRACT_AUDIT_VERSION = ohlc_contract_audit_v4_independent_derived
REVIEW_PHASE = ohlc_synthetic_evidence_independent_audit_complete
DEFAULT_PACK = pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic_audit_v4.zip
```

Add `contract_audit_version` to the exact contract-audit payload and manifest exact key set.

## Defect 1 — guardrails are forced false instead of derived

Current behavior can hide an unexpected nested proof claim:

```text
nested proof_flags.risk_budget_proven_bool = true
scenario guardrail risk_budget_proven_bool = false
```

### Task 1 — derive proof guardrails from nested results

Implement `derive_guardrails_for_scenario(...)` so it does not initialize proof-derived keys by overwriting them with false.

For every fresh fixed result or envelope assignment, read exact booleans from `state_machine_result.proof_flags` for:

```text
native_equivalence_proven_bool
native_quantity_mapping_proven_bool
native_termination_mapping_proven_bool
liquidation_modeled_bool
risk_budget_proven_bool
profitability_claims_present_bool
live_execution_present_bool
```

Requirements:

- every required nested proof key exists;
- every value is exact `bool`, not integer/string/subclass;
- all assignment values agree;
- the derived scenario value is the actual agreed nested value;
- any value `True` causes the frozen expected-False comparison to fail;
- never silently replace an unexpected `True` with `False`.

Derive adapter limitations from actual minimal-path contract evidence, not `scenario.expected`:

```text
full_intrabar_path_reconstructed_bool = false
arbitrary_intrabar_oscillation_bounded_bool = false
global_true_worst_case_proven_bool = false
global_true_best_case_proven_bool = false
```

Derive synthetic-phase readiness from an explicit versioned phase-capability contract, not from `scenario.expected`:

```text
real_bybit_batch_integration_proven_bool = false
funding_coverage_proven_bool = false
sufficient_for_bybit_batch_integration_bool = false
sufficient_for_parameter_selection_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

Add per-scenario evidence:

```text
guardrails
guardrail_sources_by_key
nested_proof_flags_consistent_bool
all_guardrails_exact_bool_bool
unexpected_true_guardrail_keys
```

Allowed source labels:

```text
nested_state_machine_proof_flags
minimal_path_contract
synthetic_phase_contract
```

Derive top-level:

```text
all_scenario_guardrails_derived_bool
all_nested_proof_flags_consistent_bool
```

## Defect 2 — contract audit can pass without evidence

Current behavior can produce `contract_audit_ok=true` with an empty scenario-check map because some conditions are literal `True` and `all([])` is true.

### Task 2 — strict non-vacuous contract audit

`build_contract_audit(...)` must fail closed unless:

```text
scenario_check_count == 24
scenario IDs exactly equal the frozen ordered IDs
scenario_audit_ok == true
reproducibility_audit_ok == true
```

Derive every contract field from actual scenario/reproducibility evidence. No required condition may be a bare literal success.

Required fields:

```text
contract_audit_version
scenario_check_count
closed_contiguous_1m_enforced_bool
minimal_path_policies_frozen_bool
funding_before_price_enforced_bool
funding_source_provenance_enforced_bool
strict_snapshot_identity_enforced_bool
fresh_nested_replay_enforced_bool
exact_cartesian_enumeration_enforced_bool
canonical_geometric_levels_enforced_bool
canonical_byte_identity_enforced_bool
all_scenario_guardrails_derived_bool
all_termination_prefixes_reconciled_bool
all_scenario_audits_pass_bool
no_live_execution_bool
failures
contract_audit_ok
```

Examples of derivation:

- closed/contiguous: all 24 per-scenario checks, exact count required;
- path policies: exact enum/length/mode contract for every frozen scenario;
- funding-before-price: inspect independently reconstructed full event schedules;
- funding provenance: exact category/symbol/source reconciliation in every scenario;
- snapshot/fresh replay: every stored/fresh replay audit passes and strict identity comparison passes;
- Cartesian enumeration: exact ordered assignment keys and counts for all envelopes;
- geometry: exact helper tuple for every assignment;
- byte identity: derived reproducibility audit passes;
- no-live: all derived live guardrails are exact false and no-live evidence is present.

`build_contract_audit({"scenario_checks_by_id": {}, "scenario_audit_ok": True}, ...)` must return `contract_audit_ok=false`, not true.

## Defect 3 — termination-prefix proof is self-referential

The current helper uses the already-terminated fresh result as the “full” event schedule and assigns later-event absence true for terminated results.

### Task 3 — reconstruct the complete source schedule

Use the accepted adapter helper:

```python
reconstruct_expected_event_schedule(
    source_candles,
    path_policies,
    source_funding_observations,
)
```

For each fixed replay and each envelope assignment, derive independently:

```text
full_schedule_event_count
consumed_event_count
unconsumed_event_count
consumed_event_prefix_exact_bool
termination_trigger_sequence_id
termination_trigger_matches_last_consumed_event_bool
later_price_or_funding_events_absent_bool
termination_event_contract_ok
ignored_candle_count_reconciled_bool
```

Rules:

- persisted/fresh generated events must be an exact strict prefix of the complete reconstructed schedule;
- non-terminated results must consume the complete schedule;
- terminated results must have one termination-trigger ledger event;
- the trigger sequence/time must match the price event that caused termination;
- no consumed generated event may follow that sequence;
- at most one residual termination fill is allowed by the frozen engine contract;
- processed + ignored candle counts must reconcile exactly;
- do not assign success merely because `terminated_bool` is true;
- do not compare the event list only to itself.

Derive top-level:

```text
all_termination_prefixes_reconciled_bool
```

## Task 4 — persisted-input-first checker reconciliation

Keep exact manifest/member/hash checks, but make the semantic checker order explicit:

1. strict-parse manifest and hashes;
2. strict-parse `scenario_inputs.jsonl`;
3. reconstruct exact typed scenarios;
4. require their canonical normalized bytes/hashes to equal the frozen v2 catalog;
5. fresh replay the reconstructed scenarios;
6. derive fixed results, envelopes, generated events, ledgers and cycles;
7. compare all six persisted core members byte-for-byte to the fresh derived members;
8. derive scenario audit from reconstructed scenarios and fresh results;
9. derive reproducibility and contract audits from the persisted/fresh evidence;
10. compare reports, status, audits and manifest exactly.

Do not rely only on an early `build_records()` equality comparison against module globals. The checker must be able to name which persisted-input-first stage failed.

## Task 5 — report and manifest consistency

The 14-member pack remains unchanged.

Manifest exact key set must include:

```text
scenario_audit_version
contract_audit_version
```

Keep:

```text
manifest_hash_policy = self_excluded_v1
exactly 13 non-manifest hashes
risk_budget_proven_bool = false
parameter_selection_authorized_bool = false
live_authorized_bool = false
```

The OHLC report must use the requested `run_id`; reports must be canonical and contradiction-free.

## Task 6 — tests

Create exactly:

```text
tests/test_sprint_06_2b_3_1_independent_evidence_truthfulness.py
```

Add at minimum:

1. nested `risk_budget_proven_bool=true` is not masked; scenario audit fails;
2. nested live/profitability proof true is not masked;
3. nested proof bool/int/string aliases fail closed;
4. proof flags disagree across two envelope assignments → fail;
5. guardrail sources exist and use only the three allowed labels;
6. empty scenario checks cannot produce passing contract audit;
7. 23/24 checks cannot pass contract audit;
8. false reproducibility audit cannot pass contract audit;
9. every contract success field is linked to concrete evidence;
10. terminated scenario consumes an exact prefix of independently reconstructed full schedule;
11. appended post-termination event fails;
12. removed/reordered pre-termination event fails;
13. wrong termination trigger sequence/time fails;
14. wrong ignored-candle count fails;
15. non-terminated scenario must consume full schedule;
16. persisted-input-first fresh replay detects changed fixed result after rehash;
17. persisted-input-first fresh replay detects changed envelope/events/ledger/cycle after rehash;
18. changed frozen scenario input plus regenerated dependent artifacts is rejected by frozen catalog identity;
19. v3 manifest/schema is rejected by v4 checker;
20. custom run ID reconciles in status, manifest and report;
21. no private/live/Telegram additions.

Temporary ZIPs are allowed only inside pytest `tmp_path`. Do not commit binary/generated fixtures.

## Required commands in Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_2b_persisted_ohlc_evidence.py -q
python -m pytest tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py -q
python -m pytest tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py -q
python -m pytest tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py -q
python -m pytest tests/test_sprint_06_2b_3_1_independent_evidence_truthfulness.py -q
python -m pytest -q
ruff check .
```

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live passes
24 scenarios = 18 fixed + 6 envelope
frozen economics and fixtures unchanged
all geometric checks remain true
all proof guardrails are derived from actual nested flags
unexpected true proof is exposed and fails
no vacuous contract-audit success
all 24 checks required
termination full schedule/prefix independently reconciled
persisted-input-first fresh replay reconciles all core evidence
scenario 04 economic-insensitive and trace-sensitive
scenario 07 equal economic fingerprint and different ledger
scenario 21 cycle min/max = 1/2
custom run ID reconciles
14 members / 13 non-manifest hashes
review_pack_ok=true
risk_budget_proven_bool=false
parameter_selection_authorized_bool=false
live_authorized_bool=false
```

## Required return to PM

Return text only:

```text
changed text files
full pytest output
all five focused 06.2B outputs
Ruff output
no-live output
derived guardrail summary
nested-proof tamper summary
non-vacuous contract-audit summary
termination full-schedule/prefix summary
persisted-input-first replay summary
geometric/fingerprint regression summary
runner JSON
builder JSON
checker JSON
risk_budget_proven_bool
parameter_selection_authorized_bool
live_authorized_bool
```

Do not create or attach binary artifacts in Codex.
