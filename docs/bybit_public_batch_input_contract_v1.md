# Bybit Public Batch Input Contract v1

Sprint 06.3B.3.1 keeps the canonical evidence path public-only and semantic-reviewable from persisted bytes.

## Provenance and networking

- Canonical captures may use exactly one selected public base URL: `https://api.bybit.com` or `https://api.bytick.com`.
- The selected `base_url` and bounded `timeout_seconds` are persisted in `capture_plan.json` and `capture_summary.json`.
- A single run never mixes hosts and never falls back automatically across hosts.
- `scripts/probe_bybit_public_connectivity.py` is an import-safe diagnostic that calls only `GET /v5/market/time`, emits compact JSON, writes no canonical run data, and returns non-zero only when all probe attempts fail.

## Source, derived, and lifecycle members

- `recorded_public_responses.jsonl` is canonical source evidence. It is independently validated as persisted raw public-response evidence and is not claimed to be reconstructed from typed rows.
- Exactly 15 artifacts are deterministic derived evidence reconstructed from the persisted raw source bytes and the frozen capture plan.
- `review_pack_manifest.json` and `public_batch_run_status.json` are lifecycle members, not reconstructed source/derived evidence members.
- The non-status artifact count remains 16: one source artifact plus 15 derived artifacts.

## Semantic validation flow

One shared validator reads persisted evidence through a directory or ZIP reader. It starts from the canonical source `recorded_public_responses.jsonl` plus the frozen `capture_plan.json`, reconstructs deterministic derived artifacts, and byte-compares every generated JSON, JSONL and Markdown member. The standalone checker reconstructs from persisted raw source bytes, and the review-pack builder uses the same semantic validator; hashes alone are not sufficient.

Directory evidence must contain exactly the 18 direct canonical regular files and nothing else. Extra regular files, missing files, extra directories, symlinks/junctions, device-like entries where detectable, nested paths, and unsafe names are rejected instead of silently filtered.

## Canonical JSON and JSONL

Every JSON member is strictly decoded, schema checked, canonicalized with sorted compact JSON, and compared byte-for-byte with the original member. Every JSONL member requires strict UTF-8, a final newline when non-empty, no blank lines, strict per-line JSON parsing, exact per-line schemas, and byte-identical canonical line reserialization.

Canonical evidence objects require exact non-empty string keys. Non-string keys in ordinary mappings are rejected to avoid collision or silent overwrite.

## Plan consumption

`capture_plan.json` freezes run id, schema version, selected base URL, symbol `BTCUSDT`, category `linear`, interval `1`, the exact 1001-row window contract, the 100-day funding lookback, and ordered plan specifications. Replayed records must have contiguous sequence ids, public `/v5/market/*` endpoints, exact params, exact plan order, matching raw body hashes, and exact parsed payload identity. Replay clients assert every plan is exhausted so extra tail records fail validation.

## Reproducibility and audits

Cross-plan booleans and page counts are derived from reconstructed primary and alternate plans. Reproducibility compares independently built derived artifact maps and requires exact key-set and byte equality before persisting `reproducibility_audit.json`, `capture_summary.json`, and `public_batch_report.md` values. Funding observations are one-to-one with funding rates whose timestamps fall inside the kline window; expected and actual timestamp tuples must match exactly.

## Closed guardrails

The evidence does not use or prove private API access, account/order/grid/position/wallet state, live execution, Telegram delivery, parameter suitability, profitability, native grid equivalence, native quantity mapping, liquidation behavior, funding-history completeness, a 5 USDT maximum-loss budget, or live readiness. `funding_coverage_proven_bool` remains `false`.
