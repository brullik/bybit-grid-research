# Bybit public Parquet store contract v1

Schema version: `bybit_public_parquet_store_v1`.

Datasets are `instrument_snapshot`, `trade_kline_1m`, `mark_kline_1m`, and `funding_rate`. Times are non-null `int64` milliseconds, booleans are Arrow `bool`, text/provenance/enums are non-null UTF-8 strings, and market numerics are `decimal128(38, 18)`. Common provenance columns are `source_run_id`, `source_review_pack_sha256`, `source_plan_id`, `source_name`, and `storage_schema_version`.

Physical layout follows the sprint layout under `store_version.json`, `evidence/sha256=<review_pack_sha256>/`, immutable `datasets/<dataset>/.../chunk=.../{data.parquet,chunk_manifest.json}`, `imports/run_id=<RUN_ID>/source_sha256=<PACK_SHA>/import_receipt.json`, and `.building/` staging.

Logical rows are projected per dataset, sorted by primary key, rendered as compact sorted-key UTF-8 JSONL with a final newline, and hashed with SHA-256. Decimals are plain normalized semantic strings, trailing fractional zeroes are removed, and `-0` becomes `0`.

Parquet file bytes are not claimed to be canonical across PyArrow/platform versions. Canonical identity is the logical row hash plus strict schema, manifest and semantic read-back.

Publication validates input before writing, writes under `.building`, writes Parquet and manifest, reads back and revalidates, atomically renames chunk directories, archives source evidence, and writes the import receipt last. Re-import is idempotent only for byte/manifest/semantic identical chunks. Conflicting primary keys fail closed with no silent choice.

Coverage uses exact inclusive one-minute grids and bounded missing windows. Funding scans report observed ranges only and never prove global funding completeness. Instrument snapshots are explicit; point-in-time metadata completeness is not inferred.

DuckDB views are read-only in-memory query helpers over committed Parquet using Hive partition discovery and `union_by_name=true`; DuckDB is not canonical storage.

Portable seed-store review packs contain safe POSIX-relative committed store members plus audits, guardrail reports, and a manifest hash for every member. Absolute paths, `..`, backslashes, drive letters, duplicate names, symlinks, non-regular entries, missing members, unexpected members, and semantic tampering are rejected.

Frozen guardrails remain false for historical coverage, funding coverage, delisted completeness, point-in-time metadata completeness, risk budget, native equivalence, parameter selection, live authorization, and live execution. Only bulk-download-engineering and resume/gap-repair-engineering sufficiency may be true for a successful seed import.

## Sprint 06.4A.2 executable lifecycle addendum

The store lifecycle is offline and fail-closed. Import reads the review-pack bytes exactly once, hashes those bytes, validates the public-batch semantic reconstruction, keeps the immutable source bytes in `ValidatedPublicBatchEvidence`, and archives those same bytes under `evidence/sha256=<source_sha256>/review_pack.zip`. Import uses receipt-last publication: chunks and evidence are validated before the import receipt is committed, and an existing receipt is strict-parsed back into typed `StoreImportReceipt` and `StoreChunkManifest` tuple models before it is returned as a no-op.

Dataset rows are validated against the single Arrow schema registry before staging. Unknown fields fail before `.building` publication. Decimal values must be `Decimal`, finite, exactly representable at decimal128(38,18), and are checked with an explicit `localcontext()` using traps for inexact or rounded quantization. The inclusive bounds `99999999999999999999.999999999999999999` and `-99999999999999999999.999999999999999999` are representable; NaN, Infinity, floats, and values requiring rounding are rejected.

Partition planning is deterministic: instrument snapshots partition by `snapshot_server_time_ms`; trade, mark, and funding rows partition by `symbol/year/month` from UTC timestamps. A candidate time-series chunk may contain exactly one symbol and one UTC month, and an instrument chunk may contain exactly one snapshot timestamp. Chunk manifests record dataset, relative path, primary-key columns, row count, min/max keys, Parquet SHA-256, and logical row SHA-256. Audit and read-back revalidate regular directory entries, manifest bytes, Arrow schema, logical rows, key order, uniqueness, and chunk hashes.

Invalid stores return a typed audit with `ok=false` and stable failure strings. Empty stores, missing committed chunks, unexpected root entries, symlinks, and stale `.building` entries are failures. Chunk-only temporary stores used by low-level writer tests can still be semantically audited at the chunk level; full imported stores additionally include receipts and evidence references.

Replay slices require explicit symbol, aligned start/end timestamps, and snapshot timestamp arguments. Trade and mark candles must be complete, ascending, duplicate-free, and timestamp-equal. Funding scans report the observed range only and never claim global completeness. Resume/repair planning emits inclusive windows capped at the requested row limit.

DuckDB usage is in-memory only. Views are created from validated store-owned Parquet paths with Hive partitioning and `union_by_name=true`; no persistent database file, extension action, or network action is used. Smoke helpers close the connection on completion.

Portable seed-store packs derive their member set from validated store members and generated audits, reject unsafe ZIP names, duplicate entries, traversal, absolute paths, and hash mismatches, and re-run the standalone checker before atomic destination replacement.

Parquet file bytes are not claimed to be canonical across PyArrow/platform versions.
Canonical identity is the logical row hash plus strict schema, manifest and semantic read-back.
