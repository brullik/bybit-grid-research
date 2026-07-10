# Sprint 04.5 — FAST Outcome Core v2 + Geometry Audit Precision Repair

## PM decision

Gate 4 is not yet closed because the v4 semantic audit fails with:

```text
adjacent grid ratio is not constant
```

The native N-cells/N+1-level geometry implementation is directionally correct. The observed failure is caused by lossy serialization:

```python
round(float(x), 10)
```

For low-priced symbols, rounding grid levels to 10 decimal places materially changes adjacent ratios even though the in-memory float64 levels were correct.

The full outcome build is also too slow. The current implementation repeatedly:

- filters the entire symbol Polars DataFrame for every event × horizon;
- filters mark-price data for every event × horizon;
- filters funding for every event × horizon;
- rescans SL hits once for every grid count even though SL is independent of grid count;
- accumulates all output rows as Python dicts before writing;
- uses only 4 workers even when `--fast-max` is provided.

This sprint has two independent deliverables:

1. repair/audit the existing v4 run without recomputing market outcomes;
2. add a materially faster outcome computation core for all future reruns.

## Safety constraints

- No Bybit API calls.
- No market-data downloads.
- No order/grid create/close.
- No Telegram/live code.
- No scoring, optimization, or backtest.
- Preserve outcome v4 semantics exactly except for lossless grid-level serialization and audit metadata.
- Do not mutate the accepted source run in place; write a new repaired run.

---

# Part A — Geometry serialization and audit repair

## A1. Use round-trip-safe level serialization

In `src/bybit_grid/research/outcome_core/grid_crossings.py`, replace 10-decimal rounding.

Required behavior:

```python
def levels_json(levels: np.ndarray) -> str:
    values = [float(x) for x in levels]
    return json.dumps(values, separators=(",", ":"), allow_nan=False)
```

Python float JSON representation must preserve enough digits to round-trip float64 values.

Add canonical field:

```text
grid_levels_serialization_version = float64_roundtrip_v1
```

Do not change:

```text
grid_cell_number
grid_interval_ratio
grid activity calculations
exit labels
SL labels
funding labels
outcome_match_key
```

## A2. Make geometry audit numerically robust

Update `scripts/audit_outcome_semantics.py`:

- audit full-precision serialized levels;
- validate endpoints;
- validate strict monotonicity;
- compare adjacent ratios in log-space or with scale-aware tolerance;
- report the first failing row with:
  - symbol;
  - outcome_id;
  - range_low/range_high;
  - grid_cell_number;
  - expected_ratio;
  - max_adjacent_ratio_abs_error;
  - max_adjacent_ratio_rel_error;
- retain all ATR/SL/ambiguity/funding/duplicate checks.

Recommended ratio check:

```python
expected_log_ratio = math.log(high / low) / n
actual_log_ratios = [math.log(levels[i + 1] / levels[i]) for i in range(n)]
max_error = max(abs(x - expected_log_ratio) for x in actual_log_ratios)
```

Use a float64-appropriate tolerance. The test must pass for low-priced symbols such as:

```text
low=0.000008
high=0.000012
cell_number=20
```

## A3. Repair existing v4 run without recomputing outcomes

Add:

```text
scripts/repair_outcome_grid_serialization.py
```

Command:

```powershell
python scripts/repair_outcome_grid_serialization.py `
  --source-run outcomes_semantics_v4_native_grid_123x90 `
  --target-run outcomes_semantics_v4_native_grid_123x90_r1
```

Behavior:

- read source outcome partitions;
- regenerate only canonical grid geometry/serialization fields from `range_low`, `range_high`, and `grid_cell_number`;
- keep `outcome_id` and `outcome_match_key` stable because economic semantics are unchanged;
- copy all non-grid fields exactly;
- write new run-isolated partitions;
- rebuild summaries;
- run semantic audit;
- compare source/target non-grid invariants;
- write machine-readable repair report.

Allowed changed fields:

```text
geometric_grid_levels_json
grid_levels_serialization_version
optional audit metadata only
```

All other fields must remain invariant.

Add comparison output:

```text
rows_compared
non_grid_drift_count
outcome_id_drift_count
outcome_match_key_drift_count
serialization_rows_changed
semantic_audit_ok
```

## A4. Review pack

Create/check the repaired run pack:

```text
pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip
```

The checker must require:

- semantic audit JSON/Markdown;
- `semantic_audit_ok=true`;
- repair comparison report;
- `non_grid_drift_count=0`;
- funding diagnostics;
- no outcome partitions/raw data/secrets/caches.

---

# Part B — FAST Outcome Core v2

## B1. New symbol-indexed array model

Add package/modules similar to:

```text
src/bybit_grid/research/outcome_core/symbol_arrays.py
src/bybit_grid/research/outcome_core/outcome_fast.py
src/bybit_grid/research/outcome_core/outcome_reference.py
scripts/profile_outcome_core.py
scripts/benchmark_outcome_cores.py
```

Create `OutcomeSymbolArrays` containing sorted contiguous arrays:

```text
time_ms
open
high
low
close
volume
mark_time_ms
mark_close
funding_time_ms
funding_rate
bad_ohlc_prefix
zero_volume_prefix
```

Build these arrays exactly once per symbol.

## B2. Never Polars-filter the full symbol frame inside event/horizon loops

Production fast core must not call:

```python
klines.filter(...)
mark_klines.filter(...)
funding.filter(...)
```

inside the event or horizon loops.

Use:

```python
start_idx = np.searchsorted(time_ms, entry_ms, side="left")
end_idx = np.searchsorted(time_ms, end_ms, side="left")
```

Use prefix sums/searchsorted for:

- missing/coverage checks;
- bad OHLC count;
- zero-volume count;
- funding count/sum/mean;
- mark window bounds.

## B3. Compute each semantic grain only once

Refactor an event into three reusable grains.

### Event-horizon base grain

Compute once per event × horizon:

```text
future coverage
first range exit
inside-range metrics
max excursion metrics
midline crossings
zone touches
mark-price context
funding aggregation
```

### Event-horizon-SL grain

Compute once per event × horizon × SL buffer:

```text
SL boundary
first SL side/time
SL ambiguity
SL hit
```

SL calculations must not be repeated for every grid count.

### Event-horizon-grid grain

Compute once per event × horizon × grid count:

```text
N+1 levels
close-cross proxy
intrabar-touch proxy
unique-level-touch proxy
interval ratio/bps
```

Finally materialize the Cartesian output rows from cached base/grid/SL grains without rescanning candles.

## B4. Reuse the maximum horizon window

For each event:

- slice the maximum requested horizon once;
- horizons are sorted ascending;
- compute per-candle activity arrays once;
- use cumulative sums / prefix maxima to derive shorter-horizon metrics.

For each grid count, calculate per-candle crossing/touch contributions once for the max horizon, then cumulative sums provide all requested horizons in O(1) each.

For each SL buffer, locate first hit in the max horizon once, then determine whether it falls inside each requested horizon.

## B5. Streaming writes

Do not retain all 241,155 rows as a single Python `list[dict]` in the main process.

Required:

- process one symbol at a time;
- produce a Polars DataFrame or Arrow table per symbol;
- write/dedupe symbol partitions immediately;
- release memory before the next completed symbol;
- keep only compact progress counters in the main process.

## B6. FAST worker policy

Make `--fast-max` real.

Add:

```text
--core reference|numpy_fast_v2
--executor auto|thread|process
--workers auto|N
--profile-core
```

Defaults:

```text
core = numpy_fast_v2
executor = auto
workers = auto
```

`auto` should choose the fastest safe local setting. At minimum:

```python
workers = min(len(symbols), max(1, (os.cpu_count() or 4) - 1), 16)
```

For CPU-heavy Python orchestration on Windows, benchmark process vs thread on a small sample and choose the faster mode. Avoid 64 CPU workers; maximum throughput, not maximum contention, is the goal.

## B7. Performance telemetry

Persist in `outcome_perf.json`:

```text
core_name
executor_name
workers_used
symbols_processed
events_processed
outcome_rows_total
total_runtime_seconds
market_data_load_seconds
array_prepare_seconds
base_grain_seconds
sl_grain_seconds
grid_grain_seconds
materialization_seconds
write_seconds
events_per_second
rows_per_second
peak_memory_mb
```

Progress:

```text
progress symbols_done=... symbols_total=... events_done=... rows_written=... events_per_sec=... rows_per_sec=... eta_sec=...
```

## B8. Equivalence tests

Keep the existing implementation as `reference` during this sprint.

Add tests comparing reference vs fast core on:

- synthetic events;
- low-priced symbols;
- missing future candles;
- same-candle ambiguity;
- all horizons;
- grid counts 5/10/20;
- SL buffers 0/0.5/1.0;
- funding overlap/no-overlap;
- mark-price data.

Required equality:

- exact IDs and categorical labels;
- exact integer counters;
- float equality within documented float64 tolerance;
- same row count and composite keys;
- no lookahead.

## B9. Benchmark targets

Smoke 10 symbols × 30 days:

```text
reference and fast outputs equivalent
fast runtime <= 20 seconds preferred
speedup >= 5x over current v4 smoke
```

Full 123 × 90:

```text
runtime <= 5 minutes preferred
runtime <= 10 minutes hard acceptance ceiling
241155 rows
no duplicates
semantic audit pass
```

If NumPy fast v2 still exceeds 10 minutes after profiling, prepare a separate Rust/PyO3 migration proposal. Do not implement Rust blindly in this sprint.

---

# Required commands on owner machine

## 1. Tests

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python -m pytest -q
ruff check .
```

## 2. Repair current v4 run — no heavy recomputation

```powershell
python scripts/repair_outcome_grid_serialization.py `
  --source-run outcomes_semantics_v4_native_grid_123x90 `
  --target-run outcomes_semantics_v4_native_grid_123x90_r1

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1

python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1
```

## 3. Benchmark fast core

```powershell
python scripts/benchmark_outcome_cores.py `
  --range-run-id action_density_v2_123x90 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0
```

## 4. Fast smoke run

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_fast_v2_smoke_10x30 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --core numpy_fast_v2 `
  --executor auto `
  --workers auto `
  --fast-max

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_fast_v2_smoke_10x30
```

Do not run a new full 123×90 outcome build unless:

- repaired existing v4 audit passes;
- core equivalence tests pass;
- smoke semantic audit passes;
- benchmark shows meaningful speedup.

---

# Required output from Codex

- commit hash;
- changed files;
- tests/lint output;
- geometry low-price regression result;
- repaired-run comparison summary;
- semantic audit summary;
- reference vs fast benchmark;
- smoke runtime and speedup;
- known blockers.

# Files the owner should upload after the run

Upload only:

```text
pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip
outcome_core_benchmark_summary.json
```

If the fast smoke was run, additionally upload:

```text
pm_review_pack_outcomes_fast_v2_smoke_10x30.zip
```

Do not upload:

```text
full repository archive
data/raw
outcome parquet partitions
range partitions
.env
.venv
__pycache__
.pytest_cache
.ruff_cache
```
