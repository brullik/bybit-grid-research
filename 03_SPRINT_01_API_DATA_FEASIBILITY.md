# Sprint 01 — API & Data Feasibility

## Sprint goal

Доказать, что проект может надежно работать с Bybit API и локальным хранилищем данных без открытия сделок.

В этом спринте запрещено:

- реализовывать стратегию проторговки;
- реализовывать backtest;
- открывать grid bot;
- закрывать live grid bot;
- добавлять ML;
- оптимизировать параметры.

## Deliverables

К концу Sprint 01 должны быть готовы:

1. GitHub repository с базовой структурой проекта.
2. `.env.example` без секретов.
3. Bybit V5 REST client.
4. HMAC signing для private endpoints.
5. Redacted logging.
6. Получение всех linear instruments через pagination.
7. Получение tickers и 24h volume/turnover.
8. Загрузка sample 1m OHLCV.
9. Загрузка sample mark price kline.
10. Загрузка sample funding history.
11. Проверка дыр в данных.
12. Проверка account info / UTA status.
13. Validate-only проверка Futures Grid Bot, если endpoint доступен.
14. `reports/sprint_01_api_report.md`.
15. Минимальные pytest tests.

## Task list

### T01 — Repository bootstrap

Создать структуру проекта, `pyproject.toml`, `.gitignore`, `README.md`, `src/`, `scripts/`, `tests/`, `data/`, `reports/`.

Acceptance criteria:

- `python -m pytest` запускается.
- `.env` в `.gitignore`.
- `data/` в `.gitignore`, кроме `.gitkeep`.

### T02 — Config and secrets

Реализовать config loader через `pydantic-settings` и `.env`.

Acceptance criteria:

- Без `.env` public scripts работают.
- Private scripts требуют API key/secret и дают понятную ошибку, если ключей нет.
- Secret не печатается в логах.

### T03 — Bybit public client

Реализовать `BybitClient.public_get()` с retries/backoff.

Acceptance criteria:

- Умеет вызывать market endpoints.
- Логирует endpoint, status, retCode, retMsg.
- Обрабатывает rate limit / temporary failure.

### T04 — Instruments downloader

Реализовать загрузку всех `category=linear` instruments через cursor.

Acceptance criteria:

- Получены все страницы.
- Сохранен `data/metadata/instruments_linear.parquet`.
- В отчете есть количество symbols по status.
- PreLaunch исключаются из trading universe V1.

### T05 — Tickers snapshot and liquidity filter

Получить tickers и сохранить snapshot.

Acceptance criteria:

- Сохранен Parquet snapshot.
- В отчете есть top/bottom by turnover24h.
- Минимальный volume threshold пока не фиксируется стратегически; он выносится в будущий research, но поле готово.

### T06 — Kline downloader sample

Скачать 1m OHLCV за 7 дней для BTCUSDT, ETHUSDT и 1–3 ликвидных альтов.

Acceptance criteria:

- Используется limit=1000 и chunking.
- Сохраняется partitioned Parquet.
- Нет дублей после повторного запуска.

### T07 — Mark price kline downloader sample

Скачать mark price kline за тот же период и symbols.

Acceptance criteria:

- Схема совместима с OHLCV.
- Отдельный storage path.

### T08 — Funding history sample

Скачать funding history для sample symbols.

Acceptance criteria:

- Учитывается лимит 200.
- Сохраняется funding Parquet.

### T09 — Gap detection

Реализовать проверку 1m gaps.

Acceptance criteria:

- На synthetic data тесты проходят.
- На sample data создается `data/quality/gap_report_*.parquet`.
- Отчет показывает количество missing minutes по symbol.

### T10 — Private account smoke

Реализовать signed GET `/v5/account/info` и wallet balance.

Acceptance criteria:

- Без секретов скрипт не падает stacktrace, а дает понятную ошибку.
- С секретами сохраняется redacted JSON.
- В отчете показан account mode / UTA status, если API его вернул.

### T11 — Futures grid validate-only smoke

Сделать метод validate-only для Futures Grid Bot, без create.

Acceptance criteria:

- Никаких live create/close методов не вызывается.
- Если endpoint недоступен, отчет фиксирует ошибку и статус.
- Если endpoint доступен, отчет сохраняет допустимые ranges для 1–3 symbols.

### T12 — Sprint report

Создать `reports/sprint_01_api_report.md`.

Report must include:

- дата запуска;
- env: mainnet/testnet/demo;
- public API status;
- number of linear instruments;
- number of Trading symbols;
- sample data coverage;
- gap summary;
- account info summary;
- grid validate status;
- blockers;
- next sprint recommendation.

## Sprint gate

Sprint 01 считается завершенным только если:

- Все public data scripts работают.
- Account info получен или причина невозможности ясно зафиксирована.
- Futures Grid validate либо прошел, либо его невозможность подтверждена отчетом.
- В репозитории нет секретов.
- Есть gap report.
- Есть sprint report.
- `pytest` зеленый.

Если validate не работает на demo/testnet, это не блокер. Если validate не работает на mainnet с нужными permission/account mode, это блокер до решения.
