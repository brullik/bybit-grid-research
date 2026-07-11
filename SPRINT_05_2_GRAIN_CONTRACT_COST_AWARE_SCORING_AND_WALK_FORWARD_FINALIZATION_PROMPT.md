# Sprint 05.2 — Grain Contracts, Cost-Aware Proxy Scoring & Walk-Forward Finalization

PM decision: Sprint 05.1 fixed the source-row contamination, Cartesian counts, fee coverage and basic temporal leakage audit. The implementation is accepted as a foundation, but Gate 5A is **not closed**. Do not start the native neutral-grid state machine, PnL simulation, live execution, Telegram, or parameter selection.

## Accepted immutable inputs

```text
source outcome run: outcomes_true_fast_v4_canonical_123x90_v1
accepted diagnostic scoring run: scoring_cost_v2_123x90
new scoring run: scoring_cost_v3_123x90
risk budget: 5 USDT maximum loss per grid
risk_budget_proven_bool: false
```

Do not mutate `scoring_cost_v2_123x90`.

## Accepted Sprint 05.1 evidence

```text
source rows = 241155
unique event-horizon rows = 26795
event-horizon-grid rows = 80385
event-horizon-SL rows = 80385
expanded rows = 241155
Cartesian completeness = true
fee coverage = 100%
resolved fee snapshot = fee_linear_20260711T112444Z
walk-forward folds = 2
reported temporal leakage violations = 0
```

## Non-negotiable safety and performance rules

- No order create/cancel.
- No native grid create/close.
- No Telegram or live execution.
- `LIVE_TRADING_ENABLED=false`, `ALLOW_LIVE_TRADING=NO` remain defaults.
- Read-only fee snapshots are allowed; this sprint should reuse the existing snapshot and make no network calls by default.
- FAST-first: vectorized Polars expressions; do not run Python `iter_rows()` once per scoring row and scenario.
- No score/threshold/parameter optimization.
- Every score remains `ex_post_*`, diagnostic and proxy-only.
- No PnL, ROI, EV, profitability or proven-edge claims.

---

# Blocker 1 — Grain rows are not semantically canonical

Current `unique_grain()` groups by keys and independently calls `drop_nulls().first()` on every other column. This can create a synthetic “Frankenstein” row and carries arbitrary grid/SL-specific fields into `event_horizon`.

Example problem:

```text
event_horizon key = event + horizon
but output can still contain one arbitrary grid_cell_number,
one arbitrary sl_atr_buffer, grid activity and SL fields.
```

## Required grain contracts

Add explicit, versioned contracts, for example:

```python
GRAIN_CONTRACT_VERSION = "grain_contract_v2"
GRAIN_KEYS = {
    "event_horizon": ["range_action_event_id", "future_horizon_minutes"],
    "event_horizon_sl": ["range_action_event_id", "future_horizon_minutes", "sl_atr_buffer"],
    "event_horizon_grid": ["range_action_event_id", "future_horizon_minutes", "grid_cell_number"],
    "expanded_scoring_input": [
        "range_action_event_id", "future_horizon_minutes", "grid_cell_number", "sl_atr_buffer"
    ],
}
```

Create explicit allowlists for each grain:

### `event_horizon`

Only event/horizon-invariant columns, including identity, time, range, future coverage, range exit, funding context, mark-price context and data-quality fields.

It must **not** contain:

```text
grid_cell_number
grid_interval_*
geometric_grid_levels_json
future_*grid* / future_*level*
sl_atr_buffer
lower_sl_price / upper_sl_price
sl_hit_bool / first_sl_* / minutes_to_first_sl
```

### `event_horizon_sl`

Event/horizon columns plus SL-probe fields. It must not contain grid geometry/activity fields.

### `event_horizon_grid`

Event/horizon columns plus grid geometry/activity fields. It must not contain SL-probe fields.

### `expanded_scoring_input`

Full canonical expanded outcome row.

## Invariance audit

Before collapsing a grain, verify that every retained non-key column has at most one distinct non-null value per grain key. Do not silently use `first()` when values conflict.

Write:

```text
data/processed/scoring_runs/scoring_cost_v3_123x90/outcome_grain_contract_audit.json
data/processed/scoring_runs/scoring_cost_v3_123x90/outcome_grain_invariance_violations.parquet  # only if non-empty
```

Required fields:

```text
grain_contract_version
contract_columns_by_grain
forbidden_columns_found_by_grain
invariance_violation_count_by_grain
grain_contract_audit_ok
```

Fail closed on any forbidden column or invariance violation.

Expected row counts remain:

```text
event_horizon = 26795
event_horizon_sl = 80385
event_horizon_grid = 80385
expanded_scoring_input = 241155
```

---

# Blocker 2 — Incomplete evidence can receive an unrealistically good score

Current logic can produce:

```text
SL not hit + incomplete future data -> ex_post_sl_risk_score = 0
coverage minutes equal horizon despite missing rows -> data score = 1
```

Unknown evidence must never silently receive the best score.

## Required null/evidence policy

Add:

```text
ex_post_event_evidence_complete_bool
ex_post_sl_evidence_complete_bool
ex_post_grid_evidence_complete_bool
ex_post_score_eligible_bool
ex_post_score_incomplete_reason
```

### Data completeness

Use all available evidence:

```text
future_data_complete_bool
future_coverage_minutes
future_rows_available
future_missing_minutes_count
future_bad_ohlc_count
future_zero_volume_count
```

For 1m outcomes, calculate a bounded completeness score using both elapsed coverage and expected row coverage. A row with `future_data_complete_bool=false` must not receive `ex_post_data_complete_score=1.0`.

### SL evidence

`ex_post_sl_risk_score` is valid only when:

```text
sl_proxy_valid_bool = true
and future evidence covers the relevant horizon/termination
```

If evidence is incomplete, keep the SL score null and mark the row ineligible or apply an explicit conservative penalty. Do not fill unknown SL survival with the best value.

### Data quality score

Create an explicit composite, for example:

```text
ex_post_data_quality_score
```

It must use real completeness, bad-OHLC rate and ambiguity. Keep zero-volume as a separately reported context/sensitivity component; do not assume every zero-volume candle is equally harmful.

Document all null handling in:

```text
reports/scoring_runs/scoring_cost_v3_123x90/scoring_null_policy.md
```

---

# Blocker 3 — Current score ignores grid activity and fee viability

Current fixed score uses range survival, data completeness, SL risk and capital turnover. It does not use the calculated grid activity or cost-scenario diagnostics, so different grid counts can receive identical scores.

Do not present one generic score as if it ranks the entire native-grid configuration.

## Required grain-specific diagnostic scores

Create separate versioned scores:

```text
ex_post_event_quality_score_v2_*       # event_horizon grain
ex_post_sl_probe_score_v2_*            # event_horizon_sl grain
ex_post_grid_probe_score_v2_*          # event_horizon_grid grain
ex_post_combined_probe_score_v2_*      # expanded grain
```

### Event score inputs

```text
range survival
data quality
ambiguity
capital-lock/turnover proxy
```

### SL score inputs

```text
event score components
SL survival/risk
SL evidence completeness
```

### Grid score inputs

```text
event score components
close-cross lower-bound activity rate
intrabar-touch upper activity rate
unique levels touched
one-cycle fee viability under each cost scenario
```

### Combined score inputs

```text
event + SL + grid/cost components
```

All activity values remain proxies, not actual native fills.

Use several frozen sensitivity weight sets such as:

```text
balanced_v2
survival_heavy_v2
quality_heavy_v2
cost_heavy_v2
```

Do not select a winning weight set or threshold in this sprint. Weights must be versioned, sum to 1 and be written to the resolved run config.

## Score audit

Write:

```text
scoring_semantics_audit.json
score_component_summary.parquet
score_correlation_report.json
```

Audit at minimum:

```text
all required source columns exist
score columns are finite and bounded
unknown/incomplete evidence is not scored as perfect
cost-aware grid scores vary when grid interval/cost viability varies
no placeholder constants masquerade as evidence
risk_budget_proven_bool = false
```

Report Pearson and Spearman correlations between fixed score variants. No optimization.

---

# Blocker 4 — Cost config is labelled “resolved” but still contains placeholders

Current pack has:

```yaml
fee_snapshot_id: REQUIRED_FOR_ACCOUNT_ACTUAL
fee_source: manual_scenario
```

while the actual run used:

```text
fee_snapshot_id = fee_linear_20260711T112444Z
fee_source = account_actual
```

## Required resolved provenance

Generate `cost_model_config_resolved.yml` programmatically. It must contain:

```text
cost_model_version
cost_formula_version
fee_snapshot_id_requested
fee_snapshot_id_resolved
fee_source
fee_coverage_rate
scenario definitions
score weight version
```

Do not copy the unresolved source config verbatim.

## Fee validation

Fail closed on:

```text
non-finite fee values
missing symbols
mixed fee sources in one snapshot
conflicting duplicate rates
snapshot ID mismatch
```

## Correct slippage normalization

The config says `slippage_bps_per_market_leg`. If slippage is applied to each leg’s own notional, normalize consistently:

```text
long, normalized to buy notional P:
  slippage_long = entry_slippage + exit_slippage * r

short, normalized to opening sell notional P*r:
  slippage_short = entry_slippage + exit_slippage / r
```

Do not use `2 * slip` for both sides unless the config explicitly defines slippage relative to initial notional. Add worked asymmetric tests.

## FAST cost calculation

Replace Python per-row/per-scenario `iter_rows()` loops with vectorized Polars expressions. `--fast-max` must be real or removed from this CLI.

## Cost evidence outputs

Write:

```text
cost_model_audit.json
cost_scenario_summary.parquet
cost_scenario_report.md
```

For each scenario and relevant grid/horizon groups report:

```text
row_count
fee_break_even_both_rate
net_cycle_return_long_bps_proxy quantiles
net_cycle_return_short_bps_proxy quantiles
fee_efficiency long/short quantiles
```

These remain one-cycle diagnostics—not event PnL.

---

# Blocker 5 — Walk-forward “45-day train” currently becomes 43 days

The current profile sets:

```text
min_train_days = 45
purge = 2 days
```

but calculates validation start at `start + 45 days` and train end two days earlier. The first accepted train window is therefore 43 days.

## Required window semantics

Define `min_train_days` as the usable post-purge training window.

One valid construction:

```text
train_start = data_start
train_end = train_start + min_train_days
validation_start = train_end + purge
validation_end = validation_start + validation_days
test_start = validation_end + embargo
test_end = test_start + test_days
```

Subsequent expanding folds move validation/test by `step_days` while keeping train start fixed.

The loop condition must include purge and embargo and must not create a fold whose test window exceeds available canonical label coverage.

## Complete-label eligibility

Build one event-level eligibility table before splits:

```text
one row per range_action_event_id
max configured horizon
max-horizon future_data_complete_bool
outcome_end_ms
range_regime_id
```

By default, events without complete max-horizon evidence are excluded from fold evaluation and counted explicitly.

## Required fold/coverage audit

Add:

```text
walk_forward_event_eligibility.parquet
walk_forward_coverage_audit.json
walk_forward_fold_summary.parquet
walk_forward_temporal_leakage_audit.json
```

Per fold report:

```text
configured_train_days
actual_train_days
purge_gap_minutes
validation_days
embargo_gap_minutes
test_days
train/validation/test event counts
incomplete_label_excluded_count
purged_event_count
embargo_excluded_event_count
regime_excluded_event_count
unassigned_event_count
```

Audit must require:

```text
actual_train_days >= configured_train_days
all three roles non-empty
no event/regime in multiple roles within a fold
train outcomes end before validation start
validation outcomes end before test start
test outcomes end by test end
purge and embargo gaps match config
test_end is within available label coverage
```

---

# Blocker 6 — Review pack is too easy to make stale or self-approve

Current pack builder copies existing files and prints `review_pack_ok=true` without running the content checker. Several reports are only one-line placeholders.

## Self-contained pack builder

`make_scoring_review_pack.py` must:

1. Rebuild compact reports from run artifacts.
2. Run all audits.
3. Fail before ZIP creation if any audit fails.
4. Write a run manifest with hashes and provenance.
5. Create ZIP only after validation.

## Required v3 pack members

At minimum:

```text
review_pack_manifest.json
scoring_run_manifest.json
fee_snapshot_report.md
fee_coverage_audit.json
cost_model_config_resolved.yml
cost_model_audit.json
cost_scenario_summary.parquet
cost_scenario_report.md
outcome_source_audit.json
outcome_grain_audit.json
outcome_grain_contract_audit.json
outcome_cartesian_completeness_audit.json
scoring_null_policy.md
scoring_semantics_audit.json
score_component_summary.parquet
score_correlation_report.json
outcome_scoring_summary.parquet
outcome_scoring_report.md
score_sensitivity_report.md
risk_budget_readiness_report.md
walk_forward_design_report.md
walk_forward_fold_summary.parquet
walk_forward_coverage_audit.json
walk_forward_leakage_audit_summary.json
walk_forward_temporal_leakage_audit.json
```

`outcome_scoring_summary.parquet` must contain compact aggregates by at least:

```text
overall
future_horizon_minutes + grid_cell_number + sl_atr_buffer
symbol
```

It must not contain raw scoring rows.

## Checker requirements

The checker must verify:

```text
manifest scoring_run_id equals CLI scoring_run_id
exact ZIP member parity
no duplicate ZIP members
no forbidden paths / traversal
all mandatory audit booleans
summary/fold Parquets are non-empty and have expected aggregate schemas
fold_count > 0 and each role count > 0
grained row counts match canonical expected counts
risk_budget_proven_bool = false
```

---

# New/updated tests

Add regression tests for:

1. `event_horizon` contains no grid/SL columns.
2. `event_horizon_sl` contains no grid columns.
3. `event_horizon_grid` contains no SL columns.
4. Conflicting values in a retained invariant column fail closed.
5. Incomplete future evidence cannot receive perfect data/SL score.
6. Missing SL evidence remains null/ineligible, not best.
7. Grid score changes with grid interval/cost viability.
8. Quality score uses bad OHLC and ambiguity evidence.
9. Cost config output contains the resolved account snapshot ID/source.
10. Slippage normalization is asymmetric and correct for long/short denominators.
11. Vectorized cost output matches scalar worked examples.
12. Score correlations are produced.
13. First fold has at least 45 usable train days.
14. Fold construction includes purge and embargo in total span.
15. Incomplete max-horizon events are excluded and counted.
16. Pack builder refuses stale/failed audits before writing ZIP.
17. Pack checker verifies scoring_run_id and Parquet content.
18. Safety audit still passes; create/close/order/Telegram remain absent.

---

# Acceptance commands on owner Windows machine

No market downloads, range detection or outcome rebuilds are needed.

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

Build v3 grains:

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v3_123x90
```

Build cost/scoring:

```powershell
python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v3_123x90 `
  --fee-snapshot-id fee_linear_20260711T112444Z `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

Build and audit splits:

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v3_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v3_123x90
```

Build/check pack:

```powershell
python scripts/report_cost_and_scoring.py `
  --scoring-run-id scoring_cost_v3_123x90

python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v3_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v3_123x90.zip `
  --scoring-run-id scoring_cost_v3_123x90
```

---

# Definition of Done / Gate 5A

Gate 5A closes only when:

```text
all tests and ruff pass
safety audit passes
all four grain row counts match 26795 / 80385 / 80385 / 241155
grain contract audit passes
no Frankenstein/invariant conflicts
fee coverage = 100%
resolved cost config names the real snapshot/source
cost formula/slippage audit passes
cost scenario summary exists
incomplete evidence is never scored as perfect
scores are grain-specific, bounded, finite and proxy-labelled
score correlation report exists
first fold has >=45 usable train days
walk-forward coverage and temporal leakage audits pass
review pack is self-contained and checker passes
risk_budget_proven_bool remains false
```

No parameter selection and no profitability claim are allowed.

---

# Required Codex final summary

Provide:

```text
commit hash
changed files
pytest output
ruff output
source/grain/contract/Cartesian audit summaries
resolved fee snapshot ID and coverage
cost formula and scenario summary
score component/correlation summary
walk-forward fold/coverage/leakage summary
review pack checker output
confirmation that risk_budget_proven_bool=false
confirmation that no live/create/close/order/Telegram code was added
```
