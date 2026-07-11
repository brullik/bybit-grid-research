# Sprint 05.3 — Provenance, Grain Null Policy & Walk-Forward Coverage Finalization

PM decision: Sprint 05.2 implementation is directionally accepted, but Gate 5A remains open. Do not start the neutral-grid state machine or PnL backtest yet.

## Accepted evidence from scoring_cost_v3_123x90

- Canonical source rows: 241155.
- event_horizon rows: 26795.
- event_horizon_grid rows: 80385.
- event_horizon_sl rows: 80385.
- Cartesian completeness: pass.
- Grain contract v2: pass under current checks.
- Fee coverage: 100%, account_actual.
- Resolved fee snapshot: fee_linear_20260711T112444Z.
- Scoring rows: 241155.
- Walk-forward temporal leakage violations: 0.
- risk_budget_proven_bool: false.
- Safety audit, pytest and ruff passed on owner Windows machine.

## Actual blocker

The final review-pack checker returned:

```json
{
  "review_pack_ok": false,
  "bad_audit_values": [
    {
      "file": "cost_model_audit.json",
      "key": "cost_model_audit_ok",
      "value": null,
      "expected": true
    }
  ]
}
```

Root cause: `scripts/report_cost_and_scoring.py` overwrites the canonical resolved artifacts produced by `build_outcome_scoring_dataset.py`:

- `cost_model_config_resolved.yml` is replaced with the unresolved template containing `REQUIRED_FOR_ACCOUNT_ACTUAL` / `manual_scenario`.
- `cost_model_audit.json` is replaced with a minimal file that omits `cost_model_audit_ok` and the v2 formula provenance.

There are also two correctness gaps not caught by the current audits:

1. Grain construction uses first non-null aggregation per column. Different source rows can be combined into a synthetic “Frankenstein” row when null patterns differ.
2. Walk-forward coverage does not exclude empirically incomplete max-horizon labels and hard-codes `incomplete_label_excluded_count=0` and `unassigned_event_count=0`.

## Non-negotiable safety rules

- No Bybit create/close/order/cancel/position changes.
- No Telegram/live execution.
- No market downloads.
- No range or outcome rebuild.
- Keep `risk_budget_proven_bool=false`.
- Keep all scoring names `ex_post_*`, proxy-only, not PnL/EV/profitability.
- Preserve FAST-first behavior.

## New run ID

```text
scoring_cost_v4_123x90
```

Do not mutate v1/v2/v3 artifacts.

---

## Task 1 — Stop report scripts from overwriting canonical provenance

Refactor reporting into importable functions.

### `scripts/report_cost_and_scoring.py`

It must:

- read canonical artifacts already generated under `data/processed/scoring_runs/<run_id>/` and `reports/scoring_runs/<run_id>/`;
- validate them;
- generate human-readable Markdown only;
- never overwrite:
  - `cost_model_config_resolved.yml`
  - `cost_model_audit.json`
  - `fee_coverage_audit.json`
  - scoring datasets/audits.

If canonical provenance is absent or inconsistent, fail closed.

### Canonical resolved config

Write it only from the scoring builder. It must include:

```yaml
scoring_run_id: scoring_cost_v4_123x90
source_outcome_run_id: outcomes_true_fast_v4_canonical_123x90_v1
cost_model_version: cost_v1
cost_formula_version: cost_formula_v2_asymmetric_slippage
fee_snapshot_id_requested: fee_linear_20260711T112444Z
fee_snapshot_id_resolved: fee_linear_20260711T112444Z
fee_source: account_actual
fee_coverage_rate: 1.0
score_weights_version: score_weights_v2_frozen
risk_budget_usdt: 5
risk_budget_proven_bool: false
scenarios: ...
weight_sets: ...
```

JSON content in a `.yml` file is technically valid YAML, but prefer deterministic YAML or rename to `.json`. Do not keep unresolved template values.

### Canonical cost audit

Required fields:

```json
{
  "cost_model_audit_ok": true,
  "cost_model_version": "cost_v1",
  "cost_formula_version": "cost_formula_v2_asymmetric_slippage",
  "asymmetric_fee_normalization_ok": true,
  "asymmetric_slippage_normalization_ok": true,
  "fee_snapshot_id_resolved": "fee_linear_20260711T112444Z",
  "fee_source": "account_actual",
  "fee_coverage_rate": 1.0,
  "risk_budget_proven_bool": false
}
```

Add a regression test that calls scoring builder → report generator and proves the resolved config/audit remain byte-identical.

---

## Task 2 — Replace per-column first-non-null grain aggregation

Current pattern is unsafe:

```python
pl.col(column).drop_nulls().first()
```

It can combine values from different source rows.

### Required contract

For each grain key:

1. Select the exact allowlisted columns.
2. Treat null as a real value during invariance checks.
3. Verify the entire allowed row struct is identical across all expanded rows:

```python
pl.struct(non_key_columns).n_unique()
```

4. Fail if struct cardinality > 1.
5. Select one complete representative source row, not one value per column.

Alternative implementation: sort deterministically and use `.unique(keys, keep="first")` only after whole-struct invariance passes.

### New audit fields

```text
whole_row_invariance_violation_count_by_grain
null_pattern_violation_count_by_grain
synthetic_row_risk_detected_bool
representative_row_selection_version = whole_row_v1
```

Add tests for:

- row A: `field_a=value`, `field_b=null`;
- row B: `field_a=null`, `field_b=value`;
- same grain key;
- builder must fail rather than produce a combined row.

Also test identical rows with nulls pass.

---

## Task 3 — Make incomplete evidence ineligible, not silently ranked

Current v2 scoring computes numeric combined scores for all rows, while the outcome dataset has incomplete future evidence in a small fraction of rows.

Create canonical v3 diagnostic score columns:

```text
ex_post_event_quality_score_v3_<weight_set>
ex_post_sl_probe_score_v3_<weight_set>
ex_post_grid_probe_score_v3_<weight_set>
ex_post_combined_probe_score_v3_<weight_set>
```

Rules:

- if `ex_post_score_eligible_bool=false`, canonical v3 scores are null;
- retain a clearly named conservative diagnostic if needed:
  - `ex_post_combined_probe_score_v3_<weight_set>_conservative_all_rows`;
- never use the conservative all-row score as a ranking score;
- v2 columns may remain legacy/deprecated but must not be the default report headline.

### Required eligibility report

```text
rows_total
score_eligible_rows
score_ineligible_rows
score_eligible_rate
ineligible_reason_counts
score_null_count_by_weight_set
```

The report must explicitly state that incomplete evidence is excluded from ranking.

---

## Task 4 — Summarize costs at the correct grain

Cost diagnostics depend on event+horizon+grid, not SL buffer.

Current expanded summary can count each event+horizon+grid three times because of the three SL probes.

Build cost scenario summaries from `event_horizon_grid.parquet` joined to fees, or dedupe expanded rows on:

```text
range_action_event_id
future_horizon_minutes
grid_cell_number
```

Expected row count:

```text
80385 total event_horizon_grid rows
5359 rows per horizon × grid combination when all events are present
```

Add:

```text
cost_summary_grain = event_horizon_grid
cost_summary_source_rows
cost_summary_duplicate_key_count
cost_summary_dimension_multiplication_detected_bool
```

Fail if cost summary is multiplied by SL dimension.

---

## Task 5 — Walk-forward label completeness and coverage reconciliation

Use `event_horizon.parquet`, but derive one event-level eligibility row from the maximum horizon.

### Max-horizon eligibility

For each event:

- require a row with `future_horizon_minutes = max_outcome_horizon_minutes`;
- require `future_data_complete_bool=true` for that max-horizon row;
- require non-null event/regime/time keys;
- compute/retain `outcome_end_ms` from the canonical max-horizon row where possible;
- exclude incomplete max-horizon labels before role assignment.

### Real reason counts per fold

Calculate, do not hard-code:

```text
source_event_count
complete_label_event_count
incomplete_label_excluded_count
train_events
purged_event_count
validation_events
embargo_excluded_event_count
test_events
regime_excluded_event_count
outside_fold_window_count
unassigned_event_count
```

Add reconciliation:

```text
coverage_reconciliation_ok
coverage_reconciliation_delta
```

Define the reconciliation clearly. Avoid double-counting regimes and time-gap reasons.

### Coverage audit

It must fail unless:

- fold_count >= 1;
- train, validation and test are non-empty in every fold;
- actual_train_days >= configured_train_days;
- purge and embargo >= max outcome horizon;
- max train outcome_end < validation_start;
- max validation outcome_end < test_start;
- max test outcome_end <= test_end;
- no event or regime crosses roles within a fold;
- incomplete max-horizon events are excluded;
- reason counts reconcile.

For the 90-day dataset, one fold is acceptable only as a prototype. Emit:

```text
walk_forward_scope = prototype_90d
sufficient_for_parameter_selection_bool = false
sufficient_for_state_machine_engineering_bool = true
```

Do not claim robust model selection from one fold.

---

## Task 6 — Stronger scoring semantics audit

Extend `scoring_semantics_audit.json` with:

```text
scoring_semantics_audit_ok
scoring_run_id
source_outcome_run_id
rows_total
score_eligible_rows
score_ineligible_rows
score_eligible_rate
non_finite_score_count
out_of_bounds_score_count
canonical_score_version = v3
risk_budget_usdt = 5
risk_budget_proven_bool = false
profitability_claims_present_bool = false
pnl_claims_present_bool = false
placeholder_constant_components_present = false
```

Fail if:

- eligible rows have null canonical score;
- ineligible rows have non-null canonical ranking score;
- scores are outside [0,1];
- non-finite values exist;
- risk budget is marked proven;
- PnL/ROI/EV/profitability claims appear.

Add a high-correlation diagnostic only; do not optimize weights in this sprint:

```text
high_correlation_pair_count_abs_spearman_ge_0_98
high_correlation_pairs
```

This is evidence for later simplification, not a failure by itself.

---

## Task 7 — Self-contained, fail-closed review pack

`make_scoring_review_pack.py` must:

1. validate canonical data artifacts;
2. run/rebuild all audits;
3. generate all Markdown reports;
4. ensure canonical provenance files are not overwritten;
5. validate content consistency;
6. write manifest with SHA-256 hashes;
7. run the same checker logic before creating the ZIP;
8. create no ZIP on failure.

### Manifest fields

```json
{
  "review_pack_schema_version": "scoring_review_pack_v3",
  "scoring_run_id": "scoring_cost_v4_123x90",
  "source_outcome_run_id": "outcomes_true_fast_v4_canonical_123x90_v1",
  "fee_snapshot_id_resolved": "fee_linear_20260711T112444Z",
  "cost_formula_version": "cost_formula_v2_asymmetric_slippage",
  "grain_contract_version": "grain_contract_v3_whole_row",
  "canonical_score_version": "v3",
  "risk_budget_proven_bool": false,
  "members": [...],
  "sha256": {"file": "hash"}
}
```

### Checker cross-file consistency

Verify:

- resolved config fee snapshot/source equals fee coverage audit;
- cost audit formula/version equals resolved config;
- source outcome run ID is consistent everywhere;
- grain row counts match Cartesian audit;
- whole-row grain contract passes;
- cost summary uses event_horizon_grid grain;
- scoring eligibility/null policy passes;
- walk-forward coverage and leakage audits pass;
- prototype split is marked insufficient for parameter selection;
- `risk_budget_proven_bool=false` everywhere;
- no duplicate ZIP members, path traversal, extra or missing members;
- hashes match.

---

## Task 8 — Reports must be substantive

Generate compact but useful reports.

### Outcome scoring report

Include:

- source/grain row counts;
- eligibility rate and reasons;
- canonical v3 score distributions on eligible rows only;
- fee snapshot/source/coverage;
- cost scenario break-even rates by grid count;
- high-correlation warning;
- explicit statement: proxy only, not PnL/EV/profitability;
- explicit statement: 5 USDT max-loss budget not proven.

### Walk-forward report

Include:

- fold dates;
- train/purge/validation/embargo/test durations;
- event counts and exclusion reasons;
- coverage reconciliation;
- leakage result;
- prototype-only limitation.

---

## Task 9 — Tests

Add regression tests for all issues above, including:

- report generation does not overwrite canonical resolved config/audit;
- pack checker fails on unresolved fee provenance;
- whole-row grain invariance catches split null patterns;
- cost summary is not multiplied by SL probes;
- ineligible rows have null canonical ranking scores;
- incomplete max-horizon events are excluded from walk-forward;
- fold reason counts reconcile;
- one-fold prototype is not marked sufficient for parameter selection;
- manifest hashes and cross-file consistency;
- no live/create/close/order/Telegram additions.

---

## Acceptance commands on owner Windows machine

No network/API calls are needed.

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

Build v4 grains:

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v4_123x90
```

Build v4 scoring:

```powershell
python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v4_123x90 `
  --fee-snapshot-id fee_linear_20260711T112444Z `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

Build/audit walk-forward:

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v4_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v4_123x90
```

Create/check pack:

```powershell
python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v4_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v4_123x90.zip `
  --scoring-run-id scoring_cost_v4_123x90
```

## Gate 5A acceptance criteria

- pytest and ruff pass.
- safety audit passes.
- canonical source rows = 241155.
- event_horizon = 26795.
- event_horizon_grid = 80385.
- event_horizon_sl = 80385.
- expanded = 241155.
- Cartesian completeness passes.
- whole-row grain invariance passes.
- synthetic-row risk is false.
- fee coverage = 100%, account_actual.
- resolved config is not overwritten and matches fee/cost audits.
- cost summary grain = event_horizon_grid, without SL multiplication.
- canonical v3 ranking scores are null for ineligible rows.
- score eligibility rate/reasons are reported.
- walk-forward leakage = 0.
- walk-forward coverage reconciliation passes.
- max-horizon incomplete events are excluded.
- prototype split is marked insufficient for parameter selection.
- risk_budget_proven_bool=false.
- review pack checker returns true.
- no live/create/close/order/Telegram code.

## Output required from Codex

- commit hash;
- files changed;
- tests/lint/safety outputs;
- summary of new audits;
- any blockers.

## What the owner sends to PM after the run

Text only:

```text
commit hash
pytest output
ruff output
safety audit output
grain contract summary
score eligibility summary
resolved fee/cost provenance summary
cost summary grain/row counts
walk-forward coverage reconciliation
walk-forward leakage summary
review pack checker output
risk_budget_proven_bool
```

Upload only:

```text
pm_review_pack_scoring_scoring_cost_v4_123x90.zip
```

Do not upload the full repository, scoring dataset, outcomes, market data, `.env`, or caches.
