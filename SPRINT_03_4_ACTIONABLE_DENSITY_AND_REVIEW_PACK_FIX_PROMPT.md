# Sprint 03.4 — Actionable Density Calibration + Review Pack Correctness

PM decision: Sprint 03.3 fast core is accepted as a speed foundation, but Gate 3 is not closed. Full-run wall time improved enough, but actionable density is still too high and review packs still include stale global reports.

## Non-negotiable rules

- Do not implement future outcomes.
- Do not implement backtest.
- Do not implement live signals.
- Do not implement Telegram.
- Do not implement Bybit create/close/order endpoints.
- Keep all outputs run-isolated.
- Keep FAST-first defaults.
- Do not upload or package raw parquet partitions.
- Do not use a hard top-N cap to fake acceptable density.

## Accepted facts from Sprint 03.3

Smoke 10 symbols x 30 days, `actionable_fast_strict`, `numpy_fast`:

```text
raw_candidate_rows_written=54098
actionable_event_rows_written=20705
runtime_seconds=12.52
actionable_events_per_symbol_day_p50=63
actionable_events_per_symbol_day_p90=134
actionable_events_per_symbol_day_p99=198
acceptance_density_status=fail
```

Full 123 symbols x 90 days, `actionable_fast_strict`, `numpy_fast`:

```text
raw_candidate_rows_written=1858121
actionable_event_rows_written=635328
runtime_seconds=352.49
actionable_events_per_symbol_day_p50=61
actionable_events_per_symbol_day_p90=135
actionable_events_per_symbol_day_p99=199
symbols_with_actionable_events=123
lookbacks_with_actionable_events=7
duplicate_action_event_id_count=0
acceptance_density_status=fail
```

Interpretation:

- Speed is now acceptable enough for this phase.
- Density is close but still fails p50/p90 and compression requirements.
- `raw_to_actionable_compression_ratio` is currently reported as 0 when output_layer=actionable because raw rows are not persisted. This metric must use perf counters if raw parquet is absent.
- PM review pack includes run summary parquet/json but also stale global markdown reports. This must be fixed.

## Gate 3 targets

For the final actionable layer:

```text
actionable_events_total > 0
symbols_with_actionable_events >= 50
lookbacks_with_actionable_events >= 3
raw_to_actionable_compression_ratio >= 10
p50 actionable events/symbol/day <= 50
p90 actionable events/symbol/day <= 100
p99 actionable events/symbol/day <= 200
duplicate_action_event_id_count = 0
rejection counters numeric and meaningful
reports are run-isolated
no stale output mixing
no live/create/close/order code
```

## 1. Fix density metrics when raw parquet is not persisted

Update `report_range_candidate_density.py` and summary logic:

- If raw parquet exists, use row count from raw parquet.
- If raw parquet is absent but perf JSON has `raw_candidate_rows_written`, use that as raw count.
- If actionable parquet exists, use actionable parquet count.
- Compute:

```text
raw_to_actionable_compression_ratio = raw_candidate_rows_written / actionable_event_rows_written
```

If actionable rows are 0, compression is null and acceptance fails clearly.

Do not report `raw_to_actionable_compression_ratio=0.0` just because raw parquet was not written.

## 2. Fix review pack to include only run-specific, fresh reports

`make_pm_review_pack.py` must not include stale global markdown files like `reports/sprint_03_range_candidate_report.md` unless they were regenerated for the requested run in the same command.

Preferred behavior:

```bash
python scripts/make_pm_review_pack.py --run-id action_density_v2_123x90
```

should internally regenerate or include run-specific files:

```text
reports/range_runs/<run_id>/range_candidate_report.md
reports/range_runs/<run_id>/range_candidate_density_report.md
reports/range_runs/<run_id>/profile_summary.md, if available
data/processed/range_runs/<run_id>/summary/range_candidate_perf.json
data/processed/range_runs/<run_id>/summary/range_candidate_summary.parquet
data/processed/range_runs/<run_id>/summary/range_density_summary.parquet
data/processed/range_runs/<run_id>/summary/range_rejection_summary.parquet
```

It must exclude:

```text
data/raw/**
data/processed/range_runs/<run_id>/raw_candidates/**
data/processed/range_runs/<run_id>/event_candidates/**
data/processed/range_runs/<run_id>/range_regimes/**
data/processed/range_runs/<run_id>/actionable_events/**
.env
reports/runs/**
__pycache__/**
.pytest_cache/**
.ruff_cache/**
```

Add `scripts/check_pm_review_pack.py --zip <path> --run-id <run_id>`.

The checker must fail if stale global reports are present without run-specific report paths.

## 3. Add density calibration profiles without hard caps

Add calibrated profiles:

```text
actionable_density_v2
actionable_density_v3
strict_actionable_v2
```

These are profile-level filters, not output caps.

Recommended knobs to tune:

```text
min_regime_duration_minutes: [15, 30, 60]
min_raw_candidates_in_regime: [5, 10, 20]
min_unique_lookbacks_in_regime: [2, 3]
min_midline_cross_count: [2, 4, 6]
min_path_length_over_range: [3, 5, 8]
min_touches_lower_zone: [1, 2]
min_touches_upper_zone: [1, 2]
max_range_slope_pct: stricter than current
min_range_quality_score: [0.55, 0.65, 0.75]
zero_volume max stricter where appropriate
```

Add or improve cross-regime coalescing:

- merge regimes across lookbacks if normalized price bounds overlap strongly;
- merge adjacent regimes of same symbol if price bounds overlap and gap <= cooldown;
- default one actionable event per merged regime;
- keep `allow_reentry_events=false` by default;
- optional reentry mode must be off for Gate 3.

Do not solve density by `max_events_per_symbol_day` cap unless explicitly reported as policy cap. Gate 3 should use uncapped logic.

## 4. Add calibration script that selects a profile before full run

Add/update:

```text
scripts/calibrate_actionable_density.py
```

Command:

```bash
python scripts/calibrate_actionable_density.py --symbols-limit 10 --days-limit 30 --fast-max
```

It should evaluate candidate profiles on the same 10x30 sample and write:

```text
reports/range_density_calibration_<run_id>.md
data/processed/range_runs/<run_id>/summary/actionable_density_calibration.parquet
```

Columns/fields:

```text
profile_name
raw_candidate_rows_written
actionable_event_rows_written
raw_to_actionable_compression_ratio
actionable_events_per_symbol_day_p50
actionable_events_per_symbol_day_p90
actionable_events_per_symbol_day_p99
symbols_with_actionable_events
lookbacks_with_actionable_events
duplicate_action_event_id_count
runtime_seconds
acceptance_density_status
```

Selection logic:

- choose the fastest profile that passes p50/p90/p99/compression and still has symbols_with_actionable_events >= 8 on 10-symbol smoke;
- if none pass, print exact blockers and do not recommend full run.

## 5. Add full-run guard based on smoke density

`build_range_candidates.py --confirm-large-run` should still work, but add optional safety:

```bash
--require-density-smoke-pass <calibration_run_id>
```

If the calibration run has no passing profile, stop before full run unless `--override-density-fail` is provided.

## 6. Improve profile_range_core to profile real candidate-producing samples

`profile_range_core.py` currently may return `raw_candidates=0`, which is not useful.

Add:

```bash
--profile actionable_density_v2
--require-candidates
--symbols BTCUSDT,ETHUSDT,... optional
```

If `--require-candidates` and raw_candidates=0, exit with clear message and recommend looser profile or different symbols.

The profile report must show:

```text
input_rows
raw_candidates
actionable_events
detect_seconds
coalesce_seconds
write_seconds
rows_per_sec
raw_candidates_per_sec
actionable_events_per_sec
hot functions from cProfile
```

## 7. Tests

Add tests for:

- compression ratio uses perf raw count when raw parquet absent;
- review pack excludes stale global reports and includes run-specific report paths;
- check_pm_review_pack fails on stale/global reports;
- density calibration chooses a passing profile when one exists;
- density calibration reports blockers when none pass;
- no hard cap is applied silently;
- full-run guard refuses full run if smoke density failed;
- create/close/order code remains absent/forbidden.

## 8. Commands owner should run after Codex

```powershell
python -m pytest -q
ruff check .

python scripts/calibrate_actionable_density.py --symbols-limit 10 --days-limit 30 --fast-max

python scripts/build_range_candidates.py `
  --symbols-limit 10 `
  --days-limit 30 `
  --profile actionable_density_v2 `
  --output-layer actionable `
  --core numpy_fast `
  --fast-max `
  --run-id smoke_density_v2_10x30

python scripts/report_range_candidates.py --run-id smoke_density_v2_10x30
python scripts/report_range_candidate_density.py --run-id smoke_density_v2_10x30
python scripts/make_pm_review_pack.py --run-id smoke_density_v2_10x30
python scripts/check_pm_review_pack.py --zip pm_review_pack_smoke_density_v2_10x30.zip --run-id smoke_density_v2_10x30
```

Full run only if smoke passes density targets or PM approves override:

```powershell
python scripts/build_range_candidates.py `
  --profile actionable_density_v2 `
  --output-layer actionable `
  --core numpy_fast `
  --fast-max `
  --confirm-large-run `
  --skip-existing-ok `
  --run-id action_density_v2_123x90

python scripts/report_range_candidates.py --run-id action_density_v2_123x90
python scripts/report_range_candidate_density.py --run-id action_density_v2_123x90
python scripts/make_pm_review_pack.py --run-id action_density_v2_123x90
python scripts/check_pm_review_pack.py --zip pm_review_pack_action_density_v2_123x90.zip --run-id action_density_v2_123x90
```

## 9. What to upload after run

Upload only:

```text
pm_review_pack_smoke_density_v2_10x30.zip
```

If full run was executed, also upload:

```text
pm_review_pack_action_density_v2_123x90.zip
```

Do not upload full repo, raw data, actionable parquet partitions, `.env`, caches, or any `data/raw` files.

## Definition of done

Sprint 03.4 is done when:

- tests pass;
- ruff passes;
- smoke density report is run-isolated and not stale;
- review pack checker passes;
- compression ratio is computed correctly even with output_layer=actionable;
- at least one calibrated profile is recommended or blockers are explicit;
- if full run executed, p50 <= 50, p90 <= 100, p99 <= 200, compression >= 10, symbols_with_actionable_events >= 50;
- no live/create/close/order code added.
