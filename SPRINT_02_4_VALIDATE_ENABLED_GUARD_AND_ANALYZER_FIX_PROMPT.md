# Sprint 02.4 — Validate-Enabled Guard + Analyzer Fix + True FAST Sweep

PM decision: Sprint 02.3 code foundation is accepted, but the live sweep result is invalid. The sweep wrote 1192 rows, but every raw response was `{"skipped": true, "reason": "GRID_VALIDATE_ENABLED is false"}`. Therefore no actual `/v5/fgridbot/validate` requests were made and `best_global_min_investment=None` is not a market result.

## Permanent FAST-first rule

All heavy scripts must default to maximum safe speed:

- endpoint-aware max workers/RPS;
- shared global rate limiter;
- no serial network loops unless technically required;
- resume/checkpoint;
- skip-existing-ok;
- progress + ETA;
- dry-run-plan with request/time estimate;
- hard guard if runtime estimate > 10 minutes;
- no full Cartesian grids unless PM explicitly approves.

However, FAST mode must never fake results. If validate is disabled, the script must fail before writing constraints.

## Root cause

`BybitClient.validate_grid_bot()` currently returns a skipped dict when `GRID_VALIDATE_ENABLED=false`:

```python
if not self.settings.grid_validate_enabled:
    return {"skipped": True, "reason": "GRID_VALIDATE_ENABLED is false"}
```

That behavior is acceptable for `validate_sample_grid.py`, but not for a production feasibility sweep. The universe sweep interpreted skipped responses as rows, wrote them to `fgrid_validate_constraints.parquet`, and later analyzer crashed because all `investment_min` values were null.

## Required changes

### 1. Fail hard for real universe sweep when validate is disabled

In `scripts/validate_universe_fgrid_constraints.py`, before building/submitting futures:

```python
settings = load_settings()
if not args.dry_run_plan and not settings.grid_validate_enabled:
    raise SystemExit(
        "GRID_VALIDATE_ENABLED=false. This command would not call Bybit validate. "
        "Set GRID_VALIDATE_ENABLED=true for real min-investment sweep, or use --dry-run-plan."
    )
```

Also require private credentials before the real sweep:

```python
settings.require_private_credentials()
```

Do not create output rows when validate is disabled.

### 2. Add `--purge-skipped-constraints`

Add a safe cleanup mode:

```bash
python scripts/validate_universe_fgrid_constraints.py --purge-skipped-constraints
```

Behavior:

- read `data/processed/fgrid_validate_constraints.parquet` if exists;
- remove rows where:
  - `blocker_reason == investment_min_missing`, or
  - `raw_response_path_redacted` points to JSON with `skipped=true`, or
  - `investment_min is null` and `retCode is null` and `status_code is null`;
- rewrite the parquet with only real validation rows;
- delete raw redacted files containing `"skipped": true`;
- print `removed_rows`, `remaining_rows`, `removed_raw_files`.

If all rows were skipped, output file can be deleted or rewritten empty.

### 3. Analyzer must handle all-null investment safely

In `src/bybit_grid/bybit/fgrid_feasibility.py`, fix:

```python
float(out["min_investment_min_seen"].median())
```

When all values are null, Polars returns None. Aggregate must be:

```python
median_val = out["min_investment_min_seen"].drop_nulls().median()
...
"min_investment_median_by_symbol": float(median_val) if median_val is not None else None
```

If constraints exist but all investment values are null, `analyze_fgrid_min_investment.py` must print:

```text
No real investment_min values found. Check GRID_VALIDATE_ENABLED and purge skipped constraints.
```

and exit non-zero or write a blocker report, but not crash.

### 4. Progress metrics must distinguish rows from real API calls

Current progress printed `rps=148.9` even though `/v5/fgridbot/validate` limit is 10/s. This happened because skipped rows were counted as completed rows, not real API requests.

Change progress line fields:

```text
progress done_rows=... api_calls=... planned_requests=... rows_per_sec=... api_rps=... eta_sec=... skipped_disabled=... errors=... skipped_resume=...
```

`api_calls` increments only after an actual `private_post` attempt.

### 5. Enforce endpoint rate evidence

Bybit returns rate-limit headers:

- `X-Bapi-Limit`
- `X-Bapi-Limit-Status`
- `X-Bapi-Limit-Reset-Timestamp`

Capture these headers in client response metadata or logging for private validate calls. Write per-run summary:

```text
api_calls_attempted
api_calls_succeeded
api_calls_failed
max_observed_endpoint_limit
min_observed_limit_status
rate_limit_10006_count
effective_api_rps
```

Do not store secret headers.

### 6. Clean command sequence for owner

After this hotfix the owner must run:

```powershell
python -m pytest -q
ruff check .
python scripts/validate_universe_fgrid_constraints.py --purge-skipped-constraints
python scripts/analyze_fgrid_min_investment.py
```

Then enable validate-only locally:

```powershell
$env:GRID_VALIDATE_ENABLED="true"
$env:LIVE_TRADING_ENABLED="false"
$env:ALLOW_LIVE_TRADING="NO"
```

Run plan:

```powershell
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max --dry-run-plan
```

Run real sweep:

```powershell
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max
```

Then analyze:

```powershell
python scripts/analyze_fgrid_min_investment.py
```

### 7. Tests

Add tests for:

- real sweep exits before writing rows when `GRID_VALIDATE_ENABLED=false`;
- dry-run-plan still works when validate is disabled;
- purge removes skipped rows and skipped raw JSON files;
- analyzer handles all-null investment without crash;
- progress line includes `api_calls` and `api_rps`;
- no create/close implementation was introduced.

## Acceptance criteria

Sprint 02.4 is complete only when:

- `pytest -q` passes;
- `ruff check .` passes;
- skipped fake constraint rows can be purged;
- analyzer no longer crashes on all-null constraints;
- real sweep refuses to run unless `GRID_VALIDATE_ENABLED=true`;
- real sweep with validate enabled produces rows with non-null `investment_min` or explicit Bybit parameter errors;
- report shows real `api_calls_attempted > 0`;
- create/close remain forbidden.
