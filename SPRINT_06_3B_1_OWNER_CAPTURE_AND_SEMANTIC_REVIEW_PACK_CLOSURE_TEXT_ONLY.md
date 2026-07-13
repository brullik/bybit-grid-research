# Sprint 06.3B.1 — Owner Public Capture, Persisted Reconstruction and Semantic Review-Pack Closure

## PM decision

Sprint 06.3B is **not accepted**.

The owner environment and regression suite were healthy:

```text
numeric environment: ok
pip check: no broken requirements
no-live audit: ok
06.3A: 7 passed
06.3A.1: 15 passed
06.3B focused: 4 passed
full suite: 350 passed
Ruff: passed
```

However, the required owner lifecycle failed before making any network request:

```text
PublicBatchError: owner_network_capture_not_run_by_codex
```

The current implementation is a scaffold, not the Sprint 06.3B acceptance implementation:

- `scripts/run_bybit_public_batch_evidence.py` raises intentionally in normal owner mode;
- fixture mode writes only status and summary, not the canonical evidence set;
- no real cross-plan capture orchestrator exists;
- no persisted-input-first reconstruction exists;
- the pack checker verifies member hashes and a few guardrails but does not rebuild evidence from raw responses;
- a semantically fabricated pack with recomputed hashes can pass;
- only 4 focused tests were added although the frozen Sprint 06.3B contract required the full lifecycle/tamper matrix;
- canonical serialization fails for dataclasses containing `MappingProxyType`;
- parsed-payload comparison is not exact-type-safe because Python treats `True == 1`.

Do not begin Sprint 06.4. Close 06.3B truthfully first.

## Safety and frozen scope

Preserve all accepted economics and all closed guardrails.

Allowed:

```text
public Bybit GET /v5/market/* only
no credentials
no private endpoints
no order/create/close/cancel/position/account/wallet operations
no native grid operations
no Telegram
no parameter optimization
no profitability claim
no Parquet in this closure
owner-generated evidence only outside source-controlled roots
```

Codex must not perform a real network capture. Codex must implement and test the owner network path with synthetic/injected public HTTP responses. The owner performs the real capture after code review.

Keep frozen identifiers:

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

Keep the exact 18-member review-pack order from Sprint 06.3B.

## Allowed source changes

Prefer a small, explicit implementation. Changes may include:

```text
src/bybit_grid/data/public_batch/recording.py
src/bybit_grid/data/public_batch/pagination.py
src/bybit_grid/data/public_batch/assemble.py
src/bybit_grid/data/public_batch/audit.py
src/bybit_grid/data/public_batch/models.py
src/bybit_grid/data/public_batch/evidence.py
src/bybit_grid/data/public_batch/capture.py              # optional new module
src/bybit_grid/data/public_batch/reconstruct.py          # optional new module
src/bybit_grid/data/public_batch/__init__.py
scripts/run_bybit_public_batch_evidence.py
scripts/make_bybit_public_batch_review_pack.py
scripts/check_bybit_public_batch_review_pack.py
docs/bybit_public_batch_input_contract_v1.md
tests/test_sprint_06_3b_persisted_public_batch_evidence.py
tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py  # recommended
.gitignore only if required
```

Do not modify accepted neutral-grid/OHLC replay formulas, fixtures, scenario IDs, or outputs.

## Defect 1 — normal owner mode is deliberately nonfunctional

Current normal mode contains an unconditional failure instead of capture.

### Task 1 — implement the real owner capture lifecycle

`run_bybit_public_batch_evidence.py` must perform the full public-only lifecycle in normal mode.

Required order:

```text
1. write status=building first;
2. instantiate an import-safe public recording client inside main/run function only;
3. fetch Bybit server time exactly once;
4. derive the exact 1001-row closed BTCUSDT window from that snapshot;
5. run all primary and alternate retrieval plans;
6. persist recorded raw public responses atomically;
7. strictly read persisted raw responses back;
8. reconstruct all normalized evidence only from persisted raw response bodies;
9. reconcile primary/alternate plans;
10. reconstruct and audit the replay-ready primary batch;
11. derive reproducibility audit, summary and reports;
12. atomically write every non-status canonical artifact;
13. run full directory validation from persisted files;
14. write status=complete last.
```

On every exception:

```text
write status=failed last;
include stable exception_type and exception_message;
never leave or restore status=complete;
print one strict compact JSON object;
return non-zero;
no traceback for expected operator errors.
```

Remove the current operator-facing behavior where normal mode always raises.

Do not retain a CLI flag that can mark a two-file fixture as `complete`. Test-only failure hooks or synthetic capture inputs must be internal/injected and must still produce/validate the complete canonical artifact set.

## Defect 2 — plan provenance is absent

The persisted contract requires exact plan identity, but the current recorded responses and request audits do not carry it.

### Task 2 — introduce exact plan-scoped recording

Every recorded request must have an exact `plan_id`.

Required capture plan IDs:

```text
server_time_snapshot
instrument_primary_1000
instrument_alternate_200
trade_primary_1000
trade_alternate_251
mark_primary_1000
mark_alternate_251
funding_primary_backward_200
funding_alternate_chunked_100
```

Requirements:

- plan ID is an exact stripped string from the frozen set;
- request sequence IDs are exact contiguous integers starting at 1;
- the single server-time response is recorded first;
- each pagination call is made through an explicit plan-scoped client/view;
- every persisted normalized row that can occur in more than one plan is wrapped/tagged with its exact `plan_id`;
- every persisted request-page audit is tagged with its exact `plan_id`;
- primary replay assembly uses only the declared primary rows/audits;
- the checker rejects missing, extra, unknown, swapped, duplicated or inconsistent plan IDs.

Do not rely on mutable global `current_plan` state. Prefer an immutable plan-scoped client view sharing one underlying sequence/record store.

## Defect 3 — recorded payload identity is not exact-type-safe

A raw body `{"a":1}` currently can be paired with `{"a":true}` because Python equality treats `True == 1`.

### Task 3 — exact strict JSON identity

Implement exact recursive JSON identity:

- object key sets and order-independent key/value identity;
- exact type identity for `dict`, `list`, `str`, `int`, `bool`, and `None`;
- `bool` never equals `int`;
- floats remain forbidden;
- duplicate keys and non-finite constants remain forbidden.

Prefer deriving `parsed_payload` directly from `raw_body_text` through a factory/classmethod instead of trusting a caller-provided duplicate payload. If the public constructor remains available, it must compare with exact recursive type identity.

Add regressions for:

```text
1 vs true
0 vs false
list element 1 vs true
nested object 1 vs true
```

## Defect 4 — canonical serialization breaks on immutable mappings

`dataclasses.asdict()` deep-copies `MappingProxyType` and raises `TypeError: cannot pickle 'mappingproxy' object`.

### Task 4 — deterministic serializer without `asdict()` deep-copy

Replace the serializer traversal with a strict recursive normalizer that:

- iterates dataclass fields directly via `dataclasses.fields()`;
- supports immutable/general `collections.abc.Mapping` without mutating or aliasing it;
- sorts mapping keys deterministically;
- serializes `Decimal` as exact strings;
- serializes enums by exact `.value` only when the value is an allowed JSON scalar;
- supports tuple/list as JSON arrays;
- rejects float, set, bytes, Path and unknown object types;
- never silently stringifies unknown keys or values;
- produces compact UTF-8 JSON with sorted keys and no NaN/Infinity;
- produces JSONL with a final newline.

Add tests using real `BybitInstrumentUniverseAudit` instances containing mapping proxies.

## Defect 5 — the public recorder fabricates bodies on transport errors

The current recorder creates a synthetic JSON body for non-HTTP exceptions. That is not an exact captured response body.

### Task 5 — harden the public recording boundary

Requirements:

- validate constructor parameters with exact types and finite bounds;
- `max_attempts`: exact int, not bool, bounded `1..10`;
- `backoff_seconds`: exact `Decimal` or exact int policy chosen explicitly; no float ambiguity in canonical evidence; finite and non-negative;
- base URL must be an approved HTTPS Bybit public API base in owner mode; injected opener remains allowed for tests;
- only GET and `/v5/market/*` endpoints;
- no credential-like query keys or forbidden headers;
- distinguish HTTP response errors from transport errors;
- for `HTTPError`, preserve exact status, headers/content type and exact body bytes/text;
- for transport/DNS/timeout errors with no response, raise a stable error; do not invent a response body;
- decode exact UTF-8 and fail closed on invalid UTF-8;
- close response objects deterministically;
- retry only 429 and 5xx;
- preserve final recorded HTTP response before parser failure when an actual response exists;
- import remains network-free.

## Defect 6 — no real cross-plan orchestration or reconciliation exists

### Task 6 — implement all frozen retrieval plans

Use one server-time snapshot.

#### Instrument universe

Run:

```text
primary limit=1000
alternate limit=200
```

Derive both normalized universes independently and require exact deterministic equality by canonical normalized row bytes in symbol order.

Require:

```text
no duplicate symbols
no cursor cycles
no max-page overflow
alternate owner capture page_count >= 2
both universe audits pass
```

#### Trade and mark klines

For the same exact 1001-row closed window run each endpoint under:

```text
primary page_limit=1000
alternate page_limit=251
```

Require:

```text
trade primary == trade alternate
mark primary == mark alternate
1001 rows each
complete ascending timestamps
timestamp equality across trade and mark
primary page_count >= 2
alternate page_count >= 4
```

#### Funding

For the preceding exact 100 days run:

```text
primary backward pagination limit=200
alternate non-overlapping chunks derived from parsed BTCUSDT funding interval,
target_records_per_window=100, page_limit=200
```

Require exact normalized ordered row equality.

Owner acceptance requires:

```text
primary funding page_count >= 2
alternate funding chunk_count >= 2
no duplicates
no out-of-range rows
no truncation risk
strict progress
```

Cross-plan equality remains window-specific. Keep `funding_coverage_proven_bool=false`.

## Defect 7 — funding observations can silently omit a boundary record

The current pure assembler excludes a funding timestamp equal to the first candle timestamp and the audit does not require one-to-one in-window coverage.

### Task 7 — exact in-window funding observation contract

For each funding rate satisfying:

```text
requested_window.start_open_time_ms <= funding_time_ms <= requested_window.end_open_time_ms
```

require exactly one observation joined to the mark-price candle with the same open timestamp.

Requirements:

- include the start boundary;
- include the end boundary when present;
- reject a missing mark boundary;
- reject duplicate observations;
- reject extra observations without a matching in-window funding rate;
- audit exact expected observation timestamp tuple and count;
- preserve the documented minute-data approximation.

Do not claim complete historical funding coverage.

## Defect 8 — current review-pack validation is hash-only, not semantic

A fabricated pack with recomputed hashes and even an unexpected manifest field currently passes.

### Task 8 — persisted-input-first semantic reconstruction

Implement one shared validator used by:

```text
run lifecycle directory validation
review-pack builder preflight
review-pack temporary self-check
standalone review-pack checker
```

The validator must begin from persisted `recorded_public_responses.jsonl`, not from in-memory write-path objects.

It must independently:

1. enforce exact JSON/JSONL canonical encoding;
2. verify contiguous sequence IDs;
3. verify each raw-body SHA-256;
4. strict-parse every raw body;
5. verify plan ID, endpoint and exact params against `capture_plan.json`;
6. verify pagination transitions and requested windows;
7. rerun existing response parsers;
8. rebuild normalized instrument/trade/mark/funding rows for every plan;
9. rebuild both instrument universe audits;
10. reconcile all primary/alternate normalized rows;
11. rebuild primary request-page audits;
12. rebuild the replay-ready batch with the pure assembler;
13. rerun `audit_bybit_public_replay_batch()`;
14. rebuild funding observations;
15. rebuild cross-plan reconciliation audit;
16. rebuild all deterministic summary fields;
17. rebuild exact canonical reports;
18. compare every rebuilt artifact byte-for-byte with the persisted member;
19. derive reproducibility evidence by rebuilding canonical non-status artifacts twice;
20. reject every mismatch even when the manifest hashes were recomputed.

Do not validate persisted normalized rows by comparing them only to another object produced in the same capture/write path.

## Defect 9 — manifest and pack semantics are under-validated

### Task 9 — exact review-pack contract

Manifest must have an exact key set, exact types and exact frozen values.

At minimum validate exactly:

```text
review_pack_schema_version
manifest_hash_policy
review_phase
run_id
symbol
evidence_schema_version
members
member_sha256
all frozen guardrail keys
```

Reject:

```text
extra/missing keys
wrong JSON types
bool-as-int aliases
wrong schema/review phase/symbol/run ID
wrong member order
missing/extra/duplicate ZIP members
absolute paths
`..` segments
backslashes
stale or malformed hashes
self-hash
missing/non-complete status
non-canonical JSON or JSONL
```

Require exactly 18 members and exactly 17 lowercase SHA-256 hashes for non-manifest members.

The builder must:

```text
validate the source directory semantically before ZIP creation;
create a temporary ZIP in the destination directory;
run the full semantic checker against the temporary ZIP;
atomically replace the destination only on success;
remove the temporary ZIP on every failure;
create destination parent directories safely;
print strict compact JSON without traceback for expected errors.
```

## Defect 10 — reports are placeholders

### Task 10 — deterministic contradiction-proof reports

`public_batch_report.md` must be derived from reconstructed evidence and include:

```text
run_id and symbol
Bybit server time and last closed cutoff
exact 1001-row window start/end/count
page counts for every plan
instrument counts and replay-eligible count
trade/mark/funding normalized row counts
funding observation count
all four primary/alternate equality booleans
public batch audit result
reproducibility audit result
contains_credentials=false
```

`risk_budget_readiness_report.md` must list every closed guardrail and state explicitly that the pack does not prove:

```text
profitability
parameter suitability
native grid equivalence
native quantity mapping
liquidation behavior
funding-history completeness
5 USDT maximum-loss budget
live readiness
```

Checker must rebuild and compare exact report bytes.

## Task 11 — exact status and artifact contracts

Define exact key/type contracts for every singleton JSON artifact:

```text
public_batch_run_status.json
capture_plan.json
server_time.json
instrument_universe_audit.json
public_batch_audit.json
cross_plan_reconciliation_audit.json
reproducibility_audit.json
capture_summary.json
review_pack_manifest.json
```

For status:

```text
building: exact run_id + status only, unless a version field is explicitly frozen
failed: exact run_id + status + exception_type + exception_message
complete: exact run_id + status + evidence validation success/count fields derived from evidence
```

A run status must not claim that a ZIP exists or passed.

## Task 12 — complete regression matrix

The focused closure tests must cover the frozen Sprint 06.3B requirements rather than only four smoke tests.

At minimum add deterministic synthetic/mocked tests for:

### Recording and strict JSON

1. imports perform no network call;
2. public endpoint/query/header allowlist;
3. exact constructor bounds;
4. duplicate JSON key rejected;
5. JSON float rejected;
6. NaN/Infinity rejected;
7. `1` vs `true` exact identity rejected;
8. raw SHA mismatch rejected;
9. invalid UTF-8 rejected;
10. bounded 429/5xx retry;
11. transport failure does not fabricate a body;
12. response is closed.

### Pagination and plans

13. bool/float/string limit aliases rejected;
14. exact 1001-row 1000 plan = `[1000, 1]`;
15. exact 1001-row 251 plan = `[251, 251, 251, 248]`;
16. reverse API rows normalize ascending;
17. boundary rows appear once;
18. missing/duplicate kline fails;
19. instrument 1000/200 plans reconcile;
20. cursor cycle, duplicate symbol and max-pages fail;
21. funding backward and chunked plans reconcile for >200 records;
22. chunk truncation risk and no-progress fail;
23. plan IDs and request sequence exactness enforced.

### Pure assembly and audit

24. pure assembly equals network-orchestrated assembly;
25. cross-symbol/category rows fail;
26. trade/mark timestamp mismatch fails;
27. unclosed candle fails;
28. start-boundary and end-boundary funding observations are included;
29. missing/extra/duplicate funding observation fails;
30. mapping-proxy dataclass canonical serialization succeeds.

### Lifecycle

31. building -> complete with a full synthetic public capture;
32. early failure -> failed;
33. late/read-back/reconstruction failure -> failed;
34. fixture/test path cannot mark an incomplete two-file run complete;
35. normal CLI path invokes capture rather than placeholder exception.

### Pack/checker tamper matrix

36. exact 18 members and 17 hashes pass;
37. manifest self-hash absent;
38. extra manifest field rejected;
39. wrong manifest type/value rejected;
40. missing/extra/duplicate/unsafe member rejected;
41. rehashed raw-body tamper rejected semantically;
42. rehashed endpoint/params/plan tamper rejected;
43. rehashed instrument row tamper rejected;
44. rehashed trade row tamper rejected;
45. rehashed mark row tamper rejected;
46. rehashed funding rate/observation tamper rejected;
47. rehashed request-page audit tamper rejected;
48. rehashed cross-plan audit tamper rejected;
49. rehashed status/summary/report/guardrail tamper rejected;
50. builder temporary self-check and atomic replace;
51. builder removes temp ZIP on failure;
52. missing ZIP/checker error emits strict JSON without traceback;
53. no private/live/order/Telegram implementation;
54. no generated/binary files committed under deterministic source roots.

Small generated fixtures inside `tmp_path` are allowed. No real network in pytest.

## Task 13 — documentation

Update `docs/bybit_public_batch_input_contract_v1.md` to describe:

```text
real owner network lifecycle
plan-scoped raw response records
exact 1001-row window
100-day dual-plan funding retrieval
persisted-input-first reconstruction
semantic tamper resistance
manifest self-excluded hash policy
funding boundary observation rule
what cross-plan equality proves and does not prove
all closed guardrails
next stage remains Parquet storage/resume/gap repair only after acceptance
```

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py -q
python -m pytest -q
ruff check .
git diff --check
```

Codex must not run the owner network command.

## Acceptance criteria before owner rerun

```text
normal owner CLI contains no placeholder failure;
full synthetic lifecycle produces all 17 non-manifest source artifacts plus status;
strict read-back reconstructs evidence from raw bodies;
1001-row dual-plan kline fixtures reconcile;
>200-row dual-plan funding fixtures reconcile;
canonical serializer handles real immutable audit models;
exact JSON type identity rejects bool/int aliases;
checker rejects a fully rehashed semantic fake;
builder runs semantic preflight and temporary self-check;
focused closure test matrix passes;
full suite passes;
Ruff and no-live audit pass;
no generated artifact committed;
all safety/risk/parameter/live guardrails remain closed.
```

## Owner run after Codex completion

The owner should remove the previous failed run directory and stale destination pack, then run:

```powershell
$python = "C:\VV\PyMoneyMaker\.venv\Scripts\python.exe"
$runId = "bybit_public_batch_063b_btcusdt_v1"
$runRoot = "data\processed\public_batch_runs"
$pack = "pm_review_pack_bybit_public_batch_bybit_public_batch_063b_btcusdt_v1.zip"

Remove-Item -Recurse -Force "$runRoot\$runId" -ErrorAction SilentlyContinue
Remove-Item -Force $pack -ErrorAction SilentlyContinue

& $python scripts\run_bybit_public_batch_evidence.py `
  --run-id $runId `
  --symbol BTCUSDT `
  --kline-row-count 1001 `
  --funding-lookback-days 100 `
  --output-root $runRoot
if ($LASTEXITCODE -ne 0) { throw "public batch evidence capture failed" }

& $python scripts\make_bybit_public_batch_review_pack.py `
  --run-id $runId `
  --input-root $runRoot `
  --output $pack
if ($LASTEXITCODE -ne 0) { throw "review pack build failed" }

& $python scripts\check_bybit_public_batch_review_pack.py `
  --zip $pack `
  --run-id $runId
if ($LASTEXITCODE -ne 0) { throw "review pack check failed" }
```

Do not use `--no-network-fixture-mode` as a workaround.

## Required Codex return

Return text only:

```text
commit hash
changed text files
git diff --stat
numeric environment output
pip check output
no-live output
06.3A output
06.3A.1 output
06.3B output
06.3B.1 closure output
full pytest output
Ruff output
git diff --check output
normal owner lifecycle implementation summary
plan provenance summary
strict JSON/type-identity summary
canonical serializer summary
cross-plan reconciliation summary
persisted reconstruction summary
funding boundary summary
semantic checker/tamper summary
builder atomicity summary
all guardrail values
known remaining limitations
```

Do not return or upload owner-generated ZIP/JSON/JSONL/market data, `.env`, API keys or owner logs from the Codex environment.
