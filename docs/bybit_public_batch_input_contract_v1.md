# Bybit public batch input contract v1

This contract admits only small, public, read-only Bybit V5 market batches for replay adapter input. It does not replace legacy downloaders.

## Endpoints and fields

* `GET /v5/market/time`: parse `result.timeNano`, `result.timeSecond`, and top-level `time`; require millisecond consistency and derive `last_closed_open_time_ms = floor(server_time_ms / 60000) * 60000 - 60000` from Bybit server time.
* `GET /v5/market/instruments-info?category=linear&status=Trading&limit=1000&cursor=...`: cursor pagination is mandatory. Required fields are `symbol`, `contractType`, `status`, `baseCoin`, `quoteCoin`, `settleCoin`, `launchTime`, `deliveryTime`, `isPreListing`, `fundingInterval`, `priceFilter.tickSize`, `lotSizeFilter.qtyStep`, `lotSizeFilter.minOrderQty`, `lotSizeFilter.minNotionalValue`, `leverageFilter.minLeverage`, `leverageFilter.maxLeverage`, and `leverageFilter.leverageStep`.
* `GET /v5/market/kline`: `category=linear`, `interval=1`, inclusive `start` and `end`, `limit=1000`; each row is exactly `startTime, open, high, low, close, volume, turnover`.
* `GET /v5/market/mark-price-kline`: same one-minute inclusive request contract; each row is exactly `startTime, open, high, low, close`.
* `GET /v5/market/funding/history`: `category=linear`, symbol, `startTime`, backward `endTime`, `limit=200`.

## Normalization and provenance

All kline responses are accepted newest-first or otherwise ordered, then normalized to strictly ascending `startTime`. Request windows are inclusive and planned with no gap or overlap. All normalized market prices, quantities and rates are `Decimal` values parsed directly from string tokens; floats and bool-as-int values are rejected. Every normalized row retains strict `category`, `symbol`, and source provenance.

## Instrument and funding rules

`category=linear` is broader than the project replay universe: Bybit may return `LinearPerpetual` and `LinearFutures` rows. Generic instrument metadata accepts only those two contract types, preserves source `fundingInterval=0` as evidence, rejects negative or non-integer funding intervals, and injects no cadence default. Replay admission requires exactly `LinearPerpetual`, `Trading`, non-prelisting, `quoteCoin=USDT`, `settleCoin=USDT`, and positive `fundingInterval`. A zero-funding `LinearFutures` row is valid non-replay metadata; a zero-funding USDT `LinearPerpetual` replay candidate is parsed for diagnosis but fails the independently derived universe audit with its exact symbol. Funding pagination is backward from the requested end using `next endTime = minimum returned funding timestamp - 1 ms`. Funding cadence comes from instrument `fundingInterval`; no eight-hour default is assumed.

## Mark-price funding alignment

Funding observations join a funding timestamp to the mark-price one-minute candle with the exact same open timestamp and use that candle's open as `mark_price`. This is a deterministic minute-data approximation only.

## Limitations and guardrails

* minute mark-price data is not tick-level settlement evidence
* owner public smoke is small, read-only adapter contract evidence and is not full historical funding coverage proof
* no delisted-history completeness claim
* no liquidation claim
* no native quantity mapping claim
* no 5 USDT risk proof
* no parameter selection
* no profitability claim
* no live readiness
* Public Bybit GET endpoints only; no private endpoints, credentials, native grid calls, orders, positions, wallets, accounts, Telegram code, Parquet, ZIP, database, JSONL, or generated reports are committed by this contract.

## Sprint 06.3B persisted public-batch evidence contract

Sprint 06.3B persists public-only Bybit market responses as reproducible evidence rather
than owner-local logs. The canonical owner capture uses one Bybit server-time snapshot to
set a closed one-minute candle window of exactly 1001 rows for `BTCUSDT`: the end open
minute is `server_time.last_closed_open_time_ms` and the start open minute is 1000 minutes
earlier.

### Retrieval plans

- Instrument universe is captured through a primary `/v5/market/instruments-info` plan
  with `limit=1000` and an alternate cursor-pagination plan with `limit=200`.
- Trade klines are captured for the same closed 1001-row window through primary
  `limit=1000` pages and alternate `limit=251` pages.
- Mark-price klines use the same primary and alternate page sizes as trade klines.
- Funding history covers the preceding 100 days for `BTCUSDT` through primary backward
  pagination with `limit=200` and an alternate deterministic chunk plan derived from the
  parsed instrument `fundingInterval` with a target of 100 records per window.

### Raw response provenance and canonical persistence

Every public response is recorded with a monotonically increasing request sequence,
public `/v5/market/` endpoint, deterministically sorted parameters, HTTP status,
content type, exact UTF-8 JSON body text, SHA-256 of that body, and a strict JSON object
payload. Strict parsing rejects duplicate object keys, float tokens, and non-finite JSON
constants. Canonical persisted JSON uses sorted keys and compact separators; canonical
JSONL has one strict JSON object per line and a final newline. Decimal values are emitted
as strings.

### Cross-plan equality

Primary/alternate equality proves only that the two retrieval plans normalized to the
same records for the accepted recorded window. It does not prove that Bybit supplied all
multi-year historical funding records, does not prove strategy profitability, does not
prove native grid equivalence, and does not authorize parameter selection or live trading.
`funding_coverage_proven_bool` therefore remains `false`.

### Safety guardrails

The persisted evidence contract keeps these guardrails closed: no credentials, no
private API, no live execution, no native grid operations, no Telegram, no parameter
optimization, no PnL/EV/ROI/profitability claim, and no Parquet evidence output in this
sprint. It is sufficient only for the next engineering stage: Parquet storage, resume,
and gap-repair design.

## Sprint 06.3B.1 closure: owner capture and semantic review-pack validation

The owner capture command is a real public-only lifecycle, not a placeholder. It writes
`public_batch_run_status.json` with `status=building` before constructing the import-safe
recording client, fetches Bybit public server time once via `GET /v5/market/time`, derives the
closed 1001-row BTCUSDT one-minute window from that snapshot, executes every primary and
alternate public `GET /v5/market/*` retrieval plan, persists raw responses first, reads those
persisted responses back, reconstructs normalized evidence from raw response bodies, reconciles
primary/alternate plans, audits the replay-ready primary batch, writes deterministic artifacts,
validates the directory from persisted files, and writes `status=complete` last. Failures write
`status=failed` last with stable exception type and message.

Every raw response record carries a stripped frozen plan id and a contiguous sequence id. The
frozen plan ids are `server_time_snapshot`, `instrument_primary_1000`,
`instrument_alternate_200`, `trade_primary_1000`, `trade_alternate_251`, `mark_primary_1000`,
`mark_alternate_251`, `funding_primary_backward_200`, and
`funding_alternate_chunked_100`. Plan-scoped client views share one underlying sequence and
record store; mutable global plan state is not part of the contract.

The instrument universe is captured with 1000-row and 200-row pagination plans and reconciled by
canonical normalized rows. Trade and mark one-minute klines use the exact same 1001-row closed
window with 1000-row and 251-row plans. Funding history covers the preceding 100 days with a
200-row backward plan and non-overlapping chunked plan derived from the parsed BTCUSDT funding
interval. Cross-plan equality proves deterministic equivalence of these public retrieval plans
within the requested windows only; it does not prove complete historical funding coverage.

Persisted-input-first reconstruction begins at `recorded_public_responses.jsonl`. The validator
checks canonical JSON/JSONL encoding, sequence ids, raw-body SHA-256 values, strict JSON parsing,
plan ids, endpoint/parameter identity, parser output, primary/alternate row equality, replay
assembly, funding observations, cross-plan summary fields, reports, and byte-for-byte artifact
identity. A review pack with recomputed hashes but semantically fabricated raw responses or
normalized rows is outside the accepted contract and must be rejected by semantic validation.

The review-pack manifest uses the self-excluded hash policy: `review_pack_manifest.json` is not
listed in `member_sha256`, while the other 17 members have exact lowercase SHA-256 hashes in the
frozen 18-member order. Extra or missing keys, stale hashes, unsafe paths, duplicate ZIP members,
non-canonical JSON/JSONL, or a complete status without validated evidence are invalid.

Funding observations use an inclusive in-window rule. Every funding rate whose timestamp satisfies
`requested_window.start_open_time_ms <= funding_time_ms <= requested_window.end_open_time_ms` must
produce exactly one observation joined to the mark-price candle with the same open timestamp. The
minute-data mark-open join remains an approximation and is documented as such.

All closed guardrails remain closed: no credentials, no private endpoints, no order/create/close/
cancel/position/account/wallet operations, no native grid operations, no Telegram, no parameter
optimization, no profitability claim, no Parquet output in this closure, no native-grid
equivalence, no native quantity mapping, no liquidation-behavior proof, no funding-history
completeness proof, no 5 USDT maximum-loss proof, and no live-readiness authorization. After this
closure is accepted, the next stage remains Parquet storage, resume behavior, and gap repair only.
