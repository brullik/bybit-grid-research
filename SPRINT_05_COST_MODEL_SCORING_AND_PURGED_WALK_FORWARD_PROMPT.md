# Sprint 05 — Account-Specific Cost Model, Ex-Post Outcome Scoring & Purged Walk-Forward Design

## PM decision and accepted inputs

Gate 4 canonical outcome dataset is accepted.

Canonical input run:

```text
range_run_id = action_density_v2_123x90
outcome_run_id = outcomes_true_fast_v4_canonical_123x90_v1
```

Accepted evidence:

```text
outcome_rows_total = 241155
unique_outcome_id_count = 241155
duplicate composite rows = 0
unique_event_horizon_rows = 26795
future_data_complete_rate = 0.9941780182869938
input_hygiene_ok = true
semantic_audit_ok = true
equivalence_ok = true
reference_rows = fast_rows = joined_rows = 12960
mismatch_count_total = 0
wall-clock speedup >= 8x
```

The canonical loader removed duplicate physical file references, not market observations:

```text
kline refs 860 -> unique files 430
mark refs 860 -> unique files 430
funding refs 224 -> unique files 112
contradictory duplicate timestamps = 0
```

## Sprint 05 purpose

Build a transparent, account-specific cost and scoring layer and freeze the walk-forward evaluation protocol before any parameter optimization.

Sprint 05 must answer:

1. Which grid intervals are large enough to survive the owner's actual Bybit fee rates?
2. How should range survival, SL risk, activity proxies, data quality and funding context be represented without pretending OHLC proxies are real fills?
3. How should chronological train/validation/test folds be constructed without outcome-window leakage?
4. Which parameter families are eligible for a future state-machine backtest?

Sprint 05 does **not** select final parameters and does **not** claim strategy PnL.

## Non-negotiable safety and research rules

- No live execution.
- No order create/cancel.
- No grid create/close.
- No Telegram.
- No parameter optimization.
- No ML training.
- No final ROI, Profit Factor, Sharpe or risk-of-ruin claims.
- No hardcoded fee such as `0.055%`.
- Fee rates must come from a versioned local snapshot or an explicitly named scenario config.
- Funding-rate context must not be converted into USDT PnL without a position/exposure path.
- Activity proxies must never be called actual fills or completed trades.
- All future-outcome-based scores must be named `ex_post_*`; they are not deployable live-signal scores.
- The 5 USDT maximum-loss rule is not proven by minimum investment or SL distance alone.

---

# Task 0 — Portable Windows test gate

Current owner test run has one failure because `test_no_live_order_telegram_additions` shells out to `rg`, which is not installed on Windows. The test also accepts both `rg` match/no-match return codes and therefore does not meaningfully enforce safety.

Replace the external-executable test with a pure-Python/AST safety audit.

Required helper:

```text
src/bybit_grid/common/source_safety_audit.py
scripts/check_no_live_execution.py
```

The audit must:

- scan Python files under `src/bybit_grid` and `scripts` using `pathlib`/`ast` only;
- require `create_grid_bot` and `close_grid_bot` placeholders to raise `NotImplementedError`;
- fail on actual private POST calls to:
  - `/v5/fgridbot/create`
  - `/v5/fgridbot/close`
  - `/v5/order/create`
  - `/v5/order/cancel`
  - batch order endpoints;
- allow endpoint strings in settings/constants and tests;
- require `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO` defaults;
- not require Git, ripgrep, grep or any other external executable.

Delete the `subprocess.run(["rg", ...])` test.

Acceptance before any other Sprint 05 work:

```powershell
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

All tests must pass on the owner's Windows environment.

---

# Task 1 — Account-specific fee-rate snapshot

Bybit provides a private read-only fee-rate endpoint:

```text
GET /v5/account/fee-rate
category=linear
```

Add:

```text
src/bybit_grid/research/cost_model/fee_snapshot.py
scripts/snapshot_fee_rates.py
```

CLI examples:

```powershell
python scripts/snapshot_fee_rates.py --category linear --symbols-from-outcome-run outcomes_true_fast_v4_canonical_123x90_v1
python scripts/snapshot_fee_rates.py --category linear --all-linear
```

Requirements:

- read-only private API only;
- require private credentials but not `GRID_VALIDATE_ENABLED` or live flags;
- never print/store API keys, signatures, balances or account value;
- persist only:
  - snapshot ID;
  - UTC timestamp;
  - environment/base URL;
  - category;
  - symbol;
  - makerFeeRate;
  - takerFeeRate;
  - API response status/provenance;
- outputs:

```text
data/metadata/fee_snapshots/<fee_snapshot_id>/fee_rates.parquet
data/metadata/fee_snapshots/<fee_snapshot_id>/fee_rates.json
reports/cost_runs/<cost_run_id>/fee_snapshot_report.md
```

Also support an explicit offline scenario file when private API is unavailable:

```text
config/cost_scenarios.example.yml
```

Offline scenarios must be labeled `source=manual_scenario`, never `account_actual`.

Do not hardcode a default fee rate in Python code.

---

# Task 2 — Versioned cost scenarios

Add:

```text
src/bybit_grid/research/cost_model/models.py
src/bybit_grid/research/cost_model/cycle_costs.py
config/cost_scenarios.yml
```

Required fee execution scenarios:

```text
maker_maker
maker_taker
taker_taker
stress_taker_plus_slippage
```

Configuration fields:

```yaml
cost_model_version: cost_v1
fee_snapshot_id: <required for account_actual>
scenarios:
  maker_maker:
    entry_fee_source: maker
    exit_fee_source: maker
    sl_exit_fee_source: taker
    slippage_bps_per_market_leg: 0
  maker_taker:
    entry_fee_source: maker
    exit_fee_source: taker
    sl_exit_fee_source: taker
    slippage_bps_per_market_leg: 0
  taker_taker:
    entry_fee_source: taker
    exit_fee_source: taker
    sl_exit_fee_source: taker
    slippage_bps_per_market_leg: 0
  stress_taker_plus_slippage:
    entry_fee_source: taker
    exit_fee_source: taker
    sl_exit_fee_source: taker
    slippage_bps_per_market_leg: 2
```

For a geometric interval with buy price `P` and sell price `P*r`, calculate per-unit-entry-notional cycle economics without needing quantity:

```text
gross_cycle_return_long = r - 1
fee_fraction_long = buy_fee_rate + sell_fee_rate * r
net_cycle_return_long = gross_cycle_return_long - fee_fraction_long

# Short-side normalization must be documented and separately calculated.
```

Required fields per scenario:

```text
grid_interval_ratio
grid_interval_bps
round_trip_fee_bps_approx
net_cycle_return_long_bps
net_cycle_return_short_bps
fee_break_even_long_bool
fee_break_even_short_bool
fee_efficiency_ratio_long
fee_efficiency_ratio_short
cost_assumption_id
fee_snapshot_id
fee_source
```

Tests must independently verify formulas for multiple price ratios and asymmetric maker/taker rates.

---

# Task 3 — Grain-correct outcome views

Do not score directly from expanded 241155 rows without controlling duplicated dimensions.

Create canonical views:

```text
src/bybit_grid/research/scoring/outcome_grains.py
scripts/build_outcome_grains.py
```

Outputs:

```text
data/processed/scoring_runs/<scoring_run_id>/event_horizon.parquet
data/processed/scoring_runs/<scoring_run_id>/event_horizon_sl.parquet
data/processed/scoring_runs/<scoring_run_id>/event_horizon_grid.parquet
data/processed/scoring_runs/<scoring_run_id>/expanded_scoring_input.parquet
```

Expected unique keys:

```text
event_horizon:
  range_action_event_id + future_horizon_minutes

event_horizon_sl:
  range_action_event_id + future_horizon_minutes + sl_atr_buffer

event_horizon_grid:
  range_action_event_id + future_horizon_minutes + grid_cell_number

expanded_scoring_input:
  range_action_event_id + future_horizon_minutes + grid_cell_number + sl_atr_buffer
```

Required assertions:

- unique key count equals row count for every grain;
- all base event-horizon fields are invariant across grid/SL expansion;
- all SL fields are invariant across grid counts;
- all grid fields are invariant across SL buffers;
- funding values are sourced from the unique event-horizon grain;
- no aggregation accidentally weights a fact 3x or 9x.

---

# Task 4 — Transparent ex-post scoring components

Add:

```text
src/bybit_grid/research/scoring/components.py
src/bybit_grid/research/scoring/score_builder.py
scripts/build_outcome_scoring_dataset.py
```

The scoring dataset evaluates historical configuration outcomes. It is not a live signal model.

Required component families:

## A. Data integrity

```text
ex_post_data_complete_score
ex_post_ambiguity_penalty
ex_post_bad_ohlc_penalty
ex_post_zero_volume_penalty
```

## B. Range survival / breakout

```text
ex_post_range_survival_minutes
ex_post_range_survival_ratio
ex_post_exit_risk_score
ex_post_stayed_in_range_bool
```

## C. SL behavior

```text
ex_post_sl_survival_bool
ex_post_minutes_to_sl
ex_post_sl_distance_atr
ex_post_sl_risk_score
```

## D. Grid activity proxies

```text
ex_post_close_cross_activity_lower
ex_post_intrabar_touch_activity_upper
ex_post_completed_cycle_proxy_lower = floor(close_cross_activity / 2)
ex_post_completed_cycle_proxy_upper = floor(intrabar_touch_activity / 2)
```

These completed-cycle fields must include:

```text
proxy_only_bool = true
not_actual_native_fills_bool = true
```

## E. Cost efficiency

For every cost scenario:

```text
ex_post_fee_break_even_long_bool
ex_post_fee_break_even_short_bool
ex_post_net_cycle_bps_long
ex_post_net_cycle_bps_short
ex_post_cost_efficiency_score
```

## F. Funding context

Funding is rate context only until a position state machine exists:

```text
ex_post_funding_rate_sum_context
ex_post_funding_rate_abs_sum_context
ex_post_funding_missing_bool
ex_post_funding_position_path_unknown_bool = true
```

Do not calculate `funding_pnl_usdt` in this sprint.

## G. Capital lock

```text
ex_post_capital_lock_minutes_proxy
ex_post_capital_turnover_score
```

## H. Versioned composite proxy score

A transparent fixed-weight diagnostic score may be created:

```text
ex_post_proxy_score_v1
```

Rules:

- weights are declared in YAML and versioned;
- no search/optimization of weights;
- report every component alongside the total;
- total score must not be named EV, PnL, ROI or profitability;
- produce sensitivity report for at least three fixed weight sets rather than selecting the best one.

Outputs:

```text
data/processed/scoring_runs/<scoring_run_id>/outcome_scoring_dataset.parquet
reports/scoring_runs/<scoring_run_id>/outcome_scoring_report.md
reports/scoring_runs/<scoring_run_id>/score_sensitivity_report.md
```

---

# Task 5 — 5 USDT risk-budget readiness screen

The owner's project rule is maximum loss of 5 USDT per bot, not merely 5 USDT investment.

Sprint 05 must not claim this is solved.

Add screening fields:

```text
risk_budget_usdt = 5
risk_model_status
risk_position_path_available_bool = false
risk_budget_proven_bool = false
sl_distance_fraction_from_range_edge
max_single_side_notional_proxy_for_5usdt
```

`max_single_side_notional_proxy_for_5usdt` may be calculated as a clearly labeled screening bound:

```text
5 / sl_distance_fraction
```

but the report must state that neutral-grid net exposure varies as orders execute, so a native position state machine is required before claiming actual maximum loss.

Join validated configuration fields when available:

```text
fgrid_investment_min
target_init_margin_inside_validate_range
validated_leverage
validated_liquidation_prices
```

Required report section:

```text
Risk Budget Status: NOT YET PROVEN
Next required model: native neutral-grid position/exposure simulator
```

---

# Task 6 — Purged walk-forward split design

Add:

```text
src/bybit_grid/research/walk_forward/splits.py
src/bybit_grid/research/walk_forward/leakage_audit.py
scripts/build_walk_forward_splits.py
scripts/audit_walk_forward_splits.py
```

The split unit is `range_action_event_id`, grouped by `range_regime_id`.

Required properties:

- chronological only;
- no random row split;
- a whole `range_regime_id` belongs to one split;
- use signal time, not outcome completion time, for ordering;
- purge training events whose outcome windows overlap validation/test periods;
- embargo at least the maximum horizon: 2880 minutes;
- no event appears in more than one train/validation/test role within a fold;
- report symbol and time coverage per fold;
- deterministic split IDs.

Prototype 90-day defaults:

```yaml
min_train_days: 45
validation_days: 14
test_days: 14
step_days: 14
purge_minutes: 2880
embargo_minutes: 2880
```

Long-history defaults must be configurable separately:

```yaml
min_train_days: 365
validation_days: 90
test_days: 90
step_days: 30
purge_minutes: 2880
embargo_minutes: 2880
```

Outputs:

```text
data/processed/scoring_runs/<scoring_run_id>/walk_forward_splits.parquet
data/processed/scoring_runs/<scoring_run_id>/walk_forward_leakage_audit.parquet
reports/scoring_runs/<scoring_run_id>/walk_forward_design_report.md
```

Leakage audit must fail on:

- overlapping event IDs;
- overlapping regime IDs;
- train outcome window crossing into validation/test;
- missing embargo;
- non-chronological boundaries.

No parameter selection is performed in this sprint.

---

# Task 7 — Reporting and PM review pack

Add:

```text
scripts/report_cost_and_scoring.py
scripts/make_scoring_review_pack.py
scripts/check_scoring_review_pack.py
```

Review pack:

```text
pm_review_pack_scoring_<scoring_run_id>.zip
```

Allowlisted members only:

```text
fee_snapshot_report.md
cost_model_config.yml
cost_model_audit.json
outcome_grain_audit.json
outcome_scoring_summary.parquet
outcome_scoring_report.md
score_sensitivity_report.md
walk_forward_design_report.md
walk_forward_leakage_audit_summary.json
risk_budget_readiness_report.md
review_pack_manifest.json
```

Exclude:

```text
.env
API headers/signatures
data/raw
full outcome partitions
full scoring dataset
balances/account value
cache directories
```

---

# Task 8 — Tests

Add tests for:

- no external `rg`/Git dependency;
- live endpoint AST audit;
- fee snapshot redaction and provenance;
- no hardcoded 0.055 fee in scoring/cost modules;
- long/short geometric cycle formulas;
- asymmetric maker/taker rates;
- all four grain uniqueness rules;
- funding not multiplied by grid/SL dimensions;
- score component determinism;
- score weights versioning and no optimization;
- risk-budget fields explicitly unproven;
- purged walk-forward overlap removal;
- regime grouping;
- embargo enforcement;
- deterministic fold IDs;
- review-pack allowlist;
- no live/create/close/order/Telegram implementation.

---

# Owner runbook

## 1. Environment and portable test fix

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest -q
ruff check .
```

## 2. Fee snapshot

```powershell
python scripts/snapshot_fee_rates.py `
  --category linear `
  --symbols-from-outcome-run outcomes_true_fast_v4_canonical_123x90_v1
```

The owner must not paste credentials or raw signed headers into ChatGPT/Codex.

## 3. Build scoring grains and cost model

```powershell
python scripts/build_outcome_grains.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v1_123x90

python scripts/build_outcome_scoring_dataset.py `
  --outcome-run-id outcomes_true_fast_v4_canonical_123x90_v1 `
  --scoring-run-id scoring_cost_v1_123x90 `
  --fee-snapshot-id latest `
  --cost-config config/cost_scenarios.yml `
  --fast-max
```

## 4. Build purged walk-forward design

```powershell
python scripts/build_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v1_123x90 `
  --profile prototype_90d

python scripts/audit_walk_forward_splits.py `
  --scoring-run-id scoring_cost_v1_123x90
```

## 5. Reports and pack

```powershell
python scripts/report_cost_and_scoring.py `
  --scoring-run-id scoring_cost_v1_123x90

python scripts/make_scoring_review_pack.py `
  --scoring-run-id scoring_cost_v1_123x90

python scripts/check_scoring_review_pack.py `
  --zip pm_review_pack_scoring_scoring_cost_v1_123x90.zip `
  --scoring-run-id scoring_cost_v1_123x90
```

---

# Required console outputs

At the end, print compact JSON/key-value summaries for:

```text
pytest status
fee snapshot ID
symbols with fee rates
missing fee symbols
cost scenarios generated
event_horizon rows
event_horizon_sl rows
event_horizon_grid rows
expanded scoring rows
duplicate key counts
fee-break-even rate by grid count and scenario
score distribution by fixed weight set
risk_budget_proven_bool (must be false)
walk-forward fold count
leakage violations (must be 0)
review_pack_ok
```

---

# Definition of Done / Gate 5A

Sprint 05 passes only if:

```text
✅ all tests pass on Windows without rg/Git
✅ ruff passes
✅ account fee snapshot or explicit manual scenario exists
✅ no hardcoded fee rate in Python
✅ all cost formulas are audited
✅ all outcome grains have unique keys
✅ funding/base facts are not dimension-multiplied
✅ scoring components are transparent and versioned
✅ no final profitability claim is made
✅ risk_budget_proven_bool remains false with explicit next step
✅ walk-forward folds are purged and embargoed
✅ leakage audit violations = 0
✅ review pack passes
✅ no live/create/close/order/Telegram code
```

## Next sprint after Gate 5A

```text
Sprint 06 — Native Neutral-Grid Position State Machine,
5 USDT Risk Calibration, Costed PnL Simulation and Walk-Forward Backtest
```

Sprint 06 will be the first stage allowed to model actual position quantity, realized grid cycles, unrealized PnL, funding PnL, SL termination and portfolio-level drawdown. It must consume the frozen Sprint 05 cost model and split protocol without changing them after seeing test results.
