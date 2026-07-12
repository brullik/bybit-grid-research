# Sprint 06.3B — Persisted Bybit Public Batch Evidence, Cross-Plan Pagination Reconciliation and Review-Pack Gate

## PM state

Sprint 06.3A.1 is accepted.

The accepted owner smoke proved that the current public adapter can:

```text
parse the full Bybit linear universe;
distinguish LinearPerpetual from LinearFutures;
preserve zero fundingInterval for dated futures;
select replay-eligible USDT perpetuals;
obtain Bybit server time;
assemble a closed three-minute BTCUSDT trade/mark/funding batch;
keep all risk, parameter-selection and live guardrails false.
```

This sprint turns that small smoke into reproducible persisted evidence. It does not select parameters and does not evaluate strategy profitability.

## Text-only Codex rule

Codex may add or modify only text source files:

```text
.py
.md
.gitignore
```

Codex must not create, modify or commit:

```text
ZIP
Parquet
JSON or JSONL evidence outputs
SQLite or other databases
market-data snapshots
owner logs
.env
API keys
binary fixtures
```

Temporary generated files inside pytest `tmp_path` are allowed.

## Frozen economics — do not change

Do not change any accepted formula or semantic in:

```text
neutral-grid geometric levels;
fill crossing/order semantics;
one-way position accounting;
average entry;
realized/unrealized PnL;
grid-cycle pairing;
maker/taker fee timing;
funding formula;
termination/slippage;
OHLC and OLHC minimal paths;
funding-before-price event ordering;
ambiguity-envelope enumeration.
```

Do not change the accepted 24 synthetic OHLC scenarios or Gate 6A state-machine scenarios.

## Safety rules

- Public Bybit endpoints only.
- No API key or secret.
- No private endpoints.
- No order/create/close/cancel/position mutations.
- No native grid creation.
- No Telegram.
- No parameter optimization.
- No PnL, EV, ROI or profitability claim.
- No Parquet in this sprint.
- Preserve all closed guardrails.

## Frozen identifiers and owner capture plan

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
EVIDENCE_SCHEMA_VERSION = bybit_public_batch_evidence_v1
REVIEW_PACK_SCHEMA_VERSION = bybit_public_batch_review_pack_v1
REVIEW_PHASE = persisted_public_batch_evidence
SYMBOL = BTCUSDT
KLINE_ROW_COUNT = 1001
PRIMARY_KLINE_LIMIT = 1000
ALTERNATE_KLINE_LIMIT = 251
PRIMARY_INSTRUMENT_LIMIT = 1000
ALTERNATE_INSTRUMENT_LIMIT = 200
FUNDING_LOOKBACK_DAYS = 100
PRIMARY_FUNDING_LIMIT = 200
ALTERNATE_FUNDING_TARGET_RECORDS_PER_WINDOW = 100
DEFAULT_PACK = pm_review_pack_bybit_public_batch_bybit_public_batch_063b_btcusdt_v1.zip
```

The capture derives its end timestamp once from Bybit server time:

```text
end_open_time_ms = server_time.last_closed_open_time_ms
start_open_time_ms = end_open_time_ms - 1000 * 60000
```

Therefore the canonical kline window contains exactly 1001 closed one-minute rows.

## Task 1 — Strict recorded public-response boundary

Add:

```text
src/bybit_grid/data/public_batch/recording.py
```

Implement an import-safe, public-only recording client.

Minimum record contract:

```text
request_sequence_id: exact int >= 1
endpoint: exact stripped string beginning with /v5/market/
params: deeply immutable exact mapping
http_status: exact int
content_type: exact string
raw_body_text: exact UTF-8 JSON text
raw_body_sha256: lowercase 64-character SHA-256
parsed_payload: strict JSON object
```

Requirements:

- Only GET requests.
- No authentication headers, API keys, cookies or private endpoints.
- Sort query parameters deterministically for evidence.
- Record the exact response body as text and its SHA-256.
- Strict JSON parser must reject duplicate object keys.
- Reject JSON float tokens and non-finite constants.
- Verify `raw_body_sha256` against `raw_body_text` before exposing payload.
- Retry only public transient failures: HTTP 429 and 5xx.
- Bounded exponential backoff with a finite attempt count.
- Preserve the final HTTP status and response body on failure.
- Importing the module must never make a network call.

Do not store machine-specific local wall-clock fields in canonical evidence.

## Task 2 — Generalize deterministic pagination without changing defaults

Update public-batch pagination with strict exact-int limits:

```text
fetch_all_instruments(..., limit=1000)
fetch_trade_klines(..., page_limit=1000)
fetch_mark_klines(..., page_limit=1000)
fetch_funding_history_backward(..., limit=200)
```

Validation:

```text
instrument/kline limits: exact int, not bool, 1..1000
funding limit: exact int, not bool, 1..200
```

Keep existing defaults and behavior backward compatible.

Add an independent funding retrieval path:

```text
fetch_funding_history_chunked(
    client,
    symbol,
    start_ms,
    end_ms,
    funding_interval_minutes,
    *,
    target_records_per_window=100,
    page_limit=200,
)
```

The alternate planner must create non-overlapping inclusive request ranges and must fail closed on:

```text
invalid exact types;
non-positive interval;
page truncation risk;
duplicate funding timestamps;
out-of-range rows;
missing progress;
raw page returning page_limit rows when the planned interval should be below the target;
```

Do not inject an assumed eight-hour interval. Use the parsed instrument value.

## Task 3 — Pure assembly from already parsed rows

Add a pure function, for example:

```text
assemble_bybit_public_replay_batch_from_rows(...)
```

It must accept explicit:

```text
instrument;
server_time;
requested_window;
trade rows;
mark rows;
funding rows;
request-page audits.
```

It must produce the same `BybitPublicReplayBatch` as the network orchestration path, with no network calls.

The existing network wrapper should delegate to this pure assembler.

The pure assembler must enforce:

```text
exact model types;
exact category and symbol provenance;
closed-candle cutoff;
complete ascending 1m timestamp coverage;
trade/mark exact timestamp equality;
no duplicates;
funding observations joined to mark-price open at the funding minute;
immutable tuples;
public-batch audit passes.
```

This is required so the review-pack checker can reconstruct the batch from persisted responses without contacting Bybit.

## Task 4 — Cross-plan capture and reconciliation

Add a capture orchestrator that uses one server-time snapshot and records all public responses.

### Instrument universe

Fetch twice:

```text
primary plan: limit=1000
alternate plan: limit=200 with cursor pagination
```

Require:

```text
same normalized instrument records in deterministic symbol order;
no duplicate symbols;
all cursor transitions recorded;
no cursor cycles;
alternate plan has at least two pages in the accepted owner capture;
universe audit passes for both plans.
```

### Trade and mark klines

For the same 1001-row closed BTCUSDT window, fetch each endpoint twice:

```text
primary plan: page_limit=1000
alternate plan: page_limit=251
```

Require exact equality of normalized records across plans:

```text
trade primary == trade alternate
mark primary == mark alternate
```

The accepted owner capture must show:

```text
1001 trade rows;
1001 mark rows;
primary plan uses at least two pages;
alternate plan uses at least four pages;
no gaps or duplicates;
all rows are closed relative to the one saved server-time snapshot.
```

### Funding history

Capture the preceding 100 days for BTCUSDT using two independent methods:

```text
primary: backward pagination, limit=200;
alternate: deterministic non-overlapping chunks derived from the parsed funding interval and target 100 records/window.
```

Require exact normalized row-set equality and deterministic ordering.

The accepted owner capture must show at least two primary funding pages and at least two alternate chunks. Exact equality of the two retrieval plans proves plan reconciliation for the recorded window only; it does not prove that Bybit supplied every historical funding record. Keep `funding_coverage_proven_bool=false`.

### Replay-ready batch

Build the canonical 1001-row replay-ready batch from the primary normalized rows and audit it.

No strategy replay or PnL is performed in this sprint.

## Task 5 — Canonical persisted evidence contract

Add:

```text
src/bybit_grid/data/public_batch/evidence.py
```

Use strict canonical JSON and JSONL:

```text
UTF-8;
sorted object keys;
compact separators;
final newline for JSONL;
no duplicate keys;
no float tokens;
no NaN/Infinity;
exact JSON type identity;
Decimal values serialized as strings;
```

Canonical review-pack member set — exactly 18 files:

```text
review_pack_manifest.json
public_batch_run_status.json
capture_plan.json
server_time.json
recorded_public_responses.jsonl
instrument_records.jsonl
instrument_universe_audit.json
trade_klines.jsonl
mark_klines.jsonl
funding_rates.jsonl
funding_observations.jsonl
request_page_audits.jsonl
public_batch_audit.json
cross_plan_reconciliation_audit.json
reproducibility_audit.json
capture_summary.json
public_batch_report.md
risk_budget_readiness_report.md
```

Every row that can occur under multiple plans must contain an exact `plan_id`.

Required plan IDs:

```text
instrument_primary_1000
instrument_alternate_200
trade_primary_1000
trade_alternate_251
mark_primary_1000
mark_alternate_251
funding_primary_backward_200
funding_alternate_chunked_100
```

## Task 6 — Run lifecycle

Add owner-only CLI:

```text
scripts/run_bybit_public_batch_evidence.py
```

Required arguments/defaults:

```text
--run-id bybit_public_batch_063b_btcusdt_v1
--symbol BTCUSDT
--kline-row-count 1001
--funding-lookback-days 100
--output-root data/processed/public_batch_runs
```

Lifecycle:

```text
write status=building first;
perform network capture;
write all non-status evidence atomically;
strictly read it back;
reconstruct every normalized record from persisted raw response bodies;
reconcile primary/alternate plans;
reconstruct and audit the replay-ready batch;
derive reproducibility audit;
write status=complete last.
```

On every exception:

```text
write status=failed;
include stable exception_type and exception_message;
never leave complete;
print strict JSON summary;
return non-zero.
```

Run status must not claim that a review pack exists or has passed.

## Task 7 — Independent persisted-evidence validation

The shared validator and pack checker must be persisted-input-first.

From `recorded_public_responses.jsonl`, independently:

1. verify each raw body SHA-256;
2. strict-parse each raw response body;
3. match the exact request endpoint/params to the declared plan;
4. rerun existing response parsers;
5. rebuild normalized instrument, trade, mark and funding rows;
6. compare canonical bytes with persisted normalized evidence;
7. rerun both universe audits;
8. rerun primary/alternate cross-plan reconciliation;
9. rebuild the replay batch from rows;
10. rerun `audit_bybit_public_replay_batch()`;
11. rebuild funding observations;
12. derive all summary/report claims.

Do not validate persisted output by comparing it only with another value produced in the same write path.

## Task 8 — Reproducibility audit

Derive, do not hard-code:

```text
raw_body_hashes_verified_bool
strict_raw_json_parse_bool
normalized_rows_reconstructed_bool
primary_alternate_universe_equal_bool
primary_alternate_trade_equal_bool
primary_alternate_mark_equal_bool
primary_alternate_funding_equal_bool
canonical_artifact_bytes_rebuilt_bool
canonical_artifact_hashes_rebuilt_bool
machine_specific_fields_absent_bool
credentials_absent_bool
reproducibility_audit_ok
```

Rebuild canonical non-status evidence twice from the same persisted inputs and compare bytes and hashes.

## Task 9 — Guardrails and summary

`capture_summary.json`, manifest and reports must preserve exact booleans:

```text
contains_credentials = false
private_api_used_bool = false
live_execution_present_bool = false
risk_budget_proven_bool = false
native_equivalence_proven_bool = false
funding_coverage_proven_bool = false
parameter_selection_authorized_bool = false
sufficient_for_parameter_selection_bool = false
live_authorized_bool = false
sufficient_for_parquet_storage_engineering_bool = true
```

`funding_coverage_proven_bool` remains false because this sprint proves the accepted snapshot and two retrieval plans, not complete multi-year historical funding coverage.

No profitability or parameter claim may appear in reports.

## Task 10 — Review-pack builder and checker

Add:

```text
scripts/make_bybit_public_batch_review_pack.py
scripts/check_bybit_public_batch_review_pack.py
```

Builder CLI:

```text
python scripts/make_bybit_public_batch_review_pack.py \
  --run-id bybit_public_batch_063b_btcusdt_v1 \
  --output pm_review_pack_bybit_public_batch_bybit_public_batch_063b_btcusdt_v1.zip
```

Checker CLI:

```text
python scripts/check_bybit_public_batch_review_pack.py \
  --zip pm_review_pack_bybit_public_batch_bybit_public_batch_063b_btcusdt_v1.zip \
  --run-id bybit_public_batch_063b_btcusdt_v1
```

Builder requirements:

```text
require status=complete;
validate all source artifacts before ZIP creation;
create a temporary ZIP;
run the full checker against the temporary ZIP;
atomically replace destination only after success;
remove temporary ZIP on failure;
strict JSON output without traceback for expected operator errors.
```

Manifest requirements:

```text
exact key set;
review_pack_schema_version = bybit_public_batch_review_pack_v1;
manifest_hash_policy = self_excluded_v1;
review_phase = persisted_public_batch_evidence;
run_id;
symbol = BTCUSDT;
evidence_schema_version = bybit_public_batch_evidence_v1;
member list in canonical order;
SHA-256 for exactly 17 non-manifest members;
no self-hash;
all closed guardrails.
```

Checker must reject extra/missing/duplicate members, unsafe paths, unexpected manifest fields, wrong types, stale hashes and every semantic mismatch.

## Task 11 — Reports

Create deterministic builders for:

```text
public_batch_report.md
risk_budget_readiness_report.md
```

Reports must be exact canonical bytes, derived from evidence, and contradiction-proof.

Public report must include at least:

```text
run_id and symbol;
server time and closed cutoff;
1001-row requested window;
page counts per plan;
instrument counts and replay-eligible count;
trade/mark/funding normalized row counts;
all primary/alternate reconciliation booleans;
public batch audit result;
contains_credentials=false.
```

Risk report must state all closed guardrails and explicitly state that this evidence does not prove profitability, native equivalence, liquidation, parameter selection or the 5 USDT maximum-loss budget.

## Task 12 — Tests

Add:

```text
tests/test_sprint_06_3b_persisted_public_batch_evidence.py
```

All tests use synthetic/mocked public responses. No network.

Required regression coverage:

1. Module imports make no network call.
2. Exact limit types/ranges; bool/float/string aliases rejected.
3. 1001 rows reconcile under 1000 and 251 page plans.
4. Reverse API rows normalize ascending.
5. Boundary rows appear exactly once.
6. Missing/duplicate kline row fails.
7. Instrument 1000/200 pagination plans reconcile.
8. Cursor cycle/duplicate symbol/max-pages fail.
9. Funding backward and alternate chunk plans reconcile for more than 200 rows.
10. Funding plan truncation risk fails.
11. Raw-body SHA mismatch fails.
12. Duplicate JSON key, float token and non-finite token fail.
13. Pure row assembly equals network orchestration assembly.
14. Cross-symbol/category rows fail.
15. Trade/mark timestamp mismatch fails.
16. Unclosed candle fails.
17. Missing funding mark boundary fails.
18. Building → complete lifecycle.
19. Early and late failures end `failed`, never `complete`.
20. Exact 18-member pack and 17 hashes.
21. Manifest self-hash absent.
22. Missing/extra/duplicate/unsafe member rejected.
23. Rehashed tamper of raw response rejected semantically.
24. Rehashed tamper of instrument row rejected.
25. Rehashed tamper of trade row rejected.
26. Rehashed tamper of mark row rejected.
27. Rehashed tamper of funding rate/observation rejected.
28. Rehashed tamper of request page audit rejected.
29. Rehashed tamper of cross-plan audit rejected.
30. Rehashed tamper of status/summary/report/guardrail rejected.
31. Credentials/private endpoint claim rejected.
32. Builder temporary self-check and atomic replace.
33. Missing ZIP returns strict JSON without traceback.
34. No live/private/order/Telegram implementation.
35. No generated/binary file committed under deterministic source roots.

Use small fixtures and `tmp_path`; do not depend on owner evidence.

## Task 13 — Documentation

Extend:

```text
docs/bybit_public_batch_input_contract_v1.md
```

Document:

```text
primary/alternate retrieval plans;
raw response provenance;
canonical persistence;
1001-row closed-candle evidence window;
100-day funding comparison;
what cross-plan equality proves;
what it does not prove;
all safety guardrails;
next stage: Parquet storage/resume/gap repair.
```

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest -q
ruff check .
git diff --check
```

Do not run real network capture in Codex.

## Acceptance criteria

```text
all tests pass;
Ruff passes;
no-live audit passes;
accepted 06.3A.1 behavior remains unchanged;
1001-row dual-plan kline fixtures reconcile;
>200-row dual-plan funding fixtures reconcile;
raw public responses can independently reconstruct all normalized evidence;
run status is atomic;
review pack has exactly 18 members and 17 non-manifest hashes;
review pack checker performs semantic fresh reconstruction;
all reports are exact canonical bytes;
all safety/risk/parameter/live guardrails remain false;
no generated artifact is committed.
```

## Required Codex return

Return text only:

```text
commit hash
changed text files
git diff --stat
numeric environment output
pip check output
no-live audit output
06.3A focused output
06.3A.1 focused output
06.3B focused output
full pytest output
Ruff output
git diff --check output
recording-client summary
pagination/cross-plan summary
pure assembly summary
persisted reconstruction summary
lifecycle summary
tamper-test summary
review-pack contract summary
all guardrail values
known remaining limitations
```

Do not return or upload ZIP, JSON, JSONL, market data, `.env` or owner-generated evidence from the Codex environment.
