# Codex Prompt — Sprint 01

Скопируй этот prompt в Codex после создания пустого репозитория.

---

Ты senior Python engineer. Создай основу проекта `bybit-grid-research` для исследования и будущего live execution нативного Bybit Futures Grid Bot.

Очень важно: в этом спринте запрещено открывать сделки, создавать grid bot или закрывать live grid bot. Реализуется только API/data feasibility.

Прочитай файлы:

- `00_PROJECT_CONTEXT_FOR_CODEX.md`
- `01_PROJECT_RULES.md`
- `02_TECHNICAL_SPEC.md`
- `03_SPRINT_01_API_DATA_FEASIBILITY.md`

Сделай реализацию Sprint 01.

## Scope Sprint 01

Реализуй:

1. Структуру проекта из technical spec.
2. `pyproject.toml` с зависимостями.
3. `.gitignore` и `.env.example`.
4. Config loader через `pydantic-settings`.
5. Безопасный logger с redaction для API key, secret, signature.
6. Lightweight Bybit V5 REST client на `httpx`:
   - public GET;
   - private signed GET;
   - request retries/backoff;
   - basic rate-limit awareness;
   - structured errors.
7. HMAC signing для Bybit V5 private endpoints.
8. Instruments downloader:
   - `GET /v5/market/instruments-info?category=linear`;
   - cursor pagination;
   - save to Parquet.
9. Tickers snapshot downloader:
   - `GET /v5/market/tickers?category=linear`;
   - save to Parquet.
10. Kline downloader:
   - `GET /v5/market/kline`;
   - interval `1`;
   - limit 1000;
   - chunking;
   - save partitioned Parquet.
11. Mark price kline downloader:
   - `GET /v5/market/mark-price-kline`;
   - interval `1`;
   - limit 1000;
   - save partitioned Parquet.
12. Funding history downloader:
   - `GET /v5/market/funding/history`;
   - limit 200;
   - save partitioned Parquet.
13. Gap detection for 1m klines.
14. Private smoke script:
   - `GET /v5/account/info`;
   - `GET /v5/account/wallet-balance`;
   - save redacted JSON.
15. Validate-only scaffold for Futures Grid Bot:
   - method should call validate endpoint only if configured;
   - no create/close;
   - live trading guard must prevent unsafe operations.
16. CLI scripts:
   - `scripts/smoke_public_api.py`
   - `scripts/smoke_private_account.py`
   - `scripts/download_sample_data.py`
   - `scripts/validate_sample_grid.py`
17. Tests:
   - HMAC signing;
   - secret redaction;
   - storage path generation;
   - gap detection;
   - mocked pagination.
18. Generate `reports/sprint_01_api_report.md` when scripts run.

## Safety requirements

- Default: `LIVE_TRADING_ENABLED=false`.
- `ALLOW_LIVE_TRADING=NO` by default.
- No live create/close functions in Sprint 01.
- If you add placeholder methods for create/close, they must raise `NotImplementedError` and also check safety flags.
- Never log API secret, signature, or raw headers with signature.
- `.env` and `data/` must be ignored by git.
- Code must be readable and modular.
- Prefer explicit errors over silent failures.

## After implementation

Run or provide commands:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .[dev]
python -m pytest
python scripts/smoke_public_api.py
python scripts/download_sample_data.py --symbols BTCUSDT ETHUSDT --days 7
```

Do not ask to implement strategy yet. Finish Sprint 01 only.
