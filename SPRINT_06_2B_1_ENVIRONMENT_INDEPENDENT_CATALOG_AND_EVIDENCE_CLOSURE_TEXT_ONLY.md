# Sprint 06.2B.1 — Environment-Independent Hygiene, Frozen Scenario Semantics and Persisted Replay Audit Closure

## PM decision

Sprint 06.2B is on HOLD. The owner run failed because a pytest test unconditionally executed `git ls-files` even though Git is optional and unavailable in the owner environment.

PM review also found that several frozen scenario names do not match their actual replay behavior and that the current scenario audit contains hard-coded claims. This sprint closes all of those defects together.

Do not implement Sprint 06.3 or real Bybit batch integration in this commit.

## Text-only rule

Codex may modify only repository text files:

```text
.py
.md
.gitignore
```

Do not add or commit:

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

Temporary generated files inside pytest `tmp_path` are allowed.

Codex must not generate the final owner pack.

## Frozen economic semantics — do not change

Do not change accepted Gate 6A / Sprint 06.2A.2 behavior:

```text
Decimal neutral-grid accounting
canonical geometric N cells -> N+1 levels
open-start / closed-end crossing
one-way signed position accounting
weighted average entry
realized/unrealized PnL
adjacent cycle pairing
fee calculation
funding formula/sign
termination and slippage accounting
OHLC = open -> high -> low -> close
OLHC = open -> low -> high -> close
consecutive duplicate-node removal
previous close -> next open gap preservation
funding before later candle price path
closed contiguous 1m validation
exact 2^k minimal-path enumeration
strict replay snapshot identity
```

No parameter search, historical backtest, liquidation model, native quantity mapping, private API, Telegram, or live execution.

## Versioning

The previous v1 evidence was not accepted and no canonical owner review pack was produced. Because scenario definitions materially change, use new evidence identifiers:

```text
OHLC_REPLAY_CONTRACT_VERSION = ohlc_minimal_path_replay_contract_v2
SCENARIO_VERSION = ohlc_minimal_path_scenarios_v2
RUN_ID = ohlc_minimal_v2_synthetic
REVIEW_PACK_SCHEMA_VERSION = ohlc_minimal_path_review_pack_v2_semantic_replay
MANIFEST_HASH_POLICY = self_excluded_v1
EVIDENCE_TYPE_CONTRACT_VERSION = strict_json_type_identity_v1
CANONICAL_SERIALIZATION_VERSION = neutral_grid_canonical_json_v1
REVIEW_PHASE = ohlc_synthetic_evidence_complete
DEFAULT_PACK = pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic.zip
CANONICAL_SCENARIO_COUNT = 24
```

Keep all risk, parameter-selection, profitability and live guardrails false.

## Task 1 — Remove the Git dependency from pytest

Replace `test_no_generated_binary_artifacts_committed()`.

It must not:

```text
call git
require .git
inspect untracked operator artifacts at repository root
scan root data/ or reports/
```

Inspect only deterministic source-controlled areas:

```text
src/
scripts/
tests/
docs/
config/
```

Forbidden suffixes there:

```text
.zip
.parquet
.jsonl
.db
.sqlite
.sqlite3
.pyc
.pyo
```

Also reject cache/packaging directories in those roots:

```text
__pycache__
.pytest_cache
.ruff_cache
*.egg-info
```

Add a pure helper that accepts an arbitrary root so it can be tested with `tmp_path`.

Required tests:

1. Passes when Git is absent from PATH.
2. Passes when `.git` is absent.
3. Ignores a root-level operator ZIP/JSONL.
4. Rejects a forbidden file under `src/`.
5. Rejects an `.egg-info` directory under a deterministic source root.

Do not solve this by skipping the test when Git is missing.

## Task 2 — Make scenario definitions immutable and self-validating

Update `src/bybit_grid/backtest/ohlc_replay/scenarios.py`.

`OhlcReplayScenario` must validate in `__post_init__`:

```text
exact scenario_id/scenario_version str types
stripped non-empty scenario_id
exact ScenarioMode enum
exact NeutralGridConfig
entry_time_ms exact int, not bool
candles exact tuple of exact OhlcCandle1m
funding_observations exact tuple of exact FundingObservation
fixed_replay => path_policies exact tuple, one per candle, cap is None
ambiguity_envelope => path_policies is None, cap exact int >= 0
expected semantics immutable and canonical-serializable
```

Do not retain a mutable plain dict inside the frozen scenario. Use an immutable typed dataclass or `MappingProxyType` with exact validation.

## Task 3 — Correct the frozen scenario fixtures

Keep the exact 24 IDs and order, but correct their definitions so names match behavior.

Use these known-good fixtures as minimum guidance:

### Scenario 04 — path insensitive

Use ambiguity-envelope mode with one candle:

```text
open=100 high=102 low=98 close=100
```

Both minimal paths must be enumerated and `path_sensitive_bool=false` must be derived.

### Scenario 05 — path-sensitive long

Use a fixture such as:

```text
open=92 high=96 low=90 close=92
```

Both assignments must end non-negative with at least one positive long exposure, and material outcome/cycle evidence must differ between paths.

### Scenario 06 — path-sensitive short

Use a fixture such as:

```text
open=100 high=110 low=100 close=110
```

Both assignments must end with negative short exposure and material outcome/cycle evidence must differ between paths.

### Scenario 07 — exact equal PnL, different nested ledger

Use:

```text
config: lower=80 upper=120 base=100 cells=6 quantity=0.01
candle: open=94 high=96 low=82 close=92
```

Required exact invariants:

```text
OHLC final_total_pnl_usdt == OLHC final_total_pnl_usdt
full nested state_machine_result differs
ledger differs
```

Do not use tolerance for the PnL equality.

### Scenario 08 — two ambiguous candles

Must derive exactly four unique Cartesian assignments.

### Funding scenarios 13–17

They must exercise real signed exposure at funding boundaries.

Known-good long fixture before the second-candle boundary:

```text
candle 1: open=100 high=100 low=98 close=98
candle 2: flat at 98
policy: OHLC
```

Known-good short fixture:

```text
candle 1: open=100 high=106 low=100 close=106
candle 2: flat at 106
policy: OLHC
```

Required derived checks:

```text
13 positive funding + long position -> funding PnL < 0
14 positive funding + short position -> funding PnL > 0
15 negative funding + long position -> funding PnL > 0
16 flat position at funding -> funding PnL == 0
17 exactly two funding ledger events at two boundaries, with expected signs derived from positions/rates
```

Scenario 13/14/15 must not have zero cumulative funding PnL.

### Scenario 21 — cycle count envelope 1 to 2

Use the known-good fixture:

```text
config: lower=80 upper=120 base=100 cells=6 quantity=0.01
candle: open=98 high=115 low=96 close=107.4
```

Fresh enumeration must derive:

```text
completed_cycle_count_min = 1
completed_cycle_count_max = 2
```

### Scenario 22

Must use exactly:

```text
CandleSource.bybit_trade_kline_1m
FundingRateSource.bybit_funding_history
FundingMarkPriceSource.bybit_mark_price_kline_1m
```

It remains a synthetic fixture of the source contract, not downloaded evidence.

### Termination/gap/low-price/tight-range scenarios

Derive and verify their named semantics rather than assuming them.

## Task 4 — Replace hard-coded scenario audit claims with derived evidence

Remove the current hard-coded `build_scenario_audit()` claims.

Implement a deterministic derived audit, for example:

```text
derive_scenario_audit(catalog, replay_records)
```

It must fresh-run every scenario and derive at minimum:

```text
scenario count/order/unique IDs
mode contract
all category/symbol/source consistency
closed contiguous candle status
path assignment count and uniqueness
path-sensitive/path-insensitive behavior
exact equal-PnL/different-ledger behavior for scenario 07
gap preservation for 09/10
canonical level preservation for 11/12
funding event count, signed position before funding and funding PnL sign for 13–17
termination reason and ignored later candles for 18–20
cycle min/max for 21
Bybit source enum provenance for 22
one-sided termination guardrails for 23/24
all risk/selection/live guardrails
```

Persist:

```text
scenario_checks_by_id
failures
scenario_audit_ok
```

Every success boolean must be computed from replay/evidence. No claimed scenario semantic may be a literal `True` without computation.

The audit must compare computed values to each scenario's immutable expected contract and fail closed on any mismatch.

## Task 5 — Independently reconstruct persisted input records

The current checker must not rely only on regenerating `build_records()` from the global catalog.

Implement strict deserialization from each row of `scenario_inputs.jsonl`:

```text
deserialize_scenario_record(row) -> OhlcReplayScenario
```

Requirements:

```text
exact key sets
exact bool/int/string types
Decimal reconstructed only from canonical strings
enums reconstructed by exact accepted values
no unknown fields
no missing fields
scenario_input_sha256 verified
exact catalog ID/order/version membership
reconstructed normalized scenario bytes equal persisted scenario bytes
```

For every reconstructed scenario:

1. Fresh-run fixed replay or envelope.
2. Re-run the in-memory audit.
3. Reconcile complete normalized result/envelope.
4. Reconcile generated replay events.
5. Reconcile complete nested state-machine ledger.
6. Reconcile completed cycles.
7. Reconcile assignment keys/order.
8. Verify all result/envelope hashes.
9. Reject missing, duplicate or extra records.

Comparing the pack to `build_records()` may remain an additional check, but it is not a substitute for persisted-input reconstruction.

## Task 6 — Make status lifecycle fail-closed

`complete` must be written last.

Required lifecycle:

```text
write building
build non-status artifacts
write/read back canonical artifacts
reconstruct persisted scenarios
fresh replay and full semantic audit
derive reproducibility audit
validate exact reports
write complete status last
```

On any normal exception:

```text
write failed status
return nonzero
never leave complete
```

Do not include `review_pack_ok=true` in the run status before a pack is actually built. Use an evidence/run audit field if needed.

Add tests for:

```text
building visible during implementation
complete written only after every required artifact exists and validates
deliberate post-write audit failure -> failed
missing artifact -> builder refusal
failed/building status -> builder refusal
```

## Task 7 — Derive reproducibility audit from actual bytes

Do not write reproducibility booleans as constants.

At minimum:

1. Build the canonical in-memory records twice.
2. Compare per-member bytes and hashes.
3. Read persisted bytes back with strict parsers.
4. Reconstruct scenarios and replay again.
5. Compare persisted/fresh output bytes.
6. Derive machine/wall-clock field absence from recursive key inspection.

Only then set:

```text
reproducibility_audit_ok=true
```

## Task 8 — Complete the adversarial regression suite

Create or extend:

```text
tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py
```

Tests must be synthetic and use `tmp_path`.

Required coverage:

1. Git unavailable and `.git` absent.
2. Root operator ZIP ignored; forbidden source ZIP rejected.
3. Exact 24 IDs/order and immutable scenario definitions.
4. Scenario 04 path-insensitive derived.
5. Scenario 05 long path-sensitive derived.
6. Scenario 06 short path-sensitive derived.
7. Scenario 07 exact equal PnL and different nested result.
8. Scenario 08 exact four assignments.
9. Scenario 13/14/15 non-zero correct funding signs.
10. Scenario 16 flat funding zero.
11. Scenario 17 exactly two funding events and derived signs.
12. Scenario 21 cycle min=1/max=2.
13. Scenario 22 exact source enums.
14. Scenario audit rejects any expected-semantics mismatch.
15. Runner building -> complete.
16. Deliberate late failure -> failed, never complete.
17. Pack builder/checker happy path.
18. Exact 14 members / 13 hashes.
19. Persisted input tamper rejected after rehash.
20. Fixed nested-result substitution rejected after rehash.
21. Generated-event tamper rejected after rehash.
22. Ledger price/fee/sequence tamper rejected after rehash.
23. Completed-cycle tamper rejected after rehash.
24. Envelope aggregate/assignment tamper rejected after rehash.
25. Missing/duplicate/extra records rejected after rehash.
26. Manifest key/type/guardrail tamper rejected after rehash.
27. Report contradiction/extra text rejected after rehash.
28. Missing ZIP returns strict JSON without traceback.
29. No live/private API/Telegram additions.

A semantic tamper test must recompute the affected member hash in the manifest. Rejection must not rely on a stale hash mismatch.

## Task 9 — CLI and final v2 pack

Keep CLI compatibility:

Runner:

```text
--run-id
--output-root
--report-root
--fail-after-building-test-hook
```

Builder:

```text
--run-id
--output-root
--report-root
--output
--pack-path alias
```

Checker:

```text
--zip
--run-id
positional ZIP alias
```

Expected operator failures must emit one strict JSON object and no traceback.

Final owner artifacts use:

```text
run_id = ohlc_minimal_v2_synthetic
pack = pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic.zip
```

## Task 10 — Documentation

Update:

```text
docs/ohlc_minimal_path_replay_contract_v1.md
```

Document:

```text
v2 frozen scenario semantics
why Git is not a test dependency
persisted input deserialization and fresh replay chain
complete-written-last lifecycle
all remaining false guardrails
minimal paths are not complete intrabar bounds
```

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_2a_ohlc_minimal_path_replay.py -q
python -m pytest tests/test_sprint_06_2a_1_ohlc_replay_provenance_audit_and_envelope_closure.py -q
python -m pytest tests/test_sprint_06_2a_2_strict_snapshot_identity_and_funding_provenance.py -q
python -m pytest tests/test_sprint_06_2b_persisted_ohlc_evidence.py -q
python -m pytest tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py -q
python -m pytest -q
ruff check .
git diff --check only when Git is available
```

The focused 06.2B suite must pass when:

```text
Git executable is absent
.git directory is absent
root-level operator ZIPs exist
```

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live audit passes
no test requires Git
24 exact scenario IDs
all named scenario semantics derived and passing
scenario 13/14/15 funding PnL non-zero with correct signs
scenario 07 exact equal PnL with different nested result
scenario 21 cycle min=1/max=2
persisted inputs independently deserialized and replayed
all events/ledger/cycles exact-reconciled
complete status written last
14 unique pack members
13 verified non-manifest hashes
semantic tamper rejected after rehash
risk_budget_proven_bool=false
parameter_selection_authorized_bool=false
live_authorized_bool=false
review_pack_ok=true
```

## Required Codex return

Return text only:

```text
commit hash when available
changed text files
git diff --stat when available
numeric environment output
pip check output
no-live audit output
focused test outputs
full pytest output
Ruff output
Git-independent hygiene summary
scenario semantics summary for all 24 IDs
funding scenarios 13–17 measured summary
scenario 07 measured equality/difference summary
scenario 21 measured cycle bounds
persisted deserialization/fresh replay summary
atomic lifecycle summary
semantic tamper-test summary
all guardrail values
known remaining limitations
```

Do not return or commit generated evidence or ZIP files.
