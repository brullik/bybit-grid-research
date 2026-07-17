# Project Rules

Нормативный документ. Изменения требуют отдельной PM-задачи.

## 1. Product scope

V1 ограничен Bybit USDT linear perpetual, 1m research и нативным Futures Grid Bot neutral + geometric. Binance/OKX, spot, long/short grid, собственные limit-order сетки, web UI и ML до rule-based evidence не входят в V1.

## 2. Binding risk policy

| Правило | Значение |
|---|---:|
| Research capital | 500 USDT |
| Максимальный общий убыток одной сетки | 5 USDT |
| Сеток на инструмент | 1 |
| Initial global concurrency cap | 1 |
| Grid product | Bybit native USDT linear perpetual Futures Grid |
| Mode / grid type | neutral / geometric |
| Exit | SL-only |
| TP / trailing | запрещены |
| Withdrawal permission | запрещена |
| Первые live-действия | ручное Telegram confirmation |

5 USDT — лимит полного убытка, включая fees, spread, slippage и funding, а не investment. Если sizing/validate не доказывает лимит, кандидат отклоняется.

Exact policy state:

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

## 3. Current authority

Существование кода или flags LIVE_TRADING_ENABLED, ALLOW_LIVE_TRADING и --live не предоставляет authority. Сейчас create_grid_bot, close_grid_bot, ordinary-order mutation, withdrawals, Telegram runtime и live execution недоступны.

Разрешённая private поверхность P0: точные read-only GET /v5/account/info, /v5/account/wallet-balance, /v5/account/fee-rate и точный POST /v5/fgridbot/validate на https://api.bybit.com. Это validate-only boundary, не live authority.

## 4. Secrets and accounts

API key не имеет withdrawal permission. Секреты запрещены в ChatGPT/Codex context, GitHub, source, issues, PR, comments, tests, fixtures, reports и logs. Хранение — только approved runtime secret store. До чистого #133 реальные credentials запрещены.

## 5. Data and research

UTC milliseconds, no lookahead, полный provenance и input commitments обязательны. Canonical Parquet store является целевым источником, а DuckDB предоставляет только read-only in-memory views; silent fallback к legacy data/raw запрещается в будущем E2E. Недостающие funding/history evidence приводят к fail-closed результату.

Range parameters, grid count, sizing и selection не задаются из головы. Current proxy scores не могут использоваться как live recommendation. OOS/test и post-signal fields запрещены для policy selection.

Исходные market data хранятся в UTC. Целевой research store — canonical Parquet; DuckDB предоставляет read-only in-memory views. Ориентир дискового бюджета владельца — 250 GB. Gap detection, de-duplication, coverage evidence и повторная загрузка обязательны. Future live state может использовать SQLite, но сейчас live state store не реализован.

V1 range означает горизонтальный диапазон с доказанными high/low, касаниями обеих зон, возвратом к середине и входом не у границы. Наклонные диапазоны и окна свыше 1440 минут не входят в V1. Minimum lifetime, ATR buffer, false-break treatment, grid levels и SL buffer определяются evidence, а не догадкой.

## 6. Live rules

SL-only. TP, trailing, time stop и profit protection запрещены. Новый сигнал по уже активному инструменту игнорируется. Emergency stop обязан блокировать новые входы до manual resume; поведение уже активных grids должно быть отдельно заморожено и доказано, а не предположено. Первые live-действия требуют Telegram confirmation. Эти правила являются будущими gates; runtime ещё не реализован.

Будущий Telegram V1 должен покрыть status, pause-new-entries, resume, close-one, close-all и emergency-stop, а также signal/create/close/SL/error/emergency notifications. Этот перечень — specification gate, не описание текущей capability.

## 7. Future signal ranking policy

Если после всех fail-closed gates одновременно допустимо больше сигналов, чем разрешает cap, будущий ranking использует только signal-time evidence:

~~~text
score =
  0.35 * expected_value_R
+ 0.20 * robustness_score
+ 0.15 * liquidity_score
+ 0.10 * fill_potential_score
+ 0.10 * capital_efficiency_score
+ 0.10 * regime_score
- 0.25 * tail_risk_score
- 0.15 * funding_penalty_score
~~~

Сначала отбрасываются candidates без risk proof, liquidity/cost sufficiency и exchange feasibility. Формула не разрешена для live selection, пока #131 не даст semantic replay и leakage-free walk-forward evidence.

## 8. Governance

Только pm_acceptance/active_task.json определяет scope. Task-definition, mandatory RED, implementation и task-close разделены. RED probes никогда не merge. Required checks: protected-paths, acceptance Python 3.12, acceptance Python 3.14 и aggregate pm-acceptance. Нельзя bypass/force merge.

## 9. Release blockers

До offline product: #134, исправленный #129 и bounded tasks #131. До credentials: #133 и security assurance. До minimal live: все пункты [Definition of Done](docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md).
