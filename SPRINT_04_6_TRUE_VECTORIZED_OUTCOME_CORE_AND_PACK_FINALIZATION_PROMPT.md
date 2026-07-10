# Sprint 04.6 — True Vectorized Outcome Core + Review Pack Finalization

## PM decision

The grid-serialization repair is accepted:

- `rows_compared=241155`
- `non_grid_drift_count=0`
- `outcome_id_drift_count=0`
- `outcome_match_key_drift_count=0`
- `semantic_audit_ok=true`

However, Sprint 05 is still blocked for two reasons:

1. `numpy_fast_v2` is not fast. The current module delegates directly to the reference implementation and benchmark speedup is ~1.01x.
2. The repaired review pack failed because `outcome_report.md` and `outcome_quality_report.md` were not generated before packaging.

This sprint must deliver a genuinely faster symbol-level outcome kernel and a self-contained, fail-closed review-pack workflow.

## Permanent performance rule

Heavy research code must be FAST-first:

- minimize work before increasing workers;
- reuse max-horizon calculations;
- use contiguous arrays and `searchsorted`;
- avoid repeated Polars filtering inside event/horizon loops;
- avoid repeated computations across grid/SL dimensions;
- stream results by symbol;
- benchmark thread vs process execution;
- show dry-run plan, progress, ETA, timings and memory;
- preserve exact semantics through reference-vs-fast parity tests.

No live trading, order create/cancel, grid create/close, Telegram or parameter optimization is allowed.

---

# Part A — Finalize repaired review pack

## A1. Make pack generation self-contained

Refactor report/audit generation into importable functions, for example:

```python
# src/bybit_grid/research/outcome_reporting.py

def generate_outcome_reports(outcome_run_id: str) -> dict: ...

def generate_outcome_semantic_audit(outcome_run_id: str) -> dict: ...
```

Update `scripts/make_outcome_review_pack.py` so it:

1. regenerates summary parquet/JSON;
2. generates `outcome_report.md`;
3. generates `outcome_quality_report.md`;
4. runs semantic audit;
5. verifies all required files exist;
6. only then creates the ZIP;
7. exits non-zero instead of silently creating an incomplete pack.

Do not depend on the operator remembering a separate report command.

## A2. Review-pack manifest

Add `review_pack_manifest.json` containing:

```json
{
  "outcome_run_id": "...",
  "pack_schema_version": "outcome_review_pack_v2",
  "run_kind": "native|repair",
  "members": [...],
  "outcome_rows_total": 241155,
  "semantic_audit_ok": true,
  "created_at_utc": "..."
}
```

Rules:

- A normal native run does not require a repair report.
- A repaired run requires `outcome_grid_serialization_repair_report.json`.
- Checker determines requirements from `run_kind`, not a universal hard-coded set.
- Pack checker rejects missing reports, failed audit, forbidden partitions/raw/cache/secrets, duplicate IDs, and manifest mismatch.

## A3. Immediate owner command after implementation

```powershell
python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1
```

Expected: `review_pack_ok=true`.

---

# Part B — Replace the scaffold with a real fast core

## B1. Remove reference delegation

Current anti-pattern:

```python
# outcome_fast.py
return _reference_compute(*args, **kwargs)
```

This must be removed.

Add a static regression test that fails if `outcome_fast.py` imports or invokes the reference `compute_event_outcomes` implementation.

## B2. New symbol-level API

Implement a symbol-level core, not an event-level wrapper:

```python
@dataclass(frozen=True)
class OutcomeCoreConfig:
    horizons_minutes: tuple[int, ...]
    grid_cell_numbers: tuple[int, ...]
    sl_atr_buffers: tuple[float, ...]
    range_run_id: str
    outcome_run_id: str


def compute_symbol_outcomes_fast(
    events: pl.DataFrame,
    arrays: OutcomeSymbolArrays,
    config: OutcomeCoreConfig,
) -> pl.DataFrame:
    ...
```

The build script should call this once per symbol.

Reference path remains for parity/testing:

```python
compute_symbol_outcomes_reference(...)
```

## B3. Prepare symbol arrays once

`OutcomeSymbolArrays` must be built once per symbol and contain contiguous, sorted arrays:

```text
time_ms, open, high, low, close, volume
mark_time_ms, mark_close
funding_time_ms, funding_rate
bad_ohlc_prefix, zero_volume_prefix
funding_rate_prefix, funding_abs_rate_prefix
```

Requirements:

- validate ascending unique timestamps;
- record duplicate/missing diagnostics;
- no Polars `.filter()` calls inside event/horizon computation;
- no DataFrame-to-NumPy conversion inside event loops.

## B4. Max-horizon reuse

For each event:

1. compute `entry_idx` once using `np.searchsorted`;
2. compute one slice up to max horizon;
3. derive horizon endpoints once;
4. compute cumulative arrays over the max slice;
5. read all horizon values from those cumulative arrays.

Do not rescan the same candles independently for 60/240/720/1440/2880.

Base grain computed once per `event × horizon`:

```text
future coverage and missing minutes
bad OHLC / zero volume
first range exit and ambiguity
inside-range count/ratio
max high above / low below / close distance
midline crossings
upper/lower boundary touches
mark-price context
funding aggregation
```

## B5. Funding via searchsorted + prefix sums

Replace Polars funding filtering with:

```python
left = np.searchsorted(funding_time_ms, entry_ms, side="right")
right = np.searchsorted(funding_time_ms, end_ms, side="right")
count = right - left
rate_sum = prefix[right] - prefix[left]
abs_sum = abs_prefix[right] - abs_prefix[left]
```

Semantics must match reference exactly.

## B6. Compute SL grain only once

SL does not depend on grid cell number.

For each event:

- derive SL thresholds once per `sl_atr_buffer`;
- use cumulative maximum/minimum or monotonic arrays to find first hit;
- produce one `event × horizon × SL` result;
- do not repeat SL scans for each grid configuration.

Required summary counter:

```text
sl_scans_avoided_vs_reference
```

## B7. Compute grid grain only once

Grid activity does not depend on SL buffer.

For each `event × grid_cell_number`:

- generate native N+1 levels once;
- compute per-candle close-cross counts once;
- compute per-candle intrabar touch counts once;
- compute cumulative counts once;
- read values for each horizon;
- do not recompute grid activity for each SL buffer.

### Exact crossing formulas

Reference close-cross condition is levels in `(min(prev, cur), max(prev, cur)]`.
Use sorted-level search:

```python
crosses = (
    np.searchsorted(levels, hi, side="right")
    - np.searchsorted(levels, lo, side="right")
)
```

Reference intrabar touch condition is levels in `[low, high]`:

```python
touches = (
    np.searchsorted(levels, high, side="right")
    - np.searchsorted(levels, low, side="left")
)
```

Parity tests must confirm exact equality to reference on boundary cases.

For unique touched levels, use a correct vectorized or interval-union method. Grid levels are at most 21 in current profiles, so a small boolean level mask is acceptable.

Required summary counter:

```text
grid_scans_avoided_vs_reference
```

## B8. Materialize Cartesian rows without Python dict explosion

Do not append 241k large Python dicts one by one when avoidable.

Preferred implementations:

- typed column lists + one Polars DataFrame construction per symbol;
- Arrow arrays/builders;
- NumPy structured arrays converted once.

The final expanded schema and IDs must remain semantically identical to repaired v4.

## B9. Streaming writes

- write each completed symbol immediately;
- free symbol arrays/results after write;
- never accumulate all symbols in the parent process;
- preserve deterministic partition dedupe;
- checkpoint successful symbols for resume.

## B10. Executor auto-benchmark

Add:

```bash
python scripts/benchmark_outcome_executors.py ...
```

Compare on the same sample:

- thread workers: 1, 4, 8, auto;
- process workers: 1, 2, 4, auto.

Avoid nested oversubscription in workers:

```text
POLARS_MAX_THREADS=1
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
```

`--executor auto` should use the fastest validated profile stored in a local benchmark JSON, otherwise use a safe default.

## B11. Real timings

`outcome_perf.json` must contain non-null stage timings:

```text
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

Also include:

```text
core_implementation = true_vectorized_symbol_v1
reference_compute_calls = 0
sl_scans_avoided_vs_reference
grid_scans_avoided_vs_reference
```

---

# Part C — Correctness and benchmark gates

## C1. Reference parity

For deterministic fixtures and a real 10-symbol sample, compare by `outcome_match_key`.

Exact equality required for categorical/integer fields:

```text
exit and SL labels/times
coverage counts
funding row counts/status
crossing/touch counts
IDs and match keys
ambiguity flags
```

Tolerant equality required for floats:

```text
abs_tol <= 1e-12 or documented field-specific tolerance
```

Add a comparison report:

```text
outcome_core_equivalence_report.json
```

Required:

```text
comparison_ok=true
missing_keys=0
extra_keys=0
categorical_drift_count=0
integer_drift_count=0
float_drift_count=0
```

## C2. Benchmark fairness

`benchmark_outcome_cores.py` must:

- use the exact same frozen events and source files;
- use new clean output run IDs;
- disable skip-existing/resume effects;
- run a warm-up before timed measurement;
- run at least 3 repetitions and report median;
- separately report compute and write times;
- verify output equivalence before declaring benchmark success.

## C3. Performance acceptance

Smoke 10×30 hard gate:

```text
reference/fast median speedup >= 5.0x
semantic audit = pass
equivalence = pass
```

Preferred:

```text
speedup >= 10x
fast runtime <= 25 sec
```

Projected full run:

```text
estimated <= 10 minutes
preferred <= 5 minutes
```

If speedup is below 5x, print exact stage bottlenecks and do not label the core `fast`.

## C4. Tests

Add tests for:

- fast core does not import/call reference implementation;
- max-horizon reuse;
- funding prefix aggregation parity;
- SL computation not repeated by grid count;
- grid computation not repeated by SL count;
- exact searchsorted crossing parity on endpoints;
- event/horizon/SL/grid grain materialization parity;
- thread/process benchmark selection;
- review pack auto-generates reports;
- native pack vs repair pack manifest rules;
- no live/create/close/order/Telegram code.

---

# Part D — Dependency hygiene

The active environment currently reports an extraneous Numba/NumPy conflict. This project does not require Numba for the production outcome core.

Do not add Numba to default dependencies.

Owner cleanup command:

```powershell
python -m pip uninstall -y numba llvmlite
python -m pip check
```

If `numba_optional` remains anywhere, it must fail clearly when incompatible and must never be selected by default.

---

# Owner runbook after Codex

## 1. Environment and tests

```powershell
python scripts/check_numeric_environment.py
python -m pip uninstall -y numba llvmlite
python -m pip check
python -m pytest -q
ruff check .
```

## 2. Finalize repaired pack

```powershell
python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip `
  --outcome-run-id outcomes_semantics_v4_native_grid_123x90_r1
```

## 3. Core equivalence + benchmark

```powershell
python scripts/benchmark_outcome_cores.py `
  --range-run-id action_density_v2_123x90 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --repetitions 3 `
  --verify-equivalence
```

## 4. Fast smoke

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_true_fast_smoke_10x30 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --core numpy_fast_v3 `
  --executor auto `
  --workers auto `
  --fast-max

python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_true_fast_smoke_10x30
```

Do not run a new full outcome build until:

```text
pack checker passes
semantic audit passes
equivalence passes
speedup >= 5x
```

---

# Required output to PM

Send as text:

```text
commit hash
changed files
pytest output
ruff output
pip check output
repaired review-pack checker output
reference median runtime
fast median runtime
speedup
compute-only speedup
executor benchmark recommendation
equivalence report summary
fast smoke semantic audit summary
```

Upload only:

```text
pm_review_pack_outcomes_semantics_v4_native_grid_123x90_r1.zip
outcome_core_benchmark_summary.json
outcome_core_equivalence_report.json
outcome_executor_benchmark_summary.json
```

Do not upload the full repository, raw market data, outcome partitions, range partitions, `.env`, `.venv` or caches.

## Definition of done

Sprint 04.6 is complete only when:

```text
repaired review pack checker passes
true fast core does not delegate to reference
reference/fast equivalence passes
median speedup >= 5x
fast smoke semantic audit passes
all stage timings are populated
pytest passes
ruff passes
no live execution code added
```
