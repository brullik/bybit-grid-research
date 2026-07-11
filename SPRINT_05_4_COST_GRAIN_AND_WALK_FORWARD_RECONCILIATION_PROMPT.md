# Sprint 05.4 — Cost-Grain Audit + Walk-Forward Reconciliation Finalization

## PM decision

Sprint 05.3 implementation and the `scoring_cost_v4_123x90` run are accepted as a strong foundation, but Gate 5A is not closed.

The review pack passed its current checker, yet inspection found two audit contradictions that must be fixed before Sprint 06:

1. `cost_scenario_summary.parquet` reports:
   - `cost_summary_source_rows = 80385` — correct event-horizon-grid cardinality;
   - each horizon/grid/scenario has `row_count = 5359` — correct;
   - but `cost_summary_duplicate_key_count = 160770` and `cost_summary_dimension_multiplication_detected_bool = true` — incorrect audit semantics.
2. `walk_forward_fold_summary.parquet` reports `coverage_reconciliation_ok=true`, `coverage_reconciliation_delta=0`, and `unassigned_event_count=0`, but the actual fold counts do not reconcile:
   - complete-label events = 5280;
   - assigned train/validation/test = 3095 + 420 + 704 = 4219;
   - purge = 105;
   - embargo = 95;
   - outside fold = 579;
   - accounted = 4998;
   - unaccounted = 282.

The current walk-forward code hardcodes reconciliation fields instead of calculating them. These 282 events are likely horizon-boundary exclusions inside train/validation/test windows, but the code must prove and report that.

## Non-negotiable safety rules

- No live trading.
- No Telegram.
- No order create/cancel.
- No Bybit grid create/close.
- Do not change the immutable canonical outcome run.
- Do not download market data.
- `risk_budget_proven_bool` remains false.
- This sprint is audit/correctness only; do not optimize score weights or select parameters.

## Run ID

Create a new scoring run:

```text
scoring_cost_v5_123x90
```

Do not mutate v1/v2/v3/v4.

---

## Task 1 — Build cost summary from the canonical event-horizon-grid grain

### Current defect

The current implementation creates the cost summary by deduplicating the expanded 241155-row scoring table:

```python
cost_df = df.unique(
    ["range_action_event_id", "future_horizon_minutes", "grid_cell_number"],
    keep="first",
)
duplicate_cost_keys = df.height - cost_df.height
```

The value 160770 is not a duplicate-key count. It is the expected number of SL-dimension repetitions removed:

```text
241155 - 80385 = 160770
```

The final summary is correctly de-multiplied, but the audit says the opposite.

### Required implementation

Prefer reading the already-built canonical file:

```text
data/processed/scoring_runs/<scoring_run_id>/event_horizon_grid.parquet
```

Join the resolved fee snapshot to this grain and compute scenario diagnostics directly on it.

The cost summary audit must contain:

```json
{
  "cost_summary_audit_ok": true,
  "cost_summary_grain": "event_horizon_grid",
  "cost_summary_source_rows": 80385,
  "cost_summary_expected_rows": 80385,
  "cost_summary_duplicate_key_count": 0,
  "cost_summary_dimension_multiplication_detected_bool": false,
  "expanded_scoring_rows": 241155,
  "sl_dimension_rows_not_used_for_cost_summary": 160770,
  "cost_summary_scenario_count": 4,
  "cost_summary_group_count": 60
}
```

Canonical cost key:

```text
range_action_event_id
future_horizon_minutes
grid_cell_number
```

Fail closed if the canonical event-horizon-grid file has duplicate keys.

Add:

```text
data/processed/scoring_runs/<scoring_run_id>/cost_summary_audit.json
```

Include it in the PM review pack.

### Required report wording

`cost_scenario_report.md` must distinguish:

```text
expanded rows ignored for cost summary
SL-dimension rows intentionally removed
actual duplicate event-horizon-grid keys
```

Do not call the expected SL repetitions “duplicates”.

---

## Task 2 — Compute walk-forward coverage as disjoint event categories

### Current defect

The following fields are hardcoded:

```python
"unassigned_event_count": 0,
"coverage_reconciliation_ok": True,
"coverage_reconciliation_delta": 0,
```

The owner run proves this is not currently true.

### Required per-fold categories

For every unique source event, classify it into exactly one category per fold:

```text
incomplete_max_horizon
outside_fold_window
purge_gap
embargo_gap
train_horizon_boundary
validation_horizon_boundary
test_horizon_boundary
cross_role_regime_excluded
train_assigned
validation_assigned
test_assigned
unassigned
```

Definitions:

- `incomplete_max_horizon`: max-horizon outcome is not complete.
- `outside_fold_window`: signal time is outside `[train_start, test_end)`.
- `purge_gap`: signal is in `[train_end, validation_start)`.
- `embargo_gap`: signal is in `[validation_end, test_start)`.
- `<role>_horizon_boundary`: signal is inside the role window but `outcome_end_ms` crosses that role’s end.
- `cross_role_regime_excluded`: the same `range_regime_id` would otherwise appear in more than one role.
- assigned categories are the final role rows.
- `unassigned` is any event not captured above and must be zero.

### Regime policy

Use a conservative, deterministic regime policy:

- First determine tentative role eligibility for all events.
- If a `range_regime_id` appears in more than one role in the same fold, exclude the entire regime from all roles for that fold.
- Do not keep the train occurrence and silently drop only later validation/test occurrences.

### Reconciliation formula

Per fold:

```text
source_event_count
=
incomplete_max_horizon_count
+ outside_fold_window_count
+ purge_gap_event_count
+ embargo_gap_event_count
+ train_horizon_boundary_excluded_count
+ validation_horizon_boundary_excluded_count
+ test_horizon_boundary_excluded_count
+ cross_role_regime_excluded_event_count
+ train_events
+ validation_events
+ test_events
+ unassigned_event_count
```

Write actual values, not constants.

Required:

```text
coverage_reconciliation_delta = RHS - source_event_count
coverage_reconciliation_ok = (delta == 0 and unassigned_event_count == 0)
```

### Required artifacts

Update:

```text
walk_forward_fold_summary.parquet
walk_forward_coverage_audit.json
walk_forward_design_report.md
```

Add:

```text
walk_forward_exclusion_reason_summary.parquet
```

The coverage audit must aggregate all per-fold fields and fail closed if any fold does not reconcile.

Keep:

```text
walk_forward_scope = prototype_90d
sufficient_for_parameter_selection_bool = false
sufficient_for_state_machine_engineering_bool = true
```

One fold is acceptable for state-machine engineering only.

---

## Task 3 — Strengthen the review-pack checker

Add required member:

```text
cost_summary_audit.json
walk_forward_exclusion_reason_summary.parquet
```

The checker must require:

```text
cost_summary_audit_ok = true
cost_summary_duplicate_key_count = 0
cost_summary_dimension_multiplication_detected_bool = false
cost_summary_grain = event_horizon_grid
coverage_reconciliation_ok = true
coverage_reconciliation_delta = 0
unassigned_event_count = 0 for every fold
sufficient_for_parameter_selection_bool = false
sufficient_for_state_machine_engineering_bool = true
risk_budget_proven_bool = false
```

The checker must inspect `walk_forward_fold_summary.parquet`, not only trust JSON booleans.

Also verify:

```text
train_events + validation_events + test_events > 0
actual_train_days >= configured_train_days
purge_gap_minutes >= 2880
embargo_gap_minutes >= 2880
```

---

## Task 4 — Improve scoring summary null transparency

The canonical scores are correctly null for 1404 ineligible expanded rows, but `score_sensitivity_report.md` currently shows `null_count=0` because it reports only the eligible subset.

Keep the eligible-only distribution, but add explicit fields:

```text
rows_total
eligible_rows
ineligible_rows
canonical_null_count_all_rows
eligible_distribution_count
```

Update `outcome_scoring_summary.parquet` to include per symbol:

```text
row_count_total
score_eligible_rows
score_ineligible_rows
mean_score_eligible_only
```

Do not change score formulas or weights.

---

## Task 5 — Tests

Add regression tests for:

1. Expanded rows with three SL probes produce:
   - canonical event-horizon-grid rows with no duplicate keys;
   - `sl_dimension_rows_not_used_for_cost_summary > 0`;
   - `cost_summary_duplicate_key_count = 0`;
   - `cost_summary_dimension_multiplication_detected_bool = false`.
2. A true duplicate inside event-horizon-grid causes a fail-closed error.
3. Walk-forward events crossing train/validation/test ends are counted in the correct horizon-boundary exclusion category.
4. Coverage reconciliation uses calculated counts and catches a non-zero delta.
5. A regime tentatively spanning train and validation is excluded from both roles and counted.
6. Review-pack checker rejects:
   - multiplication flag true;
   - duplicate cost keys > 0;
   - hardcoded/incorrect reconciliation;
   - missing exclusion summary.
7. Canonical score all-row null counts match scoring semantics audit.
8. Safety audit remains green; no execution code added.

---

## Acceptance commands

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

Build v5 grains:

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v5_123x90
```

Build v5 scoring:

```powershell
python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v5_123x90 `
  --fee-snapshot-id fee_linear_20260711T112444Z `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

Walk-forward:

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v5_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v5_123x90
```

Pack:

```powershell
python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v5_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v5_123x90.zip `
  --scoring-run-id scoring_cost_v5_123x90
```

---

## Definition of Done / Gate 5A

Gate 5A closes only if:

```text
pytest passes
ruff passes
safety audit passes
grain_contract_audit_ok = true
cartesian_completeness_ok = true
cost_summary_audit_ok = true
cost_summary_duplicate_key_count = 0
cost_summary_dimension_multiplication_detected_bool = false
cost summary source rows = 80385
walk-forward coverage reconciliation delta = 0
walk-forward unassigned events = 0
temporal leakage violations = 0
prototype sufficient for state-machine engineering = true
prototype sufficient for parameter selection = false
risk_budget_proven_bool = false
review_pack_ok = true
```

After this, Sprint 06 may begin: native neutral-grid position state machine and 5 USDT max-loss calibration. No live execution is authorized.

## Required output for PM

Text in chat:

```text
commit hash
changed files
pytest output
ruff output
safety audit output
cost summary audit JSON
cost summary rows / duplicate keys / SL rows removed
walk-forward fold summary
walk-forward exclusion reason summary
coverage reconciliation JSON
leakage audit JSON
review pack checker output
risk_budget_proven_bool
```

Upload only:

```text
pm_review_pack_scoring_scoring_cost_v5_123x90.zip
```

Do not upload the full repository, scoring dataset, outcomes, range partitions, market data, `.env`, or caches.
