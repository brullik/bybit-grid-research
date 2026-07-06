# Sprint 01.7 — Private Read + Futures Grid Validate-Only

PM decision: Sprint 01.6 public/data path is accepted. Gate 1 is not fully closed until private read and futures-grid validate-only are verified on the owner’s Windows machine.

## Hard safety rules

- Do not implement live grid creation.
- Do not implement live grid closing.
- `create_grid_bot()` and `close_grid_bot()` must remain guarded `NotImplementedError` placeholders.
- No script may place orders, create positions, create grid bots, close grid bots, transfer assets, or change account settings.
- `.env` must never be printed, committed, or copied into reports.
- API key, API secret, signatures, and signed headers must be redacted in all logs/reports.
- `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_TRADING=NO` remain the default.
- `GRID_VALIDATE_ENABLED=false` remains the default; real validate-only runs only when the owner explicitly sets it to true locally.

## Context

Sprint 01.6 is green on the owner’s Windows machine:

- `python -m pytest`: 16 passed.
- `ruff check .`: passed.
- `validate_sample_grid --dry-run`: no network request.
- `smoke_public_api`: Bybit public API reachable.
- `download_sample_data`: BTCUSDT/ETHUSDT 7-day sample completed.
- Result: 20160 kline rows, 20160 mark-kline rows, 42 funding rows, gaps=0, duplicates=0, bad_ohlc=0.

Current blocker: private account smoke and futures-grid validate-only are not verified yet.

## Important correction before real validate

The current dry-run payload uses old/unsafe field names:

```json
{
  "category": "linear",
  "symbol": "BTCUSDT",
  "lowerPrice": "50000",
  "upperPrice": "80000",
  "gridNum": 10,
  "investment": "100"
}
```

For futures grid validate, update the payload builder to use the fgrid-style schema. Required fields to support:

```text
symbol
leverage
grid_mode
grid_type
max_price
min_price
cell_number
```

Optional fields to support:

```text
entry_price
init_margin
stop_loss_price
stop_loss_per
take_profit_price
take_profit_per
tp_sl_type
move_up_price
move_down_price
trailing_stop_per
```

For this sprint, do not enable TP, trailing, move up, or move down.

Use defaults for the project strategy:

```text
symbol = BTCUSDT
leverage = 1
cell_number = 10
init_margin = 100
mode = neutral
shape = geometric
```

Keep mode/type as configurable constants because Bybit may require numeric enum values. Add these settings with defaults:

```env
BYBIT_FGRID_GRID_MODE_NEUTRAL=1
BYBIT_FGRID_GRID_TYPE_GEOMETRIC=2
```

If validate returns a parameter/schema error, do not guess silently. Save the full redacted response and fail clearly with a PM action message.

## Task 1 — Harden private account smoke

Update `scripts/smoke_private_account.py` so it:

1. Requires private credentials.
2. Calls `GET /v5/account/info`.
3. Attempts safe read-only wallet/account balance calls without printing sensitive amounts to stdout.
4. Saves redacted raw JSON to:

```text
data/metadata/account_info_redacted.json
```

5. Writes a structured report run into `reports/sprint_01_api_report.md` with:

```text
command
status
account_info_status
unifiedMarginStatus
marginMode
wallet_read_status
output_paths
error_summary
```

6. If wallet balance fails for `UNIFIED`, do not crash immediately. Record the error and continue account-info summary. Do not try transfers or account modifications.

## Task 2 — Dynamic futures-grid validate payload builder

Add a small module, for example:

```text
src/bybit_grid/bybit/fgrid_payloads.py
```

Implement:

```python
build_fgrid_validate_payload(
    symbol: str,
    last_price: Decimal,
    tick_size: Decimal,
    leverage: Decimal | int = 1,
    grid_mode: int | str = settings.bybit_fgrid_grid_mode_neutral,
    grid_type: int | str = settings.bybit_fgrid_grid_type_geometric,
    cell_number: int = 10,
    init_margin: Decimal | str = "100",
    lower_mult: Decimal = Decimal("0.90"),
    upper_mult: Decimal = Decimal("1.10"),
    stop_loss_mult: Decimal = Decimal("0.85"),
) -> dict[str, Any]
```

Rules:

- Fetch `lastPrice` from public tickers.
- Fetch `tickSize` from instruments-info.
- Round `min_price`, `max_price`, `stop_loss_price` down/up to tick size safely.
- Ensure `min_price < last_price < max_price`.
- Ensure `stop_loss_price < min_price`.
- Do not include take profit.
- Do not include trailing fields.
- Do not include `sampleOnly` in real validate payload.

Expected payload shape:

```json
{
  "symbol": "BTCUSDT",
  "leverage": "1",
  "grid_mode": 1,
  "grid_type": 2,
  "min_price": "...",
  "max_price": "...",
  "cell_number": 10,
  "init_margin": "100",
  "stop_loss_price": "..."
}
```

## Task 3 — Update `scripts/validate_sample_grid.py`

Requirements:

1. `--dry-run` must still perform zero network requests unless `--dynamic` is explicitly used.
2. Add `--dynamic` to build a market-based payload using public ticker + instruments-info.
3. Add `--init-margin`, `--cell-number`, `--leverage`, `--lower-mult`, `--upper-mult`, `--stop-loss-mult` CLI args.
4. Add `--payload-json PATH` to allow sending a custom payload file for validate-only.
5. Non-dry-run path must refuse to run unless:

```env
GRID_VALIDATE_ENABLED=true
BYBIT_API_KEY is present
BYBIT_API_SECRET is present
LIVE_TRADING_ENABLED=false
ALLOW_LIVE_TRADING=NO
```

6. Non-dry-run path must call only:

```text
POST /v5/fgridbot/validate
```

7. Save redacted payload and response to:

```text
data/metadata/grid_validate_payload_redacted.json
data/metadata/grid_validate_response_redacted.json
```

8. Write a run to `reports/sprint_01_api_report.md` with:

```text
command
status
symbol
payload_mode: static|dynamic|payload-json
validate_endpoint
retCode
retMsg
check_code if present
output_paths
error_summary
```

## Task 4 — Tests

Add tests for:

- fgrid validate payload contains fgrid schema fields and not old fields.
- min/max/SL rounding respects tick size.
- dynamic payload rejects invalid `min >= max`.
- non-dry-run refuses when `GRID_VALIDATE_ENABLED=false`.
- create/close remain `NotImplementedError`.
- redaction still covers payload/response with headers and secret-like keys.

## Commands after implementation

Run locally:

```powershell
python -m pytest
ruff check .
python scripts/validate_sample_grid.py --dry-run --symbol BTCUSDT
python scripts/validate_sample_grid.py --dry-run --dynamic --symbol BTCUSDT
python scripts/smoke_private_account.py
```

Then, only after `.env` contains credentials and `GRID_VALIDATE_ENABLED=true`:

```powershell
python scripts/validate_sample_grid.py --dynamic --symbol BTCUSDT --init-margin 100 --cell-number 10 --leverage 1
```

## Acceptance criteria

- `pytest` passes.
- `ruff check .` passes.
- Static dry-run performs no network request.
- Dynamic dry-run uses public market data only and prints/saves redacted payload.
- Private account smoke saves redacted account info.
- Real validate-only either succeeds or fails with a clear redacted Bybit validation response.
- No live create/close code exists.
- No secrets in reports/logs.
- `reports/sprint_01_api_report.md` includes account smoke and validate-only results.

## PM output required from owner after this sprint

Paste back:

```text
commit hash
files changed
python -m pytest output
ruff check . output
validate_sample_grid --dry-run output
validate_sample_grid --dry-run --dynamic output
smoke_private_account output, with no secrets
validate_sample_grid --dynamic real validate output, with no secrets
summary of reports/sprint_01_api_report.md
```
