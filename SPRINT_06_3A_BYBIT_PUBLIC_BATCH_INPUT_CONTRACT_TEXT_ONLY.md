# Sprint 06.3A — Bybit Public Batch Input Contract and Closed-Candle Adapter Core

## PM authorization

The synthetic OHLC evidence gate is closed. This sprint is authorized to connect the accepted OHLC replay adapter to small, public, read-only Bybit V5 market batches.

This is not a bulk historical download sprint. It establishes a strict typed contract, deterministic pagination and a tiny owner-side public smoke test.

## Frozen behavior

Do not change:

- neutral-grid geometry or accounting;
- position, fee, funding or termination formulas;
- OHLC/OLHC minimal-path construction;
- existing 24 OHLC scenario fixtures or v4 evidence identifiers;
- canonical serialization rules;
- any risk/live guardrail from the accepted evidence pack.

## Safety and artifact rules

- Public Bybit GET endpoints only.
- No private endpoints and no API credentials.
- No native grid validate/create/close/detail calls.
- No order, position, wallet, account or Telegram code.
- No Parquet generation in Codex.
- No large data download in Codex or tests.
- No ZIP, database, JSONL or generated report committed to the repository.
- Codex changes text source/tests/docs only.
- All tests use mocked public responses; network calls are forbidden in pytest.
- The owner-side smoke script may make a few real public requests after all tests pass.

## Official endpoint contract used by this sprint

### Server time

```text
GET /v5/market/time
```

Use `result.timeNano`, `result.timeSecond` and top-level `time` to derive and cross-check server time. The closed-candle cutoff must be based on Bybit server time, not the laptop clock.

### Instruments

```text
GET /v5/market/instruments-info
category=linear
limit=1000
cursor=<nextPageCursor>
```

The default page is not enough for all linear symbols. Cursor pagination is mandatory. Required fields for a USDT perpetual batch include:

```text
symbol
contractType
status
baseCoin
quoteCoin
settleCoin
launchTime
deliveryTime
isPreListing
fundingInterval
priceFilter.tickSize
lotSizeFilter.qtyStep
lotSizeFilter.minOrderQty
lotSizeFilter.minNotionalValue
leverageFilter.minLeverage
leverageFilter.maxLeverage
leverageFilter.leverageStep
```

### Trade-price 1m kline

```text
GET /v5/market/kline
category=linear
symbol=<SYMBOL>
interval=1
start=<inclusive open time ms>
end=<inclusive open time ms>
limit=1000
```

Rows are returned newest first and must be normalized to strictly ascending `startTime`. A response row has exactly seven fields:

```text
startTime, open, high, low, close, volume, turnover
```

### Mark-price 1m kline

```text
GET /v5/market/mark-price-kline
category=linear
symbol=<SYMBOL>
interval=1
start=<inclusive open time ms>
end=<inclusive open time ms>
limit=1000
```

Rows are returned newest first and have exactly five fields:

```text
startTime, open, high, low, close
```

### Funding history

```text
GET /v5/market/funding/history
category=linear
symbol=<SYMBOL>
startTime=<range start ms>
endTime=<backward page end ms>
limit=200
```

Funding intervals vary by instrument. Use `fundingInterval` from instruments-info. Do not assume eight hours.

## Task 0 — Close two accepted-pack helper debts

### Explicit reproducibility evidence

Update `build_contract_audit(...)` so missing reproducibility evidence cannot pass:

```text
reproducibility_audit is None -> fail closed or raise a named error
reproducibility_audit == {} -> fail closed or raise a named error
reproducibility_audit_ok is missing/not exact bool -> fail closed
```

A valid explicit reproducibility audit must preserve the current canonical v4 results.

### Termination on the final expected event

Fix the termination-prefix contract so a replay is valid when:

```text
terminated_bool == true
generated events equal the complete expected schedule
last generated event is the matching termination trigger
there are zero unconsumed events
```

Continue rejecting any event after termination, non-prefix consumption, mismatched trigger sequence/time or inconsistent ignored-candle counts.

Add dedicated regression tests for both debts.

## Task 1 — Add a versioned public-batch contract document

Create:

```text
docs/bybit_public_batch_input_contract_v1.md
```

Document:

- exact public endpoints and required fields;
- server-time closed-candle cutoff;
- inclusive request windows;
- reverse-response normalization;
- Decimal-only normalized values;
- strict category/symbol/source provenance;
- funding backward pagination;
- funding interval from instrument metadata;
- mark-price alignment method;
- limitations and guardrails.

Required limitations:

```text
minute mark-price data is not tick-level settlement evidence
real public smoke is not full historical coverage
no delisted-history completeness claim
no liquidation claim
no native quantity mapping claim
no 5 USDT risk proof
no parameter selection
no profitability claim
no live readiness
```

## Task 2 — New package and strict immutable models

Create:

```text
src/bybit_grid/data/public_batch/
  __init__.py
  models.py
  parsers.py
  pagination.py
  assemble.py
  audit.py
```

Do not replace the legacy early-sprint downloaders in this sprint.

### Models

Use frozen dataclasses, exact enums and `Decimal`. Reject bool-as-int and float values.

Minimum models:

```text
InclusiveMinuteWindow
BybitServerTime
BybitInstrumentMeta
BybitTradeKline1m
BybitMarkKline1m
BybitFundingRate
PublicRequestPageAudit
BybitPublicReplayBatch
BybitPublicBatchAudit
```

### InclusiveMinuteWindow

```text
start_open_time_ms: exact non-bool int, >= 0, minute-aligned
end_open_time_ms: exact non-bool int, >= start, minute-aligned
row_count = ((end-start)/60000)+1
```

### BybitInstrumentMeta

Required exact fields:

```text
category = "linear"
symbol: stripped uppercase str
contract_type
status
base_coin
quote_coin
settle_coin
launch_time_ms
delivery_time_ms
is_pre_listing: exact bool
funding_interval_minutes: exact positive non-bool int
tick_size: positive Decimal
qty_step: positive Decimal
min_order_qty: positive Decimal
min_notional_value: positive Decimal
min_leverage: positive Decimal
max_leverage: positive Decimal
leverage_step: positive Decimal
snapshot_server_time_ms
```

Add a method or helper that admits a replay batch only when:

```text
contract_type == LinearPerpetual
status == Trading
quote_coin == USDT
settle_coin == USDT
is_pre_listing == false
```

### BybitTradeKline1m

```text
category
symbol
open_time_ms
open/high/low/close: positive finite Decimal
volume/turnover: finite non-negative Decimal
closed_bool: exact true
source contract = Bybit trade kline 1m
```

Add `to_ohlc_candle()` returning the accepted `OhlcCandle1m` with `CandleSource.bybit_trade_kline_1m`.

### BybitMarkKline1m

Same OHLC/timestamp validation, without fabricated volume/turnover.

### BybitFundingRate

```text
category
symbol
funding_time_ms: minute-aligned
funding_rate: finite Decimal
source contract = Bybit funding history
```

### BybitPublicReplayBatch

Retain detached immutable tuples of:

```text
instrument
trade_klines
mark_klines
funding_rates
funding_observations
request_page_audits
server_time
requested_window
```

No mutable list/dict aliases in returned evidence.

## Task 3 — Strict raw-response parsers

Implement parsers that consume Python objects returned by `BybitClient.public_get()` but do not trust their shape.

General rules:

- exact dict/list/string/int/bool contracts;
- `retCode` must be exact integer/string zero as already accepted by the client;
- `result.category` must equal requested category;
- `result.symbol`, where present, must equal requested symbol;
- price/rate/quantity tokens must be strings converted directly to `Decimal`;
- reject Python float tokens in all numeric market fields;
- reject null/empty required values;
- reject duplicate rows before deduplication;
- reject values outside the requested window;
- reject malformed row lengths;
- produce stable named errors.

### Server time parser

Parse `timeNano`, `timeSecond` and top-level `time`. Require internal consistency within a documented small millisecond tolerance. Derive:

```text
server_time_ms
last_closed_open_time_ms = floor(server_time_ms / 60000)*60000 - 60000
```

### Instrument page parser

Require exact category and parse the required nested filters. Do not silently default missing fields to zero.

### Trade/mark kline page parsers

- accept reverse order from Bybit;
- return strict ascending order;
- require exact minute alignment;
- reject duplicate timestamps;
- reject any row after `last_closed_open_time_ms`;
- reject any row outside the requested inclusive page window;
- validate OHLC relationships.

### Funding page parser

- require matching symbol/category for every row;
- sort ascending;
- reject duplicate funding timestamps;
- preserve negative and zero rates;
- reject timestamps outside the requested range.

## Task 4 — Deterministic pagination

### Instrument cursor pagination

Implement a client-protocol function using `limit=1000` that:

- captures every cursor request;
- rejects a repeated cursor/cursor cycle;
- rejects duplicate symbols across pages, including identical duplicates;
- rejects `nextPageCursor` with an empty page;
- has a maximum-page guard;
- returns exact page audit records.

### Kline request planning

Implement:

```text
plan_1m_windows(start_open_ms, end_open_ms, limit=1000)
```

Each inclusive window may contain at most 1000 timestamps. Adjacent windows must have no overlap and no gap.

Example:

```text
start=0, end=999*60000 -> one 1000-row window
start=0, end=1000*60000 -> two windows: 1000 rows + 1 row
```

Fetch trade and mark pages using every planned window. Merge in ascending order and fail on duplicates or missing expected timestamps.

### Funding backward pagination

The funding endpoint may return only the most recent 200 records up to `endTime`. Paginate backward:

```text
page_end = requested_end
request startTime=requested_start, endTime=page_end, limit=200
next page_end = minimum returned funding timestamp - 1 ms
```

Stop only when the requested start is covered or the endpoint returns no older rows. Detect no progress, repeated pages and duplicate timestamps.

Do not use the legacy forward `max_timestamp + 1` strategy.

## Task 5 — Assemble replay-ready public batches

Implement an orchestration function, for example:

```text
fetch_bybit_public_replay_batch(
    client,
    symbol,
    requested_window,
    *,
    server_time=None,
    instrument=None,
)
```

Rules:

1. Use Bybit server time.
2. Require the requested end to be no later than the last closed candle open.
3. Require one eligible Trading USDT LinearPerpetual instrument.
4. Fetch complete trade and mark 1m sets for the same inclusive window.
5. Require exact trade/mark timestamp-set equality.
6. Fetch funding history using the instrument's actual funding interval.
7. For each funding timestamp strictly after replay entry and before final candle close, require a mark-price candle with the same open timestamp.
8. Build `FundingObservation` using:

```text
mark_price = mark kline open at the funding timestamp
funding_rate_source = bybit_funding_history
mark_price_source = bybit_mark_price_kline_1m
```

9. Retain the alignment method in the batch/audit.
10. Return immutable replay inputs compatible with the accepted OHLC adapter.

The alignment method is a minute-data approximation and must not claim tick-level funding settlement equivalence.

## Task 6 — Independent batch audit

Implement `audit_bybit_public_replay_batch(...)` that recomputes, not trusts:

```text
exact model/container types
instrument eligibility
category/symbol consistency
server-time cutoff
closed-candle status
expected timestamp set
trade and mark continuity
trade/mark timestamp equality
OHLC validity
absence of duplicate rows
request-page reconciliation
funding sort/uniqueness
funding interval consistency
funding timestamp/mark-open exact join
funding source provenance
replay-input conversion identity
```

Minimum output flags:

```text
public_batch_audit_ok
instrument_contract_ok
closed_candle_cutoff_ok
trade_kline_coverage_ok
mark_kline_coverage_ok
trade_mark_timestamp_sets_equal_bool
funding_pagination_range_covered_bool
funding_interval_consistent_bool
funding_mark_boundary_join_ok
replay_inputs_ready_bool
```

Fail closed with stable named failures. Do not add any readiness/profit/risk/live claim.

## Task 7 — Tiny owner-side public smoke script

Create:

```text
scripts/smoke_bybit_public_batch_contract.py
```

The script must:

- require no API keys;
- fetch Bybit server time;
- exercise instruments cursor pagination;
- select `BTCUSDT` and validate its instrument contract;
- fetch a few recent funding rows;
- choose an older funding timestamp for which the surrounding candles are closed;
- request exactly three trade and three mark 1m candles: one minute before, the funding minute, and one minute after;
- assemble and independently audit the batch;
- write one UTF-8 canonical JSON file specified by `--output`;
- print a one-line strict JSON summary;
- make no private calls and place no orders.

Required summary fields:

```text
status
server_time_ms
last_closed_open_time_ms
instrument_page_count
instrument_count
symbol
funding_interval_minutes
window_start_open_time_ms
window_end_open_time_ms
trade_row_count
mark_row_count
funding_rate_row_count
funding_observation_count
funding_mark_alignment_method
public_batch_audit_ok
```

The smoke report must not contain API keys, headers, balances or account data.

## Task 8 — Regression tests

Create:

```text
tests/test_sprint_06_3a_bybit_public_batch_input_contract.py
```

Use mocked clients only. Add at least these test groups:

### Accepted-pack debt tests

1. Missing reproducibility audit cannot produce a passing contract audit.
2. Empty reproducibility audit cannot produce a passing contract audit.
3. A termination on the final full-schedule event is accepted.
4. An event after termination is still rejected.

### Model/parser strictness

5. bool-as-int and float market fields rejected.
6. whitespace/lowercase symbol rejected.
7. missing nested instrument fields rejected.
8. wrong category/symbol rejected.
9. kline row length/duplicate/out-of-window/unclosed row rejected.
10. Decimal tokens preserved exactly.

### Pagination

11. instrument multi-page cursor success.
12. repeated cursor rejected.
13. duplicate instrument across pages rejected.
14. kline 1000/1001 boundary plan exact.
15. reverse pages normalize ascending.
16. cross-page overlap or gap rejected.
17. funding 450-row backward pagination returns all rows.
18. no-progress funding page rejected.
19. 60/240/480-minute funding intervals are not replaced by an 8-hour assumption.

### Assembly/audit

20. trade/mark timestamp mismatch rejected.
21. funding joins to mark-open at the exact boundary.
22. missing boundary mark candle rejected.
23. cross-symbol funding rejected.
24. prelisting/non-USDT/non-perpetual instrument rejected.
25. source provenance exact.
26. returned batch and replay inputs are immutable/detached.
27. independent audit rejects a tampered row/page count/funding source.
28. public smoke script imports without performing network calls.
29. no private/live/Telegram surface introduced.

Tests must not require Git, `.git`, network access or owner artifacts.

## Required Codex checks

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest -q
ruff check .
git diff --check   # only when Git is available in the Codex environment
```

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live audit passes
accepted OHLC/state-machine tests remain green
missing reproducibility evidence fails closed
final-event termination prefix is accepted
server-time cutoff is deterministic
instrument pagination is cursor-safe
1m trade/mark request windows are complete and non-overlapping
funding pagination is backward and complete for mocked 450-row range
all normalized numeric market values are Decimal
no unclosed candle admitted
trade/mark timestamp sets match
funding uses instrument fundingInterval
funding observation uses exact mark-kline open at timestamp
batch audit passes for a valid mocked batch
owner public smoke script exists but is not run by pytest
risk_budget_proven_bool remains false
parameter selection remains unauthorized
live remains unauthorized
```

## Required Codex return

Return text only:

```text
commit hash
changed text files
git diff --stat
full pytest output
focused 06.3A pytest output
ruff output
no-live audit output
numeric environment output
pip check output
accepted-pack debt closure summary
server-time cutoff summary
instrument pagination summary
kline pagination/closed-candle summary
funding backward-pagination summary
funding mark-alignment summary
public batch audit summary
known remaining public-data limitations
all risk/parameter/live guardrail values
```

Do not create or upload ZIP, Parquet, JSONL, databases, market-data files or reports from the Codex environment.
