<!-- documentation-contract: current-v1 -->
# Bybit Grid Research

Исследовательский Python-проект для Bybit USDT linear perpetual и нативного Futures Grid Bot в режиме neutral + geometric.

Audit baseline: 2026-07-17, production code after PR #143 at `35a3b9c05b1bf3d86756e449b2735bef0893bc45`. Later governance-only commits do not turn missing capabilities into implemented ones.

## Текущий статус

Это библиотека реализованных и покрытых текущими тестами offline-компонентов и
fail-closed validate-only границы, а не готовый торговый бот. Для поведения,
появившегося в PR #1–66, открыт отдельный retroactive assurance #134. На текущем
main:

- реализованы public-data модели, canonical Parquet store с read-only in-memory DuckDB views, range-компоненты, neutral-grid state machine и OHLC replay;
- private transport разрешает только точные read-only GET и нативный POST /v5/fgridbot/validate;
- generic private POST, create_grid_bot и close_grid_bot недоступны;
- outcome/scoring остаётся proxy-only, parameter selection и risk budget не доказаны;
- единого пути canonical store → range → semantic replay → OOS decision пока нет;
- Telegram runtime, VPS deployment и live execution не реализованы.

Machine-readable capability status:

~~~text
`live_execution_implemented`: `false`
`telegram_runtime_implemented`: `false`
`vps_deployment_implemented`: `false`
~~~

Подробности: [архитектура и статус](docs/CURRENT_ARCHITECTURE_AND_STATUS.md).

## Быстрый offline-старт

Требуется Python 3.12 или новее.

Windows PowerShell:

~~~powershell
git clone https://github.com/brullik/bybit-grid-research.git
Set-Location bybit-grid-research
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
~~~

Linux/macOS:

~~~bash
git clone https://github.com/brullik/bybit-grid-research.git
cd bybit-grid-research
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
~~~

Для offline-проверок оставьте секреты в `.env` пустыми и не добавляйте этот файл
в Git.

Полная безопасная проверка:

~~~bash
python scripts/check_numeric_environment.py
python scripts/check_no_live_execution.py
python -m compileall -q src tests scripts
python -m pytest tests -q
python -m pytest -q
ruff check .
python -m pip check
~~~

Инструкции и диагностика: [SETUP_TEST_RUNBOOK](docs/SETUP_TEST_RUNBOOK.md).

## Нормативная risk policy

- капитал исследования: 500 USDT;
- максимальный общий убыток одной сетки: 5 USDT, это не размер investment;
- максимум одна сетка на инструмент; начальный global concurrency cap — 1;
- только нативный Bybit USDT linear perpetual Futures Grid;
- только neutral + geometric;
- выход V1 только по SL; TP и trailing запрещены;
- API key без withdrawal permission;
- первые live-действия требуют ручного подтверждения в Telegram.

Это обязательные будущие gates, а не доказательство готовой live-системы.

~~~text
`capital_usdt`: `500`
`max_loss_per_grid_usdt`: `5`
`max_grids_per_instrument`: `1`
`initial_global_concurrency_cap`: `1`
`grid_mode`: `neutral`
`grid_type`: `geometric`
`exit_policy`: `SL-only`
`take_profit_enabled`: `false`
`trailing_enabled`: `false`
`withdrawals_authorized`: `false`
`first_live_requires_manual_telegram_confirmation`: `true`
~~~

## Документы

- [Текущий контекст](00_PROJECT_CONTEXT_FOR_CODEX.md)
- [Правила проекта](01_PROJECT_RULES.md)
- [Техническая спецификация](02_TECHNICAL_SPEC.md)
- [Исторический Sprint 01](03_SPRINT_01_API_DATA_FEASIBILITY.md)
- [Исторический prompt Sprint 01](04_CODEX_PROMPT_SPRINT_01.md)
- [Risk и research policy](05_RISK_AND_RESEARCH_POLICY.md)
- [Project Board](PROJECT_BOARD.md)
- [Архитектура и статус](docs/CURRENT_ARCHITECTURE_AND_STATUS.md)
- [Setup/test runbook](docs/SETUP_TEST_RUNBOOK.md)
- [Evidence map](docs/EVIDENCE_MAP.md)
- [Minimal-live Definition of Done](docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md)
- [Безопасный шаблон окружения](.env.example)

Перед любыми credentials необходимо закрыть repository-history gate #133 и соответствующий assurance #134. Секреты запрещено помещать в ChatGPT, GitHub, исходники, issues, PR, логи и fixtures.
