# Project Rules

Дата фиксации: 2026-07-06
Роль документа: правила проекта, которые нельзя менять во время исследования без отдельного change request.

## 1. Scope

Проект строится только вокруг:

- Bybit;
- USDT perpetual futures / linear category;
- 1m OHLCV;
- нативного Bybit Futures Grid Bot;
- режима `neutral`;
- типа сетки `geometric`;
- поиска горизонтальных проторговок;
- Telegram как панели управления.

Не входят в V1:

- Binance/OKX;
- spot grid;
- long grid / short grid;
- собственная сетка через обычные limit orders;
- ML-модель до завершения rule-based research;
- trailing up/down;
- TP;
- time stop;
- profit protection;
- веб-интерфейс;
- Docker до первого рабочего прототипа.

## 2. Risk rules

- Стартовый капитал: 500 USDT.
- Максимальный риск одной сетки: 5 USDT.
- 5 USDT — это не investment, а целевой максимальный убыток по сетке.
- Если Bybit validate требует больше капитала, чем допустимо по risk model, сигнал пропускается.
- Резерв капитала в V1 не выделяется, но live cap вводится через ограничение количества активных сеток.
- Daily stop и weekly stop не включаются, но emergency stop обязателен.
- После emergency stop новые входы запрещены до ручной команды `/resume`.
- На основном аккаунте live-тест разрешен только после data/validate спринта и только с минимальными суммами.
- В live V1 максимальное количество активных сеток начинается с 1. Увеличение до 3 возможно только после smoke-live без ошибок.
- Переход выше 3 активных сеток возможен только после статистики live/paper и backtest-гейта по портфельной просадке.

## 3. Account and security

- API key без withdrawal.
- `.env` не коммитится.
- API secret нельзя вставлять в ChatGPT, Codex, GitHub issue, README, commit или log.
- На Sprint 01 private calls должны быть read-only, если endpoint это позволяет.
- Если validate требует trade permission, используется read+trade key, но live create все равно заблокирован через код.
- Перед любым live create в будущем нужны:
  - Telegram approval;
  - отдельная команда `/confirm_<id>`;
  - проверка `LIVE_TRADING_ENABLED=true`;
  - проверка `ALLOW_LIVE_TRADING=YES`;
  - проверка runtime-флага `--live`.

## 4. Data rules

- Основной источник: Bybit OHLCV 1m.
- Дополнительные источники Bybit: mark price kline, funding history, instruments-info, tickers.
- История качается с `launchTime`, если 7–10 лет недоступны.
- Формат хранения: Parquet + DuckDB.
- Live-state: SQLite.
- PostgreSQL не используется до VPS/масштабирования.
- Максимальный бюджет диска: ориентир 250 GB.
- Проверка дыр и повторная дозагрузка обязательны.
- Все данные хранятся в UTC.
- Все расчеты сигналов запрещают lookahead.

## 5. Range / проторговка rules

В V1 проторговка — горизонтальный диапазон, где:

- есть сформированные high/low границы;
- цена входила в верхнюю и нижнюю зону диапазона;
- цена возвращалась в среднюю зону;
- текущая цена на входе должна быть близко к средней зоне, а не у границы;
- наклонные диапазоны не входят в V1;
- поиск не привязывается к импульсу;
- максимальное окно исследования на 1m: 1440 минут;
- минимум жизни диапазона, ATR buffer, ложные проколы, grid levels и SL buffer не задаются из головы, а подбираются на истории.

## 6. Grid logic rules

- TP отключен в V1.
- Trailing up/down отключен в V1.
- Time stop отключен в V1.
- Profit protection отключен в V1.
- Закрытие по выходу из диапазона отключено в live V1; основной выход — SL.
- Событие выхода из диапазона все равно сохраняется как research outcome, чтобы позже сравнить гипотезу `SL only` против `range-exit close`.
- Если по инструменту уже есть активная сетка, новый сигнал по этому инструменту игнорируется.
- Активная сетка не обновляется, не пересоздается и не расширяется новым сигналом в V1.

## 7. Signal ranking rules

Если одновременно появляется много сигналов, выбирается не первый по времени, а лучший по score:

1. Сначала отбрасываются сигналы, которые не проходят Bybit validate.
2. Затем отбрасываются инструменты ниже минимальной ликвидности.
3. Затем отбрасываются сигналы с плохим fee/funding context.
4. Затем считается composite score:

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

Где `R = 5 USDT`.

## 8. Live rules

- На старте live: manual approval.
- Semi-auto возможен только после 100 завершенных подтвержденных операций без системных ошибок и после performance gates.
- Telegram-команды V1:
  - `/status`
  - `/pause_new_entries`
  - `/resume`
  - `/close_bot <id>`
  - `/close_all`
  - `/emergency_stop`
- Уведомления V1:
  - signal;
  - bot created;
  - bot closed;
  - SL;
  - daily report;
  - error;
  - emergency.

## 9. Change control

Любая новая идея добавляется в `PROJECT_BOARD.md` как backlog item. Она не внедряется в текущий спринт, если не является blocker.
