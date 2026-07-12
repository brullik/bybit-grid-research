# Sprint 06.2B — Persisted OHLC Evidence and Strict Review-Pack Gate

## PM decision

Sprint 06.2A.2 in-memory replay semantics are accepted and frozen. This sprint must not change grid economics or accepted OHLC path behavior.

The goal is to create a deterministic frozen synthetic OHLC catalog, persist all input/output evidence as canonical text, independently replay every record, and produce a semantically verified review pack.

This is the final synthetic OHLC evidence gate before real Bybit batch-data integration.

## Text-only Codex rule

Codex may modify only repository text files:

```text
.py
.md
.gitignore
```

Codex must not add or commit:

```text
.zip
.jsonl generated evidence
.parquet
.csv generated evidence
.db/.sqlite
market data
owner reports
.env
API keys
binary fixtures
```

Temporary JSON/JSONL/ZIP files inside pytest `tmp_path` are allowed and must not be committed.

The owner, not Codex, will generate final evidence and ZIP after tests pass.

## Frozen semantics — do not change

Do not change:

```text
Decimal-only neutral-grid accounting
canonical N cells -> N+1 geometric levels
open-start / closed-end crossing
one-way signed position accounting
weighted average entry
realized/unrealized PnL
adjacent grid-cycle pairing
fees once per fill
funding formula and sign
termination accounting/slippage
OHLC path = open -> high -> low -> close
OLHC path = open -> low -> high -> close
remove consecutive duplicate price nodes only
preserve previous close -> next open gaps
all candle path nodes use candle open_time_ms
funding at a later candle boundary executes before that candle path
funding at entry_time_ms is rejected
closed contiguous 1m candles only
exact 2^k enumeration below the configured cap
strict replay snapshot identity
strict full nested SimulationResult fresh-replay identity
minimal-path envelope is not a true global intrabar bound
```

No parameter search, real historical backtest, native quantity mapping, liquidation modeling, risk proof, private API or Telegram.

## Fixed identifiers

Use exactly:

```text
OHLC_REPLAY_CONTRACT_VERSION = ohlc_minimal_path_replay_contract_v2
SCENARIO_VERSION = ohlc_minimal_path_scenarios_v1
RUN_ID = ohlc_minimal_v1_synthetic
REVIEW_PACK_SCHEMA_VERSION = ohlc_minimal_path_review_pack_v1_strict_identity
MANIFEST_HASH_POLICY = self_excluded_v1
EVIDENCE_TYPE_CONTRACT_VERSION = strict_json_type_identity_v1
CANONICAL_SERIALIZATION_VERSION = neutral_grid_canonical_json_v1
REVIEW_PHASE = ohlc_synthetic_evidence_complete
DEFAULT_PACK = pm_review_pack_ohlc_replay_ohlc_minimal_v1_synthetic.zip
CANONICAL_SCENARIO_COUNT = 24
```

Guardrails must remain:

```text
native_equivalence_proven_bool = false
native_quantity_mapping_proven_bool = false
native_termination_mapping_proven_bool = false
liquidation_modeled_bool = false
real_bybit_batch_integration_proven_bool = false
funding_coverage_proven_bool = false
full_intrabar_path_reconstructed_bool = false
arbitrary_intrabar_oscillation_bounded_bool = false
global_true_worst_case_proven_bool = false
global_true_best_case_proven_bool = false
risk_budget_proven_bool = false
sufficient_for_parameter_selection_bool = false
parameter_selection_authorized_bool = false
profitability_claims_present_bool = false
live_execution_present_bool = false
live_authorized_bool = false
sufficient_for_bybit_batch_integration_bool = true
```

Do not change the proof flags embedded in the frozen neutral-grid `SimulationResult`.

## Task 1 — Add explicit funding-source provenance

Update `src/bybit_grid/backtest/ohlc_replay/models.py`.

Add exact enums:

```text
FundingRateSource.synthetic
FundingRateSource.bybit_funding_history

FundingMarkPriceSource.synthetic
FundingMarkPriceSource.bybit_mark_price_kline_1m
```

Extend `FundingObservation`:

```text
category: str
symbol: str
time_ms: int
funding_rate: Decimal
mark_price: Decimal
funding_rate_source: FundingRateSource
mark_price_source: FundingMarkPriceSource
```

Validation must require exact enum instances, not strings.

Update all tests and call sites.

Within one replay:

- all funding observations must share one exact `FundingRateSource`;
- all must share one exact `FundingMarkPriceSource`;
- their category/symbol must match source config and candles.

Extend `OhlcReplayResult` with:

```text
funding_rate_source: FundingRateSource | None
funding_mark_price_source: FundingMarkPriceSource | None
```

The fields are derived from retained observations and independently audited. Both are `None` when no funding observations exist.

## Task 2 — Frozen scenario catalog

Create:

```text
src/bybit_grid/backtest/ohlc_replay/scenarios.py
```

Add exact frozen dataclasses/enums for scenario definitions. Every scenario must include:

```text
scenario_id
scenario_version
mode: fixed_replay | ambiguity_envelope
config
entry_time_ms
candles: tuple[OhlcCandle1m, ...]
funding_observations: tuple[FundingObservation, ...]
path_policies for fixed replay, otherwise None
max_exact_ambiguous_candles for envelope, otherwise None
expected guardrail/semantic fields
```

No wall-clock data, random values or machine-specific paths.

Define exactly these 24 scenario IDs in this order:

```text
01_flat_no_ambiguity
02_open_equals_high_duplicate_node
03_low_equals_close_duplicate_node
04_single_candle_path_insensitive
05_single_candle_path_sensitive_long
06_single_candle_path_sensitive_short
07_equal_pnl_different_nested_ledger
08_two_candle_four_assignments
09_gap_up_preserved
10_gap_down_preserved
11_low_price_grid
12_tight_high_price_grid
13_positive_funding_long
14_positive_funding_short
15_negative_funding_long
16_flat_position_funding_zero
17_two_funding_boundaries
18_lower_termination_first_candle
19_upper_termination_first_candle
20_termination_ignores_later_candles
21_cycle_count_envelope_one_to_two
22_bybit_source_enum_contract
23_lower_only_termination_guardrail
24_upper_only_termination_guardrail
```

Required catalog invariants:

- IDs unique and exact order;
- count exactly 24;
- all categories `linear`;
- all symbols stripped and consistent inside a scenario;
- all candles closed/contiguous;
- scenario 07 has equal top-level PnL under its compared paths but different nested ledger/state;
- scenario 08 has two ambiguous candles and four exact assignments;
- scenario 21 has `completed_cycle_count_min=1`, `completed_cycle_count_max=2`;
- termination scenarios stop later generated events;
- low/tight scenarios preserve canonical Decimal levels;
- `22_bybit_source_enum_contract` uses `CandleSource.bybit_trade_kline_1m`, `FundingRateSource.bybit_funding_history`, and `FundingMarkPriceSource.bybit_mark_price_kline_1m`, but is clearly documented as a synthetic fixture of the source contract, not downloaded market evidence.

## Task 3 — Canonical persisted evidence module

Create:

```text
src/bybit_grid/backtest/ohlc_replay/evidence.py
```

Reuse without changing accepted Gate 6A serialization:

```text
bybit_grid.backtest.neutral_grid.serialization.normalize
canonical_json_bytes
canonical_sha256
```

Implement strict JSON parsing locally or through a clearly shared helper. It must:

- reject duplicate JSON keys;
- reject all JSON float tokens, including exponent notation;
- reject NaN/Infinity/-Infinity;
- reject blank JSONL lines;
- require final newline;
- require canonical bytes exactly equal to regenerated canonical bytes;
- preserve exact bool/int/string/Decimal-as-string identity.

Do not weaken or modify the accepted neutral-grid evidence checker.

## Task 4 — Canonical evidence records

Persist enough information to reconstruct every result from scratch.

### `scenario_inputs.jsonl`

One row per scenario containing normalized full scenario definition and:

```text
scenario_id
scenario_version
scenario_input_sha256
mode
scenario
```

### `fixed_replay_results.jsonl`

One row per fixed replay scenario:

```text
scenario_id
scenario_input_sha256
result_sha256
result_audit_passed_bool
normalized_result
```

### `envelope_results.jsonl`

One row per envelope scenario:

```text
scenario_id
scenario_input_sha256
envelope_sha256
envelope_audit_passed_bool
normalized_envelope
```

### Flattened evidence

Create:

```text
generated_replay_events.jsonl
state_machine_ledger.jsonl
completed_cycles.jsonl
```

Every flattened row must include `scenario_id` and, for envelope scenarios, a deterministic `assignment_key`.

The checker must reconstruct exact expected flattened rows from fresh replay; hashes alone are insufficient.

## Task 5 — Review-pack member contract

The canonical review pack contains exactly 14 members in this exact order:

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

No extra files, duplicate names, absolute paths, backslashes or traversal paths.

## Task 6 — Atomic owner runner

Create:

```text
scripts/run_ohlc_replay_synthetic_matrix.py
```

CLI:

```text
--run-id, default ohlc_minimal_v1_synthetic
--output-root, default data/processed/ohlc_replay_runs
--report-root, default reports/ohlc_replay_runs
--fail-after-building-test-hook, test only
```

Status lifecycle:

```text
building -> complete
building -> failed
```

Rules:

1. Write canonical `building` status first.
2. Build records deterministically.
3. Write all JSON/JSONL/report files canonically.
4. Read every file back from disk using strict parsers.
5. Perform full persisted semantic audit and fresh replay.
6. Derive reproducibility audit from read-back bytes.
7. Validate exact report bytes.
8. Only then write `complete`.
9. Any exception writes stable canonical `failed` status and returns nonzero.
10. Expected failures produce one-line strict JSON, no traceback.

Run output must include record counts derived from actual rows, not only constants.

## Task 7 — Independent persisted semantic audit

For every scenario, the persisted checker must:

1. Parse the full input record with strict type/byte rules.
2. Reconstruct exact dataclasses/enums/Decimals.
3. Validate scenario catalog membership/order/version.
4. Fresh-run fixed replay or envelope enumeration.
5. Re-run `audit_ohlc_replay_result()` or `audit_minimal_path_ambiguity_envelope()`.
6. Compare complete normalized fresh result/envelope canonical bytes to persisted bytes.
7. Compare exact generated events.
8. Compare complete nested state-machine ledger rows.
9. Compare completed cycles.
10. Validate input/result/envelope SHA-256.
11. Reject missing, duplicate or extra records.
12. Reject wrong assignment keys/order.
13. Reject any funding/candle source inconsistency.
14. Re-derive all scenario semantic flags and counts.

Hash verification is necessary but not sufficient.

## Task 8 — Contract/reproducibility audits and reports

### `ohlc_replay_contract_audit.json`

Exact key set and exact booleans, including:

```text
contract_audit_ok
closed_contiguous_1m_enforced_bool
minimal_path_policies_frozen_bool
funding_before_price_enforced_bool
funding_source_provenance_enforced_bool
strict_snapshot_identity_enforced_bool
fresh_nested_replay_enforced_bool
exact_cartesian_enumeration_enforced_bool
canonical_byte_identity_enforced_bool
no_live_execution_bool
```

### `scenario_audit.json`

Must include exact counts, failures list and derived booleans for all catalog invariants. No claimed boolean may be hard-coded without derivation.

### `reproducibility_audit.json`

Must derive:

```text
canonical_serialization_version
same_inputs_same_bytes_bool
same_inputs_same_hashes_bool
same_replay_outputs_same_bytes_bool
machine_specific_fields_present_bool=false
wall_clock_fields_present_bool=false
reproducibility_audit_ok=true
```

### Reports

Generate reports from exact deterministic builder functions:

```text
build_ohlc_replay_report(...)
build_risk_budget_readiness_report(...)
```

The checker requires exact byte equality. Substring checks are forbidden.

Risk report must preserve all false guardrails and state clearly:

```text
minimal paths are not complete intrabar bounds
real Bybit batch integration not yet proven
funding coverage not yet proven
risk budget 5 USDT not proven
parameter selection not authorized
live not authorized
```

## Task 9 — Manifest contract

Builder creates exact canonical manifest with no self-hash.

Exact keys:

```text
review_pack_schema_version
manifest_hash_policy
review_phase
run_id
ohlc_replay_contract_version
scenario_version
canonical_serialization_version
evidence_type_contract_version
canonical_scenario_count
fixed_replay_scenario_count
envelope_scenario_count
risk_budget_proven_bool
parameter_selection_authorized_bool
live_authorized_bool
members
sha256
```

Requirements:

- exact key set, no extra keys;
- exact types, no bool/int or int/float aliases;
- exact member list/order;
- `review_pack_manifest.json` absent from `sha256`;
- `sha256` keys exactly equal other 13 members;
- each hash lowercase 64-character hex;
- manifest bytes canonical;
- all non-manifest hashes verified.

## Task 10 — Builder/checker CLI

Create:

```text
scripts/make_ohlc_replay_review_pack.py
scripts/check_ohlc_replay_review_pack.py
```

Builder CLI:

```text
--run-id
--output-root
--report-root
--output
--pack-path alias
```

Checker CLI:

```text
--zip
--run-id
positional ZIP alias for compatibility
```

Expected operator failures emit one strict JSON object and no traceback.

ZIP creation must be atomic through a temporary file in the destination directory.

## Task 11 — Adversarial regression tests

Create:

```text
tests/test_sprint_06_2b_persisted_ohlc_evidence.py
```

Tests must be fully synthetic and use `tmp_path`.

At minimum cover:

1. Exact 24-scenario catalog and ID order.
2. Funding source enums reject strings and mixed sources.
3. Runner `building -> complete`.
4. Deliberate runner failure ends `failed`.
5. Happy-path pack builder/checker.
6. Exact 14 members and 13 non-manifest hashes.
7. Manifest extra key rejected after rehash.
8. Manifest bool/int and int/float aliases rejected.
9. Duplicate JSON key rejected.
10. JSON float/nonfinite token rejected.
11. Noncanonical JSON/JSONL bytes rejected.
12. Input candle/path/funding tamper rejected after rehash.
13. Equal-PnL alternate nested result substitution rejected after rehash.
14. Generated event tamper rejected after rehash.
15. Ledger price/fee/sequence tamper rejected after rehash.
16. Completed-cycle tamper rejected after rehash.
17. Envelope aggregate/assignment tamper rejected after rehash.
18. Missing/duplicate/extra scenario records rejected.
19. Contradictory or extra report text rejected after rehash.
20. Missing/failed status rejected by builder.
21. Missing ZIP returns strict JSON without traceback.
22. No generated/binary artifacts committed in deterministic source areas only.
23. No live/private API/Telegram additions.

For semantic tamper tests, recompute the affected manifest member hash. Rejection must come from semantic/fresh-replay validation, not a stale hash mismatch.

## Task 12 — Documentation

Update:

```text
docs/ohlc_minimal_path_replay_contract_v1.md
```

Add a Sprint 06.2B section documenting:

- frozen catalog;
- funding source provenance;
- canonical persisted evidence;
- fresh replay chain;
- pack contract;
- all remaining limitations and false guardrails.

Do not rename the existing document unless required; the contract identifier is versioned inside evidence.

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_2a_ohlc_minimal_path_replay.py -q
python -m pytest tests/test_sprint_06_2a_1_ohlc_replay_provenance_audit_and_envelope_closure.py -q
python -m pytest tests/test_sprint_06_2a_2_strict_snapshot_identity_and_funding_provenance.py -q
python -m pytest tests/test_sprint_06_2b_persisted_ohlc_evidence.py -q
python -m pytest -q
ruff check .
git diff --check, only when Git is available
```

Codex must not generate the final owner run or final ZIP.

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live audit passes
24 frozen scenarios
canonical persisted input evidence
fixed replay and envelope evidence fresh-reconciled
all generated events/ledger/cycles exact-reconciled
funding source provenance exact
atomic complete/failed lifecycle
14 unique pack members
13 verified non-manifest hashes
manifest exact-key/self-excluded contract
canonical JSON/JSONL/report bytes
semantic tamper rejected after rehash
risk_budget_proven_bool=false
parameter_selection_authorized_bool=false
live_authorized_bool=false
sufficient_for_bybit_batch_integration_bool=true
review_pack_ok=true
```

## Required Codex return

Return text only:

```text
commit hash, when available
changed text files
git diff --stat, when available
numeric environment output
pip check output
no-live audit output
focused 06.2A/06.2A.1/06.2A.2 output
focused 06.2B output
full pytest output
Ruff output
git diff --check/status, when available
scenario catalog summary
funding-source provenance summary
persisted evidence member/count summary
fresh replay reconciliation summary
semantic tamper-test summary
atomic lifecycle summary
all guardrail values
known remaining limitations
```

Do not return or commit binary/generated evidence files.
