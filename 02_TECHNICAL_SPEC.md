# Technical Specification

## 1. Architecture V1

Проект делится на модули:

```text
bybit-grid-research/
  README.md
  pyproject.toml
  .env.example
  .gitignore
  config/
    research.yaml
    risk.yaml
    bybit.yaml
  src/
    bybit_grid/
      __init__.py
      config.py
      logging.py
      bybit/
        __init__.py
        client.py
        signing.py
        models.py
        rate_limit.py
      data/
        __init__.py
        instruments.py
        tickers.py
        klines.py
        mark_klines.py
        funding.py
        quality.py
        storage.py
      research/
        __init__.py
        range_candidates.py
        features.py
      backtest/
        __init__.py
        grid_simulator.py
      live/
        __init__.py
        signal_engine.py
        execution_engine.py
        risk_manager.py
        telegram_bot.py
        state_store.py
  scripts/
    smoke_public_api.py
    smoke_private_account.py
    download_sample_data.py
    validate_sample_grid.py
  tests/
    test_signing.py
    test_storage_paths.py
    test_gap_detection.py
  data/
    raw/
    processed/
    metadata/
  reports/
```

В Sprint 01 реализуются только:

- `bybit/client.py`
- `bybit/signing.py`
- `bybit/rate_limit.py`
- `data/instruments.py`
- `data/tickers.py`
- `data/klines.py`
- `data/mark_klines.py`
- `data/funding.py`
- `data/quality.py`
- `data/storage.py`
- smoke scripts
- tests

Research/backtest/live модули создаются как пустые package files или placeholders, но не реализуются.

## 2. Dependencies

```toml
python = ">=3.12"
httpx = "*"
pydantic = "*"
pydantic-settings = "*"
python-dotenv = "*"
tenacity = "*"
polars = "*"
pyarrow = "*"
duckdb = "*"
pytest = "*"
ruff = "*"
```

## 3. Environment variables

```text
BYBIT_ENV=mainnet
BYBIT_API_BASE_URL=https://api.bybit.com
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_RECV_WINDOW=5000
LIVE_TRADING_ENABLED=false
ALLOW_LIVE_TRADING=NO
DATA_DIR=./data
LOG_LEVEL=INFO
```

## 4. Bybit endpoints needed in Sprint 01

Public:

- `GET /v5/market/instruments-info?category=linear`
- `GET /v5/market/tickers?category=linear`
- `GET /v5/market/kline?category=linear&symbol=...&interval=1&start=...&end=...&limit=1000`
- `GET /v5/market/mark-price-kline?category=linear&symbol=...&interval=1&start=...&end=...&limit=1000`
- `GET /v5/market/funding/history?category=linear&symbol=...&startTime=...&endTime=...&limit=200`

Private:

- `GET /v5/account/info`
- `GET /v5/account/wallet-balance`
- Futures Grid Bot validate endpoint, if accessible on account. Validate only. No create.

## 5. Storage layout

```text
data/
  metadata/
    instruments_linear.parquet
    tickers_linear_snapshot_YYYYMMDD_HHMMSS.parquet
    account_info_redacted.json
  raw/
    klines/
      symbol=BTCUSDT/year=2026/month=07/part.parquet
    mark_klines/
      symbol=BTCUSDT/year=2026/month=07/part.parquet
    funding/
      symbol=BTCUSDT/year=2026/part.parquet
  quality/
    gap_report_YYYYMMDD_HHMMSS.parquet
  reports/
    sprint_01_api_report.md
```

## 6. Kline schema

```text
symbol: str
category: str
open_time_ms: int64
open_time_utc: datetime[ms]
open: float64
high: float64
low: float64
close: float64
volume: float64
turnover: float64
source: str
fetched_at_ms: int64
```

## 7. Funding schema

```text
symbol: str
category: str
funding_rate_timestamp_ms: int64
funding_rate: float64
source: str
fetched_at_ms: int64
```

## 8. Data quality checks

Minimum checks:

- no duplicate `(symbol, open_time_ms)`;
- candles sorted ascending after normalization;
- expected 1m interval exactly 60_000 ms;
- missing intervals reported;
- overlapping downloaded windows de-duplicated;
- raw API rows are normalized consistently;
- start/end boundaries included in report;
- retry failed chunks.

## 9. CLI scripts expected

```bash
python scripts/smoke_public_api.py
python scripts/smoke_private_account.py
python scripts/download_sample_data.py --symbols BTCUSDT ETHUSDT --days 7
python scripts/validate_sample_grid.py --symbol BTCUSDT --dry-run
```

All scripts must run safely without live trading.

## 10. Testing

Sprint 01 requires tests for:

- HMAC signing string construction;
- redaction of secrets in logs;
- Parquet path builder;
- gap detection on synthetic candles;
- pagination handling with mocked responses.
<!-- RED probe only: no documentation behavior -->
