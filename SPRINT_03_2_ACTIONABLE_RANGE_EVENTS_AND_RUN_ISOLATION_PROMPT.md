# Sprint 03.2 — Actionable Range Events, Run Isolation, and Density Calibration

PM decision: Sprint 03.1 implementation is accepted as a diagnostic layer, but Gate 3 is not closed. The current event layer is still too dense and mixes stale outputs across runs. Do not start future outcomes/backtest/live.

## Current evidence

Owner machine run:

- `pytest -q` -> 96 passed.
- `ruff check .` -> passed.
- 10-symbol / 30-day smoke produced:
  - `candles_scanned=432000`
  - `raw_candidate_rows_written=1624243`
  - `event_candidate_rows_written=827358`
  - `candidates_per_10k_candles=37598.2`
- Full/large run produced:
  - `symbols_processed=123`
  - `candles_scanned=13282241`
  - `raw_candidate_rows_written=15119283`
  - `event_candidate_rows_written=7697366`
- Density summary from parquet:
  - `balanced_research_raw=15647225`
  - `balanced_research_event=7964728`
  - `raw_to_event_compression_ratio≈1.96`
  - `event_candidates_per_symbol_day_p50≈908`
  - `event_candidates_per_symbol_day_p90≈1253`
  - `event_candidates_per_symbol_day_p99≈1515`
  - `symbols_with_events=123`

This is not ready for Sprint 04 outcomes. Current “events” are still repeated minutes/windows inside the same range, not actionable range-entry events.

## Hard safety rules

- Do not implement future outcomes.
- Do not implement PnL/backtest.
- Do not implement live signals.
- Do not implement Telegram.
- Do not implement order/create/close/grid execution.
- Preserve all create/close NotImplementedError guardrails.
- No Bybit private calls in this sprint.
- No API downloads are needed; use existing local Parquet data only.

## FAST-first rules

- Default to FAST mode.
- Use maximum safe local parallelism.
- Use lazy Polars scans where possible.
- Avoid writing huge raw layers by default.
- All heavy scripts need `--dry-run-plan`, progress, ETA, resume/checkpoint, and run summaries.
- No stale output mixing across runs.
- If planned runtime > 10 minutes, print plan and require `--confirm-large-run`.

## Main blockers to fix

### B01 — Event density is far too high

Balanced profile currently produces ~7.96M events and p99 around 1515 events/symbol/day. Gate target is:

```text
balanced/actionable event_candidates_per_symbol_day_p99 <= 200
raw_to_event_compression_ratio >= 10
```

### B02 — Event coalescing is too narrow

Current coalescer groups by:

```text
symbol, profile_name, lookback_minutes, range_cluster_id
```

This keeps separate events for each lookback. For an actionable event layer, multiple lookbacks that describe the same range at the same time must be merged.

### B03 — Run outputs are not isolated

Reports can mix old smoke outputs with new full outputs. Example: a 10-symbol smoke report showed `event_symbols_processed=11`. This is unacceptable for PM gates.

### B04 — Rejection counters are not real enough

Summary still shows zero for all rejection counters. Detector must materialize ordered rejection counts from total window positions, not only count accepted rows.

## Required architecture change

Keep 3 layers:

```text
1. raw window candidates        -> diagnostic only
2. range regimes/clusters       -> compressed continuous range states
3. actionable range events      -> Sprint 04 input
```

Do not use the current event layer as Sprint 04 input.

## 1. Add run isolation

Implement run IDs for range candidate builds.

Default output layout:

```text
data/processed/range_runs/<run_id>/raw_candidates/...
data/processed/range_runs/<run_id>/range_regimes/...
data/processed/range_runs/<run_id>/actionable_events/...
data/processed/range_runs/<run_id>/summary/range_candidate_summary.parquet
data/processed/range_runs/<run_id>/summary/range_density_summary.parquet
reports/sprint_03_2_range_actionable_report_<run_id>.md
```

Also write/update:

```text
data/processed/range_runs/latest_run.txt
```

CLI:

```bash
python scripts/build_range_candidates.py --run-id auto
python scripts/report_range_candidates.py --run-id latest
python scripts/report_range_candidate_density.py --run-id latest
```

Rules:

- Never mix old outputs with a new run.
- `--skip-existing-ok` applies only within the same `run_id`.
- `--resume` applies only within the same `run_id`.
- `report_*` must default to latest run, not scan all historical outputs.
- Add `scripts/list_range_runs.py` and `scripts/purge_range_run.py --run-id <id>`.

## 2. Add cross-lookback actionable event coalescing

Create or update:

```text
src/bybit_grid/research/range_regime_coalescer.py
src/bybit_grid/research/range_actionable_events.py
```

### Range cluster identity

Cluster ranges across lookbacks by symbol/profile and normalized price bounds.

Recommended range cluster size:

```text
cluster_size = max(
    current_close * cluster_bps / 10_000,
    atr_14 * cluster_atr_fraction,
    tick_size * min_tick_cluster_multiplier
)
```

Defaults:

```text
cluster_bps=25
cluster_atr_fraction=0.10
min_tick_cluster_multiplier=10
```

Do not include `lookback_minutes` in the actionable cluster key.

### Range regime

A regime is a continuous period where the same range cluster remains valid.

Allow small gaps:

```text
max_gap_inside_regime_minutes=5
```

Fields:

```text
range_regime_id
symbol
profile_name
range_cluster_id
first_seen_time_ms
last_seen_time_ms
regime_duration_minutes
raw_candidates_in_regime
lookbacks_observed
lookback_min
lookback_max
range_low_median
range_high_median
range_mid_median
best_score_in_regime
best_raw_candidate_id
```

### Actionable event

One actionable event is emitted when a valid range first becomes actionable.

Default mode:

```text
first_midzone_entry_per_regime
```

Emit only one event per regime unless re-entry mode is explicitly enabled.

Re-entry mode, optional:

```text
--allow-reentry-events
--min_minutes_outside_midzone-before-reentry 30
--max_events_per_regime 3
```

Default:

```text
allow_reentry_events=false
max_events_per_regime=1
```

Actionable event fields:

```text
range_action_event_id
range_regime_id
symbol
profile_name
signal_time_ms
signal_time_utc
best_lookback_minutes
lookbacks_observed
raw_candidates_in_regime
raw_candidate_id
range_low
range_high
range_mid
range_height_pct
range_height_atr_14
current_position_in_range
midline_crosses
min_touches_lower_zone
min_touches_upper_zone
amplitude_score
path_length_over_range
horizontal_score
range_quality_score
data_quality_ok
zero_volume_candles_in_window
missing_candles_in_window
bad_ohlc_in_window
fgrid_investment_min
min_investment_feasible_at_5usdt
```

## 3. Add range quality score

Create deterministic, no-lookahead `range_quality_score`.

Suggested components:

```text
+ amplitude_score
+ normalized_midline_crosses
+ normalized_touch_balance
+ path_length_over_range
+ horizontal_score
+ turnover_score
- zero_volume_penalty
- stale_touch_penalty
- slope_penalty
- too_narrow_penalty
- too_wide_penalty
```

Important: score must use only candles up to `signal_time_ms`.

When multiple raw candidates compete for one actionable event, choose the candidate with highest `range_quality_score`. Tie-breakers:

```text
1. higher range_quality_score
2. more midline_crosses
3. more balanced touches
4. longer lookback
5. earlier signal_time_ms
6. deterministic candidate_id
```

## 4. Add actionable profiles

Keep existing profiles but add:

```text
actionable_research
strict_actionable
```

Suggested defaults:

### actionable_research

```text
range_height_pct_min=0.0015
range_height_pct_max=0.08
range_height_atr_min=3.0
range_height_atr_max=50.0
min_midline_cross_count=4
min_touches_lower_zone=2
min_touches_upper_zone=2
max_abs_slope_pct_per_window=0.008
max_zero_volume_window_pct=0.02
min_path_length_over_range=3.0
min_range_quality_score=<calibrated>
```

### strict_actionable

```text
range_height_pct_min=0.002
range_height_pct_max=0.06
range_height_atr_min=4.0
range_height_atr_max=35.0
min_midline_cross_count=5
min_touches_lower_zone=2
min_touches_upper_zone=2
max_abs_slope_pct_per_window=0.005
max_zero_volume_window_pct=0.01
min_path_length_over_range=4.0
min_range_quality_score=<calibrated>
```

## 5. Add density calibration CLI

Add:

```text
scripts/calibrate_range_event_density.py
```

Goal: tune candidate/actionable profile thresholds without future outcomes.

CLI examples:

```bash
python scripts/calibrate_range_event_density.py --symbols-limit 20 --days-limit 30 --fast-max
python scripts/calibrate_range_event_density.py --symbols-limit 50 --days-limit 30 --fast-max --confirm-large-run
```

It should test a small grid of no-lookahead thresholds:

```text
min_midline_cross_count: 3,4,5,6
min_touches_lower_zone: 1,2,3
min_touches_upper_zone: 1,2,3
range_height_atr_min: 2,3,4,5
max_abs_slope_pct_per_window: 0.003,0.005,0.008,0.010
cooldown/regime mode: first_midzone_entry_per_regime only by default
cluster_bps: 25,50,100
```

Output:

```text
data/processed/range_runs/<run_id>/summary/range_density_calibration.parquet
reports/sprint_03_2_density_calibration_<run_id>.md
```

Required columns:

```text
profile_variant
raw_candidates_total
actionable_events_total
raw_to_actionable_compression_ratio
actionable_events_per_symbol_day_avg
actionable_events_per_symbol_day_p50
actionable_events_per_symbol_day_p90
actionable_events_per_symbol_day_p99
symbols_with_actionable_events
lookbacks_with_actionable_events
pass_density_gate
```

Density target:

```text
p50 between 1 and 50 actionable events/symbol/day
p90 <= 100
p99 <= 200
symbols_with_actionable_events >= 50 on full dataset
raw_to_actionable_compression_ratio >= 10
```

## 6. Real rejection counters

Implement ordered counters in detector.

For each symbol/profile/lookback:

```text
total_window_positions
missing_window_rejection_count
bad_ohlc_window_rejection_count
zero_volume_window_rejection_count
insufficient_history_rejection_count
range_height_rejection_count
middle_zone_rejection_count
lower_upper_entry_rejection_count
midline_cross_rejection_count
touch_count_rejection_count
slope_rejection_count
range_atr_rejection_count
boring_range_rejection_count
raw_candidate_pass_count
```

Store:

```text
data/processed/range_runs/<run_id>/summary/range_rejection_summary.parquet
reports/sprint_03_2_rejection_summary_<run_id>.md
```

Counters must be numeric and not all zero on non-trivial data.

## 7. Change defaults

Current default writes too much. Change defaults:

```text
--profile actionable_research
--output-layer actionable
--run-id auto
--fast-max true for heavy local processing
```

Raw layer must be opt-in:

```bash
--output-layer raw,event,actionable
```

`--profile all` is allowed for diagnostics only and must require `--confirm-large-run` on full data.

## 8. Reporting

Update:

```text
scripts/report_range_candidates.py
scripts/report_range_candidate_density.py
```

Reports must include:

```text
run_id
raw_candidates_total
event_candidates_total
actionable_events_total
raw_to_event_compression_ratio
raw_to_actionable_compression_ratio
actionable_events_per_symbol_day_p50/p90/p99
symbols_with_actionable_events
lookbacks_with_actionable_events
duplicate_action_event_id_count
duplicate_range_regime_id_count
rejection counters
cap_applied_count
acceptance_density_status
recommendation
```

Acceptance status:

```text
pass only if actionable layer, not legacy event layer, meets density gates.
```

## 9. Tests

Add tests for:

- run isolation: two runs do not mix outputs;
- latest_run pointer works;
- report defaults to latest run;
- cross-lookback candidates merge into one regime/actionable event;
- same range cluster across adjacent lookbacks emits one action event;
- different range clusters emit separate events;
- one regime emits only one event by default;
- re-entry mode emits at most configured max;
- deterministic range_action_event_id;
- range_quality_score uses no future data;
- tie-breaker deterministic;
- rejection counters non-zero on synthetic failing windows;
- calibration report computes p50/p90/p99;
- density gate fails current loose profile and passes a synthetic calibrated profile;
- no live create/close/order code introduced.

## 10. Acceptance commands

Smoke:

```powershell
python -m pytest -q
ruff check .
python scripts/calibrate_range_event_density.py --symbols-limit 10 --days-limit 30 --fast-max
python scripts/build_range_candidates.py --dry-run-plan --symbols-limit 10 --days-limit 30 --profile actionable_research --output-layer actionable --fast-max
python scripts/build_range_candidates.py --symbols-limit 10 --days-limit 30 --profile actionable_research --output-layer actionable --fast-max --run-id smoke_actionable_10x30
python scripts/report_range_candidates.py --run-id smoke_actionable_10x30
python scripts/report_range_candidate_density.py --run-id smoke_actionable_10x30
```

Full run:

```powershell
python scripts/build_range_candidates.py --profile actionable_research --output-layer actionable --fast-max --confirm-large-run --skip-existing-ok --run-id action_123x90_v1
python scripts/report_range_candidates.py --run-id action_123x90_v1
python scripts/report_range_candidate_density.py --run-id action_123x90_v1
```

Optional diagnostic full raw run is forbidden unless PM explicitly asks.

## 11. Gate 3 acceptance criteria

Gate 3 closes only if:

```text
pytest passed
ruff passed
actionable_events_total > 0
symbols_with_actionable_events >= 50
lookbacks_with_actionable_events >= 3
raw_to_actionable_compression_ratio >= 10
actionable_events_per_symbol_day_p50 between 1 and 50
actionable_events_per_symbol_day_p90 <= 100
actionable_events_per_symbol_day_p99 <= 200
duplicate_action_event_id_count = 0
rejection counters numeric and non-zero where expected
reports are run-isolated
no stale output mixing
no live/create/close/order code
```

If density still fails, output the top 5 candidate calibration variants and do not proceed to Sprint 04.
