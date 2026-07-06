# Project Context for Codex

Ты помогаешь разрабатывать Python-проект `bybit-grid-research`.

## Цель

Создать исследовательскую и live-систему для Bybit USDT perpetual futures, которая:

1. На истории 1m ищет статистически устойчивые параметры проторговок.
2. Backtest-движок проверяет найденные параметры без lookahead.
3. Live-движок ищет текущие проторговки.
4. Execution-движок в будущем будет создавать нативный Bybit Futures Grid Bot в режиме `neutral + geometric`.
5. Telegram будет использоваться для уведомлений, статуса, ручного подтверждения и emergency stop.

## Важные пользовательские вводные

- Стартовый капитал: 500 USDT.
- Биржа: только Bybit на первом этапе.
- Инструменты: USDT perpetual futures, все доступные ликвидные инструменты.
- Таймфрейм сигналов и исследования: 1m.
- Grid bot: только нативный Bybit Futures Grid Bot.
- Режим grid: neutral + geometric.
- TP: не используется в V1.
- Trailing up/down: запрещен в V1 и не добавляется без отдельного research-проекта.
- Выход из сетки: только SL в V1.
- Максимальный риск на сетку: 5 USDT как максимальный убыток, не как investment.
- Если Bybit validate требует investment выше допустимого — инструмент/сигнал пропускается.
- Mainnet допускается только с минимальными суммами, потому что demo/testnet может не поддерживать native futures grid bot полностью.
- API key: read + trade, без withdrawal. На Sprint 01 желательно начать с read-only, а read+trade использовать только когда понадобится private validate.
- Subaccount на старте не используется, поэтому live-защита должна быть жестче.
- Telegram: нужен статус, сигналы, bot created, bot closed, SL, daily report, error, emergency.
- Semi-auto допускается только после 100 завершенных ручных live/paper операций без системных ошибок и после прохождения performance gates.
- Локальная ОС: Windows.
- Начинаем с обычного Python venv, Docker позже.
- Хранилище: Parquet + DuckDB для research; SQLite для live state. PostgreSQL не нужен до VPS/масштабирования.
- Диск под данные: около 250 GB.

## Текущий спринт

Текущий спринт — Sprint 01: API & Data Feasibility.

Не реализуй стратегию проторговки в первом спринте. Не реализуй live create. Не реализуй backtest. Цель — надежный фундамент:

- Bybit public/private client.
- Получение instruments/tickers.
- Загрузка sample OHLCV 1m, mark price kline, funding history.
- Проверка data gaps.
- Проверка account info / UTA status.
- Подготовка validate-only вызова Futures Grid Bot, без создания бота.

## Safety rules for code

- Default mode: `LIVE_TRADING_ENABLED=false`.
- Любая функция create/close должна быть недоступна, пока явно не задано `ALLOW_LIVE_TRADING=YES` и не передан runtime-флаг `--live`.
- Никогда не логировать API secret, signature, raw Authorization/sign headers.
- `.env` должен быть в `.gitignore`.
- Все API responses сохранять в redacted-виде.
- Любое исключение API должно включать endpoint, retCode/status_code, retMsg/debug_msg, но не секреты.
- Все timestamp хранить в UTC ms.
- Везде использовать idempotency там, где возможно.

## Preferred stack

- Python 3.12+
- httpx
- pydantic / pydantic-settings
- python-dotenv
- tenacity
- polars
- pyarrow
- duckdb
- pytest
- ruff

## Important implementation guidance

- Не полагайся на CCXT для native futures grid bot. Для Bybit V5 REST сделай собственный lightweight client с HMAC signing.
- Market endpoints можно вызывать без API key.
- Private endpoints подписывать через Bybit V5 HMAC rules.
- В downloader добавить pagination/rate-limit/backoff.
- Для instruments-info обязательно использовать cursor, потому что linear symbols может быть больше 500.
- Для klines учитывать, что limit максимум 1000 свечей за запрос.
- Для funding history учитывать limit 200.
- Данные хранить partitioned Parquet.
