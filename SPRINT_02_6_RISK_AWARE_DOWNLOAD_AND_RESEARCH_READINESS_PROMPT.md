# Sprint 02.6 — Risk-aware Feasible Universe + Fast Data Download + Research Readiness

PM decision: Sprint 02.5 proved that the fast validate pipeline works and that native Bybit FGrid has many `investment_min <= 5 USDT` configurations. However, this is not yet proof of `max loss <= 5 USDT`. This sprint fixes naming, separates min-investment feasibility from risk-budget feasibility, and downloads research data for the feasible universe.

## Non-negotiable project rules

- FAST-first for all heavy work.
- Public downloads: default `--fast-max`, workers=64, max rps=100, skip-existing-ok=true.
- Private FGrid validate: workers=10, max rps=9.5.
- No live create.
- No live close.
- No ordinary order create/cancel.
- No Telegram.
- No strategy trading.
- No backtest engine yet.
- No full Cartesian brute force.
- Must have dry-run-plan for long work.
- Must print progress + ETA.
- Must support resume/checkpoint.
- Must write UTF-8 reports only.
- Do not commit `.env`, `data/raw`, `data/metadata`, `reports/runs`, raw private responses, or cache folders.

## Current evidence from Sprint 02.5

Accepted:

- `pytest -q`: 72 passed.
- `ruff check .`: passed.
- `run_fast_feasibility_pipeline --dry-run-only --refresh-universe`: selected 127 symbols, planned <=1183 requests, estimated 124 seconds.
- Real validate sweep: 127 API calls attempted, 127 succeeded, 0 failed.
- Effective API rps: about 8.80.
- Bybit endpoint limit observed: 10.
- Rate-limit 10006 count: 0.
- Analyzer: 123 symbols feasible at 5/10/25/50/100/250/500 USDT according to current `investment_min` interpretation.

Important correction:

`symbols_feasible_at_5` currently means **minimum investment <= 5 USDT**, not **max possible loss <= 5 USDT**. The user rule says 5 USDT is max loss per grid, so this sprint must rename and separate these concepts.

## Goal

1. Fix terminology and reports so `investment_min` feasibility is not confused with risk feasibility.
2. Confirm that `init_margin=5` is inside validate ranges for selected feasible configs.
3. Add risk-proxy fields from validate response, without pretending they prove max loss.
4. Build a clean feasible universe for research downloads.
5. Download 90 days of 1m OHLCV + mark price + funding for the top feasible symbols at FAST speed.
6. Produce a quality report and research-readiness report.

## 1. Rename feasibility outputs

Update code and reports so names are explicit:

Old / ambiguous:

```text
feasible_user_5usdt_rule
symbols_feasible_at_5
```

New:

```text
min_investment_feasible_at_5usdt
symbols_min_investment_feasible_at_5
```

Keep backward-compatible columns for now if needed, but reports must use the new names.

Add a PM warning in `reports/sprint_02_native_grid_feasibility_report.md`:

```text
This report verifies Bybit minimum investment constraints only. It does not prove that realized loss to SL is <= 5 USDT. Risk-budget validation starts in Sprint 03/Backtest.
```

## 2. Fix aggregate min investment

Current aggregate uses all rows, including non-feasible rows with `investment_min=0` from leverage-too-high responses.

Fix:

- `min_investment_min_global_all_rows`
- `min_investment_min_global_bybit_feasible_only`
- `min_investment_min_global_5usdt_feasible_only`

The main PM headline must use feasible-only values.

For rows where `check_code != FGRID_CHECK_CODE_UNSPECIFIED` or `feasible_bybit=false`, do not let `investment_min=0` influence the global feasible minimum.

## 3. Add target-init-margin confirmation

Add fields to constraints/summary:

```text
target_init_margin_usdt = 5
target_init_margin_inside_validate_range = investment_min <= 5 <= investment_max
```

For each selected feasible symbol, confirm that target init margin 5 is inside the returned validate range.

If this is false, the symbol is not research-download eligible.

## 4. Parse and store risk-proxy fields

Extend `parse_validate_response()` to keep these fields if present:

```text
entry_price_from
entry_price_to
long_liq_price
short_liq_price
stop_loss_price_from
stop_loss_price_to
take_profit_price_from
take_profit_price_to
profit_from
profit_to
```

Add derived fields:

```text
requested_range_width_pct
requested_stop_loss_distance_from_min_pct
requested_stop_loss_distance_from_last_pct
long_liq_distance_from_last_pct
short_liq_distance_from_last_pct
```

Do not claim these are true realized risk. They are only risk proxies for screening.

## 5. Build research-eligible universe

Create:

```text
data/processed/research_eligible_universe.parquet
reports/sprint_02_research_eligible_universe_report.md
```

Eligibility v1:

- symbol selected by universe builder;
- Bybit validate successful;
- `min_investment_feasible_at_5usdt=true`;
- `target_init_margin_inside_validate_range=true`;
- `check_code=FGRID_CHECK_CODE_UNSPECIFIED`;
- no unsigned agreements;
- 24h turnover >= configured threshold;
- not prelaunch;
- enough age/history for requested download window, or launchTime adjusted.

Sort by:

1. turnover24h descending;
2. lower `min_investment_min_seen`;
3. more stable funding/data availability later.

## 6. Fast download research data

Default staged run:

```powershell
python scripts/build_research_download_manifest.py --days 90 --max-symbols 50 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/research_download_manifest.parquet --fast-max --skip-existing-ok
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet
```

If top 50 passes quality, allow:

```powershell
python scripts/build_research_download_manifest.py --days 90 --max-symbols 123 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/research_download_manifest.parquet --fast-max --skip-existing-ok
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet
```

`build_research_download_manifest.py` should use `research_eligible_universe.parquet`, not raw universe.

## 7. Research readiness report

Create:

```text
reports/sprint_02_research_readiness_report.md
```

Required fields:

```text
eligible_symbols_count
downloaded_symbols_count
normal_kline_success_rate
mark_kline_success_rate
funding_success_rate
gap_count_total
duplicate_count_total
bad_ohlc_count_total
zero_volume_rows_total
disk_usage_gb
symbols_ready_for_sprint_03
symbols_excluded_quality
recommendation: pass/fail
```

Gate 2B pass criteria:

```text
eligible_symbols_count >= 30
normal_kline_success_rate >= 98%
mark_kline_success_rate >= 95%
duplicate_count_total = 0
bad_ohlc_count_total = 0
gap_rate <= 0.01% of expected minutes
funding failures explained
```

## 8. Tests

Add tests for:

- feasibility naming migration;
- feasible-only aggregate excludes `investment_min=0` from non-feasible rows;
- `target_init_margin_inside_validate_range` true/false cases;
- risk-proxy derivation;
- research eligible universe filtering;
- research download manifest uses only eligible symbols;
- UTF-8 report output;
- fast download flags are preserved;
- no create/close implementation was added.

## 9. Acceptance commands

Owner runs:

```powershell
python -m pytest -q
ruff check .
python scripts/analyze_fgrid_min_investment.py
python scripts/build_research_eligible_universe.py --target-init-margin 5
python scripts/build_research_download_manifest.py --days 90 --max-symbols 50 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/research_download_manifest.parquet --fast-max --skip-existing-ok
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet
python scripts/report_research_readiness.py
```

If top 50 passes:

```powershell
python scripts/build_research_download_manifest.py --days 90 --max-symbols 123 --max-gb 25
python scripts/download_universe_data.py --manifest data/processed/research_download_manifest.parquet --fast-max --skip-existing-ok
python scripts/report_universe_quality.py --manifest data/processed/research_download_manifest.parquet
python scripts/report_research_readiness.py
```

## 10. Required Codex output

At the end provide:

- commit hash;
- changed files;
- tests output;
- ruff output;
- analysis output summary;
- eligible universe count;
- research manifest rows/GB;
- download performance summary if run;
- quality summary;
- readiness recommendation;
- confirmation that live create/close remains unavailable.
