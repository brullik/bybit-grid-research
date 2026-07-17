# Current Architecture and Status

Snapshot: after PR #143, main 35a3b9c05b1bf3d86756e449b2735bef0893bc45. Для текущей implementation authority всегда проверяйте pm_acceptance/active_task.json.

## Capability matrix

| Area | Evidence in current code | Honest status |
|---|---|---|
| Public API/data | src/bybit_grid/bybit, src/bybit_grid/data | implemented components |
| Validate-only P0 | src/bybit_grid/bybit/validate_only.py, client.py | fail-closed exact boundary |
| Canonical store | src/bybit_grid/data/market_store | Parquet schemas, atomic writer, audit, reader, coverage/resume; read-only in-memory DuckDB views |
| Range detector | src/bybit_grid/research/range_core, range_detector.py | implemented components; legacy reader path |
| Neutral grid | src/bybit_grid/backtest/neutral_grid | Decimal semantic state machine, mostly synthetic evidence |
| OHLC replay | src/bybit_grid/backtest/ohlc_replay | minimal-path semantics/provenance, synthetic evidence |
| Outcome/scoring | src/bybit_grid/research/outcome_core, scoring | proxy-only; no semantic candidate replay |
| Walk-forward | src/bybit_grid/research/walk_forward | splits implemented; selection insufficient |
| Live/Telegram/VPS | src/bybit_grid/live and deployment surface | not implemented |

Exact non-capability status:

~~~text
`create_grid_bot_available`: `false`
`close_grid_bot_available`: `false`
`telegram_runtime_implemented`: `false`
`live_execution_implemented`: `false`
`vps_deployment_implemented`: `false`
~~~

Strict historical evidence is split across `historical_plan.py`,
`historical_response.py`, `historical_transcript.py` and
`historical_evidence.py`; these names denote pure offline boundaries, not a
network downloader.

## Strict versus legacy data paths

Strict public-batch/historical and canonical-store paths retain provenance and commitments. scripts/build_range_candidates.py still reads data/raw/klines. scripts/build_candidate_outcomes.py reads data/raw/klines, data/raw/mark_klines and data/raw/funding. Silent fallback is not accepted for the future E2E; a canonical store adapter must be explicit.

## Missing E2E links

1. No finished network downloader → verified archive → canonical store projection.
2. No canonical-store reader wired to range/outcome scripts.
3. No real candidate → semantic replay adapter through NeutralGridReferenceEngine/OHLC replay.
4. Native quantity/levels and termination mapping are unproven.
5. Liquidation and complete 5 USDT risk proof are unproven.
6. Outcome/scoring remains proxy-only.
7. Walk-forward/OOS policy selection remains insufficient.
8. Portfolio cap and bounded decision artifact are absent.
9. No live lifecycle, Telegram runtime or deployment.

src/bybit_grid/backtest/grid_simulator.py is a literal placeholder. research/features.py, research/range_candidates.py and much of live are placeholders.

## Historical evidence state

06.4C plan, 06.4D response, 06.4E transcript and 06.4F layout are pure offline/in-memory boundaries. They grant no network, archive, filesystem, persistence, store projection, private or live authority. #129 is blocked until its frozen cap/overflow contract is corrected.

## Open gates

- #133 full-history secret scan and ref retention, mandatory before credentials.
- #134 assurance of current behavior originating in PR #1–66.
- #129 corrected deterministic archive lifecycle.
- #131 bounded tasks for canonical offline E2E.

## Safety

P0 allows only exact signed read-only private GET and exact native validate at mainnet origin. Generic private POST and create/close are unavailable. This is not a recommendation or authorization to trade.
