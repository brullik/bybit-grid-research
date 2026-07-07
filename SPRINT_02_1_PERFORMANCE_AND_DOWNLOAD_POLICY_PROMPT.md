# Sprint 02.1 — Performance, Download Policy, and Windows Report Hotfix

PM decision: Sprint 02 code foundation is accepted, but runtime is too slow and the current download policy wastes time by downloading symbols marked `blocked_by_min_investment`. Do not start strategy/research/backtest yet.

## Current evidence

Owner run:

- `python -m pytest` -> 37 passed.
- `ruff check .` -> passed.
- `build_universe.py --min-turnover 5000000 --max-symbols 100` -> selected 100 from 716 linear instruments.
- `validate_universe_fgrid_constraints.py --max-symbols 30 --max-configs-per-symbol 20 --sleep-sec 0.5` -> 600 rows.
- `download_manifest.parquet` -> 50 symbols, est_gb ~2.558.
- manifest rows show `trading_feasibility_status = blocked_by_min_investment` for all displayed rows.
- `report_universe_quality.py` fails on Windows with `UnicodeEncodeError: cp1251` because markdown writing uses default encoding and Polars box-drawing repr.

## Non-negotiable safety rules

- Do not implement strategy.
- Do not implement backtest.
- Do not implement Telegram.
- Do not implement live execution.
- Do not create or close grid bots.
- Do not call order/create or position endpoints.
- Private validate-only is allowed only where already implemented and guarded.
- Preserve all redaction/privacy protections.

## Goals

1. Cut unnecessary work first.
2. Then reduce API/network time safely.
3. Fix Windows report encoding.
4. Add profiling/reporting so we know where time goes.
5. Preserve data quality and Bybit rate-limit safety.

## Priority 0 — Fix Windows report bug

`report_universe_quality.py` currently does:

```python
Path("reports/sprint_02_universe_quality_report.md").write_text(
    "# Sprint 02 Universe Quality Report\n\n" + repr(df) + "\n"
)
```

Fix:

- Always pass `encoding="utf-8"` to all report `write_text` calls.
- Stop writing `repr(df)` into markdown because Polars uses box-drawing characters that break cp1251 terminals/files.
- Render markdown tables manually with ASCII/Markdown only, or use CSV-like plain text.
- Add a test that writes a report on a simulated Windows environment without raising Unicode errors.

Search and update all report writers:

- `scripts/report_universe_quality.py`
- `src/bybit_grid/universe/builder.py`
- `src/bybit_grid/bybit/fgrid_constraints.py`
- `src/bybit_grid/data/download_manifest.py`
- any `Path(...).write_text(...)` in reports.

## Priority 1 — Stop downloading blocked symbols by default

Current manifest can contain 50 symbols all marked `blocked_by_min_investment`, and the downloader still downloads all of them. That is the biggest quality-preserving speed win.

Change policy:

- Default: `download_universe_data.py` must skip rows where `trading_feasibility_status != validated_5usdt_feasible`.
- If fewer than 10 validated 5-USDT-feasible symbols exist, `build_download_manifest.py` should produce a blocked manifest and the downloader should exit with a clear PM blocker without downloading.
- Add override flag:

```bash
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --include-blocked --reason exploratory_data_only
```

Without `--include-blocked`, blocked rows are skipped.

Report must show:

- manifest_rows_total;
- downloadable_rows;
- skipped_blocked_by_min_investment;
- whether download was blocked by policy.

## Priority 2 — Fix FGrid constraint candidate explosion

Current grid dimensions include:

- range widths: 5
- cell numbers: 5
- leverage: 5
- init_margin probes: 5
- stop-loss multipliers: 3

Full product = 1875 candidates per symbol. Even with `--max-configs-per-symbol 20`, the first 20 are not a balanced sample and include redundant combinations.

Implement a two-stage validator:

### Stage A — fast feasibility scan

Default scan per symbol should be small and diverse:

```text
range_width_pct: [0.05, 0.10, 0.20]
cell_number: [5, 10, 20]
leverage: [1, 3, 10]
init_margin_probe: [100]
stop_loss_mult: [0.95]
```

Max 27 validate calls per symbol, but allow CLI caps.

### Stage B — expansion only for promising symbols

Only if a symbol has `investment_min <= user_threshold * expansion_multiplier`, for example `<= 25 USDT`, expand more configs.

Default:

```text
user_threshold = 5
expansion_multiplier = 5
promising_if_investment_min <= 25
```

### Important quality fix

Current dedupe key does not include `stop_loss_mult` / `stop_loss_price` and `append_constraints()` only dedupes when path exists. Fix this.

- Include all fields that define a candidate in `candidate_key`:
  - symbol
  - range_width_pct
  - cell_number_requested
  - leverage_requested
  - init_margin_requested
  - stop_loss_mult
  - min_price
  - max_price
- Deduplicate both fresh rows and appended rows.
- Add tests proving duplicate candidate rows are removed deterministically.

## Priority 3 — Safe concurrency for public downloads

The public downloader is sequential:

```python
for row in manifest:
    download_kline_range(...)
    download_mark_kline_range(...)
    download_funding_history(...)
    time.sleep(args.sleep_sec)
```

For 50 symbols x 90 days this causes thousands of serial HTTP requests.

Implement controlled parallelism for public downloads only.

Recommended first implementation: `ThreadPoolExecutor`, not async rewrite.

CLI flags:

```bash
python scripts/download_universe_data.py \
  --manifest data/processed/download_manifest.parquet \
  --workers 4 \
  --max-requests-per-second 8 \
  --skip-existing-ok
```

Requirements:

- One `BybitClient` per worker/thread or a thread-safe client wrapper.
- Shared global token-bucket rate limiter across workers.
- Default `workers=4`.
- Default `max_requests_per_second=8` for safety.
- Retry 429/5xx/transport errors with backoff.
- Continue if one symbol fails.
- Do not parallelize private validate in this sprint unless explicitly coded with a stricter limiter.

## Priority 4 — Skip already downloaded good data

Add `--skip-existing-ok`.

For each manifest symbol/source before network download:

- Check local Parquet partitions for requested range.
- If expected rows are present and quality checks pass, skip network calls.
- If partial data exists, only download missing chunks where possible.
- If this is too large for Sprint 02.1, implement coarse skip first:
  - if source/symbol rows >= expected rows and gaps=0 and duplicates=0 and bad_ohlc=0, skip.

Report:

- skipped_existing_ok count;
- downloaded count;
- failed count;
- partial/reload_required count.

## Priority 5 — Add timing/profiling metrics

Add a small timing helper.

Every script must report:

- total_seconds;
- api_requests_count;
- rows_written;
- seconds_per_symbol;
- requests_per_second_effective;
- skipped rows/symbols;
- failures.

For `download_universe_data.py`, write:

```text
reports/sprint_02_download_performance_report.md
reports/sprint_02_download_performance_report.json
```

## Priority 6 — Polars lazy quality report

`report_universe_quality.py` reads all parquet files into memory via `pl.read_parquet` and `pl.concat`. This will become slow for larger history.

Improve using lazy scans where possible:

- `pl.scan_parquet(...)`
- group by symbol/source;
- aggregate row counts, zero volumes, bad OHLC;
- only materialize final summaries.

For gap detection, it is acceptable to materialize per symbol/source at first, but do it symbol-by-symbol and not all data at once.

## Acceptance commands

Owner runs:

```powershell
python -m pytest -q
ruff check .
python scripts/report_universe_quality.py
python scripts/build_download_manifest.py --days 90 --max-symbols 50 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --dry-run
```

If manifest has no validated 5-USDT feasible symbols, expected behavior is:

```text
download blocked by policy: no validated_5usdt_feasible symbols
```

Then run exploratory override only for a tiny sample:

```powershell
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --include-blocked --symbols-limit 5 --days-override 7 --workers 4 --max-requests-per-second 8
python scripts/report_universe_quality.py
```

If feasible symbols exist:

```powershell
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --workers 4 --max-requests-per-second 8 --skip-existing-ok
python scripts/report_universe_quality.py
```

## Tests to add

- report writers use UTF-8 and do not use Polars box-drawing repr.
- downloader skips `blocked_by_min_investment` rows by default.
- `--include-blocked` allows blocked exploratory download.
- candidate key includes stop-loss and price bounds.
- append constraints dedupes fresh rows and appended rows.
- Stage A candidate generation is diverse and bounded.
- Threaded downloader respects a mocked global rate limiter.
- `--skip-existing-ok` skips a symbol/source with complete local data.
- quality report can run on generated test parquet without Unicode errors.

## Definition of done

Sprint 02.1 is done when:

- tests pass;
- ruff passes;
- Windows quality report no longer raises UnicodeEncodeError;
- default downloader does not download blocked-by-min-investment symbols;
- exploratory override works only when explicitly requested;
- public downloader supports safe parallelism;
- performance report shows effective speedup;
- no live trading code is added.
