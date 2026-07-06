# Sprint 01.8 — Validate parser + private-account privacy hotfix

PM decision: Sprint 01.7 is accepted as implementation work, but Gate 1 is still open because real validate-only was skipped. Before running real validate, apply this small hardening patch.

## Non-negotiable safety rules

- Do not implement create.
- Do not implement close.
- Do not place orders.
- Do not create grid bots.
- Keep `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO`.
- Keep `GRID_VALIDATE_ENABLED=false` by default.
- Do not log or save API keys, secrets, signatures, full wallet balances, equity, PnL, or coin-level balance values.

## Why this hotfix is required

Sprint 01.7 did the right architecture work, but two issues remain:

1. `BybitClient._handle_response()` only treats standard V5 `retCode` responses as errors. Some Bybit trading-bot style responses may use `status_code` / `debug_msg`. If such a response returns HTTP 200 with `status_code != 200`, the current parser may incorrectly treat it as success.
2. `data/metadata/account_info_redacted.json` currently saves full wallet-balance numbers. This is not an API-secret leak, but it is sensitive private account data and should not be stored in a file that may be shared for PM review.

## Task 1 — Support standard V5 and trading-bot response formats

In `src/bybit_grid/bybit/client.py`, update `_handle_response()` so it handles both formats.

Standard V5 success:

```json
{"retCode": 0, "retMsg": "OK", "result": {...}}
```

Trading-bot style success:

```json
{"status_code": 200, "debug_msg": "", "result": {...}}
```

Rules:

- If `retCode` exists, success is `retCode in (0, "0")`.
- If `status_code` exists and `retCode` does not exist, success is `status_code in (200, "200")`.
- If both are missing, HTTP 2xx can be treated as success only for public/non-Bybit unusual responses, but keep a warning/log field.
- Error message should use `retMsg` or `debug_msg`.
- Retry only temporary errors: HTTP 429/5xx or Bybit `retCode=10006`.
- Do not retry parameter/schema/auth/signature errors.
- `BybitAPIError` must include `response_data` for redacted report saving.

Add tests:

- standard V5 success `retCode=0` passes;
- standard V5 error `retCode=10001` raises;
- trading-bot success `status_code=200` passes;
- trading-bot error `status_code=400` raises;
- trading-bot error with HTTP 200 still raises;
- retryable `retCode=10006` is classified retryable.

## Task 2 — Sanitize private account saved JSON

In `scripts/smoke_private_account.py`, do not save full raw wallet balances to `account_info_redacted.json`.

Replace the saved content with a sanitized summary:

```json
{
  "account_info": {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
      "unifiedMarginStatus": 5,
      "marginMode": "REGULAR_MARGIN",
      "dcpStatus": "OFF",
      "smpGroup": 0,
      "spotHedgingStatus": "OFF"
    }
  },
  "wallet_balance": {
    "retCode": 0,
    "retMsg": "OK",
    "accountType": "UNIFIED",
    "coin_count": 1,
    "coins": ["USDT"],
    "balance_values_redacted": true
  }
}
```

Do not save:

- walletBalance;
- equity;
- totalEquity;
- totalWalletBalance;
- usdValue;
- realised/unrealised PnL;
- margin balances;
- any numeric account amounts.

Add tests that fail if the saved account JSON contains sensitive wallet amount keys:

- `walletBalance`
- `equity`
- `usdValue`
- `totalEquity`
- `cumRealisedPnl`
- `unrealisedPnl`

## Task 3 — Make static dry-run complete

Current static dry-run output may omit `grid_mode` and `cell_number` depending on the file version. Ensure static dry-run uses the same `build_fgrid_validate_payload()` path and always includes:

- `symbol`
- `leverage`
- `grid_mode`
- `grid_type`
- `min_price`
- `max_price`
- `cell_number`
- `init_margin`
- `stop_loss_price`

No old fields are allowed:

- `lowerPrice`
- `upperPrice`
- `gridNum`
- `investment`
- `sampleOnly`
- `category`

## Acceptance commands

Run locally:

```powershell
python -m pytest
ruff check .
python scripts/validate_sample_grid.py --dry-run --symbol BTCUSDT
python scripts/smoke_private_account.py
```

Then inspect `data/metadata/account_info_redacted.json` and confirm it contains no wallet/equity/PnL numbers.

## After this hotfix

Only after this hotfix passes, run real validate-only by setting environment variables locally:

```powershell
$env:GRID_VALIDATE_ENABLED="true"
$env:LIVE_TRADING_ENABLED="false"
$env:ALLOW_LIVE_TRADING="NO"
python scripts/validate_sample_grid.py --dynamic --symbol BTCUSDT --init-margin 100 --cell-number 10 --leverage 1
```

Expected acceptable outcomes:

- validate OK; or
- clean parameter/schema rejection with redacted Bybit response.

Unacceptable outcomes:

- create/close path called;
- secrets shown;
- full wallet balances stored;
- parser treats trading-bot error as success.
