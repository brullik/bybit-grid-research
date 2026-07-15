# Sprint 06.4A — strict persisted models and parsers

## Scope

This task hardens the four metadata objects persisted by the canonical market store:

- `StoreVersion`;
- `StoreEvidenceReference`;
- `StoreChunkManifest`;
- `StoreImportReceipt`.

Only `src/bybit_grid/data/market_store/models.py` and
`src/bybit_grid/data/market_store/parsing.py` may change. Both files must change.

The task deliberately excludes seed-review-pack semantics, Parquet schemas, partition and
filesystem-layout semantics, chunk reader/writer behavior, receipt/store-graph uniqueness,
transactions, audit, replay, DuckDB, CLIs, dependencies, and ordinary project tests. Those
belong to later isolated tasks.

## Persisted model contract

All four objects remain frozen dataclasses. Persisted fields accept exact primitive and
container types: a `bool` is not an `int`, an enum is not a persisted string, and subclasses
of `str` are not exact strings.

- `storage_schema_version` is the exact plain string
  `bybit_public_parquet_store_v1`.
- `dataset` is an exact plain string naming one of the four `MarketDatasetKind` values.
  Violations raise `MarketStoreError("dataset_invalid")` and never leak an enum
  `ValueError`.
- A manifest `relative_path` is a normalized relative POSIX path below `datasets/`.
  Absolute paths, backslashes, colons, control characters, and empty, `.` or `..` path
  components are invalid.
- `run_id` is a portable single path component: nonempty ASCII letters, digits, `.`, `_`
  and `-` only; it must start with a letter or digit and must not contain `..`.
- SHA-256 fields are exact lowercase hexadecimal strings of length 64.
- `row_count` is an exact positive integer.
- `primary_key_columns` is a nonempty exact tuple of unique, nonempty exact strings.
- `min_key` and `max_key` are nonempty exact tuples with the same arity as
  `primary_key_columns`. Key atoms are exact nonnegative integers or nonempty exact strings;
  corresponding positions in the two bounds have the same exact type. Shape/type failures
  use `min_key_invalid` or `max_key_invalid` before ordering is compared. A valid reversed
  pair uses `key_order_invalid`.
- A receipt `chunks` field is a nonempty exact tuple containing only exact
  `StoreChunkManifest` objects.

This task does not require the primary-key column names to match a particular dataset and
does not validate partition meaning encoded in `relative_path`.

## Parser boundary

The four public `parse_*_bytes` functions are fail-closed and never leak `TypeError`, native
`ValueError`, `UnicodeError`, `JSONDecodeError`, or enum-conversion errors.

- Input must be exact `bytes` containing one UTF-8 JSON object without a BOM.
- Missing or unknown top-level keys, a non-object root, invalid UTF-8/BOM, wrong container
  shape, and malformed nested receipt manifests raise `<context>_schema_invalid`.
- Duplicate JSON keys raise `<context>:json_duplicate_key`.
- JSON float tokens raise `<context>:json_float_token`.
- `NaN`, `Infinity`, and `-Infinity` raise `<context>:json_non_finite_token`.
- A structurally valid document with a semantic field violation preserves the model's stable
  `MarketStoreError` code.
- A semantically valid document whose bytes are not canonical raises
  `<context>_canonical_mismatch`.

Canonical market-store JSON is UTF-8 with sorted keys, compact separators, no BOM, and
exactly one final LF. The acceptance fixtures are independent hard-coded bytes; the similarly
named public-batch serializer is not part of this contract.

Contexts are `store_version`, `chunk_manifest`, `evidence_reference`, and `receipt`.

## Acceptance

The frozen tests cover canonical round trips for all four exact types, dataclass immutability,
strict JSON token handling, UTF-8/BOM and key-set failures, exact persisted types, safe path
components, key shape/type/order, safe run IDs including lone-surrogate rejection, nonempty
receipts, nested receipt shape failures, and canonical-byte mismatch errors.

The tests must be RED on the unmodified task base and GREEN only through changes to the two
allowed production files.

