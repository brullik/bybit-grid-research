# Sprint 04.3 — Outcome Semantics: ATR-Correct SL, Ambiguity, Activity Proxies

PM decision: the technical Outcome v2 run is valid for data coverage, range exits, funding diagnostics, and deterministic IDs, but Gate 4 remains open because the SL proxy uses the wrong units and several summary metrics are duplicated across probe dimensions.

Do not start scoring, parameter optimization, backtesting, Telegram, or live execution.

## Accepted inputs

- Range run: `action_density_v2_123x90`
- Existing technical outcome run: `outcomes_action_density_v2_123x90_v2`
- Existing v2 rows: 241,155
- Existing v2 unique IDs: 241,155
- Existing v2 duplicates: 0
- Existing v2 future completeness: ~99.679%
- Existing v2 funding diagnostics are present

Do not mutate or overwrite v2. Build a new semantics version.

## Critical semantic defect

Current code effectively does:

```python
atr_pct = event["range_height_atr_14"] * sl_atr_buffer
lower_sl = range_low * (1 - atr_pct / 100)
upper_sl = range_high * (1 + atr_pct / 100)
```

But `range_height_atr_14` is a dimensionless ratio:

```text
range_height_abs / atr_14_abs
```

It is not ATR percent. Therefore existing v2 `lower_sl_price`, `upper_sl_price`, `sl_distance_*`, `first_sl_*`, and `sl_hit_bool` must not be treated as valid SL labels.

Correct calculation:

```python
range_height_abs = range_high - range_low
atr_14_abs = range_height_abs / range_height_atr_14
lower_sl = range_low - sl_atr_buffer * atr_14_abs
upper_sl = range_high + sl_atr_buffer * atr_14_abs
```

If a future event schema contains direct `atr_14`, prefer it and verify consistency with the derived value.

## Safety rules

- No Bybit API calls are required.
- No downloads are required.
- Do not implement create/close/order/live/Telegram.
- Do not optimize parameters or select winners.
- Preserve no-lookahead entry at the first minute strictly after `signal_time_ms`.
- Keep FAST-first behavior, run isolation, resume, progress, ETA, and review-pack hygiene.

## Required changes

### 1. Add outcome semantics versioning

Every new outcome row must contain:

```text
outcome_semantics_version = "v3_atr_correct"
range_run_id
outcome_run_id
atr_value_source
```

`atr_value_source` values:

```text
direct_event_atr_14
derived_range_height_over_ratio
missing_or_invalid
```

New run IDs:

```text
outcomes_semantics_v3_smoke_10x30
outcomes_semantics_v3_action_density_v2_123x90
```

### 2. Implement ATR-correct SL proxy

Add a dedicated helper module, for example:

```text
src/bybit_grid/research/outcome_core/sl_proxy.py
```

Functions should:

- derive or read `atr_14_abs`;
- validate finite positive ATR;
- compute upper/lower SL as boundary ± ATR units;
- compute distance in absolute price and percent;
- expose `sl_proxy_valid_bool` and `sl_proxy_invalid_reason`;
- preserve `sl_atr_buffer` as an ATR-unit value, never percent.

Required row fields:

```text
atr_14_abs_used
atr_rel_14_used
atr_value_source
sl_atr_buffer
lower_sl_price
upper_sl_price
sl_distance_lower_abs
sl_distance_upper_abs
sl_distance_lower_pct
sl_distance_upper_pct
sl_proxy_valid_bool
sl_proxy_invalid_reason
```

### 3. Handle same-candle path ambiguity

OHLC does not reveal the intrabar sequence. If one candle reaches both upper and lower range exits or both SLs, do not arbitrarily choose one side.

Use:

```text
first_exit_side = up | down | none | ambiguous_both
first_exit_ambiguous_bool
first_sl_side = upper | lower | none | ambiguous_both
first_sl_ambiguous_bool
```

Do not include ambiguous rows in directional win/loss interpretation later.

### 4. Separate grid activity proxies

Close-to-close crossings are not actual native-grid fills. Intrabar high/low touches can indicate more activity but also do not establish order sequence.

Keep and rename metrics transparently:

```text
future_close_level_cross_count
future_intrabar_level_touch_count
future_unique_grid_levels_touched_count
fill_activity_lower_bound_proxy
fill_activity_upper_bound_proxy
```

Backward compatibility:

```text
future_grid_level_cross_count = future_close_level_cross_count
```

Definitions:

- lower bound: close-to-close level crossings;
- upper activity proxy: sum of grid levels lying inside each candle `[low, high]`;
- unique levels touched: unique grid levels touched at least once during horizon.

Reports must state these are activity proxies, not actual fills.

### 5. Remove hardcoded fee assumption

Current hardcoded divisor `0.055` must not remain in production outcome logic.

Do not invent account-specific Bybit fees.

Replace with:

```text
grid_step_pct_mean
grid_step_bps_mean
```

Either remove `grid_step_fee_multiple_proxy`, or retain it only as null/legacy with an explicit deprecation field. Sprint 05 will add a configurable cost model.

Add a test that fails if the outcome core contains a hardcoded `0.055` fee divisor.

### 6. Correct summary grains

Current expanded outcome rows repeat some labels across grid counts and SL buffers. Add summaries at explicit grains:

#### Unique event-horizon grain

Deduplicate by:

```text
range_action_event_id + future_horizon_minutes
```

Report:

```text
unique_event_horizon_rows
future_data_complete_rate_unique_event_horizon
first_exit_side_distribution_unique_event_horizon
first_exit_ambiguous_rate_unique_event_horizon
funding_coverage_rate_unique_event_horizon
funding_rows_joined_unique_event_horizon
```

#### SL-probe grain

Deduplicate grid count and group by:

```text
future_horizon_minutes + sl_atr_buffer
```

Report:

```text
sl_hit_rate
sl_ambiguous_rate
sl_proxy_invalid_rate
median_minutes_to_first_sl
```

#### Grid-activity grain

Group by:

```text
future_horizon_minutes + grid_count
```

Report lower/upper proxy distributions.

Keep old aggregate fields only for backward compatibility and label them as expanded-row metrics.

### 7. Clarify funding metrics

Because funding values are repeated across grid-count and SL-buffer combinations, distinguish:

```text
funding_joined_instances_expanded_rows
funding_joined_unique_event_horizon
funding_coverage_rate_unique_event_horizon
funding_source_status_counts_unique_event_horizon
```

Do not present a repeated expanded-row count as a count of unique funding events.

### 8. Add semantic audit script

Add:

```text
scripts/audit_outcome_semantics.py
```

Usage:

```powershell
python scripts/audit_outcome_semantics.py --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90
```

Checks:

- all nonzero valid SL buffers satisfy `distance_abs ≈ buffer * atr_14_abs_used`;
- upper SL > range_high and lower SL < range_low for buffer > 0;
- no finite/nonpositive ATR accepted;
- ambiguity fields are internally consistent;
- unique event-horizon metrics do not multiply with grid/SL dimensions;
- no hardcoded fee proxy remains;
- deterministic unique `outcome_id`;
- composite duplicates = 0.

Print strict JSON and exit nonzero on failure.

### 9. Tests

Add regression tests for:

- ATR-unit derivation from `(range_high - range_low) / range_height_atr_14`;
- direct ATR preference and consistency check;
- 0.5 ATR means exactly half an ATR outside range boundary;
- `range_height_atr_14` is never treated as percent;
- invalid/zero ATR behavior;
- same-candle both-side exit ambiguity;
- same-candle both-side SL ambiguity;
- close crossing lower-bound proxy;
- intrabar touch upper activity proxy;
- unique levels touched;
- unique event-horizon summary grain;
- SL summary not tripled by grid counts;
- funding summary not multiplied by grid/SL dimensions;
- no hardcoded `0.055` fee divisor;
- v2 is not overwritten;
- no live/create/close/order/Telegram additions.

## Required commands on owner machine

### Environment and tests

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python -m pytest -q
ruff check .
```

Note: if `pip check` reports only an unused Numba/NumPy conflict, record it. Do not silently uninstall shared-environment packages. A project-local `.venv` is preferred for future work.

### Smoke v3

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_semantics_v3_smoke_10x30 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 10 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max

python scripts/report_candidate_outcomes.py `
  --outcome-run-id outcomes_semantics_v3_smoke_10x30

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_semantics_v3_smoke_10x30
```

### Full v3

Run only if smoke audit passes:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok

python scripts/report_candidate_outcomes.py `
  --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90

python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_semantics_v3_action_density_v2_123x90.zip `
  --outcome-run-id outcomes_semantics_v3_action_density_v2_123x90
```

## Gate 4 acceptance criteria

- `pytest` and `ruff` pass;
- numeric environment doctor passes;
- v3 outcome rows > 0;
- unique outcome IDs equal row count;
- composite duplicates = 0;
- ATR audit passes;
- nonzero SL distances are based on ATR absolute units;
- ambiguous same-candle cases are reported, not assigned arbitrarily;
- activity lower/upper proxies are both present;
- no hardcoded fee divisor;
- unique event-horizon summaries exist;
- SL and funding summaries are not multiplied by irrelevant probe dimensions;
- funding diagnostics remain present;
- review pack checker passes;
- no live/create/close/order/Telegram code.

## Required output from Codex/user

Text summary:

- commit hash;
- changed files;
- `check_numeric_environment.py` output;
- `pip check` output;
- pytest output;
- ruff output;
- smoke build/report/audit summaries;
- full build/report/audit summaries;
- review-pack checker output.

Upload only:

```text
pm_review_pack_outcomes_semantics_v3_action_density_v2_123x90.zip
```

If full v3 was not run, upload only:

```text
pm_review_pack_outcomes_semantics_v3_smoke_10x30.zip
```

Do not upload the full repository, raw data, outcome partitions, range partitions, `.env`, caches, or virtual environments.
