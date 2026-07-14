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
