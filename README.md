# Bybit Futures Grid Research Project

Стартовый пакет проекта для разработки системы поиска проторговок и запуска нативного Bybit Futures Grid Bot в режиме `neutral + geometric`.

## Статус проекта

Текущая стадия: **Sprint 01 — API & Data Feasibility**.

Главная цель первой стадии — не искать прибыльную стратегию, а доказать, что проект технически реализуем:

1. Получаем список всех Bybit linear USDT perpetual инструментов с пагинацией.
2. Загружаем 1m OHLCV, mark price kline и funding history.
3. Проверяем качество данных: дыры, дубликаты, порядок свечей.
4. Проверяем тип аккаунта через API.
5. Проверяем, можем ли вызвать Futures Grid Bot validate на mainnet без создания бота.
6. Ничего не открываем в live без отдельного разрешения.

## Как использовать этот пакет

1. Создай пустой GitHub-репозиторий, например `bybit-grid-research`.
2. Скопируй туда эти файлы.
3. Открой репозиторий в Codex.
4. Начни с файла `04_CODEX_PROMPT_SPRINT_01.md`.
5. Никогда не вставляй API secret в ChatGPT, Codex, GitHub issue или commit.

## Документы

- `00_PROJECT_CONTEXT_FOR_CODEX.md` — полный контекст для Codex.
- `01_PROJECT_RULES.md` — зафиксированные правила проекта.
- `02_TECHNICAL_SPEC.md` — техническая архитектура первой версии.
- `03_SPRINT_01_API_DATA_FEASIBILITY.md` — задачи первого спринта.
- `04_CODEX_PROMPT_SPRINT_01.md` — готовый prompt для Codex.
- `05_RISK_AND_RESEARCH_POLICY.md` — правила риска, backtest и research gates.
- `PROJECT_BOARD.md` — доска задач.
- `.env.example` — пример переменных окружения без секретов.
- `pyproject.toml` — стартовые зависимости и настройки проекта.

## Неприкосновенное правило

До завершения Sprint 01 проект работает в режиме **data + validate only**. Создание и закрытие реального grid-бота — отдельный спринт после ручной проверки отчета.
