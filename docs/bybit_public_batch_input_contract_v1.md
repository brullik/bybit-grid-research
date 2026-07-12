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
