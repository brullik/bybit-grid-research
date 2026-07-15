# Sprint 06.4B — strict portable owner seed pack

## Scope

This task turns the offline owner seed review pack into a deterministic, portable,
fail-closed trust boundary for moving one already committed canonical market store to an
owner-controlled runtime. Only this production file may change, and it must change:

- `src/bybit_grid/data/market_store/evidence.py`.

The task deliberately excludes store models and parsers, canonical serialization, path and
Parquet I/O, import transactions, graph-audit policy, public-batch evidence semantics,
replay, coverage/resume, DuckDB, CLIs, dependencies, deployment, and ordinary project
tests. It authorizes no network, credentials, private Bybit API, Telegram, order, position,
wallet, native-grid, or live mutation.

## Canonical archive and identity

The archive schema is exactly `bybit_public_parquet_seed_review_pack_v1`. Its members are
the complete lexical file graph rooted directly at the canonical store root, one generated
`store_audit.json`, and one self-excluded `review_pack_manifest.json`. No synthetic `store/`
prefix is added.

The canonical manifest has exactly five keys: `members`, `run_id`, `schema`,
`source_review_pack_sha256`, and `storage_schema_version`. The member map is nonempty,
contains the SHA-256 of every archive payload except the manifest itself, and contains no
missing or extra path. The run, source-review-pack SHA, and storage schema are bound to the
archive's single strict import receipt and to its content-addressed nested public review
pack.

Every ZIP member is explicitly emitted as a sorted regular file with a fixed timestamp.
Archive comments, member comments, member extra fields, duplicate names, case-fold aliases,
file/descendant collisions, absolute or non-normalized paths, controls, backslashes,
colons, symlinks, directories, and other special entry types are rejected before payload
trust. Builder output is byte-identical across wall-clock changes.

## Fail-closed filesystem and semantic validation

- The builder first requires a successful canonical store audit and exactly one receipt.
  It inventories without following symlinks, rejects special entries, and streams each
  regular file through a no-follow descriptor while checking its identity and digest.
- A destination that is lexically or physically inside the source store, including through
  a symlinked parent, is rejected before writes. Publication uses a checked temporary file,
  preserves an existing destination on failure, removes the temporary artifact, and
  atomically replaces the destination only after its own checker succeeds.
- The checker rejects a non-regular or symlinked outer archive, validates all ZIP metadata
  and the strict canonical manifest, streams and hashes members into an isolated temporary
  store, requires exactly one receipt, re-runs the canonical store-graph audit, compares the
  embedded audit with the fresh result, and calls the existing nested public review-pack
  validator with the receipt run identity.
- Native ZIP and filesystem failures are normalized to stable `MarketStoreError` codes.
  Manifest schema, storage schema, run identity, source SHA, member-set, member-hash,
  receipt-count, receipt-identity, store-audit, nested-evidence, destination-containment,
  and source-inventory failures remain distinguishable.

The source store is kept quiescent for the complete build call, and path components above
the selected source root are trusted. Hardening the already frozen graph auditor's own
metadata-read race would require a separate `audit.py` task and is outside this one-file
scope; the seed pack is nevertheless published only after safe extraction and a fresh
semantic re-audit.

## Acceptance

The frozen suite contains 49 material tests covering canonical round-trip identity, exact
manifest and hash binding, deterministic regular ZIP metadata, eight nonportable path
classes, duplicate and three non-regular ZIP member classes, missing/extra/hash-mismatched
payloads, strict and canonical manifest parsing, three hidden ZIP metadata channels, six
manifest identity aliases, case-fold and parent/child collisions, exactly one receipt,
rehashed store, receipt, audit, and nested-evidence tampering, nested validator binding and
normalization, corrupt and symlinked outer packs, lexical and symlink-resolved destination
containment, symlink/FIFO source rejection without target reads, streaming source and ZIP
I/O, cleanup and destination preservation, and wall-clock-independent bytes.

On the unmodified task base, both Python 3.12 and Python 3.14 produce exactly 43 failures
and 6 passes. An isolated one-file feasibility implementation produces exactly 49 passes
on both versions. The suite is GREEN only through a change to the single allowed production
file.
