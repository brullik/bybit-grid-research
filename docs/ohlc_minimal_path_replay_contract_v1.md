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
