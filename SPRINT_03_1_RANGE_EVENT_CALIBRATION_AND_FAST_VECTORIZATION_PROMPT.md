# Sprint 03.1 — Range Event Calibration + FAST Vectorization

PM decision: Sprint 03 implementation is accepted as a technical foundation, but Gate 3 is not closed. The current detector produces too many raw candidates and likely emits every minute inside a range rather than one actionable range-detection event.

## Current evidence

Owner-machine smoke run:

- `pytest -q` -> 91 passed.
- `ruff check .` -> passed.
- 10 symbols x 30 days -> `candles_scanned=432000`.
- `candidate_rows_written=784071`.
- `candidates_per_10k_candles=18149.79`.
- runtime ~74.6 sec.
- `missing_window_rejection_count=not_materialized_fast_first`.
- `bad_ohlc_window_rejection_count=not_materialized_fast_first`.
- `zero_volume_window_rejection_count=not_materialized_fast_first`.

Interpretation:

- The detector is producing ~1.8 candidates per candle across lookbacks.
- This is acceptable as a broad diagnostic layer, but it is too dense for Sprint 04 outcome simulation.
- We need a second layer: raw window candidates -> coalesced event candidates.

## Non-negotiable safety rules

- Do not implement PnL backtest.
- Do not compute future outcomes.
- Do not implement Telegram/live signals.
- Do not implement create/close grid bot.
- Do not call private Bybit APIs.
- Do not use future candles in candidate construction.
- Maintain FAST-first defaults.
- Preserve raw candidates for diagnostics, but Sprint 04 must use event candidates.

## Performance requirements

- Default to FAST mode.
- Use all safe local CPU workers for symbol-level parallelism.
- Avoid Python per-row loops where possible.
- Use vectorized/lazy Polars rolling features or efficient numpy arrays.
- Every heavy script must have:
  - `--dry-run-plan`
  - progress + ETA
  - `--resume`
  - `--skip-existing-ok`
  - output row estimate
  - large-run guard
- If planned runtime > 10 minutes or output rows > 5,000,000, require `--confirm-large-run`.

## Goal

Convert Sprint 03 from a raw dense candidate generator into a calibrated research dataset with two output layers:

1. `range_raw_candidates` — broad diagnostic window-level candidates.
2. `range_event_candidates` — coalesced, actionable range-detection events suitable for Sprint 04 future-outcome simulation.

## Required outputs

```text
data/processed/range_raw_candidates/...
data/processed/range_event_candidates/...
data/processed/range_candidate_density_summary.parquet
reports/sprint_03_1_range_event_calibration_report.md
reports/sprint_03_1_range_candidate_perf.json
```

## 1. Add event coalescing

Implement:

```text
src/bybit_grid/research/range_event_coalescer.py
```

Input: raw candidates for a symbol.

Output: event candidates.

Rules:

### 1.1 Rising-edge event mode

For each `symbol + lookback_minutes + profile_name`, emit an event only when the previous candle was not an equivalent candidate.

Equivalent candidate uses a range cluster:

```text
range_low_cluster  = round(range_low / range_cluster_size)
range_high_cluster = round(range_high / range_cluster_size)
```

Default `range_cluster_size`:

```text
max(tick_size * 5, close_price * 0.0005)
```

If tick size is unavailable, use `close_price * 0.0005`.

### 1.2 Cooldown event mode

Add optional cooldown:

```text
cooldown_minutes_by_lookback = min(lookback_minutes / 4, 120)
```

Default: enabled for event candidates.

A new event can be emitted only if no equivalent event for the same symbol/lookback/range cluster occurred during cooldown.

### 1.3 Keep raw rows separate

Do not delete raw candidates. Store event candidates separately and add lineage fields:

```text
raw_candidate_id
range_event_id
range_cluster_id
event_mode
cooldown_minutes
raw_candidates_in_cluster
first_seen_time_ms
last_seen_time_ms
cluster_duration_minutes
```

## 2. Add candidate profiles

Create `config/range_profiles.yml` or constants with three profiles:

### broad_diagnostic

Purpose: reproduce current broad logic for diagnostics.

- mid-zone required.
- lower+upper zone entries required.
- loose horizontal filter.
- output raw + event.

### balanced_research

Purpose: default Sprint 04 input.

Initial defaults:

```yaml
range_height_pct_min: 0.001
range_height_pct_max: 0.10
range_height_atr_min: 2.0
range_height_atr_max: 80.0
min_midline_cross_count: 2
min_touches_lower_zone: 1
min_touches_upper_zone: 1
max_abs_slope_pct_per_window: 0.015
max_zero_volume_window_pct: 0.05
require_current_middle_zone: true
require_lower_upper_entries: true
```

### strict_research

Purpose: lower-noise candidate layer.

Initial defaults:

```yaml
range_height_pct_min: 0.002
range_height_pct_max: 0.07
range_height_atr_min: 3.0
range_height_atr_max: 50.0
min_midline_cross_count: 3
min_touches_lower_zone: 2
min_touches_upper_zone: 2
max_abs_slope_pct_per_window: 0.010
max_zero_volume_window_pct: 0.02
require_current_middle_zone: true
require_lower_upper_entries: true
```

Important: These are research-profile filters, not final trading parameters.

## 3. Add density diagnostics

Add:

```text
scripts/report_range_candidate_density.py
```

Report per profile:

- raw_candidates_total
- event_candidates_total
- raw_to_event_compression_ratio
- candidates_per_10k_candles_raw
- candidates_per_10k_candles_event
- event_candidates_per_symbol_day_avg
- event_candidates_per_symbol_day_p50/p90/p99
- symbols_with_events
- windows_with_events
- top symbols by event count
- top lookbacks by event count
- candidate counts by hour/day
- gap_affected_raw_candidates
- gap_affected_event_candidates
- zero_volume_affected candidates

Acceptance target for default balanced event layer:

```text
event_candidates_per_symbol_day_p50 between 0.2 and 50
event_candidates_per_symbol_day_p99 <= 200
raw_to_event_compression_ratio >= 10
```

If targets fail, report must say which profile/filter is too loose/tight.

## 4. Materialize rejection counters

The report currently shows:

```text
missing_window_rejection_count=not_materialized_fast_first
bad_ohlc_window_rejection_count=not_materialized_fast_first
zero_volume_window_rejection_count=not_materialized_fast_first
```

Replace with real counters:

- missing_window_rejection_count
- bad_ohlc_window_rejection_count
- zero_volume_window_rejection_count
- insufficient_history_rejection_count
- range_height_rejection_count
- middle_zone_rejection_count
- lower_upper_entry_rejection_count
- slope_rejection_count
- boring_range_rejection_count

These can be aggregated counters per symbol/profile/lookback. They do not need to store every rejected row.

## 5. Fix dry-run estimates

Current dry-run estimated rows for build candidates can be confusing. For candidate detection, estimate only normal kline rows that will be scanned, not mark/funding rows.

Expected for 10 symbols x 30 days:

```text
10 * 30 * 1440 = 432000 kline rows
```

Dry-run should print:

```text
estimated_kline_rows=432000
estimated_source=manifest/time_bounds
profiles=broad_diagnostic,balanced_research,strict_research
lookbacks=30,60,120,240,480,720,1440
```

## 6. Add CLI changes

Update `scripts/build_range_candidates.py`:

```bash
python scripts/build_range_candidates.py \
  --profile balanced_research \
  --output-layer raw,event \
  --symbols-limit 10 \
  --days-limit 30 \
  --fast-max
```

Flags:

- `--profile broad_diagnostic|balanced_research|strict_research|all`
- `--output-layer raw|event|both`
- `--coalesce-events`
- `--cooldown-mode lookback_fraction|fixed|none`
- `--cooldown-minutes 60` for fixed mode
- `--range-cluster-bps 5`
- `--max-event-candidates-per-symbol-day` default 300, warn if exceeded
- `--materialize-rejection-counters` default true

Update `scripts/report_range_candidates.py` to report both raw and event layers.

## 7. Testing requirements

Add tests for:

- event coalescing emits one event for consecutive raw candidates in same range cluster;
- different range clusters emit separate events;
- cooldown suppresses repeated events;
- after cooldown, new event is allowed;
- raw candidates are still preserved;
- no-lookahead still holds after profile filters;
- profile filters reduce broad -> balanced -> strict candidate counts;
- rejection counters are numeric, not placeholder strings;
- dry-run estimate for 10x30d equals 432000 kline rows when manifest has exact bounds;
- deterministic event_id generation;
- no live/create/close/order code was introduced.

## 8. Acceptance commands

Smoke:

```powershell
python -m pytest -q
ruff check .
python scripts/build_range_candidates.py --dry-run-plan --symbols-limit 10 --days-limit 30 --profile all --output-layer both --fast-max
python scripts/build_range_candidates.py --symbols-limit 10 --days-limit 30 --profile all --output-layer both --fast-max --skip-existing-ok
python scripts/report_range_candidates.py
python scripts/report_range_candidate_density.py
```

Full accepted run only after smoke:

```powershell
python scripts/build_range_candidates.py --profile balanced_research --output-layer both --fast-max --confirm-large-run --skip-existing-ok
python scripts/report_range_candidates.py
python scripts/report_range_candidate_density.py
```

Optional strict layer:

```powershell
python scripts/build_range_candidates.py --profile strict_research --output-layer both --fast-max --confirm-large-run --skip-existing-ok
python scripts/report_range_candidate_density.py
```

## 9. Gate 3 acceptance criteria

Gate 3 closes only if:

```text
pytest passed
ruff passed
no-lookahead tests passed
raw_candidates_total > 0
event_candidates_total > 0
raw_to_event_compression_ratio >= 10 for balanced_research
event_candidates_per_symbol_day_p99 <= 200 for balanced_research
symbols_with_events >= 50
all required lookbacks processed or skip reasons reported
no duplicate range_event_id
rejection counters are numeric
dry-run estimates are correct
report created
no live/create/close/order code
```

## 10. Do not proceed to Sprint 04 yet

Sprint 04 future outcomes starts only after Gate 3 is closed.
