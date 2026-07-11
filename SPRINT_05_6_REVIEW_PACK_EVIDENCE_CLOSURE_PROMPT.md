# Sprint 05.6 — Review-Pack Evidence Closure

## PM decision

Sprint 05.5 functional code is accepted. Gate 5A remains open only because the review artifact does not carry all newly required evidence and two required lifecycle tests are missing.

This is a narrow closeout hotfix. **Do not start Sprint 06.**

Reviewed scoring run:

```text
scoring_cost_v6_123x90
```

Reported owner commit before this hotfix:

```text
de42db62fc646c330d9e0d4279783e1ccc6161a7
```

## Safety and scope rules

- No live trading.
- No create/close/order/Telegram code.
- No Bybit API calls.
- No range, outcome, grain, or scoring rebuild should be required.
- Do not modify score formulas, weights, cost formulas, fee data, walk-forward splits, or row-level scoring outputs.
- Preserve:
  - `risk_budget_proven_bool=false`;
  - `sufficient_for_parameter_selection_bool=false`;
  - canonical score version `v3`;
  - grain contract version `grain_contract_v3_whole_row`.
- Reuse the completed local run `scoring_cost_v6_123x90`; regenerate only the review pack after code/tests pass.

## Observed evidence gaps

The code writes:

```text
outcome_category_normalization_audit.json
fee_join_context_audit.json
```

but the current review ZIP contains neither file. Therefore the pack cannot independently prove the two new Sprint 05.5 audit requirements.

The current manifest also writes a hash for `review_pack_manifest.json`, then rewrites the manifest. That stored self-hash is stale. The checker skips it, so the checker passes despite a misleading manifest entry.

The test suite also lacks explicit regression tests for:

- scoring status becoming `failed` after a deliberate build exception;
- scoring status becoming `complete` after success;
- pack builder refusing a non-complete run.

## 1. Include both new audits in the canonical review pack

Update `scripts/check_scoring_review_pack.py` `REQUIRED` and the pack builder flow so these files are mandatory:

```text
outcome_category_normalization_audit.json
fee_join_context_audit.json
```

The resulting pack should contain 29 members total: the existing 27 plus these 2.

`make_scoring_review_pack.py` must fail with strict JSON before ZIP creation if either file is missing.

## 2. Validate category normalization evidence

The checker must require all of the following from `outcome_category_normalization_audit.json`:

```text
category_normalization_ok == true
rows_before == rows_after
normalized_categories == ["linear"]
default_category == "linear"
category_source in {"project_scope_default", "source_column"}
```

If `category_source == "source_column"`, source categories may differ only by casing/whitespace before normalization but must normalize to exactly `linear`.

Cross-check the category audit against `outcome_grain_contract_audit.json`:

```text
category_present_by_grain == true for all four grains
category_values_by_grain == ["linear"] for all four grains
null_required_column_counts_by_grain[*]["category"] == 0
```

Any mismatch must set `review_pack_ok=false` with a named consistency error.

## 3. Validate fee-join context evidence

The checker must require exactly these contexts in `fee_join_context_audit.json`:

```text
expanded_scoring_input
cost_summary_event_horizon_grid
```

For each context require:

```text
fee_join_ok == true
input_rows == output_rows
scoring_categories == ["linear"]
missing_fee_row_count == 0
symbols_missing_fee_rates == []
scoring_symbol_count > 0
fee_symbol_count >= scoring_symbol_count
```

Cross-check expected row counts:

```text
expanded_scoring_input.input_rows == 241155
cost_summary_event_horizon_grid.input_rows == 80385
```

Do not hardcode those row counts in reusable library code. The checker may reconcile them against:

- `outcome_grain_audit.json.rows.expanded_scoring_input`;
- `cost_summary_audit.json.cost_summary_source_rows`.

Cross-check fee coverage:

```text
fee_coverage_audit.json.fee_coverage_ok == true
fee_coverage_audit.json.fee_coverage_rate == 1.0
```

## 4. Fix manifest hash semantics

Do not attempt to self-hash a manifest that contains its own hash.

Adopt this explicit policy:

```json
{
  "review_pack_schema_version": "scoring_review_pack_v4_audit_complete",
  "manifest_hash_policy": "self_excluded_v1",
  "sha256": {
    "every_required_member_except_review_pack_manifest.json": "..."
  }
}
```

Requirements:

- `review_pack_manifest.json` must not appear in its own `sha256` mapping.
- `sha256` keys must equal exactly `REQUIRED - {"review_pack_manifest.json"}`.
- Checker verifies every listed hash.
- Checker fails when any required member is absent from the hash map.
- Checker fails when any unexpected hash key is present.
- Checker fails when any member is modified after manifest creation.
- Keep ZIP member allowlisting and path traversal checks.

## 5. Strengthen preflight

Before building the ZIP, `make_scoring_review_pack.py` must require:

- `scoring_run_status.status == "complete"`;
- matching `scoring_run_id`;
- `cost_summary_audit_ok == true`;
- `scoring_semantics_audit_ok == true`;
- `outcome_category_normalization_audit.category_normalization_ok == true`;
- both fee-join contexts exist and have `fee_join_ok == true`;
- every required pack artifact exists.

Expected operator failures must print strict JSON and exit non-zero without traceback.

## 6. Add the missing lifecycle regression tests

Add tests covering at minimum:

1. `build_scoring_dataset()` writes `status=building` before work, then `status=failed` after a deliberate exception.
2. A successful controlled build writes `status=complete` only after all required artifacts are written.
3. `make_scoring_review_pack.py` refuses `building` status.
4. It refuses `failed` status.
5. It refuses missing category-normalization audit.
6. It refuses missing fee-join-context audit.
7. Checker requires and validates both new audits.
8. Checker detects a tampered required member by hash mismatch.
9. Manifest has no self-hash and has complete hashes for all other members.
10. Existing strict `zip_not_found` behavior remains.
11. No live/create/close/order/Telegram additions.

Use temporary directories and synthetic tiny artifacts. Do not depend on owner market data in unit tests.

## 7. Keep checker phase semantics explicit

The current pack is not a parameter-selection pack. Preserve and validate:

```text
walk_forward_scope = prototype_90d
sufficient_for_parameter_selection_bool = false
sufficient_for_state_machine_engineering_bool = true
risk_budget_proven_bool = false
```

Add to the manifest:

```json
{
  "review_phase": "state_machine_engineering_ready",
  "parameter_selection_authorized_bool": false,
  "live_authorized_bool": false
}
```

The checker must validate those values for schema v4.

## 8. Owner commands

Run:

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

The scoring data does not need to be rebuilt. Confirm the two local audits exist:

```powershell
Get-Content data/processed/scoring_runs/scoring_cost_v6_123x90/outcome_category_normalization_audit.json
Get-Content data/processed/scoring_runs/scoring_cost_v6_123x90/fee_join_context_audit.json
```

Regenerate and check the pack:

```powershell
python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v6_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v6_123x90.zip `
  --scoring-run-id scoring_cost_v6_123x90
```

## 9. Acceptance criteria

```text
all tests passed
ruff passed
no-live audit passed
review_pack_schema_version = scoring_review_pack_v4_audit_complete
manifest_hash_policy = self_excluded_v1
review_phase = state_machine_engineering_ready
parameter_selection_authorized_bool = false
live_authorized_bool = false
review pack member count = 29
outcome_category_normalization_audit.json present
category_normalization_ok = true
normalized_categories = [linear]
rows_before = rows_after
fee_join_context_audit.json present
fee join contexts = exactly expanded_scoring_input + cost_summary_event_horizon_grid
both fee_join_ok = true
both input_rows = output_rows
missing_fee_row_count = 0 for both
expanded fee join rows reconcile to 241155
cost-summary fee join rows reconcile to 80385
scoring_run_status = complete
risk_budget_proven_bool = false
sufficient_for_parameter_selection_bool = false
all non-manifest hashes verified
manifest contains no self-hash
review_pack_ok = true
```

## 10. Required return to PM

Return text:

```text
commit hash
changed files
full pytest output
focused new-test output
ruff output
no-live audit output
category normalization audit summary
both fee-join context summaries
manifest hash-policy summary
scoring status summary
review-pack checker JSON
risk_budget_proven_bool
sufficient_for_parameter_selection_bool
```

Upload only:

```text
pm_review_pack_scoring_scoring_cost_v6_123x90.zip
```

Do not upload `.env`, market data, outcomes, scoring datasets, caches, or the full repository archive.
