# Sprint 04.7 — Input Hygiene, Real Equivalence Gate, and Full FAST Outcome Rebuild

## PM decision

The true vectorized outcome core is accepted on performance:

- reference median runtime: ~132.96 sec;
- numpy_fast_v3 median runtime: ~7.14 sec;
- wall-clock speedup: ~18.63x;
- compute-only speedup: ~19.22x;
- fast smoke semantic audit: pass.

However, Gate 4 is not closed yet because two correctness issues remain:

1. `benchmark_outcome_cores.py --verify-equivalence` currently does not compare outputs. The flag is parsed but unused; `benchmark_ok` only checks process return codes.
2. `read_symbol_frame()` builds a file list from overlapping glob patterns. The same Parquet file can be included more than once. The fast core removes duplicate timestamps, while the reference path can process duplicated rows. This can inflate funding counts, candle counts, intrabar touches, inside-range counts, and related metrics.

Sprint 05 scoring/backtest remains forbidden until the canonical input and equivalence gate pass.

## Non-negotiable safety rules

- No live trading.
- No grid create/close.
- No ordinary order create/cancel.
- No Telegram/live signal work.
- No parameter optimization.
- No scoring or backtest yet.
- Keep the accepted outcome semantics: `v4_native_grid_geometry`.
- Keep `numpy_fast_v3` as the default production outcome core.

## 1. Canonical symbol market-data loader

Create a reusable module, for example:

```text
src/bybit_grid/research/outcome_core/input_loader.py
```

Required API:

```python
@dataclass(frozen=True)
class SymbolInputDiagnostics:
    symbol: str
    kline_file_refs_found: int
    kline_unique_files: int
    kline_duplicate_file_refs_removed: int
    kline_rows_before_timestamp_dedupe: int
    kline_rows_after_timestamp_dedupe: int
    kline_duplicate_timestamps_removed: int
    mark_file_refs_found: int
    mark_unique_files: int
    mark_duplicate_file_refs_removed: int
    mark_rows_before_timestamp_dedupe: int
    mark_rows_after_timestamp_dedupe: int
    mark_duplicate_timestamps_removed: int
    funding_file_refs_found: int
    funding_unique_files: int
    funding_duplicate_file_refs_removed: int
    funding_rows_before_timestamp_dedupe: int
    funding_rows_after_timestamp_dedupe: int
    funding_duplicate_timestamps_removed: int
```

```python
def discover_unique_parquet_files(base: Path, symbol: str) -> list[Path]:
    ...


def load_canonical_symbol_frames(
    symbol: str,
    *,
    klines_root: Path,
    mark_root: Path,
    funding_root: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, SymbolInputDiagnostics]:
    ...
```

Rules:

- Resolve paths and deduplicate file paths before scanning.
- Use a deterministic sorted order.
- Canonical timestamp keys:
  - klines: `open_time_ms` or `start_time_ms`;
  - mark klines: `open_time_ms` or `start_time_ms`;
  - funding: `funding_rate_timestamp_ms`, `funding_time_ms`, or `start_time_ms`.
- Sort by timestamp.
- Deduplicate each source by timestamp before either reference or fast core sees it.
- Preserve one row per timestamp deterministically.
- Fail on contradictory duplicate OHLC/funding values unless an explicit policy is implemented and reported.
- Both reference and fast paths must use exactly these canonical frames.

Replace the current overlapping-glob logic in `scripts/build_candidate_outcomes.py`.

## 2. Input hygiene artifact

Every outcome run must write:

```text
data/processed/outcome_runs/<run_id>/summary/outcome_input_hygiene.json
```

Required aggregate fields:

```text
symbols_processed
kline_file_refs_found
kline_unique_files
kline_duplicate_file_refs_removed
kline_rows_before_timestamp_dedupe
kline_rows_after_timestamp_dedupe
kline_duplicate_timestamps_removed
mark_file_refs_found
mark_unique_files
mark_duplicate_file_refs_removed
mark_rows_before_timestamp_dedupe
mark_rows_after_timestamp_dedupe
mark_duplicate_timestamps_removed
funding_file_refs_found
funding_unique_files
funding_duplicate_file_refs_removed
funding_rows_before_timestamp_dedupe
funding_rows_after_timestamp_dedupe
funding_duplicate_timestamps_removed
symbols_with_conflicting_duplicate_timestamps
input_hygiene_ok
```

Also write a compact per-symbol Parquet summary:

```text
data/processed/outcome_runs/<run_id>/summary/outcome_input_hygiene_by_symbol.parquet
```

## 3. Strengthen semantic audit with input invariants

Extend `scripts/audit_outcome_semantics.py`.

Required checks:

```text
future_rows_available <= future_horizon_minutes
future_coverage_minutes <= future_horizon_minutes
inside_range_candle_count <= future_rows_available
future_bad_ohlc_count <= future_rows_available
future_zero_volume_count <= future_rows_available
funding rows are based on unique funding timestamps
input_hygiene_ok = true
```

The audit must fail if a run appears to have duplicated candle timestamps.

## 4. Make `--verify-equivalence` real

Fix `scripts/benchmark_outcome_cores.py`.

When `--verify-equivalence` is passed, it must compare the median reference run and median fast run outputs, not merely process return codes.

Create:

```text
outcome_core_equivalence_report.json
```

Required fields:

```json
{
  "equivalence_ok": true,
  "reference_run_id": "...",
  "fast_run_id": "...",
  "reference_rows": 12960,
  "fast_rows": 12960,
  "joined_rows": 12960,
  "missing_in_reference": 0,
  "missing_in_fast": 0,
  "columns_compared": [],
  "columns_excluded": [],
  "mismatch_count_total": 0,
  "mismatch_count_by_column": {},
  "first_mismatches": []
}
```

Join key:

```text
outcome_match_key
```

Compare all canonical economic/label fields, including:

- future coverage and quality fields;
- range exit fields;
- inside-range fields;
- excursion fields;
- mark-price context;
- funding count/sum/abs-sum/mean/status;
- ATR/SL fields;
- ambiguity fields;
- native grid geometry;
- close-cross/intrabar-touch/unique-level activity proxies;
- labels.

Exclude only run-specific or performance-only fields:

```text
outcome_run_id
created_at/runtime-only metadata
```

Comparison policy:

- exact: strings, booleans, integers, IDs, JSON strings;
- floats: `rel_tol <= 1e-10`, `abs_tol <= 1e-12`, unless a field-specific stricter rule exists;
- null must equal null.

`benchmark_ok` must be false if equivalence fails.
The command must exit non-zero on any mismatch.

## 5. Resolve funding-count discrepancy explicitly

The previous reference and fast smoke outputs showed a factor-of-two difference in funding rows. Do not hide this.

After canonical input loading:

- reference and fast funding metrics must match exactly;
- funding timestamps must be unique;
- report how many duplicate file references and duplicate funding timestamps were removed;
- add a regression test where the same funding Parquet path is discovered twice and prove the resulting funding count is not doubled.

## 6. Improve benchmark telemetry names

Current stage timing values are summed across workers and may exceed wall-clock runtime. Rename or split them:

```text
total_wall_seconds
market_data_load_worker_seconds_sum
array_prepare_worker_seconds_sum
compute_worker_seconds_sum
materialization_worker_seconds_sum
write_wall_seconds
```

Do not present summed worker seconds as wall-clock stage duration.

Keep:

```text
median_runtime_seconds
median_compute_seconds
speedup
compute_only_speedup
```

## 7. Tests

Add regression tests for:

- overlapping glob patterns return each physical file once;
- duplicate timestamp rows are deterministically removed;
- contradictory duplicates fail or are explicitly reported;
- reference and fast receive identical canonical frames;
- real benchmark equivalence report passes on synthetic data;
- benchmark exits non-zero on an injected mismatch;
- funding count is not doubled by duplicate file references;
- semantic audit rejects `future_rows_available > horizon`;
- no live/create/close/order/Telegram additions.

## 8. Full FAST canonical rebuild

After smoke equivalence passes, build a new canonical full run:

```text
outcomes_true_fast_v4_canonical_123x90_v1
```

This run replaces the repaired reference run as the future Sprint 05 input.

Do not mutate or delete:

```text
outcomes_semantics_v4_native_grid_123x90_r1
```

Keep the repaired run as an audit/reference artifact only.

## 9. Review-pack requirements

For native full FAST runs, the review pack must include:

```text
outcome_report.md
outcome_quality_report.md
outcome_semantic_audit.json
outcome_semantic_audit.md
outcome_summary.parquet
outcome_quality_summary.parquet
outcome_perf.json
outcome_input_hygiene.json
outcome_input_hygiene_by_symbol.parquet
outcome_core_equivalence_report.json
review_pack_manifest.json
```

Update pack builder/checker so it requires:

```text
semantic_audit_ok = true
input_hygiene_ok = true
equivalence_ok = true
outcome_rows_total > 0
unique_outcome_id_count == outcome_rows_total
duplicate composite count == 0
```

## Owner runbook

### Environment and tests

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python -m pytest -q
ruff check .
```

### Real equivalence benchmark

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

Expected:

```text
benchmark_ok=true
equivalence_ok=true
mismatch_count_total=0
speedup>=5
```

### Full canonical FAST build

Only after equivalence passes:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --core numpy_fast_v3 `
  --executor auto `
  --workers auto `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok
```

### Audit and pack

```powershell
python scripts/audit_outcome_semantics.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1

python scripts/report_candidate_outcomes.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1

python scripts/make_outcome_review_pack.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1

python scripts/check_outcome_review_pack.py `
  --zip pm_review_pack_outcomes_true_fast_v4_canonical_123x90_v1.zip `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1
```

## Definition of done

Sprint 04.7 is complete only when:

```text
pytest passes
ruff passes
real equivalence report passes
mismatch_count_total = 0
speedup >= 5x
input_hygiene_ok = true
no duplicate file references reach the scanner
no duplicate market timestamps reach either core
full canonical outcome rows > 0
semantic audit passes
review pack passes
no live/create/close/order/Telegram code added
```

## Required response from Codex

Provide:

- commit hash;
- files changed;
- pytest output;
- ruff output;
- benchmark summary;
- equivalence summary;
- input hygiene summary;
- full canonical build summary if owner data is available;
- known blockers.
