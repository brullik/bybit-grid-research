# Sprint 03 — FAST Range Candidate Dataset

PM decision: Gate 2B is closed. Start range research, but do not start backtest, Telegram, execution, or live trading.

## Current accepted state

Accepted owner-machine evidence:

- `pytest -q` passed: 81 tests.
- `ruff check .` passed.
- Native FGrid minimum-investment feasibility: 123 eligible symbols.
- Research manifest: 123 symbols.
- Research data downloaded locally.
- Fast quality report completed:
  - `manifest_symbols=123`
  - `rows_scanned_approx=29121520`
  - `duplicate_count_total=0`
  - `bad_ohlc_count_total=0`
- Research readiness completed:
  - `eligible_symbols_count=123`
  - `downloaded_symbols_count=123`
  - `normal_kline_success_rate=100.0`
  - `mark_kline_success_rate=100.0`
  - `funding_success_rate=100.0`
  - `gap_count_total=1503`
  - `zero_volume_rows_total=648710`
  - `symbols_ready_for_sprint_03=123`
  - `recommendation=pass`

## Non-negotiable safety rules

- Do not implement live execution.
- Do not create or close Bybit grid bots.
- Do not add Telegram.
- Do not add real order placement.
- Do not implement strategy selection based on PnL.
- Do not implement backtest in this sprint.
- No private API calls.
- No Bybit network calls are needed.
- Work only from local Parquet data.
- Keep create/close guarded as `NotImplementedError`.

## Performance requirements — project-wide FAST-first rule

Every heavy local data script must be FAST-first:

- Use Polars lazy scanning where possible.
- Avoid collecting the full 29M-row dataset unless required.
- Process symbol partitions independently.
- Use parallel workers by default.
- Default local workers: `min(32, os.cpu_count() or 8)`.
- Support `--workers` override.
- Support `--symbols-limit` for fast smoke runs.
- Support `--resume` and `--skip-existing-ok`.
- Print dry-run plan before heavy execution.
- Print compact progress + ETA.
- Write incremental outputs per symbol, then merge summaries.
- If estimated runtime > 10 minutes, require `--confirm-large-run`.
- No pandas full-dataset loops.
- No exact minute-by-minute gap expansion by default; use existing quality summary and manifest boundaries.

## Goal

Build the first research dataset of historical range/protorgovka candidates without lookahead.

This sprint answers:

> At each historical minute, can we identify a horizontal range that matches our formal definition using only past candles?

It does **not** answer whether the range is profitable. Outcome/backtest comes later.

## Definition of protorgovka v1

Only horizontal ranges.

At signal time `t`, use only candles ending at or before `t`.

Candidate lookback windows:

```text
30, 60, 120, 240, 480, 720, 1440 minutes
```

Baseline detection conditions:

- range high/low are computed only inside lookback window;
- current close is in middle zone, not near edges;
- price has entered lower zone and upper zone inside lookback;
- range height is positive and above tick-size noise;
- enough valid candles inside lookback;
- no disqualifying data quality issue inside lookback;
- horizontal-only baseline: no trendline/rising/falling ranges in v1.

Default zones:

```text
lower_zone: bottom 20% of range
mid_zone: center 30% of range
upper_zone: top 20% of range
```

These are research defaults, not final trading parameters.

## Required outputs

```text
data/processed/range_candidates/
  symbol=<SYMBOL>/year=<YYYY>/month=<MM>/candidates.parquet

data/processed/range_candidate_summary.parquet
reports/sprint_03_range_candidate_report.md
reports/sprint_03_range_candidate_perf.json
```

## Required columns in candidate rows

Identity/time:

- `candidate_id`
- `symbol`
- `signal_time_ms`
- `signal_time_utc`
- `lookback_minutes`

Range geometry:

- `range_low`
- `range_high`
- `range_mid`
- `range_height_abs`
- `range_height_pct`
- `current_close`
- `current_position_in_range`

Zone/touch features:

- `touches_lower_zone`
- `touches_upper_zone`
- `entered_lower_zone`
- `entered_upper_zone`
- `midline_crosses`
- `time_since_last_lower_touch_minutes`
- `time_since_last_upper_touch_minutes`

Volatility/amplitude:

- `atr_14`
- `atr_60`
- `atr_rel_14`
- `atr_rel_60`
- `range_height_atr_14`
- `range_height_atr_60`
- `amplitude_score`
- `mean_abs_return_inside_range`
- `realized_volatility`

Quality/filters:

- `valid_candles_in_window`
- `expected_candles_in_window`
- `missing_candles_in_window`
- `zero_volume_candles_in_window`
- `bad_ohlc_in_window`
- `data_quality_ok`
- `candidate_passed_baseline_filters`

Context:

- `turnover_sum_window`
- `volume_sum_window`
- `symbol_rank_by_turnover` if available from universe metadata
- `launch_age_days_at_signal` if available

## Required summary metrics

Report must include:

- symbols processed;
- candles scanned;
- candidate rows written;
- candidates by lookback window;
- candidates by symbol;
- candidates per 10k candles;
- data-quality rejection counts;
- zero-volume window rejection counts;
- average/median range height pct;
- average/median range height ATR;
- top 20 symbols by candidate frequency;
- runtime seconds;
- rows/sec;
- workers used;
- output size MB/GB;
- recommendation for Sprint 04.

## Data-quality handling

The readiness report accepted 1503 total gaps and 648710 zero-volume rows, but Sprint 03 must not blindly use bad windows.

Rules:

- Candidate windows with missing candles > 0 are rejected by default.
- Candidate windows with bad OHLC > 0 are rejected.
- Candidate windows with too many zero-volume candles are rejected.
- Default zero-volume window threshold: max 5% of lookback window.
- Add CLI override `--max-zero-volume-window-pct`.
- Store rejection counts; do not silently discard without reporting.

## Implementation modules

Add/update:

```text
src/bybit_grid/research/range_features.py
src/bybit_grid/research/range_detector.py
src/bybit_grid/research/range_candidate_store.py
src/bybit_grid/research/range_candidate_summary.py
scripts/build_range_candidates.py
scripts/report_range_candidates.py
tests/test_sprint_03_range_candidates.py
```

## CLI requirements

Dry-run plan:

```powershell
python scripts/build_range_candidates.py --manifest data/processed/research_download_manifest.parquet --dry-run-plan --fast-max
```

Smoke run:

```powershell
python scripts/build_range_candidates.py --manifest data/processed/research_download_manifest.parquet --symbols-limit 5 --days-limit 14 --fast-max
python scripts/report_range_candidates.py
```

Full accepted run:

```powershell
python scripts/build_range_candidates.py --manifest data/processed/research_download_manifest.parquet --fast-max --resume --skip-existing-ok
python scripts/report_range_candidates.py
```

Optional large run confirmation:

```powershell
python scripts/build_range_candidates.py --manifest data/processed/research_download_manifest.parquet --fast-max --resume --skip-existing-ok --confirm-large-run
```

## Algorithm guidance

Preferred approach:

1. Work symbol-by-symbol.
2. Load only needed local Parquet for the symbol.
3. Sort by `open_time_ms`.
4. Create rolling features for each lookback window.
5. Avoid Python loops per candle where Polars rolling/window expressions are practical.
6. If pure Polars becomes too complex, use NumPy for per-symbol arrays, but keep processing per-symbol and parallelized.
7. Emit only candidate rows, not all minute rows with features, unless `--debug-write-all-features` is explicitly set.
8. Write candidates per symbol/month to avoid one huge output file.

Candidate detector baseline can use array-based rolling windows if faster/simpler:

- precompute rolling max high / rolling min low;
- compute position in range;
- compute zone masks;
- rolling sum lower-zone entries / upper-zone entries;
- rolling midline crosses;
- rolling ATR and return amplitude.

## Tests

Add tests for:

- no lookahead: changing candles after signal time must not change candidate at signal time;
- horizontal range baseline on synthetic candles;
- current price must be in mid-zone;
- requires lower and upper zone entries;
- rejects missing candles in lookback;
- rejects bad OHLC in lookback;
- zero-volume threshold behavior;
- candidate_id stable/deterministic;
- per-symbol partition writing;
- dry-run plan does not process data;
- workers/resume/skip-existing behavior;
- no live create/close/order paths added.

## Acceptance criteria

Codex output must include:

- commit hash;
- files changed;
- tests output;
- ruff output;
- dry-run plan output;
- smoke run output for 5 symbols / 14 days;
- full run output if performed;
- summary report metrics.

PM closes Sprint 03A only if:

```text
pytest passed
ruff passed
dry-run plan works
smoke run works
candidate rows > 0
no lookahead tests pass
rejection counts are reported
full run or approved partial run completes
report_range_candidates.py outputs candidate frequency by symbol/window
no private API calls
no live execution code
```

## Explicitly out of scope

- No profitability labels.
- No grid PnL simulation.
- No SL/TP outcome labels.
- No parameter optimization.
- No strategy selection.
- No Telegram.
- No Bybit create/close.

Those start in Sprint 04 after the candidate dataset is verified.
