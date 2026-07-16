# Sprint 06.4F — strict offline historical evidence layout

## Scope and authority

This task adds one pure, deterministic, in-memory evidence-layout boundary after the completed
06.4C historical request planner, 06.4D response-admission boundary, and 06.4E transcript
reconciliation boundary. The sole implementation path is:

- `src/bybit_grid/data/public_batch/historical_evidence.py`.

No other production, package-export, ordinary-test, dependency, configuration, control-plane,
or frozen-contract path may change in the implementation PR. In particular,
`bybit_grid.data.public_batch.__all__` remains byte-for-byte unchanged and does not re-export
this module.

The operation consumes one caller-supplied in-memory `HistoricalResponseTranscript` and returns
logical member names, exact member bytes, and cryptographic commitments only. It accepts no
path, directory, archive, writer, callback, client, session, transport, method, host, URL,
header, cookie, credential, secret, timeout, retry, proxy, environment, process, thread, sleep,
random source, locale, timezone database, or clock. It performs no network, DNS, HTTP,
filesystem, archive, persistence, environment, process, thread, retry, sleep, or wall-clock
operation. A logical member name is data, never filesystem or archive authority.

This task authorizes no transport, credential access, private API, Telegram, order, position,
wallet, native-grid mutation, withdrawal, live capture, archive creation, filesystem write,
store projection, store installation, deployment, response-authenticity claim, account or
account-region eligibility claim, Bybit product-availability claim, funding-completeness claim,
historical-coverage claim, parameter selection, profitability claim, native-equivalence claim,
or ordinary-order mutation. It does not establish that bytes originated from Bybit. All such
boundaries remain default-deny.

## Exact public API

The complete non-underscore module surface and exact `__all__` tuple are:

```python
(
    "HistoricalEvidenceError",
    "HistoricalEvidenceLayout",
    "build_historical_evidence_layout",
)
```

`HistoricalEvidenceError` is a `ValueError`. The sole operation is:

```python
build_historical_evidence_layout(*, transcript)
```

`transcript` is required and keyword-only. There are no positional, variadic, defaulted, path,
name, cap, callback, transport, persistence, archive, clock, or environment parameters.

The source imports none of `asyncio`, `datetime`, `http`, `httpx`, `io`, `locale`,
`multiprocessing`, `os`, `pathlib`, `random`, `requests`, `secrets`, `shutil`, `socket`, `ssl`,
`subprocess`, `tarfile`, `tempfile`, `threading`, `time`, `urllib`, `uuid`, `zipfile`, or
`zoneinfo`. It imports none of the legacy `recording`, `capture`, `pagination`, or
`reconstruct` modules. Imports use private aliases. Module assignments perform no calls.

## Exact 06.4E input and independent revalidation

- `transcript` has exact type `HistoricalResponseTranscript`; mappings, duck types, subclasses,
  and unrelated values are `transcript_not_exact_model`.
- The boundary captures the exact 06.4E unbound invariant validator, canonical serializer, and
  reconciliation operation when this module imports. Later rebinding of source module names or
  public transcript methods is not authority.
- It calls the captured unbound 06.4E invariant validator on the supplied object.
- It independently calls the captured 06.4E reconciliation operation with the retained exact
  `plan`, `receipts`, and `raw_body_bytes`. This repeats plan/request validation, receipt
  validation, raw-body admission, canonical receipt comparison, cross-page aggregation,
  digests, row identity, limits, and every 06.4E guardrail.
- A 06.4E rejection becomes
  `HistoricalEvidenceError("transcript_revalidation_failed")`, retaining the exact
  `HistoricalTranscriptError` as `__cause__`.
- An uninitialized or structurally forged exact-class transcript whose retained-slot access
  raises `AttributeError` or `TypeError` also becomes
  `HistoricalEvidenceError("transcript_revalidation_failed")`, retaining that exact structural
  exception as `__cause__`. It never escapes the evidence boundary as an ungrouped exception.
- The recomputed object has exact type `HistoricalResponseTranscript`; another type is
  `transcript_recomputation_invalid`.
- Complete supplied and recomputed canonical transcript bytes are produced with the captured
  exact 06.4E serializer and must match byte-for-byte. A mismatch is
  `transcript_canonical_mismatch`. Caller-rebound `canonical_json_bytes()` and `sha256()` methods
  are ignored.
- On success, `layout.transcript is transcript`.

Validation of the exact transcript precedes approval of any layout field. A malformed retained
transcript and malformed member commitment therefore fails as transcript revalidation, not as
member approval.

## Exact logical member sequence

The layout member sequence is fixed and caller-independent:

```text
manifest.json
transcript.json
raw/000000.json
raw/000001.json
...
```

The raw member index is zero-based, exactly six ASCII decimal digits, and follows the exact
06.4E `raw_body_bytes` tuple order. With the inherited private 06.4E page limit, the maximum
layout member count is the exact literal 258: manifest, transcript, and at most 256 raw pages.
The layout accepts no caller-selected name, prefix, extension, directory, or ordering rule.

Every name is an exact built-in `str`, ASCII, unique, relative, contains no backslash or `..`,
and matches one fixed literal or `raw/[0-9]{6}.json`. Exact type and tuple length are checked
before equality, hashing, set construction, or regex work, so a hostile `str` subclass cannot
run overloaded comparison as validation authority.

`member_bytes` is an exact tuple of exact `bytes`:

```python
(manifest_bytes, transcript_canonical_bytes, *transcript.raw_body_bytes)
```

Every raw member is the exact retained source bytes object by identity, not a copy. Duplicate
raw pages and duplicate SHA-256 values are valid and remain distinct indexed members. No hash
uniqueness, content deduplication, compression, encoding, parsing, or archive normalization is
performed. Raw bodies are included without being written.

## Exact manifest and commitments

`manifest.json` is compact, sorted-key, ASCII JSON with exactly one final LF. Its exact logical
value is:

```json
{
  "payload_member_count": "exact nonnegative integer",
  "payload_members": [
    {
      "byte_count": "exact nonnegative integer",
      "name": "transcript.json or raw/NNNNNN.json",
      "sha256": "64 lowercase hexadecimal characters"
    }
  ],
  "schema": "bybit_public_historical_evidence_manifest_v1",
  "transcript_sha256": "64 lowercase hexadecimal characters"
}
```

The ordered payload descriptors cover `transcript.json` and every raw member. The manifest
deliberately excludes itself, its own byte count, its own hash, and any layout hash, preventing
a recursive self-commitment. `manifest_self_excluded_bool` records only that narrow fact.

The layout commits every member, including the manifest, through exact tuples:

- `member_names`;
- `member_byte_counts`;
- `member_sha256s`.

For each index, the byte count is `len(member_bytes[index])` and the SHA is
`sha256(member_bytes[index]).hexdigest()`. `manifest_sha256` is the first member SHA;
`transcript_sha256` is the independently computed SHA of exact 06.4E canonical transcript
bytes; `plan_sha256` equals the revalidated transcript plan commitment.

`member_sequence_sha256` is SHA-256 of compact, sorted-key, ASCII JSON plus one LF for the exact
ordered tuple of objects:

```json
{"byte_count":0,"name":"logical-name","sha256":"lowercase-sha256"}
```

The sequence commitment therefore binds name, content length, content hash, order, duplicate
members, and manifest position.

## Factory-only immutable layout

`HistoricalEvidenceLayout` is a frozen, slotted, hashable dataclass with `init=False`, no
instance `__dict__`, and exact factory-only construction. Direct construction and
`dataclasses.replace` raise `layout_factory_only`. A private builder sets every field and runs
complete invariant validation. The module privately captures that complete layout invariant
validator. Later rebinding of `HistoricalEvidenceLayout.__post_init__` is not validation
authority: both the private `_build_layout` path and `canonical_json_bytes()` call the captured
private validator and still reject every malformed field.

The schema is exactly:

```text
bybit_public_historical_evidence_layout_v1
```

Fields occur in this exact order:

1. `schema`, `plan_sha256`, `transcript_sha256`, `manifest_sha256`;
2. `member_count`, `raw_member_count`, `total_member_byte_count`, `max_layout_members`;
3. `member_names`, `member_byte_counts`, `member_sha256s`, `member_sequence_sha256`;
4. the seven exact-true narrow evidence flags;
5. the exact-false authority, authenticity, eligibility, coverage, and selection guardrails;
6. retained `transcript`, retained `member_bytes`.

The exact-true fields are:

```text
transcript_revalidated_bool
manifest_payload_committed_bool
manifest_self_excluded_bool
member_commitments_verified_bool
member_sequence_exact_bool
member_names_safe_bool
raw_body_identity_retained_bool
```

They prove only deterministic in-memory revalidation and commitment facts.

The exact-false fields, in exact order, are:

```text
network_authorized_bool
transport_authorized_bool
filesystem_authorized_bool
archive_authorized_bool
persistence_authorized_bool
store_projection_authorized_bool
store_install_authorized_bool
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
funding_coverage_proven_bool
historical_market_data_coverage_proven_bool
parameter_selection_authorized_bool
sufficient_for_parameter_selection_bool
native_equivalence_proven_bool
```

Every flag has exact built-in `bool` type; integer aliases are invalid.

`canonical_json_bytes()` reruns complete transcript revalidation, transcript recomputation,
canonical comparison, manifest derivation, member validation, identity validation, commitment
validation, and flag validation. It serializes every non-retained field using compact,
sorted-key, ASCII JSON with one final LF. It omits `transcript` and `member_bytes`, so raw bodies
are never embedded or copied, while their exact names, counts, SHA values, root commitments,
order, and guardrails remain bound. `sha256()` hashes those canonical layout bytes.

## Validation groups and fail-closed behavior

Stable error groups are:

```text
transcript_not_exact_model
transcript_revalidation_failed
transcript_recomputation_invalid
transcript_canonical_bytes_invalid
transcript_canonical_mismatch
layout_schema_invalid
layout_counts_invalid
layout_member_names_invalid
layout_member_bytes_invalid
layout_raw_body_identity_invalid
layout_member_commitments_invalid
layout_root_commitments_invalid
layout_evidence_flags_invalid
layout_guardrails_invalid
layout_factory_only
layout_builder_fields_invalid
```

No invalid member, digest, flag, or later field can authorize partial output. The operation
returns one complete validated layout or raises. It never returns a path, archive, stream,
writer, partial layout, continuation, or best-effort result.

## Mandatory lifecycle evidence

The frozen acceptance module contains unparameterized behavior tests. Before implementation,
the missing module and a comment-only `probe/` implementation must make every new node fail in
the call phase with the exact sentinel:

```text
historical_evidence_layout_unavailable
```

The mandatory probe is closed without merge. The implementation must then make the complete
frozen suite pass without changing this contract, the frozen tests, package exports, or any
path other than the sole implementation path. Ordinary tests, no-live scanning, numeric
environment checks, compile checks, Ruff, and diff checks remain mandatory.
