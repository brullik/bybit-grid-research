# Sprint 05.6.1 — Manifest Contract Cross-Checks and Test Closure

## PM decision

The concrete Sprint 05.6 owner pack is valid: 29 members, all non-manifest hashes match, category/fee evidence passes, and the scoring run is complete.

A final narrow checker hardening is required before Sprint 06. The manifest uses `manifest_hash_policy=self_excluded_v1`, but several critical manifest claims are not explicitly validated. This sprint closes only that defect and the remaining explicit regression-test gaps.

## Safety and scope

- No live trading.
- No Bybit API calls.
- No create/close/order/cancel/position code.
- No Telegram.
- Do not change market data, ranges, outcomes, grain contents, scoring formulas, weights, costs, fee snapshot, or walk-forward splits.
- Do not rebuild market/range/outcome/scoring datasets.
- Preserve:
  - `review_pack_schema_version=scoring_review_pack_v4_audit_complete`;
  - `manifest_hash_policy=self_excluded_v1`;
  - `review_phase=state_machine_engineering_ready`;
  - `parameter_selection_authorized_bool=false`;
  - `live_authorized_bool=false`;
  - `risk_budget_proven_bool=false`;
  - `canonical_score_version=v3`;
  - `grain_contract_version=grain_contract_v3_whole_row`;
  - `sufficient_for_parameter_selection_bool=false`.

Source run:

```text
scoring_run_id = scoring_cost_v6_123x90
source_outcome_run_id = outcomes_true_fast_v4_canonical_123x90_v1
fee_snapshot_id = fee_linear_20260711T112444Z
```

## Observed defect

`scripts/check_scoring_review_pack.py` explicitly checks only a subset of top-level manifest fields. Because `review_pack_manifest.json` is excluded from the SHA-256 map, the checker must explicitly validate every critical summary claim and reconcile it to hashed evidence.

The current checker does not validate/reconcile:

```text
manifest.risk_budget_proven_bool
manifest.canonical_score_version
manifest.grain_contract_version
manifest.source_outcome_run_id
manifest.fee_snapshot_id_resolved
manifest.cost_formula_version
```

A changed manifest could therefore make a misleading top-level claim while `review_pack_ok` remains true.

## Task 1 — Define and validate the manifest contract

Update `scripts/check_scoring_review_pack.py`.

The checker must require exact values:

```text
review_pack_schema_version == scoring_review_pack_v4_audit_complete
manifest_hash_policy == self_excluded_v1
review_phase == state_machine_engineering_ready
parameter_selection_authorized_bool == false
live_authorized_bool == false
risk_budget_proven_bool == false
canonical_score_version == v3
grain_contract_version == grain_contract_v3_whole_row
scoring_run_id == requested scoring_run_id
```

Use named consistency errors, for example:

```text
manifest_risk_budget_proven_bool
manifest_canonical_score_version
manifest_grain_contract_version
manifest_source_outcome_run_id
manifest_fee_snapshot_id_resolved
manifest_cost_formula_version
```

Do not silently coerce strings such as `"false"`, `"v3 "`, or mixed-case versions.

## Task 2 — Reconcile manifest claims to hashed evidence

Require these exact reconciliations:

### Source outcome provenance

```text
manifest.source_outcome_run_id
  == outcome_source_audit.source_outcome_run_id
  == scoring_run_status.source_outcome_run_id
  == scoring_semantics_audit.source_outcome_run_id
```

All values must be non-empty strings.

### Fee snapshot provenance

```text
manifest.fee_snapshot_id_resolved
  == fee_coverage_audit.fee_snapshot_id_resolved
  == cost_model_audit.fee_snapshot_id_resolved
```

All values must be non-empty strings.

### Cost formula

```text
manifest.cost_formula_version
  == cost_model_audit.cost_formula_version
  == cost_formula_v2_asymmetric_slippage
```

### Grain contract

```text
manifest.grain_contract_version
  == outcome_grain_contract_audit.grain_contract_version
  == grain_contract_v3_whole_row
```

### Canonical score

```text
manifest.canonical_score_version
  == scoring_semantics_audit.canonical_score_version
  == v3
```

### Risk guardrail

```text
manifest.risk_budget_proven_bool is false
cost_model_audit.risk_budget_proven_bool is false
scoring_semantics_audit.risk_budget_proven_bool is false
```

Any disagreement must set `review_pack_ok=false`.

## Task 3 — Preserve hash semantics

Do not reintroduce a self-hash.

Require:

```text
sha256 keys == REQUIRED - {review_pack_manifest.json}
review_pack_manifest.json not in sha256
all listed hashes match
```

The manifest can be edited without a hash mismatch by design, so Task 1 and Task 2 are mandatory.

## Task 4 — Add manifest tamper regression tests

Extend `tests/test_sprint_05_6_review_pack_closure.py` or add a narrowly named test file.

Use the existing tiny synthetic pack helper. Add a parametrized test that mutates one manifest field at a time and proves the checker rejects at least:

1. `risk_budget_proven_bool=true`;
2. `canonical_score_version="v999"`;
3. `grain_contract_version="wrong"`;
4. mismatched `source_outcome_run_id`;
5. mismatched `fee_snapshot_id_resolved`;
6. mismatched `cost_formula_version`;
7. `parameter_selection_authorized_bool=true`;
8. `live_authorized_bool=true`.

Because the manifest is self-excluded, do not update any hashes after mutation. The failure must come from semantic validation, not hash mismatch.

## Task 5 — Close the remaining explicit regression-test gaps

Add separate tests for:

1. pack builder refuses a missing `fee_join_context_audit.json` when a valid category audit is present;
2. pack builder refuses a missing `outcome_category_normalization_audit.json` when a valid fee-join audit is present;
3. a successful minimal controlled scoring build ends with `status=complete` only after its required artifacts exist;
4. a deliberate build failure ends with `status=failed` and never leaves `status=complete`.

For the successful lifecycle test, use a tiny synthetic local fixture. Do not depend on owner market data.

A small lifecycle refactor is allowed only when needed to make the wrapper own the atomic sequence:

```text
building -> implementation/artifacts -> complete
building -> exception -> failed
```

Do not change row-level scoring semantics.

## Task 6 — Review-pack builder/checker operator behavior

Expected operator failures must remain strict JSON without traceback.

After tests pass, use the existing completed local scoring run and only regenerate the pack:

```powershell
python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v6_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v6_123x90.zip `
  --scoring-run-id scoring_cost_v6_123x90
```

Do not rebuild grains or scoring.

## Required commands

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
python -m pytest tests/test_sprint_05_6_review_pack_closure.py -q
ruff check .
```

## Acceptance criteria

```text
all tests passed
ruff passed
no-live audit passed
29 unique review-pack members
no forbidden paths
no duplicate ZIP members
manifest self-hash absent
all 28 non-manifest hashes verified
manifest risk_budget_proven_bool validated false
manifest canonical_score_version validated v3
manifest grain_contract_version validated grain_contract_v3_whole_row
source outcome provenance reconciled across manifest/audits/status
fee snapshot provenance reconciled across manifest/audits
cost formula reconciled across manifest/cost audit
missing category audit refusal has a dedicated test
missing fee-join audit refusal has a dedicated test
successful scoring lifecycle has a dedicated test
failed scoring lifecycle has a dedicated test
risk_budget_proven_bool remains false
sufficient_for_parameter_selection_bool remains false
review_pack_ok=true
```

## Required return to PM

Return text:

```text
commit hash
changed files
full pytest output
focused test output
ruff output
no-live audit output
manifest contract checks implemented
manifest tamper tests summary
successful/failed lifecycle tests summary
review-pack builder JSON
review-pack checker JSON
risk_budget_proven_bool
sufficient_for_parameter_selection_bool
```

Upload:

```text
pm_review_pack_scoring_scoring_cost_v6_123x90.zip
sprint_05_6_1_changed_files.zip
```

The changed-files ZIP should contain only modified source/test files with repository-relative paths. Do not upload `.env`, market data, outcomes, scoring datasets, caches, or the full repository.
