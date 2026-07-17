# Risk and Research Policy

## Binding risk

| Поле | Норматив |
|---|---:|
| capital_usdt | 500 |
| max_total_loss_per_grid_usdt | 5 |
| max_grids_per_instrument | 1 |
| initial_global_concurrency_cap | 1 |
| product | Bybit native USDT linear perpetual Futures Grid |
| mode | neutral |
| grid_type | geometric |
| exit | SL-only |
| TP | forbidden |
| trailing | forbidden |
| withdrawal permission | forbidden |
| first live actions | manual Telegram confirmation |

5 USDT — максимальный полный убыток, не investment. Полный worst-case включает fees, spread, slippage, funding и forced SL. Недоказанный risk budget означает rejection.

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

## Research gates

До выбора параметров обязательны:

- canonical input provenance and coverage;
- no-lookahead features frozen at signal time;
- semantic neutral-grid replay, а не crossing proxies;
- native quantity/level mapping and exchange constraints;
- liquidation, fees, spread, slippage, funding and SL accounting;
- train/validation/test or walk-forward separation;
- robustness across time, symbols and cost stress;
- explicit insufficient_evidence/no_policy_passes artifact;
- portfolio concurrency and capital constraints.

Текущее состояние не проходит эти gates: outcome/scoring proxy-only, sufficient_for_parameter_selection=false, risk_budget_proven=false, native equivalence и profitability не доказаны.

## No-lookahead and dataset split

В момент сигнала `t` разрешены только данные `<= t`. Future high/low, lifetime, crossings, death reason, PnL/R и любая фильтрация по post-signal исходу запрещены.

Минимальное разделение evidence:

- Train — формирование первичных зон параметров;
- Validation — выбор устойчивых policy;
- Test — однократная финальная проверка;
- Out-of-symbol — инструменты, не участвовавшие в выборе;
- Stress buckets — отдельные режимы рынка и cost stress.

Результат должен быть устойчив по BTC/ETH, liquidity cohorts, возрасту листинга и доступной closed/delisted истории. Один symbol не может давать более 25% итоговой net profit.

## Required metrics

Основные метрики: net PnL after all costs, expectancy в R, profit factor, max drawdown, worst 1%, consecutive losses, Monte Carlo/risk of ruin, capital locked minutes, frequency, simultaneous signals, capital efficiency и robustness по symbol/regime. Raw ROI, win rate и Sharpe/Sortino вторичны.

## Promotion thresholds

Для shadow/paper требуются no-lookahead backtest, exchange constraints, полные costs, OOS profit factor >= 1.20, положительный EV, сохранённый 5 USDT risk model и single-symbol concentration <= 25%.

Для minimal live дополнительно требуются:

- OOS profit factor >= 1.25;
- EV >= +0.05R after all costs, где R = 5 USDT;
- historical portfolio max drawdown при cap 1–3 <= 20%;
- max drawdown > 25% означает автоматический NO-GO;
- Monte Carlo probability 50% drawdown за 1000 signals <= 10%;
- Bybit validate, shadow comparability и Telegram emergency/pause/resume gates.

Profit factor interpretation: `<1.10` — NO-GO; `1.10–1.20` — research only; `1.20–1.25` — shadow/paper only; `>=1.25` может стать minimal-live candidate только при прохождении всех остальных gates. Высокий PF не заменяет robustness.

## Prohibited selection inputs

Future net PnL/R, lifetime, future crossings, death reason, oracle rank и любые post-signal values запрещены. OOS/test нельзя использовать для выбора policy.

Если сигнал по symbol уже имеет активную сетку, новый сигнал должен стать `duplicate_signal_ignored`: активная grid не обновляется, не пересоздаётся и не расширяется.

## Live promotion

Paper/owner-public runs возможны только после deterministic synthetic E2E. Private credentials — только после чистого #133 и security assurance. Первые live actions требуют owner checkpoint и manual Telegram confirmation. Semi-auto — не ранее 100 завершённых подтверждённых операций без системных ошибок и прохождения performance gates.

Эта policy задаёт gates, но не утверждает наличие live runtime.

## Evidence truthfulness

Synthetic evidence не является real-market evidence. Validate success не доказывает profitability. Legacy proxy scoring не является native-grid replay. Недостаточное evidence обязано завершаться `insufficient_evidence`, `no_policy_passes` или NO-GO, а не оптимистичным fallback.
