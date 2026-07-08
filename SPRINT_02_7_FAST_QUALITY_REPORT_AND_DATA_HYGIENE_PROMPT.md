# Sprint 02.7 — FAST Quality Report + Research Readiness + Data Hygiene

PM decision: Sprint 02.6 code and data download are accepted, but Gate 2B is not closed because `report_universe_quality.py` crashed after the successful 50-symbol research download.

## Accepted evidence

The owner successfully ran:

- `python -m pytest -q` -> 76 passed.
- `ruff check .` -> All checks passed.
- `analyze_fgrid_min_investment.py` -> `symbols_tested=127`, `investment_min_non_null_rows=127`, `symbols_min_investment_feasible_at_5=123`.
- `build_research_eligible_universe.py --target-init-margin 5` -> `eligible_symbols_count=123`.
- `build_research_download_manifest.py --days 90 --max-symbols 50 --max-gb 25` -> `rows=50 est_gb=2.595`.
- `download_universe_data.py --manifest data/processed/research_download_manifest.parquet --fast-max --skip-existing-ok` -> completed successfully.
- Download performance:
  - `manifest_rows_total=50`
  - `downloadable_rows=50`
  - `api_requests_count=11970`
  - `requests_per_second_effective=77.143`
  - `rows_written=11789242`
  - `failures=0`
  - `seconds_per_symbol=3.103`

The successful download must not be repeated unless explicitly required. Sprint 02.7 should use the existing local Parquet data and fix reporting/readiness.

## Current blocker

`python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet` crashed with:

```text
polars.exceptions.ComputeError: could not append value: 102 of type: i64 to the builder;
make sure that all rows have the same schema or consider increasing infer_schema_length
```

Root cause: `pl.DataFrame(rows)` infers schema from early kline/mark rows where funding fields are null, then later sees funding integer values. This is a schema-construction bug, not a data-download failure.

Secondary issue: current quality report is too slow/heavy because it collects and partitions full 1m datasets. It should use manifest-driven lazy Parquet aggregations and only collect small aggregate tables.

## Non-negotiable safety rules

- Do not implement strategy.
- Do not implement backtest.
- Do not implement Telegram/live execution.
- Do not create/close grid bots.
- Do not add ordinary order create/cancel.
- Preserve FAST-first defaults.
- Do not re-download data in this sprint unless the user explicitly runs a download command.
- Do not include `.env`, raw data, metadata, reports, caches, or credentials in share zips.

## Performance requirements

All heavy report scripts must be FAST-first:

- Use lazy scans where possible.
- Do not collect 10M+ rows unless absolutely required.
- Prefer grouped aggregations over Python `partition_by` over full DataFrames.
- Use manifest symbols and expected start/end boundaries.
- Print compact progress/summary.
- Write UTF-8 reports.
- No Polars box tables in CLI or Markdown.
- Any report over downloaded universe should complete in under 60 seconds for 50 symbols x 90 days on the owner laptop.

## Required changes

### 1. Fix `report_universe_quality.py` schema error

Replace:

```python
df = pl.DataFrame(rows)
```

with either explicit schema or `infer_schema_length=None`. Preferred: explicit schema.

Use a stable schema like:

```python
QUALITY_SCHEMA = {
    "symbol": pl.Utf8,
    "dataset": pl.Utf8,
    "rows": pl.Int64,
    "expected_rows": pl.Int64,
    "missing_gaps": pl.Int64,
    "duplicate_candles": pl.Int64,
    "bad_ohlc": pl.Int64,
    "zero_volume_rows": pl.Int64,
    "disk_bytes": pl.Int64,
    "requires_reload": pl.Boolean,
    "excluded_due_to_quality": pl.Boolean,
    "funding_rows_expected_approx": pl.Int64,
    "funding_rows_actual": pl.Int64,
    "funding_rows_status": pl.Utf8,
    "min_ts": pl.Int64,
    "max_ts": pl.Int64,
    "expected_start_ms": pl.Int64,
    "expected_end_ms": pl.Int64,
    "boundary_start_gap": pl.Int64,
    "boundary_end_gap": pl.Int64,
}
```

Make all rows include all keys.

### 2. Make quality report manifest-driven

`report_universe_quality.py` already accepts `--manifest`. It must actually use it.

For each manifest row:

- symbol;
- expected_start_ms;
- expected_end_ms;
- expected rows for normal 1m klines;
- expected rows for mark 1m klines;
- approximate expected funding rows.

Only evaluate symbols in the manifest. Do not scan unrelated old raw data.

### 3. Use lazy aggregate quality checks for klines/mark_klines

For each dataset (`klines`, `mark_klines`) and symbol, scan files under:

```text
data/raw/<dataset>/symbol=<symbol>/year=*/month=*/*.parquet
```

Then compute with lazy aggregations:

- `rows` = count;
- `unique_open_times` = `open_time_ms.n_unique()`;
- `duplicate_candles` = `rows - unique_open_times`;
- `min_ts` / `max_ts`;
- `expected_rows` from manifest boundaries;
- `missing_gaps` = `max(0, expected_rows - unique_open_times)`;
- `boundary_start_gap` = minutes missing before `min_ts` if `min_ts > expected_start_ms`;
- `boundary_end_gap` = minutes missing after `max_ts` if `max_ts < expected_end_ms`;
- `bad_ohlc` = count of invalid OHLC rows;
- `zero_volume_rows` only for normal klines, 0/null for mark klines.

Do not call `detect_1m_gaps(part)` on full collected DataFrames in the default path. Exact gap interval listing can be added later as `--exact-gaps`; not required now.

### 4. Funding quality must be manifest-aware and tolerant

For each funding symbol:

```text
data/raw/funding/symbol=<symbol>/year=*/*.parquet
```

Compute:

- `rows`;
- `min_ts` / `max_ts`;
- `funding_rows_actual`;
- `funding_rows_expected_approx` from manifest days * 3 as baseline;
- status values:
  - `ok` if actual is within reasonable tolerance;
  - `low` if actual < 50% expected;
  - `none` if 0;
  - `unknown` if expected cannot be derived.

Do not fail Sprint 02.7 because funding rows are not exactly equal to estimate. Funding intervals can vary by instrument.

### 5. Fix `report_research_readiness.py`

It currently reports `downloaded_symbols_count=0` after the download because quality summary failed or was empty.

After fixing quality, readiness must compute:

- eligible_symbols_count;
- manifest_symbols_count;
- downloaded_symbols_count;
- normal_kline_success_rate;
- mark_kline_success_rate;
- funding_success_rate;
- gap_count_total;
- duplicate_count_total;
- bad_ohlc_count_total;
- zero_volume_rows_total;
- disk_usage_gb;
- symbols_ready_for_sprint_03;
- symbols_excluded_quality;
- recommendation.

Pass recommendation for Gate 2B requires:

```text
manifest_symbols_count >= 50
normal_kline_success_rate >= 98
mark_kline_success_rate >= 95
duplicate_count_total = 0
bad_ohlc_count_total = 0
symbols_ready_for_sprint_03 >= 50
```

Gaps can be tolerated only if explained; default gate expects `gap_count_total=0` or near-zero with reload plan.

### 6. Add a fast local rerun path

Add or document this command sequence:

```powershell
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet --fast
python scripts/report_research_readiness.py
```

It must not hit Bybit API and must not re-download anything.

### 7. Add tests

Add `tests/test_sprint_02_7_quality_report.py` covering:

- `pl.DataFrame(rows)` schema bug reproduction: >100 kline/mark rows then funding rows with integer funding fields.
- quality summary creates stable schema with funding integers.
- manifest-driven path ignores symbols not in manifest.
- lazy aggregate computes duplicate count.
- lazy aggregate computes bad OHLC count.
- boundary gap calculation from manifest start/end.
- mark_klines zero volume handling does not break nullable volume.
- readiness returns pass when 50 symbols have kline/mark data with no dup/bad rows.
- report files are UTF-8 and contain ASCII markdown only.

### 8. Data/archive hygiene fix

The uploaded zip still contains `.env`, `data/`, `reports/`, `.pytest_cache`, `.ruff_cache`, and `__pycache__`.

Update `scripts/make_share_zip.py` so share zips exclude:

```text
.env
.env.* except .env.example
data/
reports/
.pytest_cache/
.ruff_cache/
__pycache__/
*.pyc
```

Add a CLI warning if these are present in a manual zip.

Add `scripts/check_share_hygiene.py` that exits non-zero if sensitive/generated artifacts are present.

## Acceptance commands

After Codex changes, owner runs locally:

```powershell
python -m pytest -q
ruff check .
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet --fast
python scripts/report_research_readiness.py
python scripts/check_share_hygiene.py
```

Expected:

```text
quality_report status=ok manifest_symbols=50 rows_scanned_approx=... duplicate_count_total=0 bad_ohlc_count_total=0
readiness recommendation=pass
```

If readiness fails, it must explain exactly why:

```text
failed_symbols=...
missing_klines=...
missing_mark_klines=...
gap_count_total=...
duplicate_count_total=...
bad_ohlc_count_total=...
```

## Required output from Codex

- commit hash;
- files changed;
- pytest output;
- ruff output;
- quality report output;
- research readiness output;
- share hygiene output;
- summary of `reports/sprint_02_universe_quality_report.md`;
- summary of `reports/sprint_02_research_readiness_report.md`.

## PM gate

Gate 2B closes only after:

```text
pytest passed
ruff passed
quality report completes on existing 50-symbol data
readiness report passes or gives actionable reload plan
no Bybit API calls made during report phase
no re-download required
share hygiene passes
```

After Gate 2B closes, Sprint 03 may begin: Range Candidate Dataset.
