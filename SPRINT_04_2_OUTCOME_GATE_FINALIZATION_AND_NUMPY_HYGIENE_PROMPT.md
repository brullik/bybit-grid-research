# Sprint 04.2 — Outcome Gate Finalization + NumPy Hygiene + v2 Review Pack

PM decision: Sprint 04.1 fixed the writer dedupe bug and added funding diagnostics, but Gate 4 is not closed until a full v2 outcome run has a report + valid review pack and dependency hygiene is clean.

## Non-negotiable safety rules

- Do not implement live trading.
- Do not implement Bybit create/close/order endpoints.
- Do not implement Telegram/live signals.
- Do not optimize parameters or choose a strategy.
- Sprint 04.2 is only outcome gate finalization and engineering hygiene.

## Current evidence

Accepted:

- `pytest -q` passed: 112 passed.
- `ruff check .` passed.
- `repair_outcome_run.py` on v1 scanned 343 partitions, 241155 rows, duplicates_removed=0.
- smoke v2 with `--funding-debug` produced funding diagnostics and review pack OK.
- full v2 build produced 241155 rows, unique IDs, no duplicate composite rows, future_data_complete_rate around 0.99679, and funding_rows_total=717840.

Still missing for Gate 4:

- `report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v2`
- `make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v2`
- `check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v2.zip --outcome-run-id outcomes_action_density_v2_123x90_v2`
- proof that CLI JSON output is parseable.
- dependency hygiene around NumPy.

## 1. Remove any local NumPy shim

If the repository contains a local directory or file named:

```text
numpy/
numpy.py
```

remove it.

Why: a local shim named `numpy` can shadow real NumPy because pytest config includes the repo root in `pythonpath`. It may make tests pass while silently disabling the real fast core on the owner machine.

Required actions:

- Add real `numpy>=1.26` to `pyproject.toml` dependencies.
- Do not vendor a fake `numpy` package.
- In runtime code, if NumPy is unavailable, fail clearly for `--core numpy_fast`:

```text
numpy_fast requires real numpy. Install dependencies with: python -m pip install -e .[dev]
```

- Only `--core python_reference` may run without NumPy.
- Add a test that verifies imported NumPy is not from the project root fake shim.

## 2. Make all outcome CLI summaries valid JSON or strict key=value

Commands that print JSON must use:

```python
print(json.dumps(summary, indent=2, ensure_ascii=False))
```

Add tests or smoke helpers so this works:

```powershell
python scripts/report_candidate_outcomes.py --outcome-run-id <id> > tmp_outcome_report.json
python -m json.tool tmp_outcome_report.json > NUL
```

If progress lines are mixed with JSON, use one of:

- `--json-summary-path <path>` for machine-readable summary;
- print progress to stderr and final JSON to stdout;
- key=value only, no partial JSON.

## 3. Finalize full v2 outcome review pack

Run on the owner machine:

```powershell
python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v2.zip --outcome-run-id outcomes_action_density_v2_123x90_v2
```

The checker must fail if:

- outcome_rows_total <= 0;
- unique_outcome_id_count != outcome_rows_total;
- duplicate_range_action_event_horizon_grid_sl_rows != 0;
- funding diagnostics fields are missing;
- funding_rows_total == 0 without a clear reason;
- outcome parquet partitions are included in the review pack;
- secrets/caches/raw data are included.

## 4. Funding diagnostics acceptance

The final full v2 report must include:

- funding_rows_total;
- funding_files_found_count;
- funding_symbols_with_files count;
- funding_rows_scanned_total;
- funding_rows_joined_total;
- funding_join_coverage_rate;
- funding_missing_symbols;
- funding_source_status_counts;
- funding_zero_reason.

Gate 4 can pass if some symbols are missing funding files, as long as this is explicitly reported and the outcome rows remain valid. Missing funding symbols become a known data-quality caveat for Sprint 05.

## 5. Required tests

Add or keep tests for:

- writer input dedupe;
- writer append dedupe;
- no duplicate outcome_id after repair;
- no duplicate composite key;
- funding status: ok, missing_file, empty_file, no_overlap;
- review pack rejects zero-row or missing-funding-diagnostics packs;
- no local numpy shim shadows real NumPy;
- create/close/order/Telegram remain absent.

## 6. Acceptance commands

Owner runs:

```powershell
python -m pytest -q
ruff check .
python scripts/repair_outcome_run.py --outcome-run-id outcomes_action_density_v2_123x90_v2 --dedupe --rebuild-summary
python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/make_outcome_review_pack.py --outcome-run-id outcomes_action_density_v2_123x90_v2
python scripts/check_outcome_review_pack.py --zip pm_review_pack_outcomes_action_density_v2_123x90_v2.zip --outcome-run-id outcomes_action_density_v2_123x90_v2
```

Also run JSON validation if report script prints JSON:

```powershell
python scripts/report_candidate_outcomes.py --outcome-run-id outcomes_action_density_v2_123x90_v2 > tmp_outcome_report.json
python -m json.tool tmp_outcome_report.json > NUL
Remove-Item tmp_outcome_report.json
```

## 7. What to send to PM

Text:

- commit hash;
- files changed;
- pytest output;
- ruff output;
- repair output for v2;
- report_candidate_outcomes summary for v2;
- review pack checker output;
- JSON validation output;
- confirmation that no local `numpy/` shim exists.

Files:

- `pm_review_pack_outcomes_action_density_v2_123x90_v2.zip` only.

Do not upload:

- full repository archive;
- data/raw;
- outcome parquet partitions;
- range partitions;
- `.env`;
- caches.
