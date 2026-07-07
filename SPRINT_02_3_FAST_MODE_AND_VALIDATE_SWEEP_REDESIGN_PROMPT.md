# Sprint 02.3 — FAST Mode + FGrid Validate Sweep Redesign

PM decision: The project now operates FAST-first. Every network-heavy script must default to the fastest safe throughput for its endpoint, not conservative serial loops. However, “fastest” means highest sustainable throughput inside Bybit endpoint/IP limits with adaptive backoff, not reckless requests that trigger bans or corrupt data.

## Non-negotiable safety rules

- Do not implement live create.
- Do not implement live close.
- Do not place orders.
- Do not create grid bots.
- Do not implement strategy/backtest/Telegram/live execution.
- Keep `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO`.
- Keep `create_grid_bot()` and `close_grid_bot()` as guarded `NotImplementedError` placeholders.
- Do not leak API secrets, signatures, balances, equity, or PnL.
- All private validate output stays redacted.

## Root problem

The previous command was too slow:

```powershell
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --sleep-sec 0.15
```

Reason: current Stage A creates too many validate calls per symbol:

```text
4 range widths × 4 cell numbers × 3 leverages × 5 init margins × 2 stop-loss multipliers = 480 calls/symbol
```

For 113 selected symbols this is about:

```text
113 × 480 = 54,240 private validate requests
```

At 0.15s sleep, the sleep time alone is more than 2 hours, before HTTP latency. This is a design error. We must stop brute-forcing dimensions that do not need brute force.

## New permanent performance rule

Add a project-wide performance profile:

```yaml
performance:
  profile: fast_max
  public:
    workers: 64
    max_requests_per_second: 100
    max_retries: 3
    backoff_on_429: true
    backoff_on_403: true
  private_fgrid_validate:
    workers: 10
    max_requests_per_second: 9.5
    max_retries: 2
    backoff_on_10006: true
    use_response_headers: true
  local_cpu:
    workers: auto
```

Implementation detail:

- Public endpoints can use high concurrency because Bybit default HTTP IP limit is 600 requests / 5 seconds, but still use adaptive backoff.
- `/v5/fgridbot/validate` has a 10/s endpoint limit, so default target is 9.5 rps with 10 workers.
- Remove per-call `time.sleep()` from private validate loops. Use a shared rate limiter.
- Every long script must print progress, ETA, current RPS, completed/total, skipped/resumed.

## 1. Redesign FGrid min-investment sweep

Current brute-force is unacceptable.

Create a new module:

```text
src/bybit_grid/bybit/fgrid_min_sweep.py
```

### Sweep philosophy

We are not optimizing strategy yet. We only need to answer:

```text
Can native Bybit Futures Grid Bot produce investment_min <= 5 USDT for any liquid symbol/config?
```

So use a targeted minimizer sweep, not a full Cartesian grid.

### Remove init_margin dimension from sweep

Do not sweep `init_margin` values. Use one safe probe value, e.g. `init_margin=100`, because the validate response returns `investment.from` / `investment.to`. If `init_margin=100` causes parameter issues for very expensive symbols, fallback to `init_margin=500` once.

### Candidate profiles

For each symbol, test only profiles likely to minimize investment:

```text
profile_name=ultra_min_1
range_width_pct=0.01
cell_number=2
leverage=max_valid_leverage_probe
stop_loss_mult=0.98

profile_name=ultra_min_2
range_width_pct=0.02
cell_number=2
leverage=max_valid_leverage_probe
stop_loss_mult=0.98

profile_name=min_cells_high_lev
range_width_pct=0.05
cell_number=2
leverage=max_valid_leverage_probe
stop_loss_mult=0.95

profile_name=small_grid_high_lev
range_width_pct=0.05
cell_number=5
leverage=max_valid_leverage_probe
stop_loss_mult=0.95

profile_name=baseline_high_lev
range_width_pct=0.10
cell_number=10
leverage=max_valid_leverage_probe
stop_loss_mult=0.95

profile_name=baseline_low_lev
range_width_pct=0.10
cell_number=10
leverage=1
stop_loss_mult=0.95
```

Then optionally test a small leverage ladder only if needed:

```text
leverage_ladder = [1, 3, 10, 25, 50, 100], clipped to instrument max leverage
```

Hard cap:

```text
max_profiles_per_symbol default = 12
absolute_max_profiles_per_symbol default = 24
```

This should reduce 480 calls/symbol to 6–24 calls/symbol.

For 113 symbols at 12 calls/symbol:

```text
~1356 calls / 9.5 rps ≈ 2.4 minutes plus overhead
```

## 2. Use instrument maxLeverage

`universe_selected.parquet` should already contain maxLeverage or instrument metadata. Use it.

If missing, add it to the universe builder output.

Leverage selection:

```python
def leverage_probe_values(max_leverage: Decimal) -> list[int]:
    candidates = [1, 3, 10, 25, 50, 100]
    return [x for x in candidates if Decimal(x) <= max_leverage] or [1]
```

For the ultra-min profiles, use the highest available leverage in that list.

## 3. Add concurrent private validate

Update:

```text
scripts/validate_universe_fgrid_constraints.py
```

New defaults:

```bash
--mode min-investment-sweep
--workers 10
--max-requests-per-second 9.5
--max-profiles-per-symbol 12
--resume
--progress-every 50
--stop-after-first-5usdt-feasible
```

Use `ThreadPoolExecutor` with one `BybitClient` per worker and a shared limiter.

Rules:

- If a symbol gets `investment_min <= 5`, stop testing more profiles for that symbol by default.
- If a symbol's best investment_min remains > 500 after the first 3 profiles, stop testing that symbol by default unless `--exhaustive` is set.
- Always dedupe before request using candidate key.
- Always append incrementally every N responses, e.g. every 50, so Ctrl+C does not lose progress.
- On Ctrl+C, flush rows and print resume command.

## 4. Add progress/ETA

Every long script must print compact ASCII progress:

```text
progress done=350 total=1356 pct=25.8 rps=8.9 eta_sec=113 best_5usdt_symbols=0 errors=2 skipped_resume=140
```

For downloads:

```text
progress symbols_done=3 symbols_total=50 requests=780 rps=92.1 rows=620000 skipped_existing=12 failed=0 eta_sec=180
```

## 5. Add max-speed CLI aliases

All heavy scripts should accept:

```bash
--fast-max
```

Behavior:

For private fgrid validate:

```text
workers=10
max_requests_per_second=9.5
sleep_sec=0
resume=true
progress_every=50
```

For public downloads:

```text
workers=64
max_requests_per_second=100
skip_existing_ok=true
progress_every=10
```

## 6. Remove `--sleep-sec` as the main throttle

Keep `--sleep-sec` only as compatibility/deprecated. If both are passed:

- `--max-requests-per-second` wins.
- Print warning: `--sleep-sec is deprecated; using shared rate limiter`.

## 7. Add dry-run request estimator

Before real validate, allow:

```bash
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max --dry-run-plan
```

Output:

```text
symbols=113 profiles_per_symbol_max=12 planned_requests<=1356 estimated_seconds_at_9.5rps=143
```

If planned requests > 5000, require `--confirm-large-sweep`.

## 8. Fix analyze empty result behavior

If constraints file is missing or empty, `analyze_fgrid_min_investment.py` should print:

```text
No constraints available. Run validate_universe_fgrid_constraints.py first.
```

It should not silently produce a misleading report.

## 9. Add tests

Add tests for:

- min-sweep planned request count is <= symbols × max_profiles_per_symbol;
- init_margin is not swept as a dimension;
- highest valid leverage is used for ultra-min profiles;
- stop-after-first-5usdt-feasible reduces calls;
- early stop if best investment_min > 500 after first 3 profiles;
- Ctrl+C / KeyboardInterrupt flushes partial rows;
- `--fast-max` sets correct workers/rps defaults;
- `--dry-run-plan` makes zero network calls;
- progress estimator works;
- no live create/close code is added.

## 10. Acceptance commands

Owner runs:

```powershell
python -m pytest -q
ruff check .
python scripts/build_universe.py --min-turnover 5000000 --max-symbols 150
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max --dry-run-plan
python scripts/validate_universe_fgrid_constraints.py --mode min-investment-sweep --max-symbols 150 --fast-max
python scripts/analyze_fgrid_min_investment.py
```

Expected runtime for the real sweep: target under 10 minutes. If it estimates longer than 10 minutes, the script must print why and the planned request count before starting.

## 11. Required output from Codex

Provide:

- commit hash;
- files changed;
- tests output;
- ruff output;
- dry-run planned request count;
- estimated runtime;
- actual runtime if run;
- rows written;
- symbols tested;
- best/global min investment;
- symbols feasible at 5/10/25/50/100/250/500 USDT.

## PM acceptance criteria

Sprint 02.3 is done only if:

```text
pytest passed
ruff passed
private validate sweep no longer uses full Cartesian brute force
fast-max dry-run estimates <= 24 requests/symbol
real sweep supports workers=10 and rps=9.5
a full top-150 sweep can resume after Ctrl+C
partial rows are flushed on interrupt
analyze report is meaningful
no live execution added
```
