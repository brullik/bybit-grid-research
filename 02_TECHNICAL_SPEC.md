# Technical Specification — Current Architecture

## Runtime and storage

Python >=3.12. Canonical research storage: Parquet; DuckDB создаёт read-only in-memory views. Future live state target: SQLite. PostgreSQL и Docker не требуются до отдельного deployment task.

## Implemented components

| Boundary | Main paths | Status |
|---|---|---|
| Bybit public/private client | src/bybit_grid/bybit | public + exact validate-only boundary |
| Strict historical evidence | src/bybit_grid/data/public_batch/historical_*.py | offline/in-memory through 06.4F |
| Canonical market store | src/bybit_grid/data/market_store | schemas, reader/writer, atomicity, audit, coverage/resume, DuckDB views |
| Range research | src/bybit_grid/research/range_core and range_detector.py | reference/NumPy and event components |
| Neutral grid semantics | src/bybit_grid/backtest/neutral_grid | Decimal state machine and accounting |
| OHLC replay | src/bybit_grid/backtest/ohlc_replay | minimal-path replay and provenance |
| Outcome/scoring | src/bybit_grid/research/outcome_core and src/bybit_grid/research/scoring | proxy-only |
| Walk-forward | src/bybit_grid/research/walk_forward | split mechanics; selection insufficient |

Подробная матрица: [CURRENT_ARCHITECTURE_AND_STATUS](docs/CURRENT_ARCHITECTURE_AND_STATUS.md).

## Missing vertical path

Единый production-like offline поток отсутствует:

historical evidence → canonical store → range candidates → semantic replay → complete costs and forced SL → walk-forward/OOS → bounded decision.

Текущие scripts/build_range_candidates.py и scripts/build_candidate_outcomes.py читают legacy data/raw. Current outcome/scoring не запускает NeutralGridReferenceEngine над реальными candidates. Native quantity/termination mapping, liquidation, full risk budget, parameter sufficiency и profitability не доказаны.

## Historical chain 06.4C–06.4F

- historical_plan.py: bounded request plan;
- historical_response.py: admission of supplied response bytes;
- historical_transcript.py: transcript reconciliation;
- historical_evidence.py: deterministic in-memory layout.

Network downloader, archive, untrusted re-admission, filesystem publication и store projection отсутствуют. WIP 06.4G не публикуется до исправления frozen contract.

## Private boundary

validate_only.py фиксирует mainnet origin https://api.bybit.com, три read-only GET, единственный POST /v5/fgridbot/validate и neutral/geometric payload. client.py использует private transport с trust_env=false и follow_redirects=false; generic private_post, create_grid_bot и close_grid_bot fail closed.

## CI

PM Acceptance — base-controlled pull_request_target, scope classifier, frozen tests, Python 3.12/3.14, numeric/no-live/compile/pytest/Ruff gates. Workflow доказывает PR head, но не создаёт отдельного push-status для squash merge SHA.

## Non-capabilities

src/bybit_grid/backtest/grid_simulator.py, research/features.py, research/range_candidates.py и большая часть live package остаются placeholders. Нет готового downloader-to-decision E2E, portfolio engine, Telegram runtime, VPS deployment или live trading.
