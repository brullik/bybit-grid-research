# Sprint 06.4A — context-free Decimal identity

## Scope

This task fixes the logical-row identity boundary used by canonical JSONL hashes and chunk
paths. Only this production file may change, and it must change:

- `src/bybit_grid/data/market_store/canonical.py`.

The task deliberately excludes Arrow schema and representability policy, persisted models
and parsers, path grammar, Parquet reader/writer behavior, public-batch loading, partition
planning, transactions, audit, replay, coverage/resume, DuckDB, seed packs, CLIs,
dependencies, and ordinary project tests. It authorizes no network, credentials, private
Bybit API, Telegram, order, position, wallet, or native-grid mutation.

## Decimal text identity

`decimal_to_text` accepts only an exact finite `Decimal`. Its result is derived from the
stored Decimal value without applying the process's ambient decimal precision, rounding,
traps, or flags.

- Positive and negative `decimal128(38,18)` boundaries retain all significant digits.
- Adjacent scale-18 values remain different in Decimal text, canonical JSONL, logical
  SHA-256, and the logical-hash-derived chunk path.
- Precision values 6, 28, and 80 produce identical canonical bytes and hashes.
- Enabled `Inexact` and `Rounded` traps do not fire, and canonicalization does not mutate
  their context flags.
- Fractional trailing zeroes are removed, exponent notation is expanded to plain text, and
  every signed zero is `0`.
- Non-Decimal and non-finite inputs continue to fail closed with
  `MarketStoreError("decimal_invalid")`.

## Compatibility fixtures

For the frozen funding-rate row at `1704067200000`, the exact value
`12345678901234567890.123456789012345678` has logical row SHA-256
`86182e168b79a2e2e5ea4e6947843772bfe49854fb17d9ac49416ce471ffa15f`.
The adjacent value ending in `679` has logical row SHA-256
`b6b02796d36a913149efba34b508b6f232b157215afde5b4f3f92bbafb3302d6`.
Their chunk path suffixes are respectively `86182e168b79a2e2` and
`b6b02796d36a9131`.

## Acceptance

The frozen suite contains eight material tests covering exact positive and negative
boundaries, adjacent-value separation, a hard-coded canonical JSONL/SHA fixture, precision
and trap independence, production integration through `build_planned_chunk`, retained
plain-text normalization, and fail-closed invalid inputs.

The task base is deterministically RED: both adjacent values currently collapse to logical
SHA-256 `d6227f52abf5a6a5af0c992fb094d122a74d187fa49346c0cb4045a608cb5244`
and the same chunk path because `Decimal.normalize()` applies ambient context. The suite is
GREEN only through a change to the single allowed production file.
