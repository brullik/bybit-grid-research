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

Every ZIP member is explicitly emitted in lexical order as a Unix-created, stored regular
file with mode `0600`, the ordinary non-ZIP64 version, and a fixed timestamp. ZIP64 is neither
needed nor accepted under the resource caps. Stored members make compressed and uncompressed
sizes identical, eliminate zlib-version variance, and permit exact raw-byte envelope coverage;
any deflated member, including one with an unmanifested deflate tail, is rejected from metadata
before payload reads. Archive prefixes and trailers, archive comments,
member comments, all member extra fields, reordered entries, changed timestamps, alternate
compression, platform, version or mode metadata, duplicate names, case-fold aliases,
file/descendant collisions, absolute or non-normalized paths, controls, backslashes, colons,
symlinks, directories, and other special entry types are rejected before payload trust.
Local file records must be contiguous from byte zero and followed contiguously by the central
directory and exactly covered end-of-central-directory record; orphan gaps and uncovered
prefix or trailer bytes are invalid. Builder output is byte-identical across wall-clock
changes.

## Resource envelope

Both builder preflight and checker metadata validation enforce these inclusive limits before
creating a publication temporary file or opening any archive payload:

- physical archive size: at most 512 MiB (`536870912` bytes);
- total ZIP member count, including both control members: at most 4096;
- uncompressed size of each member: at most 128 MiB (`134217728` bytes);
- total uncompressed size of all members: at most 512 MiB (`536870912` bytes);
- uncompressed size of each control member, `review_pack_manifest.json` and
  `store_audit.json`: at most 4 MiB (`4194304` bytes);
- UTF-8 encoded member-name length: at most 1024 bytes;
- central-directory size: at most 8 MiB (`8388608` bytes).

Any breach is `seed_zip_limits_invalid`. The exact defaults are frozen; a caller cannot
select weaker limits. Physical archive and raw end-of-central-directory bounds, including
central-directory size, member count, and encoded member-name lengths, are checked before
`ZipFile` construction. Metadata preflight is not a substitute for streaming and hashing
payloads after the envelope is accepted.

These limits bound parsing and extraction of the outer owner-generated seed ZIP; they are
not a total process-memory guarantee for semantic decoding inside the nested public review
pack or Parquet payloads. The existing public-batch validator and Parquet reader retain
their own behavior. Bounding their nested decompression and decoded-row expansion requires
separate frozen tasks in those production boundaries and is not silently claimed by this
one-file contract.

## Fail-closed filesystem and semantic validation

- The builder first requires a successful canonical store audit and exactly one receipt.
  It inventories without following symlinks, rejects special entries, and streams each
  regular file through a no-follow descriptor while checking its identity and digest.
- A destination that is lexically or physically inside the source store, including through
  a symlinked parent, is rejected before writes. Its owner-controlled parent directory must
  already exist, and its filename must name a new or regular-file entry. Filesystem root,
  dot, dot-dot, an existing directory, a missing parent, or another invalid destination
  shape is `unsafe_seed_destination` before store audit or temporary preparation. An
  existing destination symlink or FIFO is rejected at the same early boundary without
  reading or mutating its outside target.
  Publication uses a checked temporary file,
  binds validation and publication to the same no-follow descriptor identity, revalidates
  both that identity and destination containment immediately before publication, preserves
  an existing destination on failure, removes the temporary artifact through the original
  directory identity, and atomically replaces the destination only after its own checker
  succeeds. The public return value preserves the caller's lexical destination, including a
  relative `Path`. Replacing the validated temporary pathname or swapping the destination
  parent to a symlink cannot publish unchecked bytes or write into the source store.
- The checker rejects a non-regular or symlinked outer archive, binds its descriptor and
  pathname identity including change time for the full validation, validates all ZIP
  metadata and the strict canonical manifest, streams and hashes members into an isolated
  temporary store, requires exactly one receipt, re-runs the canonical store-graph audit,
  compares the embedded audit with the fresh result, and calls the existing nested public
  review-pack validator with the receipt run identity. Same-size in-place mutation with
  restored modification time, pathname rebinding during validation, and replacement with a
  FIFO between the checker's `lstat` and `open` are all `unsafe_seed_pack_path`; the last
  case must be rejected without blocking.
- Native ZIP and filesystem failures are normalized to stable `MarketStoreError` codes.
  Manifest schema, storage schema, run identity, source SHA, member-set, member-hash,
  receipt-count, receipt-identity, store-audit, nested-evidence, destination-containment,
  and source-inventory failures remain distinguishable.

The source store and the owner-controlled destination directory are kept quiescent for the
complete build call, and path components above the selected source root are trusted. The
descriptor-bound, no-follow publication and immediate identity/containment revalidation
close deterministic pathname replacement and parent-swap races, but an untrusted actor
with concurrent write authority over the destination directory remains outside this
one-file trust boundary. Hardening the already frozen graph auditor's own metadata-read
race would require a separate `audit.py` task and is outside this one-file scope; the seed
pack is nevertheless published only after safe extraction and a fresh semantic re-audit.

## Acceptance

The frozen suite contains 82 material tests covering canonical round-trip identity, exact
manifest and hash binding, deterministic regular ZIP metadata, eight nonportable path
classes, duplicate and three non-regular ZIP member classes, missing/extra/hash-mismatched
payloads, strict and canonical manifest parsing, three hidden ZIP metadata channels, eight
noncanonical ZIP envelope and member-metadata forms including ZIP64, orphan local-record
gaps, exact resource defaults, seven checker limit breaches before payload reads, builder
resource preflight before temp preparation, six manifest identity aliases, case-fold and
parent/child collisions, exactly one receipt, rehashed store, receipt, audit, and
nested-evidence tampering, nested validator binding and normalization, corrupt and
symlinked outer packs, FIFO pre-open rebinding, in-place mutation and pathname rebind
detection, lexical and
symlink-resolved destination containment, four early invalid-destination shapes,
missing-parent rejection, and existing destination symlink/FIFO rejection,
checked-temp replacement and destination-parent swap rejection, symlink/FIFO source
rejection without target reads, streaming source and ZIP I/O, source-descriptor close-error
normalization, ZIP-output write-error attribution, relative-destination return
compatibility, cleanup and destination preservation, and wall-clock-independent bytes.

On the unmodified task base, both Python 3.12 and Python 3.14 produce exactly 75 failures
and 7 passes. An isolated one-file feasibility implementation must produce exactly 82
passes on both versions. The suite is GREEN only through a change to the single allowed
production file.
