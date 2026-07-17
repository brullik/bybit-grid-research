# Risk and Research Policy

## 1. Research principle

Параметры не придумываются из головы. Проект идет так:

1. Сначала собираются данные.
2. Потом строятся признаки диапазонов.
3. Потом размечается будущий outcome.
4. Потом ищутся устойчивые зоны параметров.
5. Потом делается реалистичный backtest.
6. Потом shadow/paper live.
7. Потом минимальный live.

Запрещено сначала подобрать параметры под красивый ROI, а потом объяснять их логикой.

## 2. No-lookahead rules

В момент сигнала `t` разрешено использовать только данные `<= t`.

Запрещено:

- брать будущий high/low для построения диапазона;
- использовать будущую длительность диапазона в признаках;
- фильтровать сигналы по информации, которая появляется после входа;
- оптимизировать параметры на том же периоде, где считаем итоговую доходность.

## 3. Dataset split

Минимальная схема:

- Train: поиск первичных зон параметров.
- Validation: отбор устойчивых параметров.
- Test: финальная проверка, один раз.
- Out-of-symbol: отдельная группа symbols, не участвующих в подборе.
- Stress buckets: отдельные рыночные режимы.

## 4. Instrument grouping

Стратегия должна проверяться минимум по группам:

- BTC/ETH;
- high liquidity alts;
- mid liquidity alts;
- low-but-allowed liquidity alts;
- young listings;
- older instruments;
- delisted/closed history, если данные доступны.

No single symbol должен давать больше 20–25% чистой прибыли финального теста. Если дает — стратегия подозрительно зависима от одного инструмента.

## 5. Core metrics

Главные метрики:

- net PnL after fees/funding;
- expectancy per signal in R;
- profit factor;
- max drawdown;
- worst 1% trades;
- consecutive losses;
- risk of ruin / Monte Carlo;
- capital locked minutes;
- signal frequency;
- max simultaneous signals;
- net PnL per capital-minute;
- robustness by symbol group and market regime.

Вторичные метрики:

- raw ROI;
- win rate;
- Sharpe/Sortino.

## 6. Launch gates

Для допуска к shadow/paper:

- no-lookahead backtest готов;
- fees/funding учтены;
- Bybit tick/qty/min investment constraints учтены;
- out-of-sample profit factor >= 1.20;
- expected value after fees/funding > 0;
- worst 1% outcomes не ломают risk model;
- single-symbol concentration <= 25%;
- стратегия работает минимум в нескольких market regimes, а не в одном отрезке.

Для допуска к минимальному real live:

- out-of-sample profit factor >= 1.25;
- expected value >= +0.05R after fees/funding;
- historical portfolio max drawdown при live cap 1–3 сетки <= 20%;
- если max drawdown > 25%, live запрещен;
- Monte Carlo risk of 50% drawdown на горизонте 1000 сигналов <= 10%;
- все Bybit validate checks проходят;
- shadow/paper signals похожи на historical signals по частоте и качеству;
- Telegram emergency и pause/resume проверены.

Для semi-auto:

- минимум 100 завершенных ручных операций без системных ошибок;
- live/paper profit factor >= 1.10;
- нет расхождения между planned risk и фактическим закрытием;
- нет необъясненных Bybit/API ошибок;
- emergency stop протестирован.

## 7. Profit factor thresholds

- `< 1.10`: не торговать.
- `1.10–1.20`: только research, не live.
- `1.20–1.25`: допустимо shadow/paper.
- `1.25–1.50`: допустимо минимальный real live.
- `1.50+`: сильный кандидат, но все равно нужен robustness check.

## 8. Expected value thresholds

`R = 5 USDT`.

- Minimum for paper: EV > 0 after all costs.
- Minimum for live: EV >= +0.05R, то есть примерно +0.25 USDT на сигнал.
- Preferred: EV >= +0.10R, то есть примерно +0.50 USDT на сигнал.
- Excellent: EV >= +0.20R, то есть примерно +1.00 USDT на сигнал.

## 9. Rare vs frequent strategies

Для депозита 500 USDT предпочтение получает не самая редкая стратегия с огромным ROI, а стратегия с:

- достаточной частотой сигналов;
- положительным EV;
- контролируемым tail risk;
- невысокой просадкой;
- устойчивостью на разных инструментах.

Редкая сверхприбыльная стратегия может быть добавлена позже как отдельный режим, но она не должна быть основным способом раскачки депозита.

## 10. Duplicate signal rule

Если по symbol уже есть активная сетка:

- новый сигнал игнорируется;
- параметры активной сетки не обновляются;
- бот не пересоздается;
- событие нового сигнала сохраняется в лог как `duplicate_signal_ignored`.

Причина: пересоздание усложняет backtest/live equivalence и добавляет операционный риск.

## 11. Ranking when many signals appear

Если одновременно появилось больше сигналов, чем можно открыть, используется score:

```text
score =
  0.35 * expected_value_R
+ 0.20 * robustness_score
+ 0.15 * liquidity_score
+ 0.10 * fill_potential_score
+ 0.10 * capital_efficiency_score
+ 0.10 * regime_score
- 0.25 * tail_risk_score
- 0.15 * funding_penalty_score
```

Tie-breakers:

1. higher liquidity;
2. lower tail risk;
3. lower funding penalty;
4. lower correlation with already active symbols;
5. earlier signal time.

## 12. Trailing up/down decision

Trailing up/down запрещен в V1.

Причина: это меняет природу стратегии. Мы исследуем grid внутри проторговки, а trailing превращает сетку в адаптивную стратегию следования за рынком. Это отдельный research-проект, который нельзя смешивать с первым тестом.
<!-- RED probe only: no documentation behavior -->
