# Sprint 06.4E — strict offline historical transcript reconciliation

## Scope and authority

This task adds one pure, deterministic, in-memory reconciliation boundary after the completed
06.4C historical request planner and 06.4D page-response admission boundary. The sole
implementation path is:

- `src/bybit_grid/data/public_batch/historical_transcript.py`.

No other production, package-export, ordinary-test, dependency, configuration, control-plane,
or frozen-contract path may change in the implementation PR. In particular,
`bybit_grid.data.public_batch.__all__` remains byte-for-byte unchanged and does not re-export
this module.

The operation consumes caller-supplied in-memory models and bytes only. It accepts no client,
session, callback, transport, method, host, base URL, URL, header collection, cookie,
credential, API key, secret, timeout, retry, proxy, filesystem path, environment, process,
thread, sleep, random source, locale, timezone database, or clock. It performs no network, DNS,
HTTP, filesystem, persistence, environment, process, thread, retry, sleep, or wall-clock
operation. It imports none of the legacy `recording`, `capture`, `pagination`, `reconstruct`, or
`evidence` modules.

This task authorizes no public transport, credential access, private API, Telegram, order,
position, wallet, native-grid mutation, withdrawal, live capture, deployment, persistence,
funding-completeness claim, historical-coverage claim, parameter selection, profitability
claim, native-equivalence claim, or ordinary-order mutation. It only proves that one exact
ordered 06.4C plan graph, one exact ordered tuple of already admitted 06.4D receipts, and one
exact ordered tuple of retained raw response bytes reconcile under a second independent
in-memory admission pass. Transport, persistence, store installation, historical coverage,
research selection, and staged execution remain later default-deny boundaries.

## Exact public API and fixed policy

The complete non-underscore module surface and exact `__all__` tuple are:

```python
(
    "HistoricalResponseTranscript",
    "HistoricalTranscriptError",
    "MAX_HISTORICAL_TRANSCRIPT_PAGES",
    "MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES",
    "reconcile_historical_response_transcript",
)
```

The fixed public constants are exact integers:

```python
MAX_HISTORICAL_TRANSCRIPT_PAGES = 256
MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES = 268_435_456
```

The limits are policy, not caller defaults. Private literal checks and receipt fields remain
256 pages and 268,435,456 aggregate raw-body bytes after public-constant rebinding. There is no
caller-selectable page, body, row, depth, token, retry, continuation, or best-effort cap.

`HistoricalTranscriptError` is a `ValueError`. The sole operation is:

```python
reconcile_historical_response_transcript(
    *,
    plan,
    receipts,
    raw_body_bytes,
)
```

All three arguments are required and keyword-only; there is no positional, variadic, or
defaulted argument.

The source imports none of `asyncio`, `datetime`, `http`, `httpx`, `locale`,
`multiprocessing`, `os`, `pathlib`, `random`, `requests`, `secrets`, `socket`, `ssl`,
`subprocess`, `threading`, `time`, `urllib`, `uuid`, or `zoneinfo`. It also imports no module
named `recording`, `capture`, `pagination`, `reconstruct`, or `evidence`. Imports use private
aliases. There is no call-valued module assignment or executable module expression other than
an optional module docstring; class/function definitions and pure literals are the complete
import-time behavior.

## Exact input identity and plan revalidation

- `plan` has exact type `HistoricalCapturePlan`; mappings, duck types, subclasses, and unrelated
  values are `plan_not_exact_model`.
- Every object in `plan.requests` has exact type `HistoricalRequestSpec`. Each request and the
  enclosing plan are revalidated from current fields with the original exact class invariant
  functions. `object.__setattr__` mutation is `plan_invariants_invalid`.
- Plan and request canonical bytes are recomputed locally from dataclass fields with the exact
  06.4C compact, sorted-key, ASCII JSON grammar and exactly one final LF. Rebound plan/request
  `canonical_json_bytes` or `sha256` methods are ignored.
- `receipts` is an exact tuple, otherwise `receipts_not_exact_tuple`.
- `raw_body_bytes` is an exact tuple, otherwise `raw_body_bytes_not_exact_tuple`.
- Both tuple lengths equal `len(plan.requests)` exactly. Missing, extra, or unequal tuple
  lengths are `transcript_length_mismatch`; no partial transcript or continuation is returned.
- The page count is at most the private literal 256, otherwise
  `transcript_page_limit_exceeded`.
- Every supplied receipt has exact type `HistoricalResponseReceipt`; subclasses or unrelated
  objects are `receipt_not_exact_model`.
- Every raw page has exact type `bytes`; strings, mutable buffers, and memory views are
  `raw_body_not_exact_bytes`.
- Aggregate raw byte length is at most the private literal 268,435,456, otherwise
  `transcript_raw_body_limit_exceeded`.

Every receipt is revalidated from current retained fields by the exact 06.4D class invariant
function before any raw body is parsed. A tampered or malformed receipt is
`receipt_invariants_invalid`.

The supplied receipt at tuple index `i` is bound to the exact plan request at the same index.
The following must all equal independently recomputed values: plan SHA, request SHA, sequence
ID, dataset, endpoint, category, symbol, request start/end, request limit, and request target
row count. Any mismatch, including receipt permutation, is
`receipt_request_binding_invalid`.

The exact caller tuple objects are retained on success: `transcript.plan is plan`,
`transcript.receipts is receipts`, and `transcript.raw_body_bytes is raw_body_bytes`.

## Mandatory raw-body re-admission

For each `(request, receipt, raw_body)` triple in exact plan order, the boundary calls the exact
06.4D `accept_historical_response_page` operation with:

```text
plan=the exact retained plan
request=the exact plan.requests member
http_status=receipt.http_status
content_type=receipt.content_type
raw_body_bytes=the exact retained page bytes
```

No receipt digest or typed row is trusted as a substitute for this second parse. Therefore all
06.4D byte caps, scanner limits, strict UTF-8/JSON grammar, duplicate-key/float/nonfinite/int64
rules, root/result identity, kline coverage/order, funding saturation/range/uniqueness, typed
model, and receipt checks run again.

If 06.4D rejects a page, reconciliation raises
`HistoricalTranscriptError("raw_body_reverification_failed")` and retains the exact
`HistoricalResponseError` as `__cause__`. Pages are processed in plan order; the first invalid
page wins. No later page or aggregate is evaluated as approval.

Each recomputed receipt must have exact type `HistoricalResponseReceipt`. Supplied and
recomputed receipts are then compared by independently serialized complete canonical receipt
bytes—not by object equality and not through caller-rebound receipt serialization/hash methods.
An otherwise valid body whose raw bytes differ, including whitespace-only change, produces a
different body commitment and is `receipt_canonical_mismatch`. An unexpected return type is
`recomputed_receipt_invalid`.

This is deterministic evidence reconciliation, not response authenticity. It does not prove
that bytes originated from Bybit, that a transport actually ran, or that an account/region is
eligible.

## Cross-page aggregation

After every page is independently re-admitted and exactly matches its supplied receipt, receipt
rows are grouped by dataset:

```text
trade_kline_1m
mark_kline_1m
funding_rate
```

Within each dataset, a timestamp may occur at most once across all pages. A duplicate is
`cross_page_timestamp_duplicate`; nothing is deduplicated or selected. Rows are then retained
in exact ascending timestamp order. Trade and mark request graphs are already oldest-to-newest;
funding requests are newest-to-oldest, so funding aggregation deliberately canonicalizes the
accepted row union ascending. Failure to obtain exact canonical order is
`canonical_dataset_row_order_invalid`.

The transcript retains exact tuples of `BybitTradeKline1m`, `BybitMarkKline1m`, and
`BybitFundingRate`. Every aggregate row is the exact object by identity from its retained page
receipt; equal clones, lists, and tuple-like aliases are invalid. It does not merge with
previously observed/store rows. Exact requested kline pages and unsaturated funding pages
therefore do not prove complete stored history.
Empty funding pages and a transcript with no requested trade/mark pages are valid; their row
tuples are empty, endpoints are `None`, and timestamp/row digests bind canonical `[]\n`.

## Factory-only immutable transcript model

`HistoricalResponseTranscript` is a frozen, slotted, hashable dataclass with no instance
`__dict__` and `init=False`. Direct construction and `dataclasses.replace` raise
`transcript_factory_only`. A private builder sets every field and runs complete invariant
validation. `canonical_json_bytes()` and `sha256()` rerun that validation, including plan,
receipt, raw-body re-admission, canonical receipt comparison, aggregate rows, digests, limits,
and guardrails. Deliberate mutation of any retained component therefore fails closed.

Every nonempty first/last timestamp endpoint has exact non-boolean `int` type and equals the
recomputed endpoint. An empty dataset endpoint is the exact `None` singleton. Boolean and
numerically equal `Decimal` aliases are `transcript_timestamp_endpoints_invalid`.

The schema is the exact literal:

```text
bybit_public_historical_response_transcript_v1
```

Fields occur in this exact order:

1. `schema`, `plan_sha256`;
2. `request_count`, `receipt_count`, `raw_body_page_count`,
   `total_raw_body_byte_count`;
3. `max_transcript_pages`, `max_transcript_raw_body_bytes`;
4. `request_sha256s`, `raw_body_sha256s`, `receipt_sha256s`;
5. `request_sequence_sha256`, `raw_body_sequence_sha256`,
   `receipt_sequence_sha256`;
6. `trade_row_count`, `mark_row_count`, `funding_row_count`;
7. `trade_first_timestamp_ms`, `trade_last_timestamp_ms`,
   `mark_first_timestamp_ms`, `mark_last_timestamp_ms`,
   `funding_first_timestamp_ms`, `funding_last_timestamp_ms`;
8. `trade_timestamps_sha256`, `mark_timestamps_sha256`,
   `funding_timestamps_sha256`;
9. `trade_rows_sha256`, `mark_rows_sha256`, `funding_rows_sha256`;
10. `request_graph_reconciled_bool`, `raw_bodies_reverified_bool`,
    `receipts_canonical_match_bool`, `sequence_exact_bool`,
    `cross_page_timestamps_unique_bool`, `canonical_dataset_row_order_bool`;
11. fixed-false authority/coverage flags; and
12. retained verification fields `plan`, `receipts`, `raw_body_bytes`, `trade_rows`,
    `mark_rows`, `funding_rows`.

The fixed-false fields, in exact order, are:

```text
network_authorized_bool
filesystem_authorized_bool
persistence_authorized_bool
credentials_allowed_bool
private_api_allowed_bool
telegram_authorized_bool
ordinary_order_authorized_bool
native_grid_mutation_authorized_bool
wallet_authorized_bool
position_mutation_authorized_bool
live_execution_authorized_bool
funding_coverage_proven_bool
historical_market_data_coverage_proven_bool
parameter_selection_authorized_bool
sufficient_for_parameter_selection_bool
native_equivalence_proven_bool
```

The six narrow reconciliation facts are exact `True`; they state only that the supplied graph
was reconciled in this call. Every authority, coverage, persistence, and selection field is the
exact `False` singleton. A boolean subclass does not exist, and integers 0/1 are not accepted
as booleans.

## Canonical commitments

Every individual SHA has exact `str` type and lowercase 64-hex SHA-256 grammar. Each SHA
sequence has exact `tuple` type and contains only exact `str` members; tuple and string
subclasses are rejected:

- `plan_sha256` hashes independently reconstructed exact 06.4C plan canonical bytes;
- `request_sha256s` contains one independent request digest in exact plan order;
- `raw_body_sha256s` hashes each exact retained raw byte string in page order;
- `receipt_sha256s` hashes independently serialized complete 06.4D receipt bytes in page
  order.

Each sequence SHA hashes compact sorted-key JSON of the corresponding ordered SHA list plus one
LF. This binds order as well as membership. Dataset timestamp SHA values hash the canonical
ascending integer array plus one LF. Dataset row SHA values hash canonical ascending typed-row
dictionaries plus one LF. Decimal values use the exact 06.4D plain, non-exponent, minimal-scale
normalization; zero is `0`.

`canonical_json_bytes()` emits every transcript field except `raw_body_bytes` as deterministic
UTF-8 JSON with sorted object keys, compact separators, ASCII escapes, no NaN, and exactly one
final LF. The omitted bytes remain bound by exact page count, total byte count, individual raw
body SHA values, the ordered raw-body sequence SHA, every complete retained 06.4D receipt, and
the independently recomputed receipt sequence. Canonical bytes retain the complete plan,
complete receipts, and all aggregate typed rows. They are not permission to persist anything;
an eventual persistence format and raw-body storage boundary require a separate frozen task.

`sha256()` is lowercase SHA-256 over the exact canonical transcript bytes. The frozen three-page
fixture has transcript SHA-256:

```text
7f44962c80c7d8e501ace9d1b265a8fa7d24f3df83f53fef445c81376b43156a
```

## Stable validation order and errors

The top-level operation validates in this exact phase order:

1. exact plan type (`plan_not_exact_model`);
2. every current request invariant, plan graph shape, and current plan invariant
   (`plan_invariants_invalid`);
3. exact `receipts` tuple, then exact `raw_body_bytes` tuple
   (`receipts_not_exact_tuple`, `raw_body_bytes_not_exact_tuple`);
4. both lengths against the plan (`transcript_length_mismatch`), then private 256-page cap
   (`transcript_page_limit_exceeded`);
5. exact receipt item types, then exact raw-body item types
   (`receipt_not_exact_model`, `raw_body_not_exact_bytes`);
6. aggregate private raw-body cap (`transcript_raw_body_limit_exceeded`);
7. every supplied receipt invariant (`receipt_invariants_invalid`);
8. every receipt-to-request binding in order (`receipt_request_binding_invalid`);
9. 06.4D raw-body re-admission in plan order
   (`raw_body_reverification_failed`, with the exact page error as cause);
10. exact independently canonicalized supplied/recomputed receipt comparison
    (`recomputed_receipt_invalid`, `receipt_canonical_mismatch`);
11. per-dataset cross-page uniqueness and canonical ascending aggregation
    (`cross_page_timestamp_duplicate`, `canonical_dataset_row_order_invalid`); and
12. private factory construction and complete transcript invariant validation.

Transcript invariant validation uses stable groups:

```text
transcript_schema_invalid
transcript_plan_sha256_invalid
transcript_counts_invalid
transcript_fixed_limits_invalid
transcript_sequence_digests_invalid
transcript_rows_invalid
transcript_timestamp_endpoints_invalid
transcript_dataset_digests_invalid
transcript_reconciliation_flags_invalid
transcript_guardrails_invalid
```

Earlier phases win when multiple defects coexist. No error is silently repaired, reordered,
filtered, deduplicated, truncated, clamped, retried, or converted to evidence.

## Required lifecycle proof

The frozen suite has exactly 40 unparameterized meaningful nodes. On unmodified base and on the
mandatory comment-only `probe/` implementation shape, all 40 must collect and fail in call
phase with exact sentinel `historical_response_transcript_unavailable`, with no pass, skip,
xfail/xpass, deselection, collection error, setup error, or teardown error. The probe branch is
named `probe/*` and the probe PR is closed without merge.

An isolated one-file feasibility implementation must make all 40 nodes pass on Python 3.12 and
3.14. Acceptance covers the exact API/constants/field order, AST/import-time boundary, package
export compatibility, exact model and tuple identity, plan/request/receipt mutation resistance,
length/type/limit gates, exact request binding, mandatory second 06.4D admission, canonical
receipt byte comparison, method-rebinding resistance, deterministic cross-page aggregation,
exact aggregate row identity, strict endpoint types, empty funding,
sequence/body/receipt/dataset commitments, raw-body canonical omission, literal transcript SHA,
factory-only deep immutability, narrow true reconciliation flags, all false
authority/coverage guardrails, validation precedence, forbidden kwargs, and absence of external
surface calls.

An implementation PR is admissible only when all 40 frozen nodes pass on both required Python
versions, ordinary tests and no-live checks pass, the changed-file set is exactly the sole
implementation path, required statuses are successful, the expected head SHA is unchanged, and
no review thread is unresolved. Task closure is a separate PR restoring
`NO_ACTIVE_IMPLEMENTATION`.
