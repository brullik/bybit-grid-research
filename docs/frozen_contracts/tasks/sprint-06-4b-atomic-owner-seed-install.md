# Sprint 06.4B — atomic owner seed install

## Scope

This task adds the offline, last-mile installation boundary for one already validated,
canonical owner seed review pack. It installs the complete committed market-store graph into
one new owner-controlled runtime root without rebuilding rows, repartitioning chunks, merging
stores, or contacting Bybit.

Only this production file may change, and it must change:

- `src/bybit_grid/data/market_store/evidence.py`.

The task deliberately excludes store models and parsers, canonical serialization, Parquet
schemas and I/O, public-batch import transactions, graph-audit policy, replay,
coverage/resume/gap-repair, DuckDB, package exports, CLIs, dependencies, deployment, service
management, and ordinary project tests. It authorizes no network, credentials, private Bybit
API, Telegram, order, position, wallet, native-grid, withdrawal, or live mutation.

## Public operation and result

`evidence.py` exposes this exact public operation:

```python
install_seed_review_pack(path, destination_store_root)
```

Both arguments must resolve through `os.fspath` to an exact `str`; bytes paths are rejected.
The operation validates and installs exactly one archive and returns the strict
`StoreImportReceipt` parsed from the validated staging graph whose exact bytes are published. Its receipt
identity must equal the archive manifest identity and the single receipt already required by
`check_seed_review_pack`. It does not accept caller-selected resource limits, overwrite flags,
merge modes, recovery modes, or weaker validation options.

The existing `make_seed_review_pack` and `check_seed_review_pack` public behavior remains
compatible. Installation must share the checker's strict validation boundary; it must not
implement a second, weaker archive grammar.

## Absent destination and owner-controlled parent

Installation is allowed only into a new root:

- relative destinations are allowed and are anchored once against the call-entry working
  directory; the raw destination string must be nonempty and have a final lexical component
  other than empty, dot, or dot-dot; after absolute normalization it must not name the
  filesystem root; ancestor dot and dot-dot resolution is accepted only within the trusted
  path-above-parent boundary;
- its immediate parent must already exist and be an owner-controlled directory;
- the parent is opened as a no-follow directory descriptor and its pathname, directory type,
  device, and inode are bound for the call;
- the destination entry must be absent when the call starts and still absent at publication;
- an existing regular file, directory, symlink, FIFO, socket, device, or other entry is rejected;
  a metadata-only no-follow lookup may establish existence and type, but the entry is never
  opened, payload-read, followed, replaced, removed, chmodded, or otherwise mutated;
- a missing parent, symlinked final parent, non-directory parent, unsafe lexical shape, or
  pathname-to-descriptor mismatch is rejected before staging;
- the source archive itself is never moved or deleted.

There is no overwrite, append, merge, repair, or existing-store no-op mode. Repeating a
successful installation against the same destination fails because the root exists. Importing
additional public evidence into an installed store remains the separate, already existing
public-batch transaction boundary and is outside this task.

"Owner-controlled" and quiescence are operational trust assumptions, not implicit UID, GID, or
permission-bit checks. This task binds entry types and filesystem identities exactly as stated;
it does not add a caller-identity authorization policy.

All staging is created as a randomly named sibling of the destination through the already
opened parent directory descriptor. Staging is therefore on the same filesystem as the final
root. Before publication, the staging root and every installed directory have exact mode
`0700`, and every installed regular file has exact mode `0600`, independent of the process
umask. No broader or stricter mode is published.

## Single-descriptor source and strict archive validation

The source archive is required to be a regular, non-symlink entry. It is opened no-follow and
nonblocking, and validation remains bound to that descriptor. Path and descriptor identity
include device, inode, mode, link count, size, modification time, and change time. The full
archive SHA-256 is computed from the descriptor and compared again before publication.

After the outer seed-archive descriptor is accepted, the implementation must not reopen that
outer archive by its mutable pathname and must not use `Path.read_bytes()` or another
whole-archive read for it. Outer metadata, outer member hashes, extraction, and final outer
identity checks all derive from the same descriptor and stream member payloads in bounded
blocks. The already existing graph auditor and nested public-review-pack validator operate on
the extracted store paths under their separately frozen contracts; this task neither changes
nor claims single-descriptor or whole-file-read guarantees for those excluded boundaries.

Before `ZipFile` construction or creation of the sibling staging directory, the installer
checks the physical size and raw end record, including central-directory bounds, member count,
and encoded member-name lengths. Constructing metadata and streaming the descriptor SHA-256
are not trusted ZIP-member payload reads. After `ZipFile` metadata construction but before any
`archive.open(...)` member payload read or staging creation, it checks per-member, total, and
control-member sizes. Together these are the exact frozen outer-archive limits from the strict
portable seed-pack contract:

- physical archive size at most 512 MiB (`536870912` bytes);
- total member count at most 4096, including the two control members;
- uncompressed size of each member at most 128 MiB (`134217728` bytes);
- total uncompressed member size at most 512 MiB (`536870912` bytes);
- each control member at most 4 MiB (`4194304` bytes);
- encoded member-name length at most 1024 bytes;
- central-directory size at most 8 MiB (`8388608` bytes).

The installer then enforces the existing exact stored/no-ZIP64 byte envelope, canonical lexical
member order and metadata, safe POSIX member names, duplicate/case-fold/ancestor collision
rules, canonical manifest, complete member set and hashes, exactly one canonical receipt,
receipt/manifest/storage identity, canonical store audit, and nested public review-pack
validation. For identical immutable archive bytes and otherwise successful filesystem
operations, every archive-semantic rejection produced by `check_seed_review_pack` is also
rejected by the installer with the same stable validation meaning. Destination, staging,
cleanup, and publication failures are installer-specific additions.

The generated `review_pack_manifest.json` and `store_audit.json` are validation controls, not
members of the canonical store. They are not published. The destination graph contains exactly
the archive's manifest members other than `store_audit.json`, with identical regular-file
bytes, and no staging or installer metadata.

These are outer ZIP and extracted-byte bounds. They are not a claim of total process-memory
boundedness for semantic decoding inside the nested public review pack or Parquet readers.
Hardening those already separate production boundaries requires later frozen tasks and is not
silently claimed here.

## Staging validation and atomic publication

Extraction occurs only below the descriptor-bound sibling staging root. Member paths are
constructed from already validated path components, parent directories are created without
following archive-provided links, and files are created exclusively and no-follow. Payloads are
streamed and hashed while written. A short read, write failure, close failure, hash mismatch,
unexpected entry, or filesystem type change fails closed.

Before publication, the installer must:

1. validate the complete extracted graph with `audit_market_store`;
2. compare its fresh canonical audit bytes with the archive audit;
3. parse and validate exactly one canonical receipt and its path;
4. validate the nested public review pack with that receipt's exact run identity;
5. prove that the staging pathname still names the originally opened staging directory;
6. prove that the source descriptor and pathname are still bound and that its full digest is
   unchanged;
7. prove that the destination parent pathname still names the opened parent descriptor; and
8. prove that the final destination entry is still absent.

Successful publication is one same-parent, no-replace directory rename. On the Linux target it
must use a kernel no-replace primitive, such as `renameat2(RENAME_NOREPLACE)`, against the opened
parent descriptor. An unavailable or failed no-replace primitive fails closed; it must not fall
back to `os.replace`, `os.rename`, link/unlink emulation, copy-then-delete, per-member
publication, or another non-atomic substitute. `EEXIST` and `ENOTEMPTY` from the kernel
no-replace primitive are `seed_install_destination_exists`; every other primitive failure is
`seed_install_publish_invalid`. An entry appearing at the destination immediately before the
kernel operation is preserved.

The no-replace rename is the sole commit point and the last fallible operation that may affect
the public result. Source-context exit checks, semantic validation, mode normalization, cleanup
preparation, staging and parent identity checks, and final destination-absence precheck all
complete before it. A successful kernel rename returns the validated receipt; best-effort
descriptor closes after that commit cannot convert success into a reported failure. The direct
sibling staging root is itself renamed, so no task-owned wrapper directory requires fallible
post-commit removal.

Atomicity here means namespace visibility: before the publication operation the destination is
absent, and after success it is the complete validated store root. It does not claim durability
across kernel, filesystem, hardware, or power failure. Crash-consistent fsync policy and stale
sibling recovery are separate deployment concerns.

## Race handling and trust boundary

The source archive and destination parent are owner-controlled and kept quiescent for the
complete call. Path components above the opened parent and source parent are trusted. An
untrusted actor with concurrent mutation authority over those directories is outside this
task's supported operating boundary.

Within that boundary, deterministic pathname-race simulations remain fail-closed:

- regular-file to FIFO or symlink replacement between source `lstat` and open is rejected
  without blocking or reading the replacement target;
- same-size source mutation with restored modification time is detected through change time,
  descriptor identity, and the full digest;
- source pathname rebinding during validation cannot substitute different archive bytes;
- staging-root replacement or rebinding cannot publish unchecked bytes;
- destination-parent pathname replacement cannot redirect publication through a symlink or a
  different directory;
- destination creation immediately before publication cannot be overwritten; and
- cleanup is addressed through the originally opened parent descriptor, not a rebound pathname.

## Failure, cleanup, and stable errors

Before successful publication, every ordinary validation, extraction, audit, identity, resource,
or publication failure leaves the final destination absent and removes the task-owned sibling
staging tree through the original parent descriptor. It never removes an entry it cannot prove
belongs to the current call. A cleanup failure is surfaced as a stable failure and is never
reported as a successful install; the final destination remains absent even if the operating
system prevents removal of a hidden staging artifact.

Existing seed-pack validation errors retain their meanings, including
`unsafe_seed_pack_path`, `seed_zip_limits_invalid`, `seed_zip_metadata_invalid`,
`unsafe_zip_path`, `zip_member_type_invalid`, `zip_member_hash_mismatch`, receipt, manifest,
audit, identity, and nested-evidence errors. New destination and publication failures are
distinguishable as:

- `unsafe_seed_install_destination` for invalid destination shape, parent type, parent binding,
  or unsafe destination resolution;
- `seed_install_destination_exists` when any final destination entry already exists or wins the
  no-replace race;
- `seed_install_temp_unsafe` for exclusive staging creation, open, or binding failure, or when
  the task-owned staging identity later cannot be proved;
- `seed_install_publish_invalid` when no-replace publication is unavailable or otherwise fails;
- `seed_install_cleanup_invalid` when task-owned staging cannot be safely removed.

Native ZIP and filesystem exceptions are normalized to a relevant `MarketStoreError`; raw
platform exceptions and traceback-dependent messages are not the public contract. Error
normalization must not collapse semantic validation failures into a generic success or accept a
pack rejected by the checker.

If cleanup fails while another pre-publication error is active,
`seed_install_cleanup_invalid` is the public error and the original failure is chained as its
cause. `seed_install_temp_unsafe` remains observable only when every task-owned staging entry
was safely removed. A non-task-owned replacement is always preserved.

## Acceptance

The new installer suite contains distinct material tests for the installer-specific behavior
families below. It runs in the same base-isolated harness as the already frozen 82-node strict
portable seed-pack suite. Those existing nodes continue to enforce canonical ZIP grammar,
resource limits, parser errors, make/check compatibility, and the shared extraction/semantic
boundary; the new suite does not duplicate every existing archive mutation solely to recount it.

- canonical make/check/install round trip, typed receipt identity, exact installed graph,
  owner-only modes, and exclusion of both archive control members;
- invalid destination root, dot and dot-dot shapes, missing parent, symlinked parent,
  and existing regular-file, directory, symlink, and FIFO destination classes;
- no reads or mutations through an existing destination symlink or FIFO;
- corrupt outer archive, rehashed semantic tamper, extraction failure, and nested-evidence
  rejection without publication or task-owned staging leakage;
- source symlink/FIFO rejection, nonblocking pre-open FIFO rebinding, same-size in-place
  mutation, pathname rebinding, one outer source descriptor, and streaming outer payload I/O;
- staging creation in the opened destination parent, same-filesystem single-publication
  behavior, staging identity replacement, destination-parent swap, and immediate destination
  creation at the no-replace boundary;
- absence of overwrite-capable fallback, per-member publication, merge, append, repair, or
  existing-store no-op behavior;
- extraction, semantic-validation, and publication failures, no final partial root, cleanup of
  the moved task-owned stage, and preservation of replacement and other non-task-owned entries.

The base-controlled no-live scanner and unchanged protected-path/dependency gates continue to
enforce the absence of network, credentials, private API, Telegram, trading, wallet,
native-grid, withdrawal, and live behavior.

The new frozen suite contains exactly 39 material nodes: 38 installer-specific RED nodes and
one already-green checker-compatibility node. Against the unmodified task base it produces
exactly 38 failures and 1 pass on both Python 3.12 and Python 3.14. An isolated feasibility
implementation changing only the one allowed production file produces exactly 39 passes on
both interpreters. Together with the preceding 82-node strict portable seed-pack suite, the
feasibility harness produces exactly 121 passes on each interpreter.

The mandatory RED probe must reproduce the exact 38-failure/1-pass active profile on both
interpreters and must be closed unmerged before implementation begins.
