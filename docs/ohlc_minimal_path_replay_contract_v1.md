# OHLC 1m minimal-path replay contract v1

Bybit trade Kline data is aggregated OHLC data. A closed one-minute candle exposes open, high, low and close, but it does not expose the event order in which the high and low occurred.

Only explicit closed candles are accepted. The model does not use wall-clock time to infer closure. The signal candle is excluded from replay; entry begins at the next minute boundary using `entry_time_ms = ((signal_time_ms // 60000) + 1) * 60000`, and the first replay candle must start exactly at `entry_time_ms`.

The adapter supports exactly two deterministic minimal-turn hypotheses:

- `open_high_low_close`
- `open_low_high_close`

These visit each reported extreme once. They are minimal-turn hypotheses only. They do not reconstruct the real tick path, and arbitrary extra intrabar oscillations are not modeled or bounded. The resulting exact enumeration is named `minimal_path_ambiguity_envelope`; it is not a true best case, true worst case or complete intrabar bound.

Generated price events preserve exact `Decimal` prices. Consecutive duplicate prices are removed, while later repeated prices separated by another price are retained. Generated `time_ms` values are candle-bucket timestamps equal to the candle `open_time_ms`; they are not reconstructed tick timestamps for the actual high or low.

Funding observations are optional. When supplied, funding times must be strictly increasing, minute-aligned, match a replay candle open boundary, be greater than `entry_time_ms`, and be earlier than the final candle close boundary. Funding at `entry_time_ms` is rejected. Funding at a candle boundary is processed before that candle's price-path events and uses its explicit mark price; trade OHLC is not used to infer mark price.

This adapter does not add volume queue modeling, partial fills, spread, tick rounding, liquidation modeling, native quantity mapping, parameter selection, or profitability claims. It delegates all fills, fees, funding accounting, termination accounting and PnL identity checks to the frozen neutral-grid reference state machine.

Proof/readiness guardrails remain false: `native_equivalence_proven_bool`, `native_quantity_mapping_proven_bool`, `native_termination_mapping_proven_bool`, `liquidation_modeled_bool`, `risk_budget_proven_bool`, `parameter_selection_performed_bool`, `profitability_claims_present_bool`, and `live_execution_present_bool`.

## Sprint 06.2A.1 provenance, audit, and envelope closure

Sprint 06.2A.1 tightens the OHLC minimal-path adapter contract before any persisted OHLC evidence or historical backtest use.

* **Config/candle provenance:** the replay adapter accepts exactly `NeutralGridConfig` and `OhlcCandle1m` instances. The config category and every candle category must be `linear`; the config symbol and every candle symbol must be identical stripped non-empty strings. Candle sequence validation type-checks objects before reading fields and fails closed with `ValueError`.
* **Retained immutable source evidence:** each `OhlcReplayResult` retains detached tuples of `source_candles` and `source_funding_observations`. Public result provenance fields, counts, entry time, and path policies are auditable from this retained evidence.
* **Strict generated-event contract:** generated replay evidence uses `ReplayEventKind.price` and `ReplayEventKind.funding`. Runtime validation requires non-bool integer sequence IDs and minute-aligned times, finite positive Decimal prices/mark prices, exact candle indexes, `None` funding rates for price events, and finite Decimal funding rates for funding events.
* **Fresh replay audit:** `audit_ohlc_replay_result()` validates retained inputs, reconstructs the expected event schedule, runs an independent fresh replay, re-runs the nested state-machine audit, and compares exact type-aware replay fields and generated events. Malformed snapshots return stable audit failures rather than tracebacks.
* **Termination-prefix rule:** the generated event tuple must be the exact prefix of the reconstructed schedule. When termination occurs the prefix ends at the event that caused termination, and no later generated event is accepted.
* **Exact Cartesian assignment evidence:** ambiguity envelopes retain every assignment result in deterministic Cartesian order with OHLC before OLHC. The envelope audit requires a non-empty exact assignment set, no duplicates, no missing or extra assignments, canonical non-ambiguous policies, and exact assignment count `2 ** ambiguous_candle_count`.
* **Independent aggregation:** envelope PnL bounds retain deterministic PnL tie-breaking by full policy assignment key. Completed-cycle count min/max, trading-fee min/max, termination reasons, and `path_sensitive_bool` are independently recomputed across all assignments. `path_sensitive_bool` is true when material replay outcomes differ, including final total PnL, termination reason, completed cycle count, cumulative trading fees, or signed final position.
* **Strict enumeration cap type:** `max_exact_ambiguous_candles` must be an `int`, not `bool`, and must be `>= 0`. Floats, strings, booleans, and negative values are rejected before enumeration or candle processing. `MinimalPathEnumerationCapExceededError` remains reserved for valid caps below the actual ambiguous-candle count.

This contract still does not claim complete tick-path reconstruction, native exchange equivalence, or a true global PnL bound outside the two minimal paths.

## Sprint 06.2A.2 strict snapshot identity and funding provenance

Sprint 06.2A.2 closes the in-memory replay-evidence contract before persisted OHLC evidence is allowed.

* **Exact Python runtime type identity:** replay and envelope audits reject scalar aliases such as `True` for `1`, `False` for `0`, floats for integers, integer zero for `Decimal("0")`, and `str` subclasses for exact public string evidence. Whole-result comparison is strict and recursive across dataclasses, enums, Decimals, tuples, and mappings.
* **Immutable tuple evidence:** retained replay evidence containers must be exact tuples: `path_policies`, `source_candles`, `source_funding_observations`, and `generated_events`. Envelope `assignment_results`, min/max assignments, and termination-reason evidence are also exact tuples. Mutable list substitutions fail closed.
* **Explicit `source_config`:** `OhlcReplayResult` retains the exact `NeutralGridConfig` used to produce the replay. The nested state-machine result config must match this source config by strict typed identity, and fresh audit replay uses `source_config` rather than trusting the nested result.
* **Uniform `CandleSource`:** a replay may contain exactly one `CandleSource` value across all source candles. The result exposes that source as `candle_source`; mixed synthetic and Bybit trade-kline candle sources are rejected.
* **Funding category/symbol provenance:** `FundingObservation` carries exact `category`, `symbol`, `time_ms`, `funding_rate`, and `mark_price` fields. Funding observations must be exact `linear` observations for the same stripped symbol as the replay config and source candles; no category or symbol is inferred or defaulted.
* **Strict non-falsey sequence inputs:** public sequence inputs fail closed unless they are real non-string sequences. `candles` and path-policy sequences reject booleans, numbers, strings, bytes, mappings, and arbitrary non-sequence objects. `funding_observations` may be `None` or an actual non-string sequence; falsey aliases such as `False`, `0`, `""`, `b""`, and `{}` are not silently treated as empty.
* **Whole-result fresh replay comparison:** the replay audit validates snapshot shape, provenance, event schedule, nested state-machine audit status, and then compares the entire stored `OhlcReplayResult` to an independently generated fresh replay using strict typed identity, including the entire nested `SimulationResult`.
* **Whole-envelope strict reconciliation:** after each assignment passes the hardened replay audit, the envelope audit reconstructs the Cartesian assignment set, rebuilds aggregate envelope evidence from assignment results, and strictly compares the whole stored envelope to the recomputed envelope while preserving deterministic ordering and PnL tie-breaking.

This contract continues to be limited to the two deterministic minimal-turn paths. It does not claim complete tick-path reconstruction, native exchange equivalence, liquidation modeling, or a true global PnL bound.

## Sprint 06.2B — persisted synthetic OHLC evidence gate

Sprint 06.2B freezes a deterministic 24-scenario synthetic OHLC catalog under contract
`ohlc_minimal_path_replay_contract_v2` and scenario version
`ohlc_minimal_path_scenarios_v1`. The catalog is text-only source code, has no wall-clock,
random, machine-specific, downloaded market-data, private API, or live-execution inputs, and
keeps the accepted Sprint 06.2A minimal path replay semantics unchanged.

Funding observations now carry explicit source provenance: one exact funding-rate source enum and
one exact funding mark-price source enum per replay. Replays reject mixed funding-rate sources,
mixed mark-price sources, and funding category/symbol mismatches. The Bybit-named source scenario
is synthetic evidence for the enum/source contract only; it is not downloaded Bybit market
evidence.

The owner runner writes canonical JSON/JSONL and Markdown evidence members, reads them back with a
strict parser, and then performs a fresh semantic replay reconciliation before writing the final
`complete` status. Strict persisted parsing rejects duplicate JSON keys, float/non-finite tokens,
blank JSONL lines, missing final newlines, and non-canonical bytes. The neutral-grid Gate 6A
canonical serializer remains reused rather than weakened.

The review pack has exactly fourteen members in a fixed order, with a self-excluded manifest that
hashes the other thirteen members. The checker independently validates member order, manifest
schema, hashes, canonical byte identity, scenario catalog membership/order/version, fixed replay
results, ambiguity envelopes, generated replay events, full state-machine ledger rows, and completed
cycles against fresh replay output. Hashes are necessary but not sufficient: semantic tampering is
rejected after rehash.

Remaining false guardrails are preserved: minimal paths are not complete intrabar bounds; native
quantity, native termination, liquidation, funding coverage, real Bybit batch integration, global
true worst/best case, risk budget 5 USDT, parameter selection, profitability, live execution, and
live authorization are not proven. The only readiness flag advanced by this synthetic gate is that
the deterministic evidence is sufficient for the next real Bybit batch-integration step.
