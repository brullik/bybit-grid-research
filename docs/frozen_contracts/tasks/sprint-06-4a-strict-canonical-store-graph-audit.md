# Sprint 06.4A — strict canonical market-store graph audit

## Scope

This task makes the offline market-store auditor a fail-closed trust boundary for the exact
persisted graph described by canonical import receipts. Only this production file may
change, and it must change:

- `src/bybit_grid/data/market_store/audit.py`.

The task deliberately excludes persisted models and parsers, path grammar, Parquet
reader/writer behavior, public-batch loading, partition planning, transactions, evidence
creation, replay, coverage/resume, DuckDB, seed-pack creation, CLIs, dependencies, and
ordinary project tests. It authorizes no network, credentials, private Bybit API, Telegram,
order, position, wallet, or native-grid mutation.

## Canonical graph

A committed store is valid only when its complete lexical, non-symlink-following tree is
exactly the graph derived from `store_version.json` and its canonical import receipts:

- every receipt is stored at the path derived from its own `run_id` and
  `source_review_pack_sha256`;
- each receipt has exactly its declared chunk directory, `chunk_manifest.json`, and
  `data.parquet` members;
- no receipt may declare the same chunk path more than once;
- each receipt has exactly its content-addressed `review_pack.zip` and
  `evidence_reference.json` members;
- all required ancestor directories exist as real directories;
- no alias receipt, orphan chunk/evidence, extra file, empty directory, symlink, special
  entry, or stale transaction entry is accepted;
- each chunk row's source run and review-pack SHA match the receipt that commits it;
- a version-only store is not a committed store: at least one receipt and one committed
  chunk are required.

The scan must not follow a symlink or read its target. Failures are sorted, unique, and
repeatable. Existing audit counters remain exact for a valid store.

This is a static offline boundary: the caller keeps the selected store root quiescent for
the complete audit call and trusts the filesystem path components above that root.
Concurrent filesystem mutation and untrusted symlink ancestors are outside this one-file
task because the existing chunk reader reopens pathnames rather than caller-owned file
descriptors.

## Compatibility fixture

The accepted fixture is a minimal canonical funding-rate store containing one real chunk,
one canonical receipt, one content-addressed review pack, one matching evidence reference,
and `store_version.json`. Its audit has one chunk, one receipt, one evidence archive, one
evidence reference, no orphans, and one `funding_rate` row.

## Acceptance

The frozen suite contains fourteen material tests covering the accepted minimal graph, receipt
paths with wrong run and wrong source SHA, an alias receipt, a nested extra file, an empty
nested directory, a missing declared chunk member, a nested stale transaction directory, a
special entry, an external-target evidence symlink with an observed no-read guard,
receipt-to-row provenance, a duplicate chunk declaration, a version-only store, and
deterministic failure ordering.

The task base is deterministically RED: only the canonical fixture passes, while thirteen
graph-integrity cases fail on the current auditor. The suite is GREEN only through a change
to the single allowed production file.
