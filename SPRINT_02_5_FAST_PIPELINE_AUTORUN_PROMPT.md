# Sprint 02.5 — FAST Pipeline Auto-Bootstrap + Real Sweep Runbook

PM decision: Sprint 02.4 code hotfix is accepted, but the real min-investment sweep was not run because `data/processed/universe_selected.parquet` was missing. The next task is to remove this manual-prerequisite failure mode and make the feasibility check a single FAST-first pipeline.

## Permanent performance rule

Every heavy script must default to maximum safe speed:

- public market data: workers=64, max_requests_per_second=100, skip_existing_ok=true;
- private FGrid validate: workers=10, max_requests_per_second=9.5;
- no serial network loops unless the endpoint cannot be parallelized;
- no full Cartesian grids unless PM explicitly approves;
- must have dry-run planning;
- must show planned requests, estimated seconds, progress and ETA;
- must support resume/checkpoint;
- must flush on Ctrl+C;
- must never silently write fake/skipped API rows.

Correctness rule: maximum speed is only valid when it produces real results.

## Current blocker

The command:

```powershell
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max --dry-run-plan
```

failed with:

```text
FileNotFoundError: data/processed/universe_selected.parquet
```

This is a bad operator experience. The script should either auto-build the universe or fail with one clear command to run. No stack trace for missing expected local artifacts.

## Goal

Create a single fast pipeline that runs:

1. build universe;
2. dry-run plan;
3. validate-only min-investment sweep;
4. analyze min investment;
5. write PM-ready report.

No research, no backtest, no live create/close.

## Non-negotiable safety rules

- Do not implement grid create.
- Do not implement grid close.
- Do not place orders.
- Do not add Telegram/live execution.
- Keep `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO`.
- Real sweep requires `GRID_VALIDATE_ENABLED=true` and private credentials.
- `--dry-run-plan` must not require private credentials.
- Create/close must remain `NotImplementedError`.

## Required changes

### 1. Friendly preflight for missing universe

In `scripts/validate_universe_fgrid_constraints.py`, before `pl.read_parquet(args.universe)`, check if the path exists.

If missing and `--auto-build-universe` is not set, print:

```text
missing_universe=data/processed/universe_selected.parquet
Run: python scripts/build_universe.py --min-turnover 5000000 --max-symbols 150
Or rerun this command with --auto-build-universe.
```

Then exit non-zero without a Python stack trace.

### 2. Add `--auto-build-universe`

Add flags:

```text
--auto-build-universe
--min-turnover 5000000
--universe-max-symbols 150
```

If universe file is missing and `--auto-build-universe` is set, call the same builder logic used by `scripts/build_universe.py` directly or via a safe function, not by shelling out if avoidable.

Result must create:

```text
data/processed/universe_selected.parquet
reports/sprint_02_universe_report.md
```

### 3. Add one-command orchestrator

Add:

```text
scripts/run_fast_feasibility_pipeline.py
```

Default behavior:

```powershell
python scripts/run_fast_feasibility_pipeline.py --max-symbols 150 --min-turnover 5000000 --fast-max
```

Pipeline steps:

1. build universe if missing or `--refresh-universe`;
2. purge skipped constraints only if `--purge-skipped`;
3. dry-run plan;
4. if planned_requests > 5000 and no `--confirm-large-sweep`, stop;
5. run real min-investment sweep;
6. run analyzer;
7. print final PM summary.

Required printed output:

```text
step=build_universe status=ok selected_count=...
step=dry_run_plan planned_requests=... estimated_seconds=...
step=validate_sweep api_calls_attempted=... api_calls_succeeded=... api_calls_failed=... effective_api_rps=...
step=analyze symbols_tested=... configs_tested=... symbols_feasible_at_5=... symbols_feasible_at_10=... symbols_feasible_at_25=... symbols_feasible_at_50=... symbols_feasible_at_100=... symbols_feasible_at_250=... symbols_feasible_at_500=...
```

If `GRID_VALIDATE_ENABLED=false`, fail before validate with:

```text
GRID_VALIDATE_ENABLED=false. Set it true for real sweep. Dry-run only is available with --dry-run-only.
```

### 4. Add `--dry-run-only` to orchestrator

```powershell
python scripts/run_fast_feasibility_pipeline.py --max-symbols 150 --fast-max --dry-run-only
```

This should:

- build universe if missing;
- print planned requests/estimated seconds;
- not require private credentials;
- not call `/v5/fgridbot/validate`.

### 5. Fix progress and final summary consistency

For real validate sweep, progress must show:

```text
api_rps <= 10.5
```

If `api_rps > 15` while using `/v5/fgridbot/validate`, print a warning:

```text
warning: api_rps exceeds endpoint limit; check whether rows are real API responses or skipped/resumed rows
```

The final summary must include:

```text
api_calls_attempted
api_calls_succeeded
api_calls_failed
rate_limit_10006_count
effective_api_rps
symbols_tested
configs_tested
investment_min_non_null_rows
best_global_min_investment
```

### 6. Analyzer output for PM

`analyze_fgrid_min_investment.py` must print threshold summary directly:

```text
symbols_tested=...
configs_tested=...
investment_min_non_null_rows=...
min_investment_min_global=...
symbols_feasible_at_5=...
symbols_feasible_at_10=...
symbols_feasible_at_25=...
symbols_feasible_at_50=...
symbols_feasible_at_100=...
symbols_feasible_at_250=...
symbols_feasible_at_500=...
```

### 7. Tests

Add tests for:

- missing universe produces friendly message, not raw `FileNotFoundError`;
- `--auto-build-universe` calls builder when universe is missing;
- orchestrator dry-run-only builds universe and prints plan without private credentials;
- orchestrator real run refuses when `GRID_VALIDATE_ENABLED=false`;
- final summary includes API calls and threshold counts;
- create/close remain `NotImplementedError`.

## Acceptance commands after Codex

Run locally on Windows:

```powershell
python -m pytest -q
ruff check .
python scripts/run_fast_feasibility_pipeline.py --max-symbols 150 --min-turnover 5000000 --fast-max --dry-run-only --refresh-universe
```

Then real sweep:

```powershell
$env:GRID_VALIDATE_ENABLED="true"
$env:LIVE_TRADING_ENABLED="false"
$env:ALLOW_LIVE_TRADING="NO"
python scripts/run_fast_feasibility_pipeline.py --max-symbols 150 --min-turnover 5000000 --fast-max
```

Expected runtime target:

```text
planned_requests <= 1500
effective_api_rps between 8 and 10
runtime about 2-5 minutes, depending on network
```

## PM output required

Send PM:

- commit hash;
- tests output;
- ruff output;
- dry-run-only output;
- real pipeline output;
- summary of `reports/sprint_02_native_grid_feasibility_report.md`;
- threshold counts for 5/10/25/50/100/250/500 USDT.
