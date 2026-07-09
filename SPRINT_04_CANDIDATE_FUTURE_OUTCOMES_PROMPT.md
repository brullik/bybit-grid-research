# Sprint 04 — Candidate Future Outcomes Dataset

PM decision: Gate 3 is closed. Sprint 04 is approved.

This sprint builds future-outcome labels for actionable range events. It must not optimize parameters, backtest a strategy, or run live trading. The goal is to describe what happened after each actionable range event so Sprint 05 can score grid suitability and build a real backtest.

## Accepted input state

Accepted range event run:

```text
range_run_id = action_density_v2_123x90
profile = actionable_density_v2
raw_candidates_total = 1,194,360
actionable_events_total = 5,359
raw_to_actionable_compression_ratio = 222.8699
actionable_events_per_symbol_day_p50 = 1.0
actionable_events_per_symbol_day_p90 = 5.0
actionable_events_per_symbol_day_p99 = 10.0
symbols_with_actionable_events = 112
lookbacks_with_actionable_events = 7
duplicate_action_event_id_count = 0
acceptance_density_status = pass
```

## Non-negotiable safety rules

- Do not implement live trading.
- Do not implement Bybit create/close grid bot.
- Do not implement ordinary order endpoints.
- Do not add Telegram/live execution.
- Do not optimize parameters for profit in this sprint.
- Do not claim realized PnL or real liquidation behavior.
- Use outcome labels and proxies only.
- Keep all outputs run-isolated.
- Preserve FAST-first behavior.

## Performance requirements

Default to FAST mode.

- Use Polars lazy scans for Parquet I/O.
- Use NumPy/array processing for per-symbol outcome calculations.
- Process symbols in parallel.
- Add `--fast-max`, `--workers`, `--dry-run-plan`, `--resume`, `--skip-existing-ok`.
- Add progress + ETA.
- No serial full-dataset loops.
- No API calls are needed in Sprint 04.
- No full Cartesian grids unless PM explicitly approves.
- If planned runtime > 10 minutes, print the plan and require `--confirm-large-run`.

## Inputs

Required:

```text
data/processed/range_runs/action_density_v2_123x90/actionable_events/**
data/processed/range_runs/action_density_v2_123x90/summary/range_candidate_perf.json
data/processed/research_download_manifest.parquet
data/raw/klines/**
data/raw/mark_klines/**
data/raw/funding/**
data/processed/fgrid_validate_constraints.parquet or fgrid_min_investment_by_symbol.parquet
```

Do not require raw candidates or range regimes for the main outcome run.

## Outputs

Use run isolation:

```text
data/processed/outcome_runs/<outcome_run_id>/outcomes/symbol=<SYMBOL>/year=<YYYY>/month=<MM>/outcomes.parquet
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_summary.parquet
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_quality_summary.parquet
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_perf.json
data/processed/outcome_runs/latest_outcome_run.txt
reports/outcome_runs/<outcome_run_id>/outcome_report.md
reports/outcome_runs/<outcome_run_id>/outcome_quality_report.md
```

Default run id:

```text
outcomes_action_density_v2_123x90_v1
```

## New modules/scripts

Add or update:

```text
src/bybit_grid/research/outcome_core/models.py
src/bybit_grid/research/outcome_core/outcome_numpy.py
src/bybit_grid/research/outcome_core/grid_crossings.py
src/bybit_grid/research/outcome_core/funding_join.py
src/bybit_grid/research/outcome_store.py
src/bybit_grid/research/outcome_summary.py
scripts/build_candidate_outcomes.py
scripts/report_candidate_outcomes.py
scripts/make_outcome_review_pack.py
scripts/check_outcome_review_pack.py
tests/test_sprint_04_candidate_outcomes.py
```

## Outcome semantics

For each actionable event:

- `signal_time_ms` is the detection time.
- Future labels must start after the signal time.
- Default entry label starts at the next 1m candle after `signal_time_ms`.
- The candle/window used to create the event must not be used as future evidence.
- It is allowed to use future data in Sprint 04 because these are labels, not live features.

## Default horizons

Use multiple horizons, but keep the default manageable:

```text
future_horizons_minutes = [60, 240, 720, 1440, 2880]
```

Each event may produce one row per horizon.

Expected rough scale:

```text
5,359 events × 5 horizons ≈ 26,795 outcome rows
```

This is acceptable.

## Default grid proxy profiles

Do not optimize. Use small fixed probe profiles:

```text
grid_counts = [5, 10, 20]
sl_atr_buffers = [0.0, 0.5, 1.0]
```

This may produce:

```text
5,359 events × 5 horizons × 3 grid_counts × 3 SL buffers ≈ 241,155 rows
```

If this is too large, use `--grid-counts 10 --sl-atr-buffers 0.5` for smoke and only expand after PM approval.

## Required output columns

Identity:

```text
outcome_id
range_action_event_id
range_regime_id
symbol
profile_name
signal_time_ms
entry_time_ms
future_horizon_minutes
grid_count
sl_atr_buffer
```

Event/range context copied from actionable event:

```text
best_lookback_minutes
lookbacks_observed
range_low
range_high
range_mid
range_height_pct
range_height_atr_14
range_quality_score
path_length_over_range
midline_crosses
min_touches_lower_zone
min_touches_upper_zone
fgrid_investment_min
min_investment_feasible_at_5usdt
```

Future coverage:

```text
future_rows_available
future_coverage_minutes
future_data_complete_bool
future_missing_minutes_count
future_bad_ohlc_count
future_zero_volume_count
```

Range survival:

```text
first_exit_side              # up/down/none
first_exit_time_ms
minutes_to_first_exit
time_inside_range_minutes
inside_range_ratio
max_high_above_range_pct
max_low_below_range_pct
max_close_distance_from_mid_pct
```

SL proxy:

```text
lower_sl_price
upper_sl_price
first_sl_side                # upper/lower/none
first_sl_time_ms
minutes_to_first_sl
sl_hit_bool
sl_distance_lower_pct
sl_distance_upper_pct
```

Grid activity proxy:

```text
geometric_grid_levels_json or fixed-level summary columns
future_grid_level_cross_count
future_midline_cross_count
future_upper_zone_touch_count
future_lower_zone_touch_count
grid_crossings_per_hour
grid_step_pct_mean
grid_step_fee_multiple_proxy
```

Funding/mark context:

```text
funding_rows_in_horizon
funding_rate_sum
funding_rate_abs_sum
mark_price_future_rows_available
mark_price_max_deviation_from_last_pct
```

Labels for later scoring, not final strategy:

```text
label_stayed_in_range_until_horizon
label_sl_hit_before_horizon
label_good_chop_proxy
label_low_activity_proxy
label_high_breakout_risk_proxy
```

## Label definitions

Keep labels transparent and configurable. Defaults:

```text
label_stayed_in_range_until_horizon = first_exit_side == "none"
label_sl_hit_before_horizon = sl_hit_bool
label_good_chop_proxy = inside_range_ratio >= 0.70 and future_grid_level_cross_count >= min_crossings_for_horizon
label_low_activity_proxy = future_grid_level_cross_count < min_crossings_for_horizon
label_high_breakout_risk_proxy = sl_hit_bool or inside_range_ratio < 0.40
```

Do not use these labels as trading rules yet.

## CLI commands

### Dry run

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_smoke_10x30_v1 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 10 `
  --sl-atr-buffers 0.5 `
  --dry-run-plan `
  --fast-max
```

### Smoke

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_smoke_10x30_v1 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 10 `
  --sl-atr-buffers 0.5 `
  --fast-max

python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_smoke_10x30_v1
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_smoke_10x30_v1
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_smoke_10x30_v1.zip --outcome-run-id outcomes_smoke_10x30_v1
```

### Full run

Only after smoke passes:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_action_density_v2_123x90_v1 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok

python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v1
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v1
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v1.zip --outcome-run-id outcomes_action_density_v2_123x90_v1
```

## Required tests

Add tests for:

- no-lookahead labeling: future starts after signal;
- first exit side/time;
- SL proxy upper/lower hit;
- grid-level crossing count;
- geometric grid levels monotonicity;
- funding aggregation by horizon;
- missing future data handling;
- deterministic `outcome_id`;
- partition write and dedupe;
- report and review pack allowlist;
- no live/create/close/order code.

## Gate 4 acceptance criteria

Gate 4 closes only if:

```text
pytest passes
ruff passes
outcome_rows_total > 0
unique outcome_id count == row count
future_data_complete rate is reported
first_exit_side distribution exists
sl_hit distribution exists
grid crossing distribution exists
funding aggregation exists
no duplicate range_action_event_id/horizon/grid/sl rows
no live/create/close/order code
review pack passes checker
```

## What the owner must send after Sprint 04

Text in chat:

```text
commit hash
files changed
pytest -q output
ruff check . output
dry-run plan output
smoke outcome build output
smoke outcome report summary
full outcome build output, if run
full outcome report summary, if run
```

Files to upload only:

```text
pm_review_pack_outcomes_smoke_10x30_v1.zip
```

If full run was executed, also upload:

```text
pm_review_pack_outcomes_action_density_v2_123x90_v1.zip
```

If `make_outcome_review_pack.py` breaks, manually upload only:

```text
reports/outcome_runs/<outcome_run_id>/outcome_report.md
reports/outcome_runs/<outcome_run_id>/outcome_quality_report.md
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_summary.parquet
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_quality_summary.parquet
data/processed/outcome_runs/<outcome_run_id>/summary/outcome_perf.json
```

Do not upload:

```text
full repo archive
data/raw
outcomes parquet partitions
range raw/actionable/regime partitions
.env
__pycache__
.pytest_cache
.ruff_cache
```

## PM note

Sprint 04 is an outcome-labeling sprint, not a strategy-selection sprint. It prepares the evidence for Sprint 05, where we will start ranking parameter families and building a real walk-forward backtest.
