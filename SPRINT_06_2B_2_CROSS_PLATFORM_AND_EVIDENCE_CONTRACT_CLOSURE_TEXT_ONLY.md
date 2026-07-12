# Sprint 06.2B.2 — Cross-Platform Hygiene and Evidence Contract Completion

## PM decision

Sprint 06.2B.1 is on HOLD. The owner Windows run failed because the hygiene helper returned `src\\bad.zip` instead of the canonical evidence path `src/bad.zip`.

Independent PM review also found that several requirements from the 06.2B.1 prompt were not implemented. Close all items in this one patch. Do not start real Bybit batch integration or historical parameter selection.

## Text-only rule

Codex may modify only repository text files:

```text
.py
.md
.gitignore
```

Do not add or commit generated evidence, ZIP, JSONL, Parquet, CSV, databases, market data, reports, `.env`, secrets, or binary fixtures. Temporary files under pytest `tmp_path` are allowed.

Codex must return text only and must not generate the owner pack.

## Frozen economics — do not change

Do not modify accepted behavior:

```text
Decimal neutral-grid accounting
canonical N-cell / N+1-level geometry
open-start / closed-end crossing
one-way signed position accounting
weighted average entry
realized/unrealized PnL
adjacent cycle pairing
fees and funding formulas
termination and slippage
OHLC = open -> high -> low -> close
OLHC = open -> low -> high -> close
consecutive duplicate-node removal
previous close -> next open gap preservation
funding before later-candle price events
closed contiguous 1m validation
exact 2^k minimal-path enumeration
strict replay snapshot identity
```

Keep the current v2 evidence identifiers because no canonical v2 owner pack has yet been accepted:

```text
OHLC_REPLAY_CONTRACT_VERSION = ohlc_minimal_path_replay_contract_v2
SCENARIO_VERSION = ohlc_minimal_path_scenarios_v2
RUN_ID = ohlc_minimal_v2_synthetic
REVIEW_PACK_SCHEMA_VERSION = ohlc_minimal_path_review_pack_v2_semantic_replay
DEFAULT_PACK = pm_review_pack_ohlc_replay_ohlc_minimal_v2_synthetic.zip
CANONICAL_SCENARIO_COUNT = 24
```

All risk, selection, profitability, native-equivalence, real-batch and live guardrails remain false.

---

## Task 1 — Canonical cross-platform hygiene paths

Update `find_source_hygiene_violations(root)`.

Requirements:

1. Every returned path uses `/` on every OS. Use `path.relative_to(root).as_posix()` or an equivalent canonical conversion.
2. Sort by canonical POSIX string.
3. Suffix matching is case-insensitive: `.ZIP`, `.JsonL`, `.PYC`, etc. must be rejected under deterministic source roots.
4. Root-level operator ZIP/JSONL remains ignored.
5. `.git` and the Git executable remain irrelevant.
6. Reject forbidden packaging/cache directories using canonical POSIX paths.

Required Windows-facing regression:

```text
actual result == ["src/bad.zip"]
not ["src\\bad.zip"]
```

Add a focused test that also checks uppercase forbidden suffixes.

---

## Task 2 — Correct run-status semantics

The prior prompt explicitly prohibited `review_pack_ok=true` before a pack exists.

Remove `review_pack_ok` from `ohlc_replay_run_status.json` and from the pre-pack OHLC run report.

Use a field such as:

```text
evidence_run_audit_ok = true
```

only after all persisted run artifacts are written, read back and semantically audited.

Required complete status exact keys should be versioned and minimal, for example:

```text
run_id
status
scenario_count
fixed_replay_result_count
envelope_result_count
evidence_run_audit_ok
```

Do not claim pack validity in run status. Only the pack builder/checker may return `review_pack_ok=true`.

Add tests proving:

- building status has no completion claim;
- complete status is written last;
- complete status has no `review_pack_ok` key;
- failed status never contains complete/evidence-success claims.

---

## Task 3 — Derive reproducibility audit from actual work

Replace literal reproducibility booleans.

Implement a deterministic function such as:

```text
derive_reproducibility_audit(...)
```

It must actually:

1. build canonical non-reproducibility artifacts twice;
2. compare bytes for every member;
3. compare SHA-256 values for every member;
4. strict-parse persisted JSON/JSONL bytes;
5. reconstruct persisted scenarios;
6. fresh-replay them;
7. compare persisted and fresh result/event/ledger/cycle bytes;
8. recursively inspect keys/values for wall-clock, hostname, absolute path, PID, random UUID or other machine-specific fields;
9. derive every boolean in `reproducibility_audit.json` from those checks.

Avoid recursive self-reference by using a two-phase core-artifact builder. Do not hard-code success booleans.

Add a regression that deliberately changes one rebuilt byte set and proves reproducibility becomes false/fails closed.

---

## Task 4 — Complete the derived scenario semantic audit

`derive_scenario_audit()` must derive and persist all named semantics, not only generic count/PnL fields.

At minimum derive:

### Scenario 04

```text
assignment_count = 2
path_sensitive_bool = false
```

### Scenario 05

```text
assignment_count = 2
all_final_positions_non_negative_bool = true
positive_long_exposure_observed_bool = true
material_path_outcome_differs_bool = true
```

### Scenario 06

```text
assignment_count = 2
all_final_positions_negative_bool = true
material_path_outcome_differs_bool = true
```

### Scenario 07

```text
exact_equal_pnl_bool = true
nested_result_differs_bool = true
ledger_differs_bool = true
```

### Scenario 08

```text
assignment_count = 4
assignment keys exact, unique and ordered
```

### Scenarios 09–10

Derive from generated price events:

```text
gap_direction = up/down
gap_preserved_bool = true
previous candle close retained
next candle open retained
no interpolated synthetic price inserted between them
```

### Scenarios 11–12

Derive:

```text
canonical_levels_preserved_bool = true
state-machine levels exactly equal canonical Decimal geometry
level count = N+1
no level collapse
```

### Scenarios 13–17

Derive:

```text
funding event count
signed position before every funding event
funding rate sign
funding PnL sign
cumulative funding PnL
```

Required:

```text
13: positive funding + long -> negative, non-zero
14: positive funding + short -> positive, non-zero
15: negative funding + long -> positive, non-zero
16: flat position -> zero
17: exactly two funding events and exact per-event derived signs/positions
```

### Scenarios 18–20

Derive:

```text
termination reason
termination candle index
position flat after termination
later price/funding events absent
candles_not_processed_after_termination
```

Scenario 20 must prove at least one later candle was ignored.

### Scenario 21

```text
completed_cycle_count_min = 1
completed_cycle_count_max = 2
```

### Scenario 22

Derive and compare:

```text
CandleSource.bybit_trade_kline_1m
FundingRateSource.bybit_funding_history
FundingMarkPriceSource.bybit_mark_price_kline_1m
synthetic_fixture_of_source_contract_bool = true
real_bybit_batch_integration_proven_bool = false
```

### Scenarios 23–24

Derive:

```text
exactly one termination boundary configured
correct lower/upper termination side
state-machine two_sided_termination_configured_bool = false
risk_budget_proven_bool = false
```

### Guardrails

Do not copy guardrails from `scenario.expected` into the computed audit.

Derive available guardrails from:

- nested `SimulationResult.proof_flags`;
- envelope completeness/bound flags;
- scenario source provenance;
- the synthetic run contract.

Then compare the independently derived values to the immutable expected contract.

---

## Task 5 — Make expected semantics closed and deeply immutable

Current unknown expected keys can be silently ignored. This is forbidden.

Requirements:

1. Define the exact allowed expected-semantics keys and exact value types.
2. Reject unknown keys in `OhlcReplayScenario.__post_init__`.
3. Reject missing required guardrail keys.
4. Do not silently skip a known key in `derive_scenario_audit()`.
5. Every expected key must map to one independently computed audit field.
6. Ensure expected values are deeply immutable. A top-level mapping proxy containing mutable nested lists/dicts is not sufficient. Prefer exact scalar/tuple contracts or a frozen typed dataclass.
7. Scenario 22's `synthetic_fixture_of_source_contract_bool` must be explicitly recognized and validated.

Add tests for unknown key rejection and nested mutable value rejection.

---

## Task 6 — Independent persisted-bundle reconciliation

Retain global canonical byte comparison as an additional contract, but do not use it as the only semantic proof.

Implement an independent persisted-bundle audit that starts from strict-parsed `scenario_inputs.jsonl` and then:

1. deserializes all 24 scenarios with exact types and keys;
2. verifies ID/order/version/input hashes;
3. fresh-runs every fixed replay/envelope from those deserialized inputs;
4. independently rebuilds expected fixed-result rows;
5. independently rebuilds envelope rows and assignment order;
6. independently rebuilds flattened generated events;
7. independently rebuilds nested state-machine ledger rows;
8. independently rebuilds completed cycles;
9. checks exact record cardinality, keys, order, uniqueness and hashes;
10. compares all persisted JSONL bytes with canonical bytes rebuilt from the persisted inputs;
11. derives scenario audit from the reconstructed scenarios and reconciles it;
12. rejects missing, duplicate and extra rows.

`check_zip()` and `audit_directory()` must use this independent audit.

Do not leave `replay_records` or equivalent parameters unused.

---

## Task 7 — Complete atomic lifecycle ownership

Make `write_run()` itself own fail-closed lifecycle behavior, not only the outer CLI.

Required sequence:

```text
building
write non-status artifacts
strict read-back
persisted-input reconstruction
fresh replay/full reconciliation
derived reproducibility audit
exact report validation
complete written last
```

On any exception after building, including a late post-write audit failure:

```text
failed written last
complete absent
exception re-raised or returned to CLI
```

Add a test-only late failure hook after artifacts are written but before complete status, for example:

```text
--fail-after-artifacts-test-hook
```

Tests must cover:

- early failure after building;
- late failure after artifacts;
- missing artifact;
- building status builder refusal;
- failed status builder refusal;
- successful complete status.

---

## Task 8 — Builder verifies its own temporary ZIP

`build_zip()` must:

1. preflight complete status and all artifacts;
2. write a temporary ZIP;
3. run the full semantic `check_zip()` on the temporary ZIP;
4. atomically replace the destination only after the checker passes;
5. remove the temporary file on failure.

The builder CLI may print `review_pack_ok=true` only after this verification.

Expected operator failures must emit one strict JSON object and no traceback.

---

## Task 9 — Add the missing adversarial regression matrix

Create:

```text
tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py
```

Use synthetic `tmp_path` artifacts. Do not require owner data or Git.

Required tests include at least:

1. Windows/POSIX canonical hygiene path.
2. Uppercase forbidden suffix rejection.
3. Run status has no pre-pack `review_pack_ok`.
4. Early and late failed lifecycle.
5. Reproducibility audit is derived, not literal.
6. Scenario 05 exact long-exposure semantics.
7. Scenario 06 exact short-exposure semantics.
8. Gap-up and gap-down evidence.
9. Low/tight canonical level preservation.
10. Funding 13–17 exact event positions/signs/non-zero rules.
11. Termination 18–20 exact reason/prefix/ignored candles.
12. Scenario 22 source contract.
13. One-sided guardrails 23–24.
14. Unknown expected key rejected.
15. Mutable nested expected value rejected.
16. Persisted-input tamper rejected after rehash.
17. Fixed nested-result substitution rejected after rehash.
18. Generated-event tamper rejected after rehash.
19. Ledger price/fee/sequence tamper rejected after rehash.
20. Completed-cycle tamper rejected after rehash.
21. Envelope aggregate/assignment tamper rejected after rehash.
22. Missing/duplicate/extra row rejected after rehash.
23. Manifest key/type/guardrail tamper rejected after rehash.
24. Report contradiction/extra text rejected after rehash.
25. Reproducibility-audit tamper rejected after rehash.
26. Builder refuses missing/building/failed artifacts.
27. Builder verifies temporary ZIP before replacement.
28. Missing ZIP returns strict JSON without traceback.
29. No live/private API/Telegram additions.

For semantic-tamper tests, recompute the changed member hash in the self-excluded manifest. Rejection must not depend on a stale SHA mismatch.

---

## Task 10 — Documentation

Update:

```text
docs/ohlc_minimal_path_replay_contract_v1.md
```

Document:

- canonical POSIX evidence paths;
- run-status versus review-pack status distinction;
- independently derived reproducibility;
- complete scenario semantic checks;
- expected-key closed contract;
- persisted-input-first reconciliation;
- complete-written-last and failed-written-last lifecycle;
- unchanged minimal-path limitations and false guardrails.

---

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_2b_persisted_ohlc_evidence.py -q
python -m pytest tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py -q
python -m pytest tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py -q
python -m pytest -q
ruff check .
git diff --check only when Git is available
```

The focused suite must pass with:

```text
Git executable absent
.git directory absent
Windows path semantics
root-level operator ZIP/JSONL present
```

## Acceptance criteria

```text
all tests pass on owner Windows
Ruff passes
no-live audit passes
hygiene paths always POSIX
no test requires Git
24 exact scenarios
all named semantics independently derived
unknown expected keys rejected
all guardrails independently reconciled
run status never claims review_pack_ok
complete written last
failed written last on early and late failure
reproducibility audit derived from actual bytes/replay
persisted-input-first full reconciliation passes
14 unique pack members
13 verified non-manifest hashes
builder self-checks temporary ZIP
rehashed semantic tamper matrix rejected
risk_budget_proven_bool=false
parameter_selection_authorized_bool=false
live_authorized_bool=false
review_pack_ok=true only from verified builder/checker
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
cross-platform hygiene summary
run-status lifecycle summary
reproducibility derivation summary
24-scenario measured semantic summary
persisted-bundle reconciliation summary
semantic tamper-test matrix summary
all guardrail values
known remaining limitations
```

Do not return or commit generated evidence or ZIP files.
