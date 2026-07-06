# Project Board

## Now — Sprint 01

| ID | Task | Owner | Status | Gate |
|---|---|---:|---|---|
| S01-T01 | Repository bootstrap | Codex | Todo | pytest runs |
| S01-T02 | Config and `.env.example` | Codex | Todo | no secrets in repo |
| S01-T03 | Bybit public client | Codex | Todo | public smoke passes |
| S01-T04 | Bybit HMAC signing | Codex | Todo | signing tests pass |
| S01-T05 | Instruments downloader | Codex | Todo | all linear pages saved |
| S01-T06 | Tickers snapshot | Codex | Todo | liquidity fields saved |
| S01-T07 | 1m kline sample downloader | Codex | Todo | sample parquet saved |
| S01-T08 | Mark price sample downloader | Codex | Todo | sample parquet saved |
| S01-T09 | Funding sample downloader | Codex | Todo | funding parquet saved |
| S01-T10 | Data gap checker | Codex | Todo | gap report generated |
| S01-T11 | Account info smoke | Codex/User | Todo | account mode known |
| S01-T12 | Futures grid validate-only smoke | Codex/User | Todo | validate status known |
| S01-T13 | Sprint report | Codex | Todo | report exists |

## Next — Sprint 02

Goal: build first research dataset, not strategy optimization.

Candidate tasks:

- Define range candidate schema.
- Generate synthetic OHLCV tests for range detector.
- Implement basic horizontal range candidate detector without lookahead.
- Calculate features: range height pct, ATR, midline crosses, touches, amplitude score.
- Build event table for candidates.
- Produce first exploratory report on 10–50 symbols.

## Later

- Sprint 03: outcome labeling and primitive grid simulator.
- Sprint 04: parameter mining and robustness checks.
- Sprint 05: realistic backtest with Bybit constraints.
- Sprint 06: live signal engine in shadow mode.
- Sprint 07: Telegram control panel.
- Sprint 08: execution engine validate/create/close with manual approval.
- Sprint 09: minimal real live.
