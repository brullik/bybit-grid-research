# Sprint 06.4C — strict bounded historical capture plan

## Scope and default-deny authority

This task adds one pure offline planner for a bounded public historical-capture request graph.
Only this production path may change, and it must change:

- `src/bybit_grid/data/public_batch/historical_plan.py`.

The module derives immutable request specifications from already parsed public models and exact
observed timestamps. It performs no network, DNS, HTTP, filesystem, environment, process,
thread, sleep, retry, random, locale, timezone-database, or wall-clock operation. It accepts no
client, session, callback, transport, host, base URL, endpoint override, header, cookie,
credential, API key, secret, timeout, retry, proxy, path, file, clock, or caller-selectable cap.

This task authorizes no credential access, private Bybit API, Telegram, order, position, wallet,
native-grid mutation, withdrawal, live capture, deployment, parameter selection, profitability
claim, native-equivalence claim, or ordinary-order mutation. Returned routes are relative public
`/v5/market/*` paths only. Executing a request, validating a response, persisting evidence,
proving historical completeness, and deciding account or regional eligibility remain separate
default-deny boundaries.

## Fixed non-weakenable policy

The module exposes these exact integer constants:

```python
MAX_PLAN_SPAN_MINUTES = 44_640
KLINE_LIMIT = 1000
FUNDING_LIMIT = 200
FUNDING_TARGET_RECORDS = 199
MAX_TOTAL_REQUESTS = 256
MAX_TOTAL_RESPONSE_ROWS = 100_000
```

They are policy, not defaults. The operation has no parameter or variadic escape hatch that can
replace, increase, disable, or reinterpret them. Builder and model invariant checks use private
literal policy values: rebinding any public constant after import changes neither a gate nor the
cap fields and request limits emitted by a plan.

`FUNDING_TARGET_RECORDS` is deliberately one below Bybit's fixed public funding-history limit.
This planner does not execute the page, but a later separately frozen executor must reject a
200-row funding page, duplicate timestamp, non-integer timestamp, non-minute timestamp, or row
outside its request range. A planned page with at most 199 possible accepted minute-aligned
timestamps does not itself prove that the exchange returned complete history.

## Exact public surface and API

The module's exact `__all__` tuple, and its complete non-underscore global surface, are:

```python
(
    "FUNDING_LIMIT",
    "FUNDING_TARGET_RECORDS",
    "HistoricalCapturePlan",
    "HistoricalPlanError",
    "HistoricalRequestSpec",
    "KLINE_LIMIT",
    "MAX_PLAN_SPAN_MINUTES",
    "MAX_TOTAL_REQUESTS",
    "MAX_TOTAL_RESPONSE_ROWS",
    "build_historical_capture_plan",
)
```

There is one top-level operation:

```python
build_historical_capture_plan(
    *,
    instrument,
    server_time,
    requested_window,
    observed_trade_open_times_ms,
    observed_mark_open_times_ms,
    observed_funding_times_ms,
)
```

Every parameter is required and keyword-only. The signature has no positional, variadic, or
defaulted argument. `HistoricalPlanError` is a `ValueError`.

The module source has no forbidden external-surface import and no call-valued module assignment
or executable module expression. In particular it imports none of `asyncio`, `datetime`,
`http`, `httpx`, `locale`, `multiprocessing`, `os`, `pathlib`, `random`, `requests`, `secrets`,
`socket`, `ssl`, `subprocess`, `threading`, `time`, `urllib`, `uuid`, or `zoneinfo`. Imports are
private aliases or otherwise do not leak extra public names. Class creation and pure constant,
function, and class definitions are the complete import-time behavior.

## Immutable request and plan models

`HistoricalRequestSpec` and `HistoricalCapturePlan` are frozen, slotted dataclasses with no
instance `__dict__`. Every nested collection is an exact tuple, so models are deeply immutable,
equality-stable, deterministic, and hashable.

`HistoricalRequestSpec` has exactly these fields, in order:

1. `sequence_id`;
2. `dataset`;
3. `endpoint`;
4. `pagination`;
5. `start_ms` and `end_ms` (inclusive);
6. `limit`;
7. `target_row_count`;
8. `requested_minute_count`; and
9. `params`, an exact tuple of key/value tuples in canonical endpoint order.

`HistoricalCapturePlan` has exactly these fields, in order:

1. `schema`, `category`, and `symbol`;
2. `launch_cutoff_open_time_ms`, nullable `delivery_cutoff_open_time_ms`,
   `request_start_open_time_ms`, `request_cutoff_open_time_ms`, and
   `server_cutoff_open_time_ms`;
3. `funding_interval_minutes`;
4. `observed_trade_row_count`, `observed_mark_row_count`,
   `observed_funding_row_count`, and `observed_funding_times_sha256`;
5. `trade_missing_row_count`, `mark_missing_row_count`, and
   `funding_recapture_observation_upper_bound`;
6. `plan_span_minutes`, `request_count`, and `planned_max_response_rows`;
7. `max_plan_span_minutes`, `max_total_requests`, and `max_total_response_rows`;
8. fixed-false `network_authorized_bool`, `credentials_allowed_bool`,
   `private_api_allowed_bool`, `live_execution_authorized_bool`,
   `funding_coverage_proven_bool`, `historical_market_data_coverage_proven_bool`,
   `parameter_selection_authorized_bool`, `sufficient_for_parameter_selection_bool`, and
   `native_equivalence_proven_bool`; and
9. `requests`, an exact tuple of `HistoricalRequestSpec`.

The schema is `bybit_public_historical_capture_plan_v1`; category is `linear`. Cap fields equal
the private fixed policy literals. Every guardrail field is the exact `False` singleton and is
not caller-selectable.

Direct construction is fail-closed, not a second unvalidated API. A malformed request spec,
including a wrong dataset/endpoint/pagination combination, bound, limit, target, minute count,
or mutable/noncanonical params, is `request_spec_invalid`. A forged plan schema, category,
symbol, cutoff identity, or malformed observed-funding digest is `plan_identity_invalid`;
changed cap fields are `plan_fixed_limits_invalid`; any guardrail other than exact false is
`plan_guardrails_invalid`; a non-tuple graph, wrong spec type, noncontiguous sequence, wrong
dataset/window order, duplicate semantic key, or graph mismatch is `plan_requests_invalid`;
and inconsistent span/count/row totals are `plan_totals_invalid`.

## Canonical bytes, hashes, and observation identity

`HistoricalCapturePlan.canonical_json_bytes()` returns the complete plan as deterministic UTF-8
JSON with sorted object keys, compact separators, JSON booleans/null, no NaN, and exactly one
final LF. Request order is retained; each params tuple serializes as a JSON array of two-element
arrays in frozen order. `HistoricalCapturePlan.sha256()` is the lowercase 64-hex SHA-256 of
those exact bytes. Neither method performs I/O or consults mutable global policy.

The exact funding-observation tuple is separately identity-bound. Its canonical bytes are the
compact JSON array of its decimal integers, in tuple order, plus one LF. The plan field
`observed_funding_times_sha256` is SHA-256 over those exact bytes. Empty observations therefore
bind to SHA-256 of `b"[]\n"`; count alone is never treated as identity. The plan constructor
requires lowercase 64-hex digest grammar.

## Input identity, eligibility, int64, and lifecycle gates

- `instrument` has exact type `BybitInstrumentMeta`, `server_time` exact type
  `BybitServerTime`, and `requested_window` exact type `InclusiveMinuteWindow`. Subclasses,
  mappings, duck types, and reconstructed aliases are rejected.
- The instrument satisfies the existing `eligible_for_replay()` boundary: linear perpetual,
  Trading, USDT quote and settlement, non-prelisting, and positive current funding interval.
  Every eligibility dimension is independently fail-closed as
  `instrument_not_replay_eligible`.
- The symbol is exact ASCII uppercase alphanumeric with length 2 through 32. Punctuation,
  whitespace, Unicode lookalikes, and shorter or longer symbols are
  `instrument_symbol_invalid`.
- Every lifecycle/server/window millisecond integer used by planning is in signed-int64 range.
  An invalid launch/delivery lifecycle or launch ceiling overflow is
  `instrument_lifecycle_invalid`; invalid server components are
  `server_time_identity_invalid`; an out-of-int64 window is `window_time_out_of_int64`.
- Instrument metadata and cutoff are one public snapshot:
  `instrument.snapshot_server_time_ms == server_time.server_time_ms`, otherwise
  `instrument_server_time_mismatch`.
- Server components mirror the accepted parser grammar rather than a stricter invented format:
  `time_nano // 1_000_000 == server_time_ms`, the distance from
  `time_second * 1000` is at most 999 ms, the distance from `top_level_time_ms` is at most
  999 ms, and `last_closed_open_time_ms` is the existing exact last-closed minute derived from
  `server_time_ms`.
- Launch cutoff is `ceil(launch_time_ms / 60000) * 60000`. The requested start may not precede
  it; the partial launch minute is excluded.
- `delivery_time_ms == 0` means no delivery cutoff. A nonzero delivery must be after launch and
  inside int64. Its last eligible full open is
  `floor(delivery_time_ms / 60000) * 60000 - 60000`; the delivery-containing minute is excluded.
- The requested end may not exceed `server_time.last_closed_open_time_ms` or a nonzero delivery
  cutoff. Start and end are used exactly, never silently clamped. Inclusive window rows equal
  `plan_span_minutes`, at most 44,640.

Stable cutoff errors are `window_before_launch`, `window_after_last_closed`,
`window_at_or_after_delivery`, and `plan_span_limit_exceeded`, after the identity/int64/lifecycle
checks above.

The current `funding_interval_minutes` remains in the plan as informational instrument metadata
and eligibility evidence only. It must never determine historical request partitioning or be
used to claim that the historical funding frequency was constant.

## Strict observed timestamp grammar

Each observed input is an exact tuple. Every member is an exact signed-int64 `int` (never `bool`
or an integer subclass), minute aligned, strictly increasing and therefore unique, and inside
the exact requested/cutoff-valid window. Input is rejected rather than sorted, deduplicated, or
silently filtered.

For argument name `NAME`, stable errors are:

- `NAME_not_exact_tuple`;
- `NAME_timestamp_not_exact_int`;
- `NAME_timestamps_not_strictly_increasing`;
- `NAME_timestamp_not_minute_aligned`; and
- `NAME_timestamp_outside_requested_window`.

Observed trade and mark timestamps drive independent resume planning. Observed funding
timestamps are validated, counted, and identity-bound, but never suppress funding requests and
never prove coverage.

## Kline missing/resume requests

For trade and mark independently, observed opens are subtracted from every requested minute.
Missing timestamps are partitioned into maximal contiguous runs, then every run is split
oldest-to-newest into inclusive windows of at most `KLINE_LIMIT`. An observed timestamp is an
exact resume boundary and appears in no planned kline range. A fully observed dataset emits no
request for that dataset.

Trade specs are exactly:

```text
dataset="trade_kline_1m"
endpoint="/v5/market/kline"
pagination="missing_windows_ascending"
params=(("category", "linear"), ("symbol", SYMBOL), ("interval", "1"),
        ("start", START_MS), ("end", END_MS), ("limit", ROW_COUNT))
```

Mark specs substitute `dataset="mark_kline_1m"` and
`endpoint="/v5/market/mark-price-kline"`. For both, `limit`, `target_row_count`, and
`requested_minute_count` equal the inclusive missing-minute count and never exceed 1000.

## Funding full-range worst-case recapture

Funding recaptures the entire requested range regardless of observed funding timestamps. The
partition uses only the already accepted-row invariant—unique minute-aligned timestamps—not the
instrument's current funding interval.

Starting at the exact range cursor:

1. `first_possible_ms = ceil(cursor / 60000) * 60000`;
2. `end_ms = min(request_cutoff, first_possible_ms + 198 * 60000)`;
3. the possible accepted-row count is the number of minute multiples from
   `first_possible_ms` through `floor(end_ms / 60000) * 60000`, inclusively; and
4. the next cursor is `end_ms + 1` millisecond.

Each nonempty range therefore permits at most 199 accepted rows. Ranges are disjoint and their
inclusive union is the complete requested millisecond range. They are first derived
oldest-to-newest, then emitted newest-to-oldest as:

```text
dataset="funding_rate"
endpoint="/v5/market/funding/history"
pagination="backward_full_range"
limit=200
params=(("category", "linear"), ("symbol", SYMBOL),
        ("startTime", START_MS), ("endTime", END_MS), ("limit", 200))
```

`target_row_count` is the exact worst-case minute-aligned count and is in `1..199`.
`requested_minute_count` is `floor((end_ms - start_ms) / 60000) + 1`. Every funding spec charges
the full 200 rows against the global response budget. Because this target can now be recomputed
from request bounds alone, both the request-spec constructor and enclosing plan reject a forged
funding target or boundary.

There is no funding skip/resume mode, historical-frequency assumption, coverage-complete flag,
unbounded backward loop, cursor, or caller-selected page/target limit. Both
`funding_coverage_proven_bool` and `historical_market_data_coverage_proven_bool` remain false.

## Exact graph order and hard budgets

Final order is trade windows oldest-to-newest, mark windows oldest-to-newest, then funding
windows newest-to-oldest. `sequence_id` is contiguous from one. Semantic key
`(dataset, start_ms, end_ms)` is unique; any duplicate is `request_spec_duplicate` before model
construction.

`request_count` is the number of specs. `planned_max_response_rows` sums every spec limit: exact
missing kline rows plus 200 per funding request. Before returning any plan:

- `plan_span_minutes <= 44_640`;
- `request_count <= 256`; and
- `planned_max_response_rows <= 100_000`.

Request count is checked before response rows. A graph violating both therefore returns
`request_limit_exceeded`, never row approval. The frozen reachable boundaries include exactly
256/257 requests and 100,000/100,001 response rows; equality succeeds and one over fails. There
is no partial graph, continuation token, best effort, automatic truncation, or cap increase.

## Compatibility and acceptance

This new module does not change `capture.py`, `pagination.py`, `reconstruct.py`, existing models,
persisted evidence, or package exports. Existing public-batch behavior remains compatible. A
later executor may consume these specs only after a separate frozen public-only transport,
response-validation, rate, retry, evidence, and rollback contract.

Frozen acceptance covers the exact surface/signature/constants, AST/import-time boundary,
slots/hashability, direct constructor invariants, canonical JSON+LF/SHA and funding observation
digest, every eligibility dimension, symbol length/ASCII grammar, parser-compatible server
identity, snapshot/int64/lifecycle and all cutoffs, observed tuple grammar, independent kline
resume and 1000/1001 splits, full funding recapture independent of current interval, exact
199-target/200-limit/+1ms partition, canonical dataset/endpoint/params/order/dedup, fixed false
proof and selection guardrails, public-constant rebinding resistance, exact reachable hard-budget
boundaries and precedence, forbidden keyword surfaces, and no network/filesystem/clock calls.

On the unmodified base, every frozen node must collect normally and fail in its call phase with
the exact sentinel `historical_capture_plan_unavailable`. A comment-only required module must
produce the same result. Collection, setup, teardown, skip, xfail/xpass, deselection, or another
failure is invalid RED evidence. An isolated one-file feasibility implementation must pass every
node on Python 3.12 and 3.14; GREEN is possible only through the required production path. The
exact frozen profile is 40 collected nodes: unmodified-base RED and comment-only probe each
produce 40 failed, 0 passed, while isolated feasibility produces 40 passed, 0 failed.
