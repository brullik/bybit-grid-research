# Sprint 02.2 — Native Grid Feasibility Decision + Data Hygiene

PM decision: Sprint 02.1 performance/policy work is accepted. Gate 2A is not closed because current validate results show zero `validated_5usdt_feasible` symbols/configs. Do not start range research/backtest yet.

## Accepted evidence from Sprint 02.1

- `pytest` passed.
- `ruff check .` passed.
- Universe builder selected liquid Bybit USDT perpetual symbols.
- FGrid constraints ran: 30 symbols x 20 configs = 600 rows.
- Download manifest correctly blocked default downloads because all rows are `blocked_by_min_investment`.
- Exploratory override worked: 5 blocked symbols x 7 days downloaded in ~14 seconds with 4 workers and shared rate limiter.
- Windows UTF-8 report bug was fixed for report files.

## Main blocker

All tested FGrid native-grid configs failed the user's 5 USDT feasibility rule:

```text
percent satisfying 5 USDT rule: 0.0%
```

The original user rule remains binding:

- 500 USDT starting capital.
- 5 USDT is maximum risk per grid.
- If Bybit validate minimum investment is above 5 USDT, skip the symbol/config.
- Native Bybit Futures Grid Bot, Neutral + Geometric only.

Therefore the project must answer one question before research:

> Is the native Bybit Futures Grid Bot feasible for the 5 USDT rule at all?

## Non-negotiable safety rules

- No strategy research.
- No backtest.
- No Telegram/live execution.
- No grid create/close.
- No normal order create/cancel.
- Validate-only is allowed.
- Public data downloads are allowed only for small exploratory checks or validated feasible symbols.
- Keep secrets and account artifacts out of shared zips.

## Task 1 — Fix remaining data hygiene issues

### 1.1 Align manifest timestamps to closed 1-minute candles

`download_manifest.py` currently uses arbitrary millisecond timestamps. Fix it.

Add helpers:

```python
ONE_MINUTE_MS = 60_000

def last_closed_minute_ms(now_ms: int | None = None) -> int:
    now = int(datetime.now(timezone.utc).timestamp() * 1000) if now_ms is None else now_ms
    return (now // ONE_MINUTE_MS) * ONE_MINUTE_MS - ONE_MINUTE_MS

def start_for_days_ms(end_ms: int, days: int) -> int:
    return end_ms - days * 24 * 60 * ONE_MINUTE_MS + ONE_MINUTE_MS
```

Use these in:

- `build_download_manifest()`
- `scripts/download_universe_data.py --days-override`

When `days=7`, expected 1m rows per source should be exactly `10080` if data is complete.

### 1.2 Recompute estimates after `--days-override`

`--days-override 7` currently changes start/end but still prints 90-day estimated rows. Fix it.

Expected for 7 days:

```text
estimated_kline_rows = 10080
estimated_mark_kline_rows = 10080
estimated_funding_rows ≈ days * 3 for 8h funding symbols
```

### 1.3 Make CLI output ASCII summaries, not Polars tables

`download_universe_data.py` still prints Polars tables with box-drawing symbols. Replace with a compact summary:

```text
manifest_rows_total=50 downloadable_rows=0 skipped_blocked=50 policy_blocked=true
```

For exploratory override:

```text
downloadable_symbols=BTCUSDT,ETHUSDT,SOLUSDT,LABUSDT,HYPEUSDT estimated_rows=... estimated_gb=...
```

### 1.4 Ensure quality report sees downloaded data

After exploratory download, `report_universe_quality.py` must produce rows for:

- klines
- mark_klines
- funding

If no data is found while files exist, fix the glob/path logic.

### 1.5 Funding row sanity check

For normal perpetual symbols, 7 days usually means about 21 funding events for 8h funding intervals. Add report fields:

- `funding_rows_expected_approx`
- `funding_rows_actual`
- `funding_rows_status`: `ok`, `low`, `missing`, `unknown_interval`

Do not fail the pipeline solely on funding count, but surface it in the report.

## Task 2 — Native FGrid feasibility sweep

Create:

```text
scripts/analyze_fgrid_min_investment.py
src/bybit_grid/bybit/fgrid_feasibility.py
```

Inputs:

```text
data/processed/fgrid_validate_constraints.parquet
```

Outputs:

```text
data/processed/fgrid_min_investment_by_symbol.parquet
reports/sprint_02_native_grid_feasibility_report.md
```

Report by symbol:

- symbol
- min_investment_min_seen
- median_investment_min
- p90_investment_min
- best_config_for_min_investment
- min_range_width_pct
- best_cell_number
- best_leverage
- best_stop_loss_mult
- bybit_feasible_config_count
- user_5usdt_feasible_config_count
- user_10usdt_feasible_config_count
- user_25usdt_feasible_config_count
- user_50usdt_feasible_config_count
- user_100usdt_feasible_config_count
- user_250usdt_feasible_config_count
- user_500usdt_feasible_config_count

Also report aggregate counts:

```text
symbols_tested
configs_tested
min_investment_min_global
min_investment_median_by_symbol
symbols_feasible_at_5
symbols_feasible_at_10
symbols_feasible_at_25
symbols_feasible_at_50
symbols_feasible_at_100
symbols_feasible_at_250
symbols_feasible_at_500
```

## Task 3 — Broaden validate-only scan efficiently

Add or modify `scripts/validate_universe_fgrid_constraints.py`:

New mode:

```bash
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --sleep-sec 0.15
```

Sweep policy:

Stage A per symbol:

```text
range_width_pct: 2%, 5%, 10%, 20%
cell_number: 2, 5, 10, 20
leverage: 1, 3, 10, max_allowed_probe_if_known
init_margin: 5, 10, 25, 50, 100
stop_loss_mult: 0.90, 0.95
```

But avoid full Cartesian explosion when possible. Generate a balanced set first, then expand only if the minimum observed `investment.from` is below 100 USDT.

Important:

- Deduplicate before request.
- Resume from existing constraints.
- Save raw redacted responses.
- Keep requests per second conservative.
- Do not call create/close.

## Task 4 — Capital decision report

At the end, the report must include a PM decision section:

```text
Decision A: Native Bybit FGrid under 5 USDT is feasible.
Decision B: Native Bybit FGrid under 5 USDT is not feasible, but feasible at X USDT.
Decision C: Native Bybit FGrid is not suitable for 500 USDT startup; consider custom grid later.
```

Do not make the decision in code. Generate the evidence for PM.

## Task 5 — Archive hygiene

Add:

```text
scripts/make_share_zip.py
scripts/clean_generated_artifacts.py
```

Default share zip must exclude:

- `.env`
- `.venv/`
- `data/`
- `reports/runs/`
- private metadata
- raw redacted validate responses
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`

Generated zips must include code, tests, configs, docs, and sanitized reports only.

## Tests

Add tests for:

- manifest timestamps are minute-aligned;
- `--days-override` recomputes estimates;
- CLI summary does not contain Polars box-drawing characters;
- quality report finds downloaded files under the current partition layout;
- funding row sanity status logic;
- min-investment summary by symbol;
- feasibility thresholds 5/10/25/50/100/250/500;
- min-investment sweep dedupe/resume;
- share zip excludes data/reports/cache/private artifacts.

## Acceptance commands

Owner runs:

```powershell
python -m pytest -q
ruff check .
python scripts/build_universe.py --min-turnover 5000000 --max-symbols 150
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --sleep-sec 0.15
python scripts/analyze_fgrid_min_investment.py
python scripts/build_download_manifest.py --days 90 --max-symbols 50 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --dry-run
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --include-blocked --reason exploratory_data_only --symbols-limit 5 --days-override 7 --workers 4 --max-requests-per-second 12 --skip-existing-ok
python scripts/report_universe_quality.py
```

## PM gate criteria

Gate 2A closes only if:

- tests pass;
- ruff passes;
- time alignment fixed;
- quality report sees exploratory downloaded data;
- performance report includes timing/request metrics;
- FGrid feasibility report exists;
- min-investment thresholds are quantified;
- we can decide whether native FGrid is viable for 5 USDT or not.
