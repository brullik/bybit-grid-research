# Sprint 04.1 — Outcome Dedupe + Funding Join + Gate Fix

PM decision: Sprint 04 implementation is accepted as a foundation, but Gate 4 is not closed. The full outcome run produced useful labels, but the test suite is failing and funding aggregation is zero. Fix correctness before any scoring/backtest work.

## Current evidence

Accepted full run output:

- `outcome_run_id=outcomes_action_density_v2_123x90_v1`
- `outcome_rows_total=241155`
- `unique_outcome_id_count=241155`
- `duplicate_range_action_event_horizon_grid_sl_rows=0`
- `future_data_complete_rate=0.9941780182869938`
- `first_exit_side_distribution`: down=109188, up=106065, none=25902
- `sl_hit_distribution`: true=86856, false=154299
- `grid_crossing_distribution`: min=0, median=89.0, max=2314
- `review_pack_ok`

Blockers:

1. `python -m pytest -q` fails in `test_partition_write_and_dedupe`:
   - expected parquet height 1
   - actual height 2
2. `funding_rows_total=0` in smoke and full reports even though funding data exists in the project and Sprint 02 readiness reported funding success.
3. Build-script console summary appears malformed or manually formatted; all CLI summary output must be valid JSON or compact key=value lines.

## Non-negotiable safety rules

- Do not implement live trading.
- Do not implement Bybit grid create/close.
- Do not implement ordinary orders.
- Do not add Telegram/live execution.
- Keep outcome labeling as offline research only.
- Keep FAST-first defaults and review-pack-only sharing.

## 1. Fix outcome partition dedupe

Find `write_partitioned_outcomes()` in `src/bybit_grid/research/outcome_store.py`.

Required behavior:

- If the input DataFrame contains duplicate `outcome_id`, dedupe before writing.
- If an existing parquet partition exists, concatenate existing + new and dedupe deterministically.
- Primary unique key: `outcome_id`.
- Secondary integrity key for reporting: `(range_action_event_id, horizon_minutes, grid_count, sl_atr_buffer)`.
- Keep stable deterministic sorting after dedupe.
- Do not allow two identical `outcome_id` rows in any partition.

Recommended implementation pattern:

```python
def dedupe_outcomes(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    sort_cols = [c for c in [
        "symbol",
        "signal_time_ms",
        "range_action_event_id",
        "horizon_minutes",
        "grid_count",
        "sl_atr_buffer",
        "outcome_id",
    ] if c in df.columns]
    df = df.sort(sort_cols) if sort_cols else df
    return df.unique(subset=["outcome_id"], keep="first", maintain_order=True)
```

Then use it:

```python
clean = dedupe_outcomes(part)
if path.exists():
    existing = pl.read_parquet(path)
    clean = dedupe_outcomes(pl.concat([existing, clean], how="diagonal_relaxed"))
clean.write_parquet(path)
```

Add/keep the failing test and make it pass.

## 2. Add outcome-run repair tool

Add:

```text
scripts/repair_outcome_run.py
```

Features:

```bash
python scripts/repair_outcome_run.py --outcome-run-id outcomes_action_density_v2_123x90_v1 --dedupe --rebuild-summary
```

Behavior:

- scans `data/processed/outcome_runs/<outcome_run_id>/outcomes/**/outcomes.parquet`;
- dedupes each partition by `outcome_id`;
- reports rows_before, rows_after, duplicates_removed;
- rebuilds `outcome_summary.parquet`, `outcome_quality_summary.parquet`, and `outcome_perf.json`;
- writes a repair report under `reports/outcome_runs/<outcome_run_id>/outcome_repair_report.md`.

## 3. Fix funding join and reporting

Current reports show:

```text
funding_rows_total=0
```

This is not acceptable unless the report explicitly proves funding files are missing for the relevant symbols/time ranges. Funding history was part of the approved data layer, so outcome reporting must distinguish:

- funding files found but no events overlap funding timestamps;
- funding files missing;
- funding read path wrong;
- funding join bug.

Add diagnostics to the outcome builder and summary:

Per outcome row or per event/horizon where feasible:

- `funding_rows_in_horizon`
- `funding_rate_sum`
- `funding_rate_abs_sum`
- `funding_rate_mean`
- `funding_source_status`: `ok`, `missing_file`, `empty_file`, `no_overlap`, `not_requested`

Summary fields:

- `funding_files_found_count`
- `funding_symbols_with_files`
- `funding_rows_scanned_total`
- `funding_rows_joined_total`
- `funding_join_coverage_rate`
- `funding_missing_symbols`
- `funding_source_status_counts`

Acceptance expectation:

- For the full 123x90 outcome run, `funding_files_found_count > 0`.
- If `funding_rows_joined_total == 0`, the report must explain exactly why.

Implementation guidance:

- Reuse current funding parquet layout from Sprint 02 downloader.
- Do not call Bybit API.
- Use local Parquet only.
- Read only funding partitions needed for the event symbol and `[entry_time_ms, entry_time_ms + horizon]`.
- Cache funding per symbol inside a worker to avoid repeated scans.

## 4. Make CLI output valid and machine-readable

All summary output from these scripts must be either valid JSON or compact key=value lines:

- `scripts/build_candidate_outcomes.py`
- `scripts/report_candidate_outcomes.py`
- `scripts/repair_outcome_run.py`

Do not manually print partial JSON. Use:

```python
print(json.dumps(summary, indent=2, ensure_ascii=False))
```

or a strict key=value formatter.

Add a test that captures CLI output and validates JSON when JSON mode is used.

## 5. Strengthen Gate 4 report/checker

Update `check_outcome_review_pack.py` so it fails if:

- tests would fail due duplicate writer? This can be represented by summary duplicate fields;
- `outcome_rows_total <= 0`;
- `unique_outcome_id_count != outcome_rows_total`;
- `duplicate_range_action_event_horizon_grid_sl_rows != 0`;
- `funding_rows_total == 0` and `funding_files_found_count > 0` without explicit blocker reason;
- stale/global reports are present;
- outcomes parquet partitions are included in the pack.

## 6. Tests to add/fix

Required:

- `test_partition_write_and_dedupe` passes.
- duplicate rows in input produce one written row.
- duplicate rows across append produce one written row.
- funding parquet with matching timestamps produces `funding_rows_in_horizon > 0`.
- funding parquet absent produces `funding_source_status=missing_file`, not silent zero.
- report summary includes funding diagnostics.
- review pack checker catches missing funding diagnostics.
- create/close/order/live safety tests still pass.

## 7. Required local commands after Codex

Run:

```powershell
python -m pytest -q
ruff check .
```

Repair existing full outcome run:

```powershell
python scripts/repair_outcome_run.py --outcome-run-id outcomes_action_density_v2_123x90_v1 --dedupe --rebuild-summary
python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v1
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v1
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v1.zip --outcome-run-id outcomes_action_density_v2_123x90_v1
```

If funding diagnostics still show missing/zero, run a small rebuild with funding debug:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_smoke_10x30_v2 `
  --symbols-limit 10 `
  --days-limit 30 `
  --grid-counts 10 `
  --sl-atr-buffers 0.5 `
  --fast-max `
  --funding-debug

python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_smoke_10x30_v2
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_smoke_10x30_v2
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_smoke_10x30_v2.zip --outcome-run-id outcomes_smoke_10x30_v2
```

Only if smoke funding is fixed, rebuild full outcomes if needed:

```powershell
python scripts/build_candidate_outcomes.py `
  --range-run-id action_density_v2_123x90 `
  --outcome-run-id outcomes_action_density_v2_123x90_v2 `
  --grid-counts 5,10,20 `
  --sl-atr-buffers 0,0.5,1.0 `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok

python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v2.zip --outcome-run-id outcomes_action_density_v2_123x90_v2
```

## 8. What to send to PM

Text only:

- commit hash;
- files changed;
- `python -m pytest -q` output;
- `ruff check .` output;
- repair output;
- outcome report summary;
- funding diagnostics summary;
- review pack checker output.

Files only:

- `pm_review_pack_outcomes_smoke_10x30_v2.zip` if a smoke rebuild was needed;
- `pm_review_pack_outcomes_action_density_v2_123x90_v1.zip` if repair was enough;
- or `pm_review_pack_outcomes_action_density_v2_123x90_v2.zip` if full rebuild was needed.

Do not upload the full repo archive or raw/outcome parquet partitions.

## 9. Gate 4 acceptance after this sprint

Gate 4 can close only when:

- pytest passes;
- ruff passes;
- outcome_rows_total > 0;
- unique_outcome_id_count == outcome_rows_total;
- duplicate composite count == 0;
- future_data_complete_rate reported;
- first_exit_side distribution reported;
- sl_hit distribution reported;
- grid crossing distribution reported;
- funding diagnostics reported and not silently zero;
- review pack passes;
- no live/create/close/order code added.
