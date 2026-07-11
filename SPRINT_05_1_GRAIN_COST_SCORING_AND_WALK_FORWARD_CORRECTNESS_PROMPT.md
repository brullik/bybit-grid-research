# Sprint 05.1 — Grain Integrity, Real Cost Integration, Ex-Post Scoring Semantics, and Purged Walk-Forward Repair

PM decision: Sprint 05 implementation foundation is accepted, but Gate 5A is **not closed**. Do not start the neutral-grid state machine or PnL backtest yet.

This sprint fixes correctness defects in the current scoring pipeline without rebuilding market data, range events, or canonical outcomes.

## Accepted upstream artifacts

Use these existing immutable inputs:

```text
outcome_run_id = outcomes_true_fast_v4_canonical_123x90_v1
fee snapshot = latest account_actual linear fee snapshot
```

Do not mutate `scoring_cost_v1_123x90`. Write a new run:

```text
scoring_run_id = scoring_cost_v2_123x90
```

## Non-negotiable safety rules

- No live order/create/cancel calls.
- No grid create/close implementation.
- No Telegram implementation.
- No PnL, ROI, EV, Profit Factor, Sharpe, or profitability claims.
- `risk_budget_proven_bool` remains false.
- FAST-first: Polars lazy scans/streaming where practical; no API calls except optional read-only fee snapshot refresh.
- Existing canonical outcome run is read-only.

---

# Blocker 1 — Outcome reader is ingesting summary Parquet files

The current scoring reader uses:

```python
root.rglob("*.parquet")
```

This includes files from the outcome run `summary/` directory in addition to actual partitioned outcome rows.

Observed evidence:

```text
canonical outcome rows = 241155
current expanded scoring rows = 241156
canonical event-horizon rows = 26795
current event-horizon rows = 26796
```

The arithmetic is diagnostic:

```text
26795 * 9 = 241155
26796 * 9 = 241164
actual = 241156
```

This is consistent with one orphan/null event-horizon row containing only one grid/SL combination.

## Required fix

Create one canonical outcome partition reader, for example:

```python
read_canonical_outcome_partitions(outcome_run_id)
```

It must read only:

```text
data/processed/outcome_runs/<run_id>/outcomes/symbol=*/year=*/month=*/outcomes.parquet
```

It must never read:

```text
summary/*.parquet
reports/**
benchmark outputs
repair artifacts
```

Resolve and de-duplicate physical paths before reading.

## Required key validation

Hard fail if any required key is null:

```text
range_action_event_id
future_horizon_minutes
grid_cell_number
sl_atr_buffer
outcome_id
outcome_match_key
symbol
signal_time_ms
```

Write:

```text
data/processed/scoring_runs/<scoring_run_id>/outcome_source_audit.json
```

Required fields:

```text
source_outcome_run_id
physical_files_found
unique_physical_files
summary_files_excluded
rows_loaded
null_key_rows
unique_outcome_id_count
duplicate_outcome_id_count
source_audit_ok
```

---

# Blocker 2 — Grain audit checks uniqueness but not Cartesian completeness

The current audit reports no duplicate keys, but it does not prove that every event-horizon has the complete requested probe set.

## Required Cartesian completeness audit

Infer the canonical probe sets from the valid outcome rows or run metadata:

```text
grid_cell_numbers = [5, 10, 20]
sl_atr_buffers = [0.0, 0.5, 1.0]
```

For every unique:

```text
range_action_event_id + future_horizon_minutes
```

require exactly:

```text
3 unique grid values
3 unique SL values
9 expanded combinations
```

Required expected cardinalities:

```text
event_horizon_grid_rows = event_horizon_rows * len(grid_set)
event_horizon_sl_rows = event_horizon_rows * len(sl_set)
expanded_rows = event_horizon_rows * len(grid_set) * len(sl_set)
```

Write:

```text
outcome_cartesian_completeness_audit.json
outcome_cartesian_incomplete_keys.parquet  # only if failures exist
```

Audit fields:

```text
event_horizon_rows
expected_event_horizon_grid_rows
actual_event_horizon_grid_rows
expected_event_horizon_sl_rows
actual_event_horizon_sl_rows
expected_expanded_rows
actual_expanded_rows
incomplete_event_horizon_count
unexpected_grid_values
unexpected_sl_values
cartesian_completeness_ok
```

The corrected run is expected to return to approximately:

```text
event_horizon = 26795
event_horizon_grid = 80385
event_horizon_sl = 80385
expanded = 241155
```

Do not hard-code those row counts in production logic; derive and audit them.

---

# Blocker 3 — Fee snapshot is collected but not used by scoring

Current `build_outcome_scoring_dataset.py` accepts:

```text
--fee-snapshot-id
--cost-config
```

but the builder does not load either one. The current scoring pack also omits the fee snapshot report and resolved fee coverage evidence.

## Required fee integration

Load:

```text
data/metadata/fee_snapshots/<fee_snapshot_id>/fee_rates.parquet
```

If `latest` is requested, resolve deterministically to the newest valid snapshot and record the resolved ID.

Join fee rates by:

```text
category + symbol
```

Normalize fee columns to numeric decimal fractions:

```text
maker_fee_rate
taker_fee_rate
```

No silent fallback to zero fees.

## Fee coverage audit

Write:

```text
fee_coverage_audit.json
fee_missing_symbols.parquet  # only when non-empty
```

Fields:

```text
fee_snapshot_id_requested
fee_snapshot_id_resolved
fee_source
scoring_symbols
symbols_with_fee_rates
symbols_missing_fee_rates
fee_coverage_rate
fee_coverage_ok
```

Default gate:

```text
fee_coverage_rate == 1.0
```

If account snapshot has multiple rows per symbol, fail unless they are identical after normalization.

## Snapshot CLI fix

`--symbols-from-outcome-run` must actually read symbols from the canonical outcome partitions and report coverage. It may still fetch all linear fee rates in one read-only request if the endpoint behaves that way, but the persisted report must identify:

```text
requested_outcome_symbols
covered_outcome_symbols
missing_outcome_symbols
```

---

# Blocker 4 — Short-side asymmetric fee formula is reversed

For a short grid cycle:

```text
entry: sell at P*r
exit:  buy at P
```

If `entry_fee_source=maker` and `exit_fee_source=taker`, then normalized by initial short-sale notional `P*r`:

```text
gross_short = (r - 1) / r
fee_short = entry_fee + exit_fee / r
```

The current implementation applies exit fee to the opening sell and entry fee to the closing buy.

## Required fix

Use explicit variables:

```python
entry_fee = select_fee(scenario.entry_fee_source)
exit_fee = select_fee(scenario.exit_fee_source)

fee_long = entry_fee + exit_fee * r + slippage
fee_short = entry_fee + exit_fee / r + slippage
```

Keep long and short denominators clearly documented.

Add worked-example regression tests for asymmetric maker/taker rates.

---

# Blocker 5 — Current ex-post scoring components are placeholders

The current implementation writes constants such as:

```text
ex_post_data_complete_score = 1.0
ex_post_ambiguity_penalty = 0.0
ex_post_sl_risk_score = 0.0
ex_post_close_cross_activity_lower = 0
ex_post_intrabar_touch_activity_upper = 0
ex_post_funding_missing_bool = true
```

Therefore the reported score means near `0.93–0.97` are not evidence about the outcomes.

## Required real component mapping

Use actual canonical outcome fields. All derived fields must remain explicitly `ex_post_*` and proxy-only.

### Data quality

```text
ex_post_data_complete_score = future_coverage_minutes / future_horizon_minutes, clipped 0..1
ex_post_bad_ohlc_rate = future_bad_ohlc_count / max(future_rows_available, 1)
ex_post_zero_volume_rate = future_zero_volume_count / max(future_rows_available, 1)
ex_post_ambiguity_penalty from first_exit_ambiguous_bool / first_sl_ambiguous_bool
```

### Range survival

Use:

```text
time_inside_range_minutes
minutes_to_first_exit
first_exit_side
future_data_complete_bool
```

Canonical fields:

```text
ex_post_range_survival_minutes
ex_post_range_survival_ratio
ex_post_stayed_in_range_bool
```

Do not treat incomplete future data as successful survival.

### SL proxy

Use:

```text
sl_proxy_valid_bool
sl_hit_bool
minutes_to_first_sl
first_sl_ambiguous_bool
sl_atr_buffer
```

Canonical fields:

```text
ex_post_sl_survival_bool
ex_post_minutes_to_sl
ex_post_sl_risk_score
ex_post_sl_ambiguity_penalty
```

Document the exact bounded formula for `ex_post_sl_risk_score`; it is a diagnostic proxy, not loss probability.

### Grid activity proxies

Use the actual fields:

```text
future_close_level_cross_count
future_intrabar_level_touch_count
future_unique_grid_levels_touched_count
```

Produce:

```text
ex_post_close_cross_activity_lower
ex_post_intrabar_touch_activity_upper
ex_post_unique_levels_touched
proxy_only_bool = true
not_actual_native_fills_bool = true
```

### Funding context

Use:

```text
funding_rate_sum
funding_rate_abs_sum
funding_rate_mean
funding_source_status
```

Produce:

```text
ex_post_funding_rate_sum_context
ex_post_funding_rate_abs_sum_context
ex_post_funding_missing_bool
ex_post_funding_no_overlap_bool
ex_post_funding_position_path_unknown_bool = true
```

Do not convert funding rates into PnL until position path exists.

### Capital lock proxy

Use a clearly documented event-horizon proxy based on the earliest relevant termination label available, clipped to the horizon. Do not label it actual capital utilization.

---

# Cost scenario fields on scoring rows

For each expanded scoring row, calculate cost diagnostics using the real symbol fee snapshot and its `grid_interval_ratio`.

Keep one row per original expanded outcome; add columns per scenario rather than multiplying rows.

For each scenario:

```text
cost_<scenario>_net_cycle_return_long_bps_proxy
cost_<scenario>_net_cycle_return_short_bps_proxy
cost_<scenario>_fee_break_even_long_bool
cost_<scenario>_fee_break_even_short_bool
cost_<scenario>_fee_break_even_both_bool
cost_<scenario>_fee_efficiency_ratio_long
cost_<scenario>_fee_efficiency_ratio_short
```

These are one-cycle fee diagnostics only. They are not event PnL.

Required provenance columns:

```text
cost_model_version
fee_snapshot_id
fee_source
maker_fee_rate
taker_fee_rate
```

---

# Score construction requirements

Fixed weights remain allowed, but scores must use real components.

## Null policy

Document and test all null handling. Missing/invalid evidence must not silently receive the best score.

## Score report

Replace the current mean-only sensitivity report with compact distributions:

```text
count
null_count
mean
std
p05
p25
median
p75
p95
min
max
```

for each fixed weight set.

Also report Spearman/Pearson correlations between fixed score variants, but do not optimize weights.

No threshold selection in this sprint.

---

# Blocker 6 — Walk-forward audit does not verify temporal label leakage

The current audit checks overlapping IDs and that an `embargo_minutes` column is at least 2880. It does not prove outcome windows remain inside their assigned role.

## Required event-level split protocol

Create one event-level assignment first, then join to all horizons/probes.

Use:

```text
max_outcome_horizon_minutes = max configured outcome horizon = 2880
outcome_end_ms = signal_time_ms + max_outcome_horizon_minutes * 60_000
```

For each fold:

```text
train window
purge gap before validation
validation window
embargo gap after validation
independent test window
```

Recommended prototype logic:

```text
train_end = validation_start - purge
validation events require outcome_end_ms <= validation_end

 test_start = validation_end + embargo
 test events require outcome_end_ms <= test_end
```

Do not assign events whose maximum outcome window crosses a role boundary.

Keep all events from the same `range_regime_id` in one role per fold.

## Required temporal leakage audit

For every fold verify:

```text
no range_action_event_id in multiple roles
no range_regime_id in multiple roles
max(train.outcome_end_ms) < validation_start_ms
max(validation.outcome_end_ms) < test_start_ms
all test outcome_end_ms <= test_end_ms
purge gap >= configured purge
embargo gap >= configured embargo
```

Write:

```text
walk_forward_fold_summary.parquet
walk_forward_temporal_leakage_audit.json
```

Report per fold:

```text
train_events
validation_events
test_events
train_start/end
validation_start/end
test_start/end
purged_event_count
embargo_excluded_event_count
regime_excluded_event_count
```

The audit must fail closed on any temporal violation.

---

# Review pack must be fail-closed and content-aware

The current checker only checks whether present filenames are allowlisted. It does not require all mandatory files or inspect audit statuses.

## Required pack members

```text
review_pack_manifest.json
fee_snapshot_report.md
fee_coverage_audit.json
cost_model_config_resolved.yml
cost_model_audit.json
outcome_source_audit.json
outcome_grain_audit.json
outcome_cartesian_completeness_audit.json
scoring_semantics_audit.json
outcome_scoring_summary.parquet
outcome_scoring_report.md
score_sensitivity_report.md
risk_budget_readiness_report.md
walk_forward_design_report.md
walk_forward_fold_summary.parquet
walk_forward_leakage_audit_summary.json
walk_forward_temporal_leakage_audit.json
```

The pack builder must generate/rebuild required reports, validate all audit files, then create the ZIP. It must not silently omit missing members.

The checker must require:

```text
source_audit_ok = true
grain_audit_ok = true
cartesian_completeness_ok = true
fee_coverage_ok = true
scoring_semantics_audit_ok = true
leakage_audit_ok = true
temporal_leakage_audit_ok = true
risk_budget_proven_bool = false
```

`outcome_scoring_summary.parquet` must be a compact aggregate summary—not the first 1000 raw scoring rows.

Manifest members must exactly match ZIP members.

---

# New/updated tests

Add tests for:

1. Summary Parquet is excluded from canonical outcome reads.
2. Null grain keys fail.
3. One orphan event-horizon with one of nine combinations fails Cartesian audit.
4. Complete 3×3 probe set passes.
5. Account fee snapshot joins by symbol with 100% coverage.
6. Missing fee symbol fails closed.
7. Short asymmetric entry/exit fee formula uses correct legs.
8. Ex-post components use non-constant source values.
9. Incomplete future data is not scored as perfect survival.
10. Funding `missing_file` and `no_overlap` remain distinct.
11. Event-level walk-forward assignments do not cross role boundaries.
12. Validation/test embargo is temporal, not merely metadata.
13. Review pack fails when a mandatory member is absent.
14. Review pack fails when any audit boolean is false.
15. Scoring summary is aggregate and contains no full raw dataset sample.
16. No live/create/close/order/Telegram additions.

---

# Acceptance commands on owner Windows machine

Do not rerun market downloads, range detection, or outcomes.

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

Build corrected grains under a new run ID:

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v2_123x90
```

Expected cardinality relationship:

```text
expanded_rows = event_horizon_rows * grid_count_cardinality * sl_buffer_cardinality
```

Build real cost/scoring dataset:

```powershell
python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v2_123x90 `
  --fee-snapshot-id latest `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

Build and audit splits:

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v2_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v2_123x90
```

Generate and check pack:

```powershell
python scripts/report_cost_and_scoring.py `
  --scoring-run-id scoring_cost_v2_123x90

python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v2_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v2_123x90.zip `
  --scoring-run-id scoring_cost_v2_123x90
```

---

# Definition of done

Gate 5A closes only when:

```text
all tests pass
ruff passes
source outcome rows = 241155 or a fully explained canonical count
no null grain keys
Cartesian probe completeness passes
actual fee snapshot is joined
fee coverage = 100%
short fee formula is corrected
ex-post components are sourced from real outcome columns
no placeholder constant scoring components remain
walk-forward temporal leakage audit passes
review pack is complete and fail-closed
risk_budget_proven_bool = false
no live execution code added
```

---

# Required output from Codex

Provide:

```text
commit hash
changed files
pytest output
ruff output
source/grain/cartesian audits
fee coverage summary
short fee formula regression result
scoring component audit summary
score distribution summary
walk-forward fold summary
leakage audit summary
review pack checker output
```

# Files for PM review

Upload only:

```text
pm_review_pack_scoring_scoring_cost_v2_123x90.zip
```

If pack creation fails, upload only these small files:

```text
outcome_source_audit.json
outcome_cartesian_completeness_audit.json
fee_coverage_audit.json
scoring_semantics_audit.json
walk_forward_temporal_leakage_audit.json
```

Do not upload the full repository, scoring dataset, outcomes, raw market data, `.env`, caches, or fee API raw responses.
