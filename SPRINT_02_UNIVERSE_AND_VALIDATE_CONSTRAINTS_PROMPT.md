# Sprint 02 — Universe Expansion + Bybit FGrid Constraint Map

PM decision: Gate 1 is closed only after public data, private account smoke, and `/v5/fgridbot/validate` are confirmed. This sprint must not implement strategy, backtest, Telegram, or live execution.

## Mission

Build the data and constraint foundation needed before range/research work:

1. Build a liquid Bybit USDT perpetual universe.
2. Map native Futures Grid Bot validate constraints across symbols and safe candidate parameter grids.
3. Detect whether the user's 5 USDT max-risk/min-investment rule is feasible for native Bybit grid bots.
4. Download a controlled historical sample only for the approved liquid universe.
5. Produce reports that let PM decide whether research can begin or whether the capital/risk assumption must be revised.

## Non-negotiable safety rules

- Do not implement live grid create.
- Do not implement live grid close.
- Do not place orders.
- Do not create positions.
- Keep `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO` defaults.
- Keep create/close as `NotImplementedError`.
- Validate-only is allowed only through `/v5/fgridbot/validate` and only if `GRID_VALIDATE_ENABLED=true`.
- Never log or persist API key, secret, signature, wallet balances, equity, PnL or exact account funds.
- No strategy/research/backtest in this sprint.

## Project constraints from PM/user

- Exchange: Bybit only.
- Instruments: USDT perpetual futures only.
- Timeframe for eventual research: 1m.
- Native Bybit Futures Grid Bot only.
- Grid mode: neutral only.
- Grid type: geometric only.
- Trailing up/down: forbidden.
- Take profit: disabled for v1.
- Close logic v1: SL only.
- Per-grid max loss/risk unit: 5 USDT.
- If Bybit validate/min-investment constraints imply more than 5 USDT, skip the instrument/config.
- PreLaunch/pre-market contracts excluded.
- Low-liquidity symbols excluded.
- Storage cap target: 250 GB.

## Important finding from Gate 1 validate

The first BTCUSDT dynamic validate response returned an `investment.from` around 449 USDT for the tested range/settings. This does not automatically mean all symbols/configs fail, but it is a major feasibility risk. Sprint 02 must quantify this across symbols and parameter grids before any strategy research begins.

## Required outputs

Create these machine-readable and markdown reports:

```text
reports/sprint_02_universe_report.md
reports/sprint_02_fgrid_constraints_report.md
reports/sprint_02_download_plan.md
data/processed/universe_candidates.parquet
data/processed/universe_selected.parquet
data/processed/fgrid_validate_constraints.parquet
data/processed/fgrid_feasible_configs.parquet
data/processed/download_manifest.parquet
```

## 1. Universe builder

Add module:

```text
src/bybit_grid/universe/builder.py
```

Add script:

```text
scripts/build_universe.py
```

Behavior:

- Fetch `/v5/market/instruments-info?category=linear` with cursor pagination.
- Fetch `/v5/market/tickers?category=linear`.
- Join by symbol.
- Filter:
  - quoteCoin == USDT.
  - contractType == LinearPerpetual when available.
  - status == Trading.
  - isPreListing != true.
  - symbol does not contain obvious test/prelaunch markers.
- Compute/select fields:
  - symbol
  - baseCoin
  - quoteCoin
  - status
  - contractType
  - launchTime
  - age_days
  - tickSize
  - qtyStep
  - minOrderQty
  - minNotionalValue
  - maxLeverage
  - fundingInterval
  - turnover24h
  - volume24h
  - lastPrice
  - liquidity_rank
  - eligible_liquidity_1m
  - eligible_liquidity_5m
  - eligible_liquidity_10m
  - eligible_liquidity_25m
- Save:
  - `data/processed/universe_candidates.parquet`
  - `data/processed/universe_selected.parquet`

CLI flags:

```bash
python scripts/build_universe.py --min-turnover 5000000 --max-symbols 100
python scripts/build_universe.py --min-turnover 10000000 --max-symbols 50
```

Report must include:

- total linear instruments;
- trading USDT perpetual count;
- excluded prelaunch count;
- excluded low-liquidity count;
- selected count;
- top 20 selected symbols by turnover;
- turnover threshold used.

## 2. FGrid validate constraint mapper

Add module:

```text
src/bybit_grid/bybit/fgrid_constraints.py
```

Add script:

```text
scripts/validate_universe_fgrid_constraints.py
```

Purpose:

Batch-call validate-only for selected symbols and parameter candidates to learn Bybit's native grid constraints.

Candidate grid:

```yaml
range_width_pct: [0.02, 0.05, 0.10, 0.15, 0.20]
cell_number: [2, 5, 10, 20, 30]
leverage: [1, 2, 3, 5, 10]
init_margin_probe: [5, 10, 25, 50, 100]
stop_loss_mult_below_min: [0.98, 0.95, 0.90]
```

Implementation notes:

- Use current `lastPrice` and `tickSize`.
- Build min/max/SL using the existing Decimal-safe fgrid payload builder or a new wrapper.
- Always neutral + geometric.
- No trailing.
- No TP.
- Throttle private calls. Default max: 2 requests/sec even if Bybit allows more.
- Add `--max-symbols`, `--max-configs-per-symbol`, `--sleep-sec`, `--resume`.
- Save every response redacted and parsed.
- Do not crash the whole run on one symbol/config error.

Parse response fields into columns:

- symbol
- lastPrice
- tickSize
- range_width_pct
- min_price
- max_price
- stop_loss_price
- cell_number_requested
- leverage_requested
- init_margin_requested
- retCode
- retMsg
- status_code
- check_code
- debug_msg
- investment_min
- investment_max
- cell_number_min
- cell_number_max
- leverage_min
- leverage_max
- min_price_from
- min_price_to
- max_price_from
- max_price_to
- stop_loss_price_from
- stop_loss_price_to
- profit_from
- profit_to
- validate_ok
- schema_or_param_rejected
- feasible_bybit
- feasible_user_5usdt_rule
- blocker_reason
- raw_response_path_redacted

Feasibility logic:

```text
feasible_bybit = validate_ok and requested fields fall inside returned ranges if ranges are present
feasible_user_5usdt_rule = feasible_bybit and investment_min <= 5
```

If `investment_min` is missing, set `feasible_user_5usdt_rule = false` and `blocker_reason = investment_min_missing`.

Reports:

- percent of symbols with any feasible config by Bybit;
- percent of symbols with any config satisfying 5 USDT rule;
- min/median/p90 investment_min by liquidity bucket;
- top feasible symbols if any;
- if none pass 5 USDT rule, write explicit PM blocker.

CLI example:

```bash
python scripts/validate_universe_fgrid_constraints.py \
  --universe data/processed/universe_selected.parquet \
  --max-symbols 30 \
  --max-configs-per-symbol 20 \
  --sleep-sec 0.5
```

## 3. Download manifest builder

Add module:

```text
src/bybit_grid/data/download_manifest.py
```

Add script:

```text
scripts/build_download_manifest.py
```

Purpose:

Create a controlled download plan before downloading large history.

Inputs:

- `universe_selected.parquet`
- `fgrid_feasible_configs.parquet`
- CLI `--days 90`, `--max-symbols 50`

Rules:

- If at least 10 symbols pass the 5 USDT validate constraint, download those first.
- If fewer than 10 pass, still allow a public-data research sample of top liquid symbols, but mark `trading_feasibility_status=blocked_by_min_investment`.
- Use launchTime: do not request data before symbol launch.
- Estimate rows and disk size before download.
- Hard stop if estimated size exceeds a CLI cap, default 25 GB for Sprint 02.

Output:

```text
data/processed/download_manifest.parquet
reports/sprint_02_download_plan.md
```

## 4. Universe data downloader

Add script:

```text
scripts/download_universe_data.py
```

Behavior:

- Read manifest.
- Download normal klines, mark-price klines, and funding history.
- Resume safely.
- Merge/dedup Parquet.
- Generate per-symbol quality reports.
- Use existing chunking logic.
- Add retry/backoff and `--sleep-sec`.
- Add `--dry-run` to print manifest without network calls.

CLI examples:

```bash
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --dry-run
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --sleep-sec 0.2
```

## 5. Data quality report

Add script:

```text
scripts/report_universe_quality.py
```

Report:

- symbols downloaded;
- rows by dataset/source;
- missing internal gaps;
- boundary gaps;
- duplicate candles;
- bad OHLC;
- zero volume rows;
- funding row count;
- mark kline row count;
- disk usage by dataset;
- symbols requiring reload;
- symbols excluded due to data quality.

Output:

```text
reports/sprint_02_universe_quality_report.md
data/processed/universe_quality_summary.parquet
```

## 6. Tests

Add tests for:

- universe filter excludes prelaunch and non-USDT.
- universe rank by turnover.
- fgrid constraint parser extracts `investment.from/to`, `cell_number.from/to`, `leverage.from/to`.
- 5 USDT feasibility rule.
- validate batch resumes and does not duplicate rows.
- download manifest respects launchTime.
- download manifest size cap.
- no private output contains secrets or balances.
- create/close still `NotImplementedError`.

## 7. Owner runbook

After Codex implementation, owner runs locally:

```powershell
python -m pytest
ruff check .
python scripts/build_universe.py --min-turnover 5000000 --max-symbols 100
python scripts/validate_universe_fgrid_constraints.py --max-symbols 30 --max-configs-per-symbol 20 --sleep-sec 0.5
python scripts/build_download_manifest.py --days 90 --max-symbols 50 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --dry-run
python scripts/download_universe_data.py --manifest data/processed/download_manifest.parquet --sleep-sec 0.2
python scripts/report_universe_quality.py
```

## 8. PM acceptance criteria

Sprint 02 is accepted only if:

- tests pass;
- ruff passes;
- universe selected report exists;
- fgrid constraints table exists;
- feasibility under the 5 USDT rule is quantified;
- if no symbols/configs pass 5 USDT, this is clearly stated as a blocker;
- manifest estimates disk usage;
- download does not exceed Sprint 02 cap;
- quality report shows gaps/duplicates/bad OHLC by symbol;
- no live execution code is added;
- no secrets/balances are persisted.

## 9. PM decision after Sprint 02

If enough symbols/configs pass the 5 USDT rule:

- Proceed to Sprint 03: Range Candidate Dataset.

If not enough pass:

- Stop research and hold PM decision:
  - revise per-grid budget;
  - change native grid assumptions;
  - consider own grid via limit orders later;
  - or restrict to paper/research only.
