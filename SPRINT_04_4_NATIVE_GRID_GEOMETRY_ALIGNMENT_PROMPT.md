# Sprint 04.4 — Native Bybit Grid Geometry Alignment + Semantic Audit Seal

PM decision: v3 fixed ATR/SL semantics, same-candle ambiguity, activity-proxy naming, funding summary grains, and fee-proxy deprecation. However, Gate 4 remains open because the current geometric-grid level generator interprets `grid_count=N` as N price levels rather than N grid intervals.

This sprint is a narrow semantic correction. Do not add scoring, parameter optimization, backtesting, live execution, Telegram, order creation, or grid-bot create/close.

## Why this sprint is required

Bybit's native Futures Grid definition uses **number of grids = number of equal intervals**. For geometric mode:

```text
interval_ratio = (upper_price / lower_price) ** (1 / number_of_grids) - 1
```

Therefore, `number_of_grids=N` requires `N+1` boundary price levels, indexed `0..N`.

Current code:

```python
np.geomspace(low, high, grid_count)
```

creates only N price levels and N-1 intervals. This makes these v3 fields inconsistent with native Bybit geometry:

- `geometric_grid_levels_json`
- `grid_step_pct_mean`
- `grid_step_bps_mean`
- `future_close_level_cross_count`
- `future_intrabar_level_touch_count`
- `future_unique_grid_levels_touched_count`
- `fill_activity_lower_bound_proxy`
- `fill_activity_upper_bound_proxy`

Exit, SL, future coverage, mark-price context, and funding labels are not expected to change.

## Non-negotiable safety rules

- No API calls are required.
- No live trading.
- No order create/cancel.
- No Futures Grid create/close.
- No Telegram.
- No parameter scoring or optimization.
- Use only local Parquet data.
- Keep FAST-first behavior.
- Preserve run isolation.

## 1. Correct native grid geometry

Update `src/bybit_grid/research/outcome_core/grid_crossings.py`.

Implement:

```python
def geometric_grid_levels(
    low: float,
    high: float,
    cell_number: int,
) -> np.ndarray:
    """Return N+1 native-grid boundary levels for N geometric cells."""
```

Rules:

- `cell_number >= 2`.
- `low > 0`.
- `high > low`.
- Invalid geometric bounds must raise `ValueError`; do not silently fall back to arithmetic `linspace`.
- Return exactly `cell_number + 1` values.
- First level equals `low`.
- Last level equals `high`.
- Ratio between adjacent levels is:

```python
ratio = (high / low) ** (1.0 / cell_number)
```

- Enforce monotonic increasing levels.

Example contract:

```python
levels = geometric_grid_levels(10_000, 30_000, 5)
assert len(levels) == 6
assert levels[0] == 10_000
assert levels[-1] == 30_000
assert levels[1] / levels[0] == pytest.approx((3.0) ** (1/5))
```

## 2. Rename semantics without breaking old readers

In v4 outcome rows add canonical fields:

```text
grid_cell_number
grid_price_level_count
grid_interval_count
grid_interval_ratio
grid_interval_pct
grid_interval_bps
```

Definitions:

```text
grid_cell_number = requested native Bybit number of grids
grid_interval_count = grid_cell_number
grid_price_level_count = grid_cell_number + 1
grid_interval_ratio = (range_high / range_low) ** (1 / grid_cell_number)
grid_interval_pct = (grid_interval_ratio - 1) * 100
grid_interval_bps = grid_interval_pct * 100
```

Keep legacy fields only as explicit aliases:

```text
grid_count = grid_cell_number
grid_step_pct_mean = grid_interval_pct
grid_step_bps_mean = grid_interval_bps
```

Add:

```text
grid_count_semantics = "native_bybit_cell_number"
grid_geometry_semantics_version = "v1_n_cells_n_plus_1_levels"
```

## 3. Version the outcome identity

Set:

```text
outcome_semantics_version = "v4_native_grid_geometry"
```

Update deterministic outcome IDs so semantic versions cannot collide across runs.

Recommended:

```python
def deterministic_outcome_id(
    event_id: str,
    horizon: int,
    grid_cell_number: int,
    sl_atr_buffer: float,
    semantics_version: str,
) -> str:
    ...
```

Also emit a cross-version join key that excludes semantics version:

```text
outcome_match_key = hash(event_id, horizon, grid_cell_number, sl_atr_buffer)
```

This allows v3/v4 invariant comparison without treating semantically different rows as identical records.

## 4. Recompute activity proxies with N+1 levels

Use the corrected `levels` array for:

- close-to-close level crossings;
- intrabar level touches;
- unique levels touched.

Keep the labels explicit:

```text
fill_activity_lower_bound_proxy
fill_activity_upper_bound_proxy
```

Do not call these fills or completed trades.

Add optional diagnostic fields:

```text
future_internal_level_close_cross_count
future_internal_level_intrabar_touch_count
```

Here "internal" excludes lower and upper range boundaries. This helps distinguish activity inside the range from boundary exits.

Do not replace the existing all-level proxies; add internal-level variants.

## 5. Add native geometry regression tests

Tests must cover:

1. Five grids create six levels.
2. Exact endpoints.
3. Monotonic levels.
4. Constant adjacent geometric ratio.
5. Invalid bounds raise rather than arithmetic fallback.
6. `grid_price_level_count == grid_cell_number + 1`.
7. `grid_interval_count == grid_cell_number`.
8. `grid_interval_pct` matches the native formula.
9. v4 deterministic IDs differ from v3 IDs.
10. `outcome_match_key` is stable across v3/v4 semantics.
11. Activity proxy tests use corrected N+1 geometry.
12. Existing ATR, ambiguity, funding, dedupe, and no-live tests still pass.

## 6. Strengthen semantic audit

Update `scripts/audit_outcome_semantics.py`.

Require and validate:

```text
outcome_semantics_version == v4_native_grid_geometry
grid_geometry_semantics_version == v1_n_cells_n_plus_1_levels
grid_price_level_count == grid_cell_number + 1
grid_interval_count == grid_cell_number
len(geometric_grid_levels_json) == grid_cell_number + 1
first level ~= range_low
last level ~= range_high
adjacent ratio is constant
stored interval ratio/pct/bps match recomputation
```

Retain all v3 checks:

- SL distance equals `sl_atr_buffer * atr_14_abs_used`;
- valid ATR finite and positive;
- SL boundaries on correct sides;
- ambiguity fields consistent;
- fee proxy unpopulated;
- outcome IDs unique;
- composite duplicates zero;
- activity proxy columns present.

Write audit artifacts:

```text
data/processed/outcome_runs/<run_id>/summary/outcome_semantic_audit.json
reports/outcome_runs/<run_id>/outcome_semantic_audit.md
```

Audit JSON contract:

```json
{
  "semantic_audit_ok": true,
  "outcome_run_id": "...",
  "outcome_semantics_version": "v4_native_grid_geometry",
  "rows_checked": 241155,
  "failures": [],
  "checks": {...}
}
```

## 7. Add v3-to-v4 invariant comparison

Add:

```text
scripts/compare_outcome_runs.py
```

Command:

```powershell
python scripts/compare_outcome_runs.py `
  --baseline outcomes_semantics_v3_action_density_v2_123x90 `
  --candidate outcomes_semantics_v4_native_grid_123x90 `
  --expect-change grid_only
```

Join by `outcome_match_key` or the legacy composite key.

Fields that must remain invariant between v3 and v4:

```text
range_action_event_id
future_horizon_minutes
sl_atr_buffer
entry_time_ms
future_rows_available
future_data_complete_bool
first_exit_side
first_exit_time_ms
first_exit_ambiguous_bool
inside_range_candle_count
inside_range_ratio
atr_14_abs_used
lower_sl_price
upper_sl_price
first_sl_side
first_sl_time_ms
first_sl_ambiguous_bool
funding_rows_in_horizon
funding_rate_sum
funding_source_status
```

Fields expected to change:

```text
geometric_grid_levels_json
grid interval fields
close crossing proxies
intrabar touch proxies
unique level touch proxies
```

The comparison must fail if a non-grid invariant changes beyond numeric tolerance.

## 8. Include audit in the PM review pack

Update:

```text
scripts/make_outcome_review_pack.py
scripts/check_outcome_review_pack.py
```

Required v4 pack members:

```text
outcome_report.md
outcome_quality_report.md
outcome_semantic_audit.md
outcome_summary.parquet
outcome_quality_summary.parquet
outcome_perf.json
outcome_semantic_audit.json
```

Checker must reject packs when:

- semantic audit files are absent;
- `semantic_audit_ok != true`;
- outcome semantics version is not v4;
- grid geometry checks fail;
- forbidden raw/outcome partition data is present;
- duplicate IDs/composites exist;
- funding diagnostics are absent.

## 9. Build commands on owner machine

### Tests

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python -m pytest -q
ruff check .
```

### Smoke v4

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_semantics_v4_smoke_10x30 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_semantics_v4_smoke_10x30
```

### Full v4

Only after smoke audit passes:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90

python scripts/report_candidate_outcomes.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90

python scripts/compare_outcome_runs.py `
  --baseline outcomes_semantics_v3_action_density_v2_123x90 `
  --candidate outcomes_semantics_v4_native_grid_123x90 `
  --expect-change grid_only

python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_semantics_v4_native_grid_123x90.zip `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90
```

## 10. Definition of done

Sprint 04.4 is complete only when:

- all tests pass;
- ruff passes;
- smoke semantic audit passes;
- full semantic audit passes;
- v4 rows are unique;
- composite duplicates are zero;
- each N-grid row has N+1 levels;
- v3-to-v4 non-grid invariants match;
- only grid activity metrics change as expected;
- funding diagnostics remain present;
- PM review pack checker passes;
- no live/create/close/order/Telegram code is added.

## Required response from Codex

Provide:

- commit hash;
- files changed;
- tests output;
- ruff output;
- smoke audit output if available;
- full audit output if available;
- v3/v4 comparison output if available;
- review pack checker output if available.

## Files owner should upload after the run

Upload only:

```text
pm_review_pack_outcomes_semantics_v4_native_grid_123x90.zip
```

Do not upload the full repository archive or outcome partitions.

If the full run is not completed, upload only:

```text
pm_review_pack_outcomes_semantics_v4_smoke_10x30.zip
```
