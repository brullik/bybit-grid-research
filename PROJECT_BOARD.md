# Project Board

Актуальный источник активной implementation authority — pm_acceptance/active_task.json. Этот файл доски не предоставляет полномочий на реализацию или live-операции.

## Завершено и принято

- Sprints 01–06.3B: исторические компоненты, требующие assurance для PR #1–66.
- 06.4A–06.4F: строгие offline/store и historical-evidence границы.
- P0 fail-closed private transport: task #135, erratum #140, RED #141, implementation #142, close #143.
- Документация #132: task #144, RED #145 закрыт без merge, implementation #146 — этот комплект документов; его merge является publication evidence.
- После каждого task-close каноническое состояние должно быть NO_ACTIVE_IMPLEMENTATION; проверять нужно active_task.json, а не эту доску.

## Приоритетный порядок

1. #133 — full-history secret scan, ref inventory и retention policy; обязательный gate до credentials.
2. #134 — staged assurance текущего main для поведения, введённого PR #1–66.
3. #129 — сначала исправить заблокированный pre-freeze acceptance profile, затем новый lifecycle deterministic archive.
4. #131 — разбить canonical offline E2E на ограниченные PM-задачи.

## Заблокировано

- Публикация старой WIP-ветки 06.4G: frozen suite не покрывает заявленные cap/overflow границы.
- Реальные credentials: до чистого #133 и security assurance.
- Parameter selection: до semantic replay, risk proof и walk-forward/OOS gates.
- Live create/close, Telegram runtime и VPS deployment: не реализованы и не авторизованы.

## Целевой offline-путь

historical evidence → canonical store → range candidates → neutral geometric semantic replay → fees/funding/spread/slippage/SL → walk-forward/OOS → bounded decision.

Каждый пункт реализуется отдельным lifecycle: PM task-definition → обязательный RED probe, закрытый без merge → fresh-main implementation → отдельный task-close.
