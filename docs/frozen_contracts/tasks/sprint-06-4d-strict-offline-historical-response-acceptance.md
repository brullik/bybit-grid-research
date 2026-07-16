# Sprint 06.4D — strict offline historical response acceptance

## Scope and authority

This task adds one pure page-level admission boundary for already obtained public Bybit
historical response bytes. The sole implementation path is:

- `src/bybit_grid/data/public_batch/historical_response.py`.

No other production, package-export, test, dependency, configuration, control-plane, or frozen
contract path may change in the implementation PR. In particular, the existing
`bybit_grid.data.public_batch.__all__` list remains byte-for-byte outside implementation scope
and does not re-export this module.

The operation accepts caller-supplied values only. It has no client, session, callback,
transport, host, URL, header collection, cookie, credential, API key, secret, timeout, retry,
proxy, filesystem path, environment, process, thread, sleep, random source, or clock. It never
imports `recording.py`. It performs no network, DNS, HTTP, filesystem, persistence, environment,
process, thread, retry, sleep, or wall-clock operation.

This task authorizes no public transport, credential access, private API, Telegram, order,
position, wallet, native-grid mutation, withdrawal, live capture, deployment, historical
coverage claim, parameter selection, profitability claim, or native-equivalence claim. It is
only a deterministic offline parser and page receipt. Multi-page reconciliation, transcript
evidence, persistence, and staged public execution remain later default-deny boundaries.

## Exact public API

The complete non-underscore module surface and exact `__all__` tuple are:

```python
(
    "MAX_HISTORICAL_RESPONSE_BODY_BYTES",
    "HistoricalResponseError",
    "HistoricalResponseReceipt",
    "accept_historical_response_page",
)
```

The one public constant is the exact integer:

```python
MAX_HISTORICAL_RESPONSE_BODY_BYTES = 1_048_576
```

`HistoricalResponseError` is a `ValueError`. The one operation is:

```python
accept_historical_response_page(
    *,
    plan,
    request,
    http_status,
    content_type,
    raw_body_bytes,
)
```

All five arguments are required and keyword-only; there is no positional, variadic, defaulted,
or caller-selectable cap argument.

The source imports none of `asyncio`, `datetime`, `http`, `httpx`, `locale`,
`multiprocessing`, `os`, `pathlib`, `random`, `requests`, `secrets`, `socket`, `ssl`,
`subprocess`, `threading`, `time`, `urllib`, `uuid`, or `zoneinfo`; it also imports no module
named `recording`. Imports use private aliases. There is no call-valued module assignment or
executable module expression other than the module docstring. Class/function definitions and
pure literals are the entire import-time behavior.

## Plan and request identity

- `plan` has exact type `HistoricalCapturePlan` and `request` exact type
  `HistoricalRequestSpec`; subclasses, mappings, duck types, or unrelated objects are rejected
  as `plan_not_exact_model` and `request_not_exact_model`.
- The exact `request` object must occur by object identity in `plan.requests`. An equal cloned
  request is `request_not_member_of_plan`.
- Frozen dataclasses are not blindly trusted. The request, every request in the plan, and the
  plan are revalidated from their current field values. `object.__setattr__` tampering is
  `request_invariants_invalid` or `plan_invariants_invalid` before response parsing.
- The plan digest independently canonicalizes every plan/request field with the exact 06.4C
  byte grammar and equals the original `HistoricalCapturePlan.sha256()` result. Rebound
  instance/class `sha256` and `canonical_json_bytes` methods are ignored. Request bytes are
  compact, sorted-key, ASCII JSON over every request dataclass field; params are arrays of
  two-element arrays in frozen order; bytes end in exactly one LF. `request_sha256` hashes
  those bytes.

## HTTP metadata admission

`http_status` is exact non-boolean `int(200)`, otherwise `http_status_not_exact_200`.

`content_type` is an exact `str` interpreted by a narrow standards-aware parser:

- the input is ASCII only;
- CR, LF, NUL, DEL, and every control except HTAB are rejected;
- commas, empty/trailing parameter segments, duplicate parameters, and more than one parameter
  are rejected;
- leading/trailing and separator OWS is SP/HTAB only;
- the media type is ASCII-case-insensitive exact `application/json`;
- zero parameters is accepted;
- the only accepted parameter is case-insensitive `charset`, with OWS around `=`, whose value
  is case-insensitive `utf-8` or quoted `"utf-8"`;
- `+json`, `text/json`, unknown parameters, and other charsets are rejected.

Failure is `content_type_not_accepted_json`. Every receipt stores the canonical literal
`application/json`, not the caller spelling.

## Fixed resource envelope and pre-parser scanner

`raw_body_bytes` has exact type `bytes`; mutable buffers, memoryviews, and strings are
`raw_body_not_exact_bytes`. Empty bytes are `response_body_empty`. The fixed private body cap is
1,048,576 bytes inclusive. The size check occurs before scanning; cap plus one is
`response_body_too_large`. Rebinding the public constant does not weaken enforcement or receipt
fields.

Before UTF-8 decode or JSON allocation, one stateful byte scanner enforces private literal
limits:

- maximum JSON container nesting depth: 8;
- maximum lexical token count: 20,000.

A token is each string opening, each primitive/literal run opening, and each outside-string
`{`, `}`, `[`, `]`, `,`, or `:` delimiter. Whitespace is not a token. The scanner tracks quote
state, odd/even backslash escape parity, and exact matching container closers. Escaped quotes,
backslashes, and text such as `\u005b` inside a string cannot alter structural depth.

Depth 8 and a syntactically valid 19,999-token array pass the scanner and reach semantic shape
rejection; depth 9 is `response_json_depth_exceeded`; 20,001 tokens is
`response_json_token_limit_exceeded`. Unclosed strings/containers and mismatched closers are
`response_json_invalid`. A full 1,000-row trade response remains below the token cap.

The receipt binds exact policy fields `max_response_body_bytes=1_048_576`,
`max_json_depth=8`, and `max_json_tokens=20_000`.

## Strict UTF-8 and JSON grammar

The body is decoded as strict UTF-8; decode failure is `response_utf8_invalid`. A UTF-8 BOM is
not stripped and is invalid JSON. JSON syntax failure is `response_json_invalid`.

The parser rejects duplicate object keys at any depth as `response_json_duplicate_key`. Every
JSON float token is `response_json_float_forbidden`. `NaN`, `Infinity`, and `-Infinity` are
`response_json_nonfinite_forbidden`.

Every JSON integer token is parsed by a bounded lexical hook before integer construction:

- canonical grammar is `0`, positive `[1-9][0-9]*`, or negative `-[1-9][0-9]*`;
- JSON `-0` is `response_json_integer_noncanonical`;
- excluding the sign, at most 19 digits are converted;
- lexical comparison against `-9223372036854775808` and `9223372036854775807` occurs before
  `int()`;
- an out-of-range or arbitrarily long integer is
  `response_json_integer_out_of_int64` without leaking Python's digit-limit exception.

After parse, every string key and value is checked for Unicode scalar validity. Lone UTF-16
surrogate escapes are `response_json_unicode_scalar_invalid`; a valid surrogate pair is
accepted as its scalar value.

## Exact top-level response shape

The root is an exact object with only these keys:

```text
retCode, retMsg, result, retExtInfo, time
```

Wrong root type or key set is `response_root_shape_invalid`. Identity is exact:

- `retCode` is exact non-boolean integer zero;
- `retMsg` is exact string `OK`;
- `retExtInfo` is an exact empty object;
- `time` is an exact non-boolean, nonnegative signed-int64 integer.

Wrong status/extension identity is `response_top_level_invalid`; wrong time is
`response_time_invalid`. JSON int64 rejection precedes time semantics.

For trade and mark, `result` has exactly `category`, `symbol`, and `list`. For funding it has
exactly `category` and `list` and no result-level symbol. `category` is `linear`, kline `symbol`
equals the plan/request symbol, and `list` is an exact JSON array. Wrong key/type shape is
`response_result_shape_invalid`; category or symbol mismatch is
`response_identity_mismatch`.

## Kline page admission

Trade rows are exact seven-string JSON arrays:

```text
[startTime, open, high, low, close, volume, turnover]
```

Mark rows are exact five-string JSON arrays:

```text
[startTime, open, high, low, close]
```

A wrong row type, width, or non-string atom is `kline_row_shape_invalid`. Timestamp strings use
ASCII canonical unsigned-integer grammar, fit signed int64, and are minute aligned; Unicode
digits, leading zeroes, a plus sign, excess length, or misalignment are
`kline_timestamp_invalid`.

Bybit's documented kline response order is frozen: the page is exact reverse `startTime`, from
`request.end_ms` through `request.start_ms` at 60,000 ms steps. Row count and timestamp set must
cover every requested minute exactly once. Missing/duplicate/out-of-range coverage is
`kline_coverage_invalid`; the right set in any other order is `kline_order_invalid`.

Prices use an ASCII, non-exponent decimal string of at most 128 characters, with no plus sign
or leading zeroes; they are finite and positive. OHLC relations are enforced by the existing
typed models. Trade volume and turnover use the same grammar and are nonnegative. Failure is
`kline_value_invalid`.

Rows become exact existing `BybitTradeKline1m` or `BybitMarkKline1m` values with
`closed_bool=True`, then canonicalize oldest-to-newest. Receipt literals are
`source_row_order="reverse_start_time"`,
`canonical_row_order="timestamp_ascending"`,
`exact_kline_coverage_bool=True`, and `funding_page_unsaturated_bool=False`.

## Funding page admission

Funding result order is deliberately unspecified: the Bybit funding-history documentation does
not guarantee response order. Each row is an exact object of three string values and keys:

```text
symbol, fundingRate, fundingRateTimestamp
```

Wrong shape is `funding_row_shape_invalid`; symbol mismatch is
`response_identity_mismatch`. Funding rate uses the signed, finite, non-exponent ASCII decimal
grammar and 128-character cap; failure is `funding_value_invalid`.

Funding timestamps are canonical unsigned ASCII integer strings in signed-int64 range and
minute aligned, otherwise `funding_timestamp_invalid`. They are unique
(`funding_duplicate_timestamp`) and fall in the exact inclusive request millisecond range
(`funding_timestamp_out_of_range`). For a request starting one millisecond after a minute, the
previous aligned minute is outside and the next aligned minute is the first admissible value.

The raw row count must be strictly below the fixed funding limit 200. A count of 200 or more is
`funding_page_saturated` before row validation. It must also be at most
`request.target_row_count`, otherwise `funding_row_limit_exceeded`. The exact 199 boundary is
accepted when the target allows it. Empty funding pages are accepted.

Accepted funding rows become exact existing `BybitFundingRate` values and canonicalize by
ascending timestamp regardless of response permutation. Receipt literals are
`source_row_order="unspecified"`, `canonical_row_order="timestamp_ascending"`,
`exact_kline_coverage_bool=False`, and `funding_page_unsaturated_bool=True`.

Empty funding has exact `rows=()`, `row_count=0`, and both timestamp endpoints `None`. It never
proves funding or historical coverage.

## Immutable factory-only receipt

`HistoricalResponseReceipt` is a frozen, slotted, hashable dataclass with no instance
`__dict__`, but it is factory-only (`init=False`). Direct construction and `dataclasses.replace`
raise `receipt_factory_only`; callers cannot invent digest evidence through a public
constructor. The acceptance function uses a private builder, validates the finished model, and
returns it.

Fields occur in this exact order:

1. `schema`, `plan_sha256`, `request_sha256`;
2. `sequence_id`, `dataset`, `endpoint`, `category`, `symbol`;
3. `request_start_ms`, `request_end_ms`, `request_limit`,
   `request_target_row_count`;
4. `http_status`, canonical `content_type`, and `response_time_ms`;
5. `raw_body_byte_count`, `raw_body_sha256`;
6. `max_response_body_bytes`, `max_json_depth`, `max_json_tokens`;
7. `row_count`, nullable `first_timestamp_ms`, nullable `last_timestamp_ms`;
8. `timestamps_sha256`, `rows_sha256`;
9. `source_row_order`, `canonical_row_order`, `exact_kline_coverage_bool`,
   `funding_page_unsaturated_bool`;
10. fixed-false authority/coverage flags; and
11. `rows`, an exact tuple of one dataset's exact typed models.

The schema is `bybit_public_historical_response_receipt_v1`. Every SHA field is lowercase
64-hex. Timestamp bytes are compact sorted-key JSON of the canonical ascending integer list plus
one LF. Row bytes are compact sorted-key JSON of canonical typed-row dictionaries plus one LF.
Enum sources serialize to their string values. Decimal values normalize to plain non-exponent
minimal scale (`1`, `1.0`, and `1.00` serialize identically), with zero serialized as `0`.
Therefore semantically equal typed rows share `rows_sha256` even when raw body hashes differ.

The exact fixed-false fields are:

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

Receipt canonicalization revalidates recomputable row/timestamp integrity and fixed identity,
cap, ordering, and guardrail policy. Deliberate `object.__setattr__` tampering of those fields
therefore makes `canonical_json_bytes()` and `sha256()` fail with the applicable stable
`receipt_*_invalid` error. Factory-only construction is not an authorization or security
boundary against deliberate valid-format replacement of a source digest that cannot be
recomputed from retained receipt fields; callers must treat receipts returned directly by this
acceptance boundary as evidence and verify persisted/transmitted receipts in a later separately
frozen transcript boundary.

`canonical_json_bytes()` emits the complete receipt as deterministic UTF-8 JSON with sorted
object keys, compact separators, ASCII escapes, normalized row decimals, no NaN, and exactly one
final LF. `sha256()` is lowercase SHA-256 over those exact bytes. Frozen acceptance includes a
complete literal one-row trade request, row serialization, receipt byte string, and literal
component/receipt hashes so serializer self-consistency alone cannot satisfy the contract.

## Stable validation order

The boundary validates, in order: exact plan/request types; current request invariants; exact
tuple/type shape and current invariants of the plan graph and plan; request object membership;
exact HTTP status; Content-Type; exact bytes/nonempty/body cap;
pre-parser depth/token/structure; strict UTF-8/JSON; exact root/top-level/result identity; then
dataset row-count, row-shape, timestamp, coverage/order, numeric/model rules. For funding,
saturation precedes target count and row validation. No failure is silently repaired, filtered,
deduplicated, truncated, clamped, or treated as evidence.

## Required lifecycle proof

The frozen suite has exactly 58 unparameterized nodes. On unmodified base and on the mandatory
comment-only `probe/` implementation shape, all 58 must collect and fail in call phase with the
exact sentinel `historical_response_page_unavailable`, with no pass, skip, xfail/xpass,
deselection, collection error, setup error, or teardown error. The probe is closed without
merge.

An implementation is admissible only when all 58 nodes pass on both required Python versions,
ordinary tests and no-live checks pass, the changed-file set is exactly the sole implementation
path, required statuses are successful, the expected head SHA is unchanged, and no review
thread is unresolved. Task closure is a separate PR restoring `NO_ACTIVE_IMPLEMENTATION`.
