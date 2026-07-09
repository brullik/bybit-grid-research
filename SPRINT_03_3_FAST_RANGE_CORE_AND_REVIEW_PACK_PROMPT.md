# Sprint 03.3 — Fast Range Core + Report Fix + Minimal Review Pack

PM decision: Sprint 03.2 implementation is accepted as a diagnostic/actionable layer, but Gate 3 is not closed. Full actionable run is too slow and density still fails. We now build a faster computation core and fix run-scoped reporting before any Sprint 04 outcome work.

## Current evidence

Owner-machine run:

```text
pytest: 96 passed
ruff: passed
smoke actionable 10x30: runtime_seconds=81.16, raw=281,325, actionable=82,513
full actionable 123x90: runtime_seconds=2679.22, raw=8,772,000, actionable=2,480,527
p50 actionable events/symbol/day=266
p90=416
p99=558
acceptance_density_status=fail
report_range_candidates.py crashes because actionable schema has best_lookback_minutes, not lookback_minutes
```

This is too slow for iterative research and too dense for Sprint 04.

## New project rule

All heavy computation must be FAST-first by default:

- maximum safe workers;
- vectorized or compiled core, no pure Python nested window loops for production;
- dry-run plan;
- progress + ETA;
- profiling report;
- checkpoint/resume;
- run isolation;
- minimal PM review pack after each run.

Correctness remains mandatory: no lookahead, deterministic IDs, and no live/create/close/order code.

## Why a faster core is needed

`src/bybit_grid/research/range_detector.py` currently converts Polars frames into Python dict/list data and then loops over:

```text
symbol -> lookback -> candle index -> window min/max/sum/set
```

This creates repeated Python work over overlapping windows. For 123 symbols x 90 days x 7 lookbacks, it is too slow.

## Core design decision

Do **not** rewrite the whole project in Rust yet. First add a replaceable core interface and a high-speed NumPy/compiled-kernel path.

Target architecture:

```text
Polars Lazy scan/parquet IO
    -> select only required columns and time bounds
    -> convert one symbol to contiguous NumPy arrays
    -> fast range detector kernel
    -> Polars DataFrame output
    -> regime/actionable coalescing
    -> partitioned run output
```

The core must be swappable later:

```text
python_reference  # current correctness baseline, small tests only
numpy_fast        # required default production core
numba_optional    # optional if environment supports it
rust_future       # not implemented in this sprint, only interface-ready
```

## Required work

### 1. Fix report crash immediately

`report_range_candidates.py` currently passes actionable events into `build_summary()`, but actionable rows use `best_lookback_minutes`, not `lookback_minutes`.

Fix `src/bybit_grid/research/range_candidate_summary.py` so it supports schemas:

- raw: `lookback_minutes`
- event/actionable: `best_lookback_minutes`
- regimes: `lookback_min`, `lookback_max`, `lookbacks_observed`

Report must never crash due to missing `lookback_minutes`.

### 2. Add profiler script

Add:

```text
scripts/profile_range_core.py
```

It must run on a small deterministic sample and write:

```text
reports/sprint_03_3_profile_summary.md
reports/sprint_03_3_profile_stats.json
```

It should measure at least:

- time spent loading parquet;
- time spent detecting raw candidates;
- time spent coalescing regimes;
- time spent building actionable events;
- time spent writing outputs;
- rows/sec by stage;
- peak-ish memory estimate if easily available.

Use `cProfile`/`pstats` for Python attribution and also explicit stage timers.

### 3. Add range core interface

Add module:

```text
src/bybit_grid/research/range_core/
  __init__.py
  models.py
  python_reference.py
  numpy_fast.py
  adapter.py
```

Interface:

```python
def detect_ranges_core(
    arrays: RangeInputArrays,
    symbol: str,
    profile: RangeProfile,
    lookbacks: tuple[int, ...],
    *,
    core: str = "numpy_fast",
) -> pl.DataFrame:
    ...
```

`RangeInputArrays` should hold contiguous arrays:

- `open_time_ms: np.ndarray[int64]`
- `open: np.ndarray[float64]`
- `high: np.ndarray[float64]`
- `low: np.ndarray[float64]`
- `close: np.ndarray[float64]`
- `volume: np.ndarray[float64]`
- optional `turnover: np.ndarray[float64]`

### 4. Implement `python_reference` for correctness comparison

Wrap existing logic or preserve equivalent logic so tests can compare small synthetic datasets.

This reference path is not used in full production runs.

### 5. Implement `numpy_fast` production core

Requirements:

- no `df.to_dicts()` in production detector;
- no repeated `min(lows[s:i+1])` / `max(highs[s:i+1])` loops;
- use contiguous NumPy arrays;
- precompute ATR14/ATR60 using vectorized or linear-time loops;
- compute rolling high/low in O(n) per lookback using monotonic deque or equivalent;
- compute bad/zero counts using prefix sums;
- use staged rejection:
  1. insufficient history / missing timestamps / duplicate timestamps;
  2. bad OHLC / zero-volume window limit;
  3. range height min/max;
  4. current middle zone;
  5. lower/upper entries;
  6. midline cross/touch requirements;
  7. slope/ATR/path/quality.
- Only run expensive window scans for rows that pass cheap filters.
- Preserve no-lookahead: row at index `i` may only use `[i-lookback+1, i]`.
- Output must preserve required columns currently consumed by coalescing/actionable code.

### 6. Add optional Numba/Rust readiness but do not force it

Do not make Numba required. The owner currently uses Python 3.14, and optional compiler dependencies may be fragile.

If Numba is available, allow:

```bash
python scripts/build_range_candidates.py --core numba_optional ...
```

But tests and default must work without Numba.

Do not implement Rust in this sprint. Add only a short `docs/performance_core_plan.md` describing when to move to Rust/PyO3:

- after profiling proves NumPy core is still too slow;
- after detector logic stabilizes;
- when expected speedup justifies build complexity on Windows.

### 7. Wire core into build CLI

Update `scripts/build_range_candidates.py`:

```bash
--core python_reference|numpy_fast|numba_optional
```

Default:

```text
--core numpy_fast
```

Add to progress/perf JSON:

- `core_name`
- `core_detect_seconds`
- `coalesce_seconds`
- `write_seconds`
- `rows_per_sec_by_core`
- `raw_candidates_per_sec`
- `actionable_events_per_sec`

### 8. Add density controls, but do not fake success

Current actionable density still fails:

```text
p50=266, p90=416, p99=558
```

Add stricter profile option:

```text
actionable_fast_strict
```

Default parameters should aim for:

```text
p50 <= 50
p90 <= 100
p99 <= 200
```

Use actual logic, not top-N clipping. If caps are added, reports must show uncapped and capped values.

Candidate quality filters to tune:

- min_range_quality_score;
- min_midline_cross_count;
- min_path_length_over_range;
- min_touches_lower_zone / upper_zone;
- max_abs_slope_pct_per_window;
- range_height_pct_min/max;
- min regime duration before action;
- minimum raw candidates per regime;
- one action per regime by default.

### 9. Real rejection funnel

Add numeric funnel counts from the fast core:

- `total_window_positions`
- `insufficient_history_rejection_count`
- `missing_window_rejection_count`
- `duplicate_timestamp_rejection_count`
- `bad_ohlc_window_rejection_count`
- `zero_volume_window_rejection_count`
- `range_height_rejection_count`
- `middle_zone_rejection_count`
- `lower_upper_entry_rejection_count`
- `midline_cross_rejection_count`
- `touch_count_rejection_count`
- `slope_rejection_count`
- `range_atr_rejection_count`
- `quality_score_rejection_count`
- `raw_candidate_pass_count`

These must be numeric in reports, not placeholders.

### 10. Minimal PM review pack

Add:

```text
scripts/make_pm_review_pack.py
```

Usage:

```bash
python scripts/make_pm_review_pack.py --run-id <RUN_ID>
```

It must create:

```text
pm_review_pack_<RUN_ID>.zip
```

Include only:

```text
reports/sprint_03_3_profile_summary.md
reports/sprint_03_3_core_benchmark.md
reports/sprint_03_range_candidate_report.md
reports/sprint_03_1_range_event_calibration_report.md
reports/sprint_03_2_density_report.md  # if present
reports/sprint_03_3_fast_core_report.md # if present
data/processed/range_runs/<run_id>/summary/*.json
data/processed/range_runs/<run_id>/summary/*.parquet
```

Exclude always:

```text
.env*
data/raw/**
data/processed/range_runs/<run_id>/raw_candidates/**
data/processed/range_runs/<run_id>/range_regimes/**
data/processed/range_runs/<run_id>/actionable_events/**
reports/runs/**
__pycache__/**
*.pyc
.pytest_cache/**
.ruff_cache/**
```

### 11. Tests

Add tests for:

- `report_range_candidates.py` does not crash on actionable schema with `best_lookback_minutes`;
- `numpy_fast` equals `python_reference` on small deterministic synthetic data for core fields;
- no-lookahead still holds;
- rejection counters are numeric and consistent;
- dry-run estimates still correct;
- PM review pack excludes raw data and secrets;
- no live/create/close/order implementation added.

## Acceptance commands

Smoke:

```powershell
python -m pytest -q
ruff check .
python scripts/profile_range_core.py --symbols-limit 3 --days-limit 7 --core numpy_fast
python scripts/build_range_candidates.py --dry-run-plan --symbols-limit 10 --days-limit 30 --profile actionable_fast_strict --output-layer actionable --core numpy_fast --fast-max
python scripts/build_range_candidates.py --symbols-limit 10 --days-limit 30 --profile actionable_fast_strict --output-layer actionable --core numpy_fast --fast-max --run-id smoke_fastcore_10x30
python scripts/report_range_candidates.py --run-id smoke_fastcore_10x30
python scripts/report_range_candidate_density.py --run-id smoke_fastcore_10x30
python scripts/make_pm_review_pack.py --run-id smoke_fastcore_10x30
```

Full run only if smoke density is reasonable:

```powershell
python scripts/build_range_candidates.py --profile actionable_fast_strict --output-layer actionable --core numpy_fast --fast-max --confirm-large-run --skip-existing-ok --run-id action_fastcore_123x90_v1
python scripts/report_range_candidates.py --run-id action_fastcore_123x90_v1
python scripts/report_range_candidate_density.py --run-id action_fastcore_123x90_v1
python scripts/make_pm_review_pack.py --run-id action_fastcore_123x90_v1
```

## Required PM output after owner run

Paste text:

- commit hash;
- files changed;
- `pytest -q` output;
- `ruff check .` output;
- `profile_range_core.py` summary;
- smoke build output;
- smoke density output;
- full build output if run;
- full density output if run.

Upload only these files, not full archive:

- `pm_review_pack_smoke_fastcore_10x30.zip`
- if full run was executed: `pm_review_pack_action_fastcore_123x90_v1.zip`

If review pack script fails, upload manually only:

```text
reports/sprint_03_3_profile_summary.md
reports/sprint_03_3_core_benchmark.md
data/processed/range_runs/<run_id>/summary/*.json
data/processed/range_runs/<run_id>/summary/*.parquet
```

Do not upload:

- full repo archive;
- `data/raw`;
- full `data/processed/range_runs/<run_id>/actionable_events`;
- `.env`;
- cache folders.

## Gate 3 condition after this sprint

Gate 3 can close only if:

```text
actionable_events_total > 0
symbols_with_actionable_events >= 50 on full run
lookbacks_with_actionable_events >= 3
raw_to_actionable_compression_ratio >= 10
p50 actionable events/symbol/day <= 50
p90 <= 100
p99 <= 200
duplicate_action_event_id_count = 0
rejection counters numeric and meaningful
full run runtime is acceptable for iteration
no live/create/close/order code
```
