# Sprint 01.6 — Polars partitioning + sample data report hotfix

## PM decision

Sprint 01.5 is accepted as a code-correctness hotfix, but Gate 1 is still blocked by a runtime error during sample data download.

Public smoke has passed on the owner's Windows machine:

```text
ok instruments=716 trading=716 tickers=722
```

The remaining blocker is:

```text
TypeError: 'Expr' object is not an instance of 'str'
while processing 'by'
```

It happens in `src/bybit_grid/data/klines.py` when calling Polars `DataFrame.partition_by()` with expressions:

```python
pl.col("open_time_utc").dt.year().alias("year")
pl.col("open_time_utc").dt.month().alias("month")
```

The same pattern must be checked and fixed everywhere, not only at the crashing line.

## Scope

This is a narrow hotfix. Do not start research, backtest, Telegram, execution, strategy logic or grid create/close work.

Allowed changes:

- fix partitioned Parquet writing for klines;
- fix partitioned Parquet writing for mark-price klines;
- fix partitioned Parquet writing for funding;
- align sample download start/end timestamps to closed 1m candles;
- make sample data report include row counts, gap counts, duplicate counts and bad OHLC counts;
- add regression tests that would fail on the current Polars `partition_by(Expr)` bug.

Forbidden changes:

- no live trading;
- no create/close implementation;
- no strategy/research implementation;
- no Telegram implementation;
- no private validate unless explicitly run by the owner after public data works.

## Required fixes

### 1. Fix `partition_by(Expr)` in kline saving

In `src/bybit_grid/data/klines.py`, replace this pattern:

```python
for part in df.partition_by(
    [
        pl.col("open_time_utc").dt.year().alias("year"),
        pl.col("open_time_utc").dt.month().alias("month"),
    ],
    as_dict=False,
):
```

with an approach that first materializes helper columns and then partitions by column names:

```python
partitioned = df.with_columns(
    pl.col("open_time_utc").dt.year().alias("_partition_year"),
    pl.col("open_time_utc").dt.month().alias("_partition_month"),
)

for part in partitioned.partition_by(
    ["_partition_year", "_partition_month"],
    as_dict=False,
    maintain_order=True,
):
    clean_part = part.drop(["_partition_year", "_partition_month"])
    write_parquet_merge(
        kline_partition_path(
            client.settings.data_dir,
            dataset,
            symbol,
            int(clean_part["open_time_ms"][0]),
        ),
        clean_part,
        ["symbol", "open_time_ms"],
    )
```

Prefer extracting this to a helper function, for example:

```python
def _write_monthly_kline_partitions(df, client, dataset, symbol) -> None:
    ...
```

### 2. Fix the same bug in mark-price klines

In `src/bybit_grid/data/mark_klines.py`, do the same materialized-column fix.

Mark-price klines must keep:

```python
source = "mark-price-kline"
volume = None
turover = None
```

Note: fix the typo above if present in code/comments: `turnover`, not `turover`.

### 3. Fix the same bug in funding partition writing

In `src/bybit_grid/data/funding.py`, remove any `partition_by(pl.col(...))` or `partition_by(expr.map_elements(...))` pattern.

Use a materialized year column:

```python
partitioned = df.with_columns(
    pl.from_epoch("funding_rate_timestamp_ms", time_unit="ms")
    .dt.year()
    .alias("_partition_year")
)

for part in partitioned.partition_by(["_partition_year"], as_dict=False, maintain_order=True):
    clean_part = part.drop("_partition_year")
    write_parquet_merge(
        funding_partition_path(
            client.settings.data_dir,
            symbol,
            int(clean_part["funding_rate_timestamp_ms"][0]),
        ),
        clean_part,
        ["symbol", "funding_rate_timestamp_ms"],
    )
```

### 4. Align sample downloader time boundaries

In `scripts/download_sample_data.py`, do not use raw `time.time() * 1000` with random milliseconds.

Use closed 1m candles:

```python
ONE_MINUTE_MS = 60_000
end = (int(time.time() * 1000) // ONE_MINUTE_MS) * ONE_MINUTE_MS - ONE_MINUTE_MS
start = end - args.days * 24 * 60 * ONE_MINUTE_MS + ONE_MINUTE_MS
```

This avoids false boundary gaps caused by non-minute-aligned start/end values.

### 5. Save quality report with boundary gaps

`save_gap_report()` currently calls `detect_1m_gaps(df)` without expected boundaries, so start/end boundary gaps are not detected during sample runs.

Change signature to:

```python
def save_gap_report(
    data_dir,
    df: pl.DataFrame,
    expected_start_ms: int | None = None,
    expected_end_ms: int | None = None,
) -> pl.DataFrame:
    report = detect_1m_gaps(df, expected_start_ms, expected_end_ms)
    ...
```

In `scripts/download_sample_data.py`, call:

```python
gaps = save_gap_report(settings.data_dir, kline_df, start, end)
quality = build_quality_report(kline_df, start, end)
```

The Sprint report must include at least:

```text
symbols
requested_days
kline_rows
mark_kline_rows
funding_rows
gap_count
duplicate_count
bad_ohlc_count
output_paths
```

### 6. Add regression tests

Add tests that fail against the current bug and pass after the fix:

1. `download_kline_range` writes a Parquet partition without `partition_by(Expr)` error.
2. `download_mark_kline_range` writes a Parquet partition without `partition_by(Expr)` error.
3. `download_funding_history` writes a Parquet partition without `partition_by(Expr)` error.
4. `save_gap_report(..., expected_start_ms, expected_end_ms)` includes boundary gaps.
5. `download_sample_data.py` time-boundary helper returns minute-aligned timestamps.

Mock Bybit API responses; do not call the network in tests.

## Commands to run

```bash
python -m pytest
ruff check .
python scripts/validate_sample_grid.py --dry-run --symbol BTCUSDT
python scripts/smoke_public_api.py
python scripts/download_sample_data.py --symbols BTCUSDT ETHUSDT --days 7
```

Do not run real validate yet. Do not implement create/close.

## Acceptance criteria

Gate 1 can continue only if:

```text
✅ python -m pytest passes
✅ ruff check . passes
✅ validate_sample_grid --dry-run does not call network
✅ smoke_public_api works on owner's Windows network
✅ download_sample_data completes for BTCUSDT/ETHUSDT --days 7
✅ klines parquet files created
✅ mark_klines parquet files created
✅ funding parquet files created or clean no-data handled
✅ gap report created with start/internal/end support
✅ duplicate and bad OHLC counts included in sprint report
✅ no secrets/signatures in reports
✅ create/close still NotImplementedError
```

## Expected reply after completion

Return:

```text
- commit hash
- files changed
- pytest output
- ruff output
- validate dry-run output
- smoke_public_api output
- download_sample_data output
- reports/sprint_01_api_report.md summary
```
