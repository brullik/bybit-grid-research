# Sprint 06.4G — strict offline historical evidence archive

## Scope and authority

This task adds one deterministic, in-memory ZIP32/STORED packing boundary after completed 06.4F.
The sole implementation path is:

- `src/bybit_grid/data/public_batch/historical_evidence_archive.py`.

No package export, ordinary test, dependency, configuration, control-plane, or other production
path may change in the implementation PR. `bybit_grid.data.public_batch.__all__` remains
byte-for-byte unchanged and does not re-export this module.

The operation consumes one exact, caller-supplied 06.4F `HistoricalEvidenceLayout` and returns
one exact in-memory archive plus commitments. It accepts no path, filename, directory, file,
stream, writer, callback, compression choice, cap, clock, environment, process, client, session,
transport, request, credential, secret, retry, or live authority. It performs no filesystem,
network, DNS, HTTP, environment, process, thread, retry, sleep, randomness, or wall-clock work.

The only newly authorized act is packing the already admitted 06.4F members into the frozen
in-memory byte grammar below. This task does not authorize publication, arbitrary archive
ingestion, archive extraction, filesystem persistence, store projection or installation,
public transport, credentials, private API, Telegram, ordinary orders, native-grid mutation,
positions, wallets, withdrawals, or live execution. It proves no source authenticity, account
or region eligibility, Bybit product availability, funding or historical coverage, parameter
fitness, native equivalence, or profitability.

## Exact public API

The complete non-underscore surface and exact `__all__` are:

```python
(
    "HistoricalEvidenceArchiveError",
    "HistoricalEvidenceArchive",
    "build_historical_evidence_archive",
)
```

`HistoricalEvidenceArchiveError` is a `ValueError`. The sole operation is:

```python
build_historical_evidence_archive(*, layout)
```

`layout` is required and keyword-only. No positional, variadic, optional, path, archive-name,
stream, callback, writer, compression, cap, clock, client, or environment parameter exists.
There is no public parser, reader, verifier, opener, extractor, writer, installer, publisher, or
arbitrary archive re-admission operation.

The implementation may use only deterministic in-process primitives. It imports no filesystem,
network, clock, concurrency, randomness, subprocess, HTTP, environment, or timezone module.
Production imports neither `io` nor `zipfile`: the ZIP grammar is emitted manually so
CPython-version changes in `zipfile.writestr` flags cannot alter the result and no stream API is
introduced. Frozen tests may use `zipfile` only as an independent compatibility reader.

## Exact 06.4F input and independent revalidation

- `layout` has exact type `HistoricalEvidenceLayout`; mappings, duck types, subclasses, and
  unrelated values are `layout_not_exact_model`.
- The module captures the original unbound 06.4F complete validator, canonical serializer, and
  evidence-layout builder when imported. Rebinding their public source names later grants no
  authority.
- It invokes the captured complete validator, rebuilds the layout from the retained exact
  transcript, and serializes both supplied and recomputed layouts with the captured canonical
  serializer.
- A 06.4F rejection or exact-class structural `AttributeError`/`TypeError` becomes
  `HistoricalEvidenceArchiveError("layout_revalidation_failed")` and retains the exact source
  exception as `__cause__`.
- The recomputed value must have exact type `HistoricalEvidenceLayout`; otherwise
  `layout_recomputation_invalid`.
- Both canonical values must be exact `bytes` and byte-identical; otherwise
  `layout_canonical_bytes_invalid` or `layout_canonical_mismatch`.
- Exact tuple/string/bytes atoms, names, and payloads must equal the recomputed layout;
  otherwise `layout_material_invalid`.
- Full nested layout revalidation precedes cap, archive field, commitment, metadata, flag, and
  envelope approval.

On success `archive.layout is layout`. The exact 06.4F commitments are retained without
reinterpretation: `plan_sha256`, `transcript_sha256`, `manifest_sha256`, and
`member_sequence_sha256`. `layout_sha256` is SHA-256 of exact 06.4F canonical layout bytes.

## Fixed bounded input

The packer accepts at most 258 members and an exact total logical member payload of
268,435,456 bytes (256 MiB). It rejects before archive allocation with
`archive_member_limit_exceeded` or `archive_payload_limit_exceeded`.

The 06.4F names have lengths 13 for `manifest.json` and 15 for every other member. For `N`
members the exact ZIP overhead is:

```text
22 + sum(30 + name_length + 46 + name_length)
```

At the maximum 258 members this is exactly 27,366 bytes. Therefore the exact maximum archive
size is 268,462,822 bytes. This is below ZIP32's unsigned 32-bit size/offset boundary and bounds
single-result memory amplification. The downstream total-payload cap is numerically aligned
with 06.4E's inherited 256 MiB **raw-body** cap; because 06.4F also adds transcript and manifest
bytes, some otherwise-valid 06.4F layouts deliberately do not fit 06.4G. Callers must split
capture windows before packing. This task never claims that every valid 06.4F layout fits. No
caller may raise any cap. Oversize archive/member conditions are
`archive_size_limit_exceeded` and `archive_member_size_limit_exceeded`.

The builder uses one final byte join over retained immutable payloads. Self-validation uses one
`memoryview`; it does not create a bytes copy of every archived member.

## Exact ZIP32/STORED grammar

The archive begins at byte zero with one local record per exact 06.4F member, in exact 06.4F
order. It then contains one central-directory record per member in the same order and exactly
one EOCD record ending at the final byte. There is no prefix, trailer, gap, directory entry,
duplicate/dropped/reordered name, data descriptor, encryption, compression, ZIP64 structure,
multi-disk structure, extra field, per-member comment, or archive comment.

All names are the exact ASCII 06.4F logical names. Every payload is byte-identical to its exact
06.4F member. Duplicate payload bytes, SHA-256 values, or CRC32 values remain distinct members
at their distinct names; no deduplication occurs.

Each local header uses little-endian `<IHHHHHIIIHH` and freezes:

```text
signature                 0x04034b50
version needed            20
general-purpose flags     0x0000
compression method        0 (STORED)
DOS time                  0
DOS date                  0x0021 (1980-01-01)
CRC32                     exact unsigned CRC32 of payload
compressed size           exact payload size
uncompressed size         exact payload size
filename length           exact ASCII-name length
extra length              0
```

The exact name and exact payload immediately follow each local header.

Each central header uses little-endian `<IHHHHHHIIIHHHHHII` and freezes:

```text
signature                 0x02014b50
version made by           0x0314 (Unix creator, version 20)
version needed            20
flags/method/time/date     exactly the local values
CRC32 and both sizes      exactly the local/payload values
filename length           exact ASCII-name length
extra/comment lengths     0
disk start                0
internal attributes       0
external attributes       0x81800000
local-header offset       exact offset of matching local record
```

`0x81800000 >> 16 == 0o100600`: an exact Unix regular file with mode `0600`; entries are not
directories, symlinks, or executable files. The exact name immediately follows each central
header.

The EOCD uses little-endian `<IHHHHIIH` and freezes signature `0x06054b50`, both disk numbers
zero, both entry counts equal to the exact member count, exact central size and offset, and zero
comment length. It ends the archive exactly.

The private raw-envelope verifier walks from byte zero without signature search. It checks
every fixed header field, name, size, exact member byte view, independently recomputed archived
CRC32, local offset, central size/offset, EOCD, and final length. CRC is only an envelope fact;
exact payload equality and 06.4F cryptographic roots remain the content authority.

## Factory-only immutable result

`HistoricalEvidenceArchive` is a frozen, slotted, hashable, `init=False` dataclass without an
instance `__dict__`. Direct construction and `dataclasses.replace` raise
`archive_factory_only`. A private builder requires exactly every field and invokes a captured
complete archive validator; later rebinding of public `__post_init__` does not weaken builder
or canonical validation.

Fields occur in this exact order:

1. `schema`;
2. `plan_sha256`, `transcript_sha256`, `manifest_sha256`, `layout_sha256`,
   `member_sequence_sha256`, `archive_sha256`;
3. `member_count`, `payload_byte_count`, `archive_byte_count`;
4. `max_archive_members`, `max_archive_payload_bytes`, `max_archive_bytes`;
5. `zip_version_made_by`, `zip_version_needed`, `zip_compression_method`,
   `zip_general_purpose_flags`, `zip_dos_time`, `zip_dos_date`, `zip_unix_mode`;
6. the eight exact-true narrow evidence/authority flags;
7. the exact-false guardrails;
8. retained `layout`, retained `archive_bytes`.

The schema is exactly `bybit_public_historical_evidence_archive_v1`.

The exact-true fields are:

```text
layout_revalidated_bool
archive_member_sequence_exact_bool
archive_member_payloads_exact_bool
zip32_envelope_verified_bool
zip_stored_only_bool
fixed_metadata_verified_bool
archive_sha256_verified_bool
in_memory_archive_authorized_bool
```

They prove only successful deterministic in-memory packing and verification.

The exact-false fields, in field order, are:

```text
filesystem_authorized_bool
persistence_authorized_bool
store_projection_authorized_bool
store_install_authorized_bool
network_authorized_bool
transport_authorized_bool
credentials_allowed_bool
private_api_allowed_bool
telegram_authorized_bool
ordinary_order_authorized_bool
native_grid_mutation_authorized_bool
wallet_authorized_bool
position_mutation_authorized_bool
live_execution_authorized_bool
source_authenticity_proven_bool
account_eligibility_proven_bool
account_region_eligibility_proven_bool
bybit_product_availability_proven_bool
publication_authorized_bool
arbitrary_archive_ingestion_authorized_bool
archive_extraction_authorized_bool
withdrawal_authorized_bool
funding_coverage_proven_bool
historical_market_data_coverage_proven_bool
parameter_selection_authorized_bool
sufficient_for_parameter_selection_bool
native_equivalence_proven_bool
profitability_proven_bool
```

Every flag has exact built-in `bool` type. Every count and ZIP-policy atom has exact built-in
`int` type; booleans are rejected. Every commitment has exact built-in `str` type and 64
lowercase hexadecimal characters; string subclasses are rejected.

`archive_sha256` is SHA-256 of the exact archive bytes and is deliberately outside the archive,
avoiding self-commitment recursion. `canonical_json_bytes()` reruns full nested-layout and raw
archive validation and serializes every non-retained field as compact sorted-key ASCII JSON
with one final LF. It excludes `layout` and `archive_bytes`. `sha256()` hashes these canonical
metadata bytes.

## Stable failure groups and precedence

Stable groups are:

```text
layout_not_exact_model
layout_revalidation_failed
layout_recomputation_invalid
layout_canonical_bytes_invalid
layout_canonical_mismatch
layout_material_invalid
archive_member_limit_exceeded
archive_payload_limit_exceeded
archive_size_limit_exceeded
archive_member_size_limit_exceeded
archive_schema_invalid
archive_counts_invalid
archive_fixed_limits_invalid
archive_zip_metadata_invalid
archive_commitments_invalid
archive_bytes_invalid
archive_envelope_invalid
archive_evidence_flags_invalid
archive_guardrails_invalid
archive_factory_only
archive_builder_fields_invalid
archive_canonical_value_invalid
archive_canonical_json_invalid
```

Precedence is: exact layout type and complete 06.4F revalidation; bounded payload approval;
archive schema and root commitments; exact archive-bytes type; counts and fixed caps; ZIP policy; archive hash; raw
envelope and member bytes; narrow true flags; false guardrails. A nested malformed layout plus
malformed archive fields therefore fails as layout revalidation.

The operation returns one complete result or raises. No partial bytes, continuation, path,
stream, writer, extraction result, or best-effort value is returned.

## Mandatory lifecycle evidence

Before implementation, both the missing module and a comment-only `probe/` module must make
every new frozen test node fail in the call phase with exactly:

```text
historical_evidence_archive_unavailable
```

The mandatory probe is closed without merge. The implementation then makes the complete frozen
suite pass without changing this contract, frozen tests, package exports, dependencies, or any
path other than the sole implementation path. No-live scanning, numeric-environment checks,
ordinary tests, compile checks, Ruff, protected-path checks, scope checks, and exact-diff checks
remain mandatory.
