# Sprint 06.4A — strict chunk path and I/O boundaries

## Scope

This task hardens the portable path, filesystem containment, and direct Parquet chunk
reader/writer boundary of the canonical market store.

Only these production files may change, and all three must change:

- `src/bybit_grid/data/market_store/paths.py`;
- `src/bybit_grid/data/market_store/writer.py`;
- `src/bybit_grid/data/market_store/reader.py`.

The task deliberately excludes persisted models and parsers, Arrow schemas and decimal
policy, public-batch loading, partition planning, receipts and store-graph uniqueness,
transactions, audit, replay, coverage/resume, DuckDB, seed packs, CLIs, dependencies, and
ordinary project tests. It authorizes no network, credentials, private Bybit API, Telegram,
order, position, wallet, or native-grid mutation.

## Typed path boundary

- `safe_symbol` accepts only an exact plain string that fully matches two through 32 ASCII
  uppercase letters or digits. A prefix match, trailing newline, string subclass, separator,
  punctuation, or non-ASCII lookalike raises `MarketStoreError("unsafe_symbol")`.
- `safe_posix_relative_text` accepts an exact plain normalized relative POSIX string. In
  addition to absolute paths, backslashes, colons, and empty, `.` or `..` components, it
  rejects C0 controls, DEL/C1 controls, and lone surrogate code points with
  `<name>_invalid`.
- Dataset conversion at `rel_chunk_path`, `build_planned_chunk`, `write_chunk_atomic`, and
  `read_dataset` accepts only an exact `MarketDatasetKind` or exact plain string and is
  fail-closed. Unknown values, string subclasses, and arbitrary objects, including objects
  with hostile protocol methods, raise
  `MarketStoreError("dataset_invalid")` and never leak enum `TypeError` or `ValueError`.
- Path timestamps are exact nonnegative signed-int64 values. Time-series bounds remain
  minute-aligned, ordered, and within one UTC calendar month. Native datetime conversion
  failures are normalized to `min_ms_invalid` or `max_ms_invalid`; an out-of-range snapshot
  timestamp uses `snapshot_server_time_ms_invalid`.
- A valid trade-kline chunk path has the exact portable layout
  `datasets/trade_kline_1m/symbol=<SYMBOL>/year=<YYYY>/month=<MM>/`
  `chunk=<MIN>-<MAX>-<LOGICAL_HASH_PREFIX>`.

## Filesystem containment and entry types

`ensure_safe_store_path(root, path)` performs lexical containment without resolving through
symlinks. The target must be the root or be below it after absolute lexical normalization.
Every existing component inspected from the root chain through the target must be a real
directory, except that the final target may be a real regular file. Symlinks, special files,
lexical escapes, invalid native paths, and unsafe root types raise
`MarketStoreError("unsafe_store_entry")`.

The check is a deterministic preflight boundary; concurrent hostile filesystem replacement
and OS-level transactional guarantees are outside this task.

- `write_chunk_atomic` rejects a symlinked store root, `datasets` ancestor, or staging
  ancestor before creating `.building` or publishing bytes. A rejected path must not mutate
  the symlink target outside the store.
- `read_and_validate_chunk` and existing-store reuse reject a symlinked store root or any
  intermediate ancestor with `unsafe_store_entry`.
- A chunk directory contains exactly `chunk_manifest.json` and `data.parquet`, both real
  regular files. A symlinked chunk member raises `chunk_dir_contract_invalid` before its
  bytes are read. Writer idempotent-reuse validation enforces the same member contract as
  the reader.

## Chunk I/O and stable failures

- Manifest bytes, Parquet SHA-256, exact Arrow schema, primary-key order and uniqueness,
  manifest row bounds, logical row hash, and re-derived relative path remain mandatory.
- A hash-consistent but non-Parquet or otherwise undecodable Parquet member never leaks a
  PyArrow exception. Reader and writer reuse raise
  `MarketStoreError("parquet_read_invalid")`.
- Native filesystem rejection of an invalid store path, including an overlong component, is
  normalized to `unsafe_store_entry` before any partial chunk is published.
- `early`, `mid`, and `late` injected writer failures preserve their existing stable error
  codes, publish no dataset chunk, and leave no entry below `.building`.
- Writing the same logical rows in a different input order is deterministic. The second
  write validates and reuses the identical immutable chunk; a read with the expected
  manifest returns rows in primary-key order.

## Acceptance

The frozen suite contains 40 material tests covering exact symbol/path grammar, dataset and
timestamp native-error normalization, exact UTC partition layout, lexical escape rejection,
root and intermediate symlink escapes, symlinked chunk members in both reader and writer,
existing-store planned reuse, PyArrow decode failure normalization, invalid native store
paths, all three injected cleanup points, and deterministic write/read/idempotent reuse.

The tests are RED on the unmodified task base and GREEN only through changes to the three
allowed production files.
