# Current Project Context for Codex

## Цель

Развить bybit-grid-research в доказуемый offline research product, а затем — только после отдельных gates — в управляемую систему нативного Bybit Futures Grid Bot.

## Фактический статус

Текущий код не является готовым торговым роботом. Реализованы строгие компоненты public data, canonical store, range research, neutral-grid/OHLC semantics и fail-closed validate-only transport. Не соединены canonical store, detector, semantic replay, OOS scoring и bounded decision. Live/Telegram/VPS отсутствуют.

Текущий статус и разрывы описаны в [CURRENT_ARCHITECTURE_AND_STATUS](docs/CURRENT_ARCHITECTURE_AND_STATUS.md). Активную implementation authority определяет только pm_acceptance/active_task.json.

## Binding scope

- Bybit, USDT linear perpetual, данные 1m.
- Нативный Futures Grid Bot.
- neutral + geometric.
- SL-only; TP, trailing, time stop и profit protection запрещены в V1.
- Капитал 500 USDT; максимум 5 USDT общего убытка на сетку.
- Одна сетка на инструмент; initial global cap 1.
- API без withdrawal permission.
- Первые live-действия — только после ручного Telegram confirmation.

## Governance

Перед любой работой сначала прочитать AGENTS.md, затем pm_acceptance/active_task.json и frozen contract активной задачи. `NO_ACTIVE_IMPLEMENTATION` означает отсутствие production-edit authority.

Implementation PR может менять только allowed paths активной PM-задачи. Frozen acceptance нельзя ослаблять. Probe-ветки всегда закрываются без merge. Собственный непробный PR допускается к merge только при неизменном head SHA, точном scope, всех зелёных checks и отсутствии unresolved review.

Любые credentials, private/local Bybit runs, live actions или новые endpoint authority требуют отдельного owner checkpoint. Флаги конфигурации сами по себе authority не создают.

## Текущий порядок работы

1. Правдивая документация #132.
2. Repository-history gate #133 до credentials.
3. Assurance #134 по текущему main без исполнения старых веток.
4. Исправление pre-freeze #129.
5. Ограниченные задачи umbrella #131 до deterministic offline E2E.
6. Owner-provided public history только после synthetic E2E.
7. Live design — отдельный будущий проект после выполнения Definition of Done.

Не использовать устаревшие 03/04 документы как инструкции: они сохранены только как исторический архив.
