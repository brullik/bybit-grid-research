# PM Review — Sprint 01 + Sprint 01.5 Hotfix Prompt

Дата: 2026-07-06
Статус Sprint 01: **условно принят, Gate 1 не закрыт**

## 1. PM verdict

Sprint 01 выполнил главную цель: создан безопасный фундамент API/data без live execution. Код содержит guardrails, redaction, public/private client, downloaders, storage helpers, gap detection, CLI scripts и тесты.

Но Gate 1 нельзя закрывать, пока не исправлены hotfix-блокеры ниже и не выполнен локальный smoke run с машины/сети владельца проекта.

Решение: **не начинать Sprint 02 Research**. Сначала выполнить **Sprint 01.5 — API/data correctness hotfix + local verification**.

## 2. Что принимается

Принято:

- secure defaults: `LIVE_TRADING_ENABLED=false`, `ALLOW_LIVE_TRADING=NO`;
- credentials required only for private calls;
- no create/close implementation in Sprint 01;
- redacted logging helper;
- HMAC signing baseline;
- lightweight HTTP client;
- instruments pagination;
- 1m kline chunking;
- Parquet partition storage;
- funding downloader baseline;
- CLI scripts baseline;
- placeholder packages for research/backtest/live;
- test baseline.

## 3. Blockers before Gate 1

### B1 — Futures Grid validate endpoint path/method is wrong

Current code uses:

```env
BYBIT_GRID_VALIDATE_PATH=/v5/grid-bot/order/validate
```

and calls it via private GET.

Required hotfix:

- futures grid validate endpoint must be configurable as `/v5/fgridbot/validate`;
- validate must use private POST, not GET;
- create/close must remain placeholders and forbidden.

### B2 — private POST signing is missing

Current client signs GET query strings only. Validate needs POST JSON body signing.

Required hotfix:

- add `private_post(endpoint, body)`;
- sign exact compact JSON body string;
- send the same exact body string as request content;
- add `Content-Type: application/json`;
- test that signed body equals sent body.

### B3 — GET signing may mismatch actual query order

Current code builds sorted canonical query but passes a plain params dict to httpx. If httpx sends a different query order than the signed string, private GET signatures can fail.

Required hotfix:

- for private GET, build the query string yourself;
- sign exactly that string;
- send request using `endpoint + '?' + query_string`, not unordered params;
- add regression test.

### B4 — mark-price kline parser is incompatible with Bybit response

Normal market klines have 7 fields: time, open, high, low, close, volume, turnover.

Mark-price klines have only 5 fields: time, open, high, low, close.

Current mark downloader reuses normal kline parser and will index missing volume/turnover.

Required hotfix:

- separate normalizer for mark-price klines;
- store `volume=null`, `turnover=null`, or use separate schema;
- add test with mocked mark-price response.

### B5 — gap detection misses boundary gaps

Current gap detection only checks gaps between returned candles. It does not detect if the first returned candle is later than requested start or the last returned candle is earlier than requested end.

Required hotfix:

- add optional `expected_start_ms` and `expected_end_ms`;
- detect start boundary gap;
- detect end boundary gap;
- add tests.

### B6 — OHLC quality checks are incomplete

Sprint 01 required invalid OHLC checks. Current code has gap detection only.

Required hotfix:

- detect `high < low`;
- detect `high < open` / `high < close`;
- detect `low > open` / `low > close`;
- detect duplicate `(symbol, open_time_ms, source)`;
- include these in sample report.

### B7 — redaction coverage must include API key headers

Current redaction handles `X-BAPI-SIGN`, but add explicit coverage for:

- `X-BAPI-API-KEY`;
- `X-BAPI-TIMESTAMP` is not secret but can be retained;
- `apiKey`, `apiSecret`, `api-key`, `api-secret`;
- nested headers dict.

Add tests.

### B8 — report writer overwrites Sprint report

Current `write_sprint_report` overwrites `reports/sprint_01_api_report.md` every script run. For PM review we need one consolidated report.

Required hotfix:

- write machine-readable JSON for each run under `reports/runs/*.json`;
- write/update consolidated markdown summary;
- include command, start/end UTC, status, counts, output paths, errors.

### B9 — local 403 is unresolved

The container/network returned 403 before Bybit API access. This is not a code failure by itself, but Gate 1 requires a successful public API smoke run from the target Windows machine/network.

Required hotfix output:

- if 403 occurs locally, print a clear diagnostic:
  - target base URL;
  - status code;
  - whether response came from proxy or Bybit;
  - redacted response body first 500 chars;
  - suggested next PM action: verify network/API availability; do not continue to private validate.

## 4. Sprint 01.5 Codex prompt

Copy everything below into Codex.

---

# Codex Task — Sprint 01.5 API/data correctness hotfix

You are working in repository `bybit-grid-research`.

PM decision: Sprint 01 is conditionally accepted, but Gate 1 is not closed. Do not implement strategy, backtest, Telegram, live execution, create grid, or close grid. This task is a correctness/safety hotfix only.

## Hard safety rules

- Do not implement live grid create.
- Do not implement live grid close.
- `create_grid_bot` and `close_grid_bot` must remain guarded placeholders raising `NotImplementedError` after live guard.
- No API secret may be printed, logged, saved, or committed.
- Validate-only may call private POST only when explicitly enabled and credentials are present.
- `--dry-run` must never perform a network request.

## Tasks

### T1. Fix futures grid validate config

Update config and `.env.example`:

```env
GRID_VALIDATE_ENABLED=false
BYBIT_FGRID_VALIDATE_PATH=/v5/fgridbot/validate
BYBIT_FGRID_CREATE_PATH=/v5/fgridbot/create
BYBIT_FGRID_CLOSE_PATH=/v5/fgridbot/close
BYBIT_FGRID_DETAIL_PATH=/v5/fgridbot/detail
```

Keep create/close/detail unused in Sprint 01.5 except for constants/config.

### T2. Add private POST support with exact-body signing

In `src/bybit_grid/bybit/client.py` add:

```python
private_post(endpoint: str, body: dict[str, Any]) -> dict[str, Any]
```

Requirements:

- require private credentials;
- compact JSON body with stable deterministic serialization:
  - `json.dumps(body, separators=(",", ":"), ensure_ascii=False)`;
- sign payload as `timestamp + api_key + recv_window + json_body_string`;
- send `content=json_body_string`, not `json=body`;
- set `Content-Type: application/json`;
- retry only retryable network / 429 / 5xx / Bybit too-many-visits errors;
- no retry for bad signature, invalid params, permission errors.

### T3. Fix private GET signing consistency

For private GET:

- build canonical sorted query string once;
- sign exactly that string;
- send exactly that query string in the URL;
- do not pass an unordered params dict to httpx for signed requests.

Add test proving the signed query string is the same query string sent to httpx.

### T4. Fix validate-only grid scaffold

`validate_grid_bot(payload, runtime_live=False)` should:

- return skipped when `GRID_VALIDATE_ENABLED=false`;
- call `private_post(settings.bybit_fgrid_validate_path, payload)` when enabled;
- never call create/close;
- save redacted result through script.

`scripts/validate_sample_grid.py`:

- `--dry-run` prints and saves redacted payload, no network;
- when not dry-run and enabled, performs validate-only POST;
- default payload should be explicit and marked as sample only;
- if required Bybit fields are missing, script should exit with clear message instead of sending a bad request.

### T5. Fix mark-price kline parsing

Do not reuse normal kline parser blindly.

Implement either:

1. separate `normalize_mark_kline_rows`, or
2. general normalizer that supports both 7-field market kline and 5-field mark-price kline.

Required output columns for mark klines:

- symbol
- category
- open_time_ms
- open_time_utc
- open
- high
- low
- close
- volume nullable
- turnover nullable
- source=`mark-price-kline`
- fetched_at_ms

Add mocked test with a 5-field Bybit mark-price row.

### T6. Upgrade data quality checks

In `src/bybit_grid/data/quality.py` add:

- `detect_duplicate_candles(df)`;
- `detect_bad_ohlc(df)`;
- `detect_1m_gaps(df, expected_start_ms=None, expected_end_ms=None)` with boundary gaps;
- `build_quality_report(df, expected_start_ms=None, expected_end_ms=None)`.

Tests:

- internal missing candle;
- start boundary gap;
- end boundary gap;
- duplicate candle;
- bad OHLC rows.

### T7. Improve redaction coverage

Add redaction support/tests for:

- `X-BAPI-API-KEY`;
- `X-BAPI-SIGN`;
- `apiKey`;
- `apiSecret`;
- `api-key`;
- `api-secret`;
- nested `headers` dict;
- raw strings containing these headers.

### T8. Improve report writing

Replace single overwriting report behavior with:

- append or create per-run JSON under `reports/runs/`;
- regenerate `reports/sprint_01_api_report.md` from available run JSONs;
- include command name, started_at, ended_at, status, counts, output paths, error summary.

### T9. Add network diagnostic for 403/proxy errors

When public smoke receives HTTP 403 or `httpx.ProxyError`, write a diagnostic section into report:

- base URL;
- exception type;
- status if available;
- redacted first 500 chars of response body if available;
- recommended PM action: verify that target network can reach Bybit API before private calls.

### T10. Tests and acceptance

Add or update tests. Acceptance:

```bash
python -m pytest
ruff check .
python scripts/validate_sample_grid.py --dry-run --symbol BTCUSDT
```

Expected:

- tests pass;
- ruff passes;
- dry-run performs no network calls;
- no create/close implementation exists;
- no secrets in logs/reports.

After completion, output:

- changelog;
- files changed;
- exact commands run;
- whether tests passed;
- any remaining blockers.

