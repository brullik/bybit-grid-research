# Sprint 05.5 — Category Contract + Atomic Scoring Finalization

PM decision: Sprint 05.4 code is accepted, but the owner run failed in `build_outcome_scoring_dataset.py` before cost artifacts were completed. Gate 5A remains open. Do not start Sprint 06.

## Observed owner failure

`build_outcome_grains.py` succeeded with canonical row counts:

```text
event_horizon = 26795
event_horizon_grid = 80385
event_horizon_sl = 80385
expanded_scoring_input = 241155
grain_contract_audit_ok = true
cartesian_completeness_ok = true
```

But scoring failed here:

```text
cost_df = cost_df.join(fees, on=["category", "symbol"], how="left")
ColumnNotFoundError: unable to find column "category"
```

The expanded scoring input receives a fallback `category="linear"`, but `event_horizon_grid.parquet` is built before that fallback and does not contain `category`. The current grain audit reports the intended contract columns, not the actual output columns, so it did not catch the missing join key.

## Safety rules

- No live trading.
- No create/close/order/Telegram implementation.
- No Bybit API calls are needed.
- Do not rebuild ranges or outcomes.
- Preserve `risk_budget_proven_bool=false`.
- Use a new run ID; do not mutate the incomplete v5 run.

## New run ID

```text
scoring_cost_v6_123x90
```

## 1. Add canonical category normalization before grain construction

In `src/bybit_grid/research/scoring/outcome_grains.py`, add one canonical normalization function, for example:

```python
def normalize_outcome_category(
    df: pl.DataFrame,
    *,
    default_category: str = "linear",
) -> tuple[pl.DataFrame, dict[str, object]]:
    ...
```

Rules:

- If `category` exists:
  - cast to Utf8;
  - lowercase/strip;
  - reject null/empty values;
  - require the category set to be exactly `{linear}` for this project run.
- If `category` is absent:
  - add `category="linear"`;
  - record `category_source="project_scope_default"`.
- Never silently mix categories.
- Return an audit with:
  - `category_normalization_ok`;
  - `category_source`;
  - `category_column_present_in_source`;
  - `source_categories`;
  - `normalized_categories`;
  - `rows_before` / `rows_after`;
  - `default_category`.

Call this function **before** `build_outcome_grains()` so every canonical grain receives `category`.

Write:

```text
data/processed/scoring_runs/<run_id>/outcome_category_normalization_audit.json
```

Project scope is Bybit linear USDT perpetual only; this fallback is valid only because it is explicit, versioned, and audited.

## 2. Make category a required grain contract field

Add `REQUIRED_COLUMNS_BY_GRAIN`, including at minimum:

```python
{
  "event_horizon": ["range_action_event_id", "future_horizon_minutes", "symbol", "category"],
  "event_horizon_sl": ["range_action_event_id", "future_horizon_minutes", "sl_atr_buffer", "symbol", "category"],
  "event_horizon_grid": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number", "symbol", "category"],
  "expanded_scoring_input": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number", "sl_atr_buffer", "symbol", "category"],
}
```

Fail before writing any grains if required fields are missing/null.

Extend `outcome_grain_contract_audit.json` with:

```text
actual_columns_by_grain
missing_required_columns_by_grain
null_required_column_counts_by_grain
category_present_by_grain
category_values_by_grain
grain_contract_audit_ok
```

Do not report only the intended contract. The audit must inspect the actual written DataFrames.

## 3. Add a shared fee-join preflight

In `score_builder.py`, create one helper used for both expanded scoring and event-horizon-grid cost summary:

```python
def join_account_fees(
    df: pl.DataFrame,
    fees: pl.DataFrame,
    *,
    context: str,
) -> tuple[pl.DataFrame, dict[str, object]]:
    ...
```

It must:

- require `category` and `symbol` in both frames;
- require all scoring categories to be `linear`;
- require fee snapshot categories to include `linear` and have one identical row per `(category, symbol)`;
- join on `(category, symbol)`;
- fail on missing fee coverage;
- report context-specific row/symbol/category counts.

Use it for:

```text
expanded_scoring_input
cost_summary_event_horizon_grid
```

Write the two preflight results into `fee_coverage_audit.json` or a dedicated:

```text
fee_join_context_audit.json
```

## 4. Remove unsafe fallback inside cost-summary generation

The cost summary must read the canonical `event_horizon_grid.parquet`, which now contains category. It must not depend on a late ad hoc fallback.

Add an explicit assertion before join:

```python
required = {"category", "symbol", "range_action_event_id", "future_horizon_minutes", "grid_cell_number"}
```

## 5. Make scoring builds atomic/fail-closed

The failed v5 run left grains and walk-forward files but no complete cost/scoring artifacts. Prevent future partial runs from looking complete.

Implement a status artifact:

```text
data/processed/scoring_runs/<run_id>/scoring_run_status.json
```

Lifecycle:

```json
{"status":"building", ...}
```

then only after all scoring/cost/audit outputs succeed:

```json
{
  "status":"complete",
  "scoring_run_id":"...",
  "source_outcome_run_id":"...",
  "rows":241155,
  "completed_at_utc":"..."
}
```

On exception:

```json
{"status":"failed", "failed_stage":"...", "error_type":"...", "error_summary":"..."}
```

Requirements:

- Pack builder requires `status=complete`.
- Walk-forward builder requires completed grains but may run before scoring; however the final review pack must require completed scoring.
- Checker requires `scoring_run_status.json` and validates matching `scoring_run_id`.
- Never create a ZIP when status is not complete.

## 6. Friendly missing-ZIP checker behavior

Current checker throws a raw `FileNotFoundError` when pack creation failed and the ZIP does not exist.

Change `check_scoring_review_pack.py` so a missing ZIP emits strict JSON and exits non-zero:

```json
{
  "review_pack_ok": false,
  "error": "zip_not_found",
  "zip": "...",
  "scoring_run_id": "..."
}
```

No traceback for this expected operator error.

## 7. Prevent downstream use after scoring failure

Add a preflight to `make_scoring_review_pack.py` requiring:

- `scoring_run_status.status == complete`;
- `cost_summary_audit_ok == true`;
- `scoring_semantics_audit_ok == true`;
- required cost artifacts exist.

The v5 walk-forward files may be structurally valid because they use grains, but the **v5 run as a whole is invalid/incomplete** and must not be accepted or packed.

## 8. Tests

Add regression tests for:

1. Source outcomes without category become audited `linear` before grain build.
2. `event_horizon_grid.parquet` contains category.
3. Grain contract fails if category is removed after normalization.
4. Fee join works for canonical linear category.
5. Fee join fails on mixed category or missing category.
6. Cost summary builds from event-horizon-grid without `ColumnNotFoundError`.
7. Scoring status is `failed` after a deliberate exception and `complete` after success.
8. Pack builder refuses incomplete status.
9. Checker returns JSON `zip_not_found` instead of traceback.
10. No live/create/close/order/Telegram additions.

## 9. Owner cleanup and rerun

Do not reuse `scoring_cost_v5_123x90`. Use v6.

No market/range/outcome rebuild is required.

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

Build grains:

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v6_123x90
```

Build scoring:

```powershell
python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v6_123x90 `
  --fee-snapshot-id fee_linear_20260711T112444Z `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

Walk-forward:

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v6_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v6_123x90
```

Pack:

```powershell
python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v6_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v6_123x90.zip `
  --scoring-run-id scoring_cost_v6_123x90
```

## 10. Acceptance criteria

```text
pytest passed
ruff passed
safety audit passed
category_normalization_ok = true
category_present_by_grain = true for all four grains
category_values_by_grain = [linear]
event_horizon = 26795
event_horizon_grid = 80385
event_horizon_sl = 80385
expanded = 241155
fee_coverage_rate = 1.0
cost_summary_source_rows = 80385
cost_summary_duplicate_key_count = 0
sl_dimension_rows_not_used_for_cost_summary = 160770
coverage_reconciliation_delta = 0
unassigned_event_count = 0
temporal_leakage_violations = 0
scoring_run_status = complete
risk_budget_proven_bool = false
review_pack_ok = true
```

## Required user return

Text:

```text
commit hash
changed files
pytest output
ruff output
category normalization audit summary
actual grain category columns/values
fee join context audit summary
cost summary audit summary
walk-forward reconciliation/leakage summary
scoring run status
review pack checker output
risk_budget_proven_bool
```

Upload only:

```text
pm_review_pack_scoring_scoring_cost_v6_123x90.zip
```

Do not upload the full repository, scoring datasets, outcomes, ranges, market data, `.env`, or caches.
