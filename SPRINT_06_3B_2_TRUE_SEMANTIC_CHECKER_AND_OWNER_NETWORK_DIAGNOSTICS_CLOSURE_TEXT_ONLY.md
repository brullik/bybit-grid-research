# Sprint 06.3B.2 — True Semantic Checker and Owner Network Diagnostics Closure

## Status

Mandatory closure sprint.

Do not start Sprint 06.4, Parquet storage, parameter research, private API integration or live execution.

## Motivation

Sprint 06.3B.1 introduced a real public-only owner capture path, but the gate remains blocked for two independent reasons:

1. the owner capture failed with a context-free `transport_error:TimeoutError`;
2. the standalone review-pack checker remains structural/hash-based and accepts fully rehashed semantic fabrications.

The purpose of this sprint is to make persisted public evidence independently reconstructable, semantically verifiable and operationally diagnosable while preserving all no-private/no-live guardrails.

## Non-negotiable safety constraints

- Public Bybit `GET /v5/market/*` only.
- No API keys or credentials.
- No private/account/order/grid/position/wallet endpoints.
- No live execution.
- No Telegram.
- No parameter selection.
- No profitability or live-readiness claims.
- No real network calls in pytest.
- Codex must not run the canonical owner capture.
- Do not alter accepted neutral-grid or OHLC replay formulas, fixtures or outputs.

## Files in scope

Expected primary scope:

```text
src/bybit_grid/data/public_batch/recording.py
src/bybit_grid/data/public_batch/capture.py
src/bybit_grid/data/public_batch/reconstruct.py
src/bybit_grid/data/public_batch/evidence.py
src/bybit_grid/data/public_batch/audit.py
src/bybit_grid/data/public_batch/models.py
scripts/run_bybit_public_batch_evidence.py
scripts/make_bybit_public_batch_review_pack.py
scripts/check_bybit_public_batch_review_pack.py
scripts/probe_bybit_public_connectivity.py            # new
tests/test_sprint_06_3b_2_true_semantic_closure.py   # new
docs/bybit_public_batch_input_contract_v1.md
```

Small helper modules are allowed when they keep responsibilities explicit.

## Task 1 — one shared persisted-evidence validator

Implement a single semantic validation engine used by all four paths:

```text
owner run-directory validation
review-pack builder preflight
review-pack temporary self-check
standalone review-pack checker
```

Recommended design:

```python
class EvidenceReader(Protocol):
    def names(self) -> tuple[str, ...]: ...
    def read_bytes(self, name: str) -> bytes: ...

class DirectoryEvidenceReader: ...
class ZipEvidenceReader: ...

def validate_persisted_public_batch_evidence(
    reader: EvidenceReader,
    *,
    expected_run_id: str,
    require_complete_status: bool,
) -> ValidationResult:
    ...
```

The semantic engine must start from persisted bytes, especially `recorded_public_responses.jsonl`. It must not trust in-memory capture objects or persisted normalized artifacts.

The standalone checker must invoke this engine. Hash validation alone is never sufficient.

## Task 2 — exact member and singleton schemas

Freeze exact key sets, exact JSON types and exact values for:

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

Requirements:

- reject extra and missing fields;
- reject bool-as-int aliases;
- reject wrong strings, counts, symbols, run IDs, versions and guardrails;
- require exact `BTCUSDT`, exact 1001-row window and exact 100-day funding lookback for this canonical run;
- require `status=complete` in a review pack;
- complete status must have an exact key set;
- derive the non-status artifact count from `CANONICAL_MEMBERS`;
- use the correct value: 16 non-status members in the current 18-member pack;
- status must not claim ZIP creation or ZIP validation.

Building and failed status schemas remain exact:

```text
building: run_id + status
failed: run_id + status + exception_type + exception_message
complete: run_id + status + evidence_validation_ok + non_status_artifact_count
```

## Task 3 — canonical JSON and JSONL byte enforcement

For every `.json` member:

```text
strict parse -> exact schema/type validation -> canonical reserialize -> exact byte equality
```

For every `.jsonl` member:

```text
UTF-8 strict decode
final newline required when non-empty
no blank lines
strict parse every line
exact line schema/type validation
canonical reserialize every line
canonical line bytes + newline must equal original bytes exactly
```

`records_from_jsonl()` must enforce the exact recorded-response key set.

No parser may ignore unknown fields.

## Task 4 — lossless canonical mapping policy

In canonical evidence, JSON object keys must be exact non-empty strings.

Reject all non-string mapping keys. Do not call `str(k)`.

Add regressions for:

```python
{1: "a"}
{True: "a"}
{1: "a", "1": "b"}
{False: "a", "False": "b"}
```

All must fail. No collision or silent overwrite is allowed.

## Task 5 — executable capture-plan provenance

Expand `capture_plan.json` into a complete frozen contract containing at least:

```text
run_id
schema_version
base_url
symbol=BTCUSDT
category=linear
interval=1
kline_row_count=1001
funding_lookback_days=100
ordered plan specifications
```

Each plan specification must freeze:

```text
plan_id
endpoint
pagination method
page limit / target records
fixed params
order index
acceptance page-count rule
```

Dynamic cursor and time-window transitions are reconstructed and verified from raw responses plus the frozen plan.

The selected base URL must be persisted. Allowed owner values are exactly:

```text
https://api.bybit.com
https://api.bytick.com
```

Do not automatically mix or fallback between hosts inside one canonical run.

## Task 6 — exact recorded-response stream validation

Every recorded response must have an exact schema including the selected base URL or an unambiguous reference to it through the capture plan.

Validate:

- contiguous sequence IDs starting at 1;
- server-time record first and exactly once;
- exact global plan order;
- no interleaving outside the frozen order;
- exact endpoint and params;
- exact public-only path;
- exact plan ID;
- raw SHA-256;
- strict raw-body parse;
- exact parsed-payload identity;
- approved HTTP status/content type policy;
- no extra records;
- no missing records;
- no duplicate tail records.

`ReplayClient` must expose and use `assert_exhausted()` for every plan. The shared validator must also verify that all records in the global stream were consumed exactly once.

## Task 7 — actual semantic reconstruction

From only `recorded_public_responses.jsonl` and the frozen capture plan, independently:

1. parse server time exactly once;
2. derive the exact closed 1001-row minute window;
3. reconstruct both instrument plans;
4. rebuild both universe audits;
5. reconcile instrument rows by canonical normalized bytes in symbol order;
6. reconstruct both trade plans;
7. reconstruct both mark plans;
8. reconstruct both funding plans;
9. reconcile all primary/alternate normalized rows;
10. rebuild every request-page audit;
11. assemble the primary replay batch;
12. rerun the public-batch audit;
13. rebuild exact funding observations;
14. rebuild cross-plan audit;
15. rebuild summary and reports;
16. compare every deterministic artifact byte-for-byte.

Persisted normalized JSON/JSONL members are outputs to verify, never inputs to trust.

## Task 8 — enforce page-count and window invariants

For the canonical owner run enforce:

```text
instrument primary page count >= 1
instrument alternate page count >= 2
trade primary page sizes [1000, 1]
trade alternate page sizes [251, 251, 251, 248]
mark primary page sizes [1000, 1]
mark alternate page sizes [251, 251, 251, 248]
funding primary page count >= 2
funding alternate chunk count >= 2
```

Also enforce:

- no cursor cycles;
- no duplicate symbols;
- no max-page overflow;
- no kline gaps, overlaps or duplicates;
- exact ascending 1001 timestamps;
- exact trade/mark timestamp equality;
- no funding duplicates;
- no funding out-of-range rows;
- strict funding pagination progress;
- no chunk truncation risk.

Keep `funding_coverage_proven_bool=false`.

## Task 9 — exact funding-observation audit

Derive:

```python
expected_funding_observation_times = tuple(
    f.funding_time_ms
    for f in funding_rates
    if window.start_open_time_ms <= f.funding_time_ms <= window.end_open_time_ms
)
```

Require exact equality with the observation timestamp tuple.

Reject:

- missing start-boundary observation;
- missing end-boundary observation;
- missing mark candle;
- extra observation;
- duplicate observation;
- wrong funding rate;
- wrong mark price;
- wrong source/category/symbol.

Extend the audit model with exact expected/actual count and tuple checks if needed.

## Task 10 — derived cross-plan and reproducibility audits

Remove hardcoded success booleans.

`cross_plan_reconciliation_audit.json` must be constructed from actual comparisons and actual page counts.

`reproducibility_audit.json` must be derived by:

```text
build canonical non-status artifact byte map A
build the same byte map independently again as B
require A == B
record exact member count and success
```

Do not hardcode `True`.

## Task 11 — deterministic complete reports

`public_batch_report.md` must be rebuilt from validated evidence and include exactly:

```text
run_id
base_url
symbol
Bybit server time
last closed cutoff
window start/end/count
page count and page sizes for every plan
instrument count
replay-eligible count
trade row count
mark row count
funding row count
funding observation count
four primary/alternate equality booleans
public batch audit result
reproducibility audit result
contains_credentials=false
```

`risk_budget_readiness_report.md` must enumerate every frozen guardrail and explicitly state that the pack does not prove:

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

The checker must rebuild and compare exact Markdown bytes.

## Task 12 — HTTP recording cleanup

In `RecordingPublicClient`:

- close normal responses deterministically;
- explicitly close `HTTPError` response objects after reading;
- preserve actual final HTTP response before downstream parser failure;
- keep transport failures fail-closed with no fabricated body;
- keep retries restricted to actual 429 and 5xx responses;
- preserve import safety.

Add exact context to transport errors without credentials:

```text
transport_error:<ExceptionType>:plan_id=<id>:endpoint=<path>:attempt=<n>
```

Do not include secret-bearing values; this client is public-only.

## Task 13 — owner connectivity diagnostics

Add `scripts/probe_bybit_public_connectivity.py`.

It must:

- be public-only and import-safe;
- accept exact `--base-url` from the two approved hosts;
- accept exact integer `--timeout-seconds` in a bounded range, recommended 1..120;
- call only `GET /v5/market/time`;
- perform a small explicit number of independent probes, recommended 3;
- emit one strict compact JSON object;
- report base URL, attempt count, per-attempt success/failure type and elapsed milliseconds;
- never auto-select a host;
- never write a canonical evidence run;
- never use credentials;
- return non-zero only when all attempts fail.

Update the canonical runner to accept:

```text
--base-url
--timeout-seconds
```

Defaults:

```text
--base-url https://api.bybit.com
--timeout-seconds 30
```

Validate exact types/ranges. Persist the selected base URL and timeout policy in the capture plan and summary. A single canonical run must use one host only.

## Task 14 — atomic lifecycle and clean failure semantics

The owner lifecycle must retain:

```text
building first
complete last
failed last on every exception
```

Additional requirements:

- do not leave stale `complete` after failure;
- remove/replace stale deterministic artifacts before a fresh run or require an empty run directory;
- no partial artifact set may be packaged;
- builder must use the shared semantic validator before ZIP creation;
- temporary ZIP must be checked by the same full semantic validator;
- temporary ZIP removed on every failure;
- destination replaced atomically only after success;
- standalone checker must reject `status!=complete`.

Diagnostic failure context belongs in failed status. Do not claim a pack exists in status.

## Task 15 — complete focused regression matrix

Create a focused deterministic suite. The prior 11-case file is insufficient.

At minimum cover all of the following:

### Recording and transport

1. imports make no network calls;
2. approved base URLs pass;
3. unapproved/HTTP base URLs fail;
4. public endpoint allowlist;
5. credential-like params fail;
6. exact constructor bounds;
7. duplicate JSON key fails;
8. float fails;
9. NaN/Infinity fail;
10. bool/int exact identity failures;
11. SHA mismatch fails;
12. invalid UTF-8 fails;
13. 429 retry bounded;
14. 5xx retry bounded;
15. non-retryable 4xx not retried;
16. transport failure has plan/endpoint/attempt context;
17. transport failure creates no fabricated record;
18. normal response closes;
19. HTTPError closes.

### Canonical encoding

20. MappingProxyType dataclass succeeds;
21. Decimal exact strings;
22. enum scalar values;
23. float/set/bytes/Path/unknown fail;
24. non-string mapping keys fail;
25. key-collision examples fail;
26. noncanonical JSON fails;
27. noncanonical JSONL whitespace/order fails;
28. blank JSONL line fails;
29. final newline missing fails;
30. extra record field fails.

### Plans and pagination

31. exact 1001 primary trade plan;
32. exact 1001 alternate trade plan;
33. same for mark;
34. instrument primary/alternate reconcile;
35. alternate instrument page count >=2;
36. cursor cycle fails;
37. duplicate symbol fails;
38. extra/unconsumed plan record fails;
39. swapped plan fails;
40. interleaved plan sequence fails;
41. duplicate tail record fails;
42. funding >200 primary/alternate reconcile;
43. funding page/chunk minima enforced;
44. funding truncation/no-progress fail.

### Assembly and audit

45. pure/network-replayed assembly equality;
46. 1001 complete timestamps;
47. trade/mark mismatch fails;
48. unclosed candle fails;
49. start-boundary funding included;
50. end-boundary funding included;
51. missing/extra/duplicate observation fails;
52. wrong mark/funding source fails.

### Lifecycle and semantic tamper

53. full synthetic building -> complete lifecycle;
54. early failure -> failed;
55. late rebuild failure -> failed;
56. exact complete status count is derived and equals 16;
57. fully fabricated rehashed ZIP fails;
58. failed-status rehashed ZIP fails;
59. fake-symbol rehashed ZIP fails;
60. raw-body rehash tamper fails;
61. endpoint/params/plan rehash tamper fails;
62. normalized instrument/trade/mark/funding tamper fails;
63. funding observation tamper fails;
64. page-audit tamper fails;
65. cross-plan/reproducibility tamper fails;
66. summary/report/guardrail tamper fails;
67. missing/extra/duplicate/unsafe ZIP member fails;
68. builder source preflight is semantic;
69. temporary ZIP self-check is semantic;
70. temporary ZIP removed on failure;
71. no-live audit remains clean;
72. source archive hygiene excludes caches/binaries.

The focused suite may have more than 72 tests due parameterization. No real network in pytest.

Delete or rewrite the old test that asserts placeholder fabricated packs are valid.

## Task 16 — documentation and source hygiene

Update the public batch contract documentation to match actual behavior, not intended behavior.

Document:

- selected base URL provenance;
- owner connectivity probe;
- no automatic cross-host fallback;
- exact semantic validation flow;
- exact JSONL canonical enforcement;
- exact plan consumption;
- derived reproducibility;
- funding one-to-one observation rule;
- all closed guardrails.

Remove all generated files from the source handoff:

```text
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
generated review packs
owner logs
run data
```

Return a clean source ZIP. If Git is available, include the commit hash. If Git remains unavailable, include the clean source ZIP SHA-256.

## Required commands for Codex

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_2_true_semantic_closure.py -q
python -m pytest -q
ruff check .
git diff --check
```

Codex must not run:

```text
scripts/run_bybit_public_batch_evidence.py
```

against the real network.

Synthetic/injected responses only.

## Acceptance criteria before owner network activity

All must be true:

```text
one shared validator is used by directory, builder and standalone ZIP checker
fully fabricated rehashed pack is rejected
failed-status pack is rejected
noncanonical JSONL is rejected
all records are consumed exactly once
capture plan freezes base URL and exact plan semantics
cross-plan booleans/page counts are derived
reproducibility is derived by two independent builds
funding observation audit is one-to-one
complete status count is derived and correct
reports contain all required evidence-derived fields
connectivity probe exists and is public-only
owner timeout errors identify plan and endpoint
focused closure matrix passes
full suite passes
Ruff/no-live/pip checks pass
clean source archive contains no caches or binaries
all private/live/risk/parameter guardrails remain closed
```

## Owner procedure after PM code review only

Do not run this section until PM explicitly opens the owner-network gate.

First probe both official hosts independently:

```powershell
$python = "C:\VV\PyMoneyMaker\.venv\Scripts\python.exe"

& $python scripts\probe_bybit_public_connectivity.py `
  --base-url https://api.bybit.com `
  --timeout-seconds 30

& $python scripts\probe_bybit_public_connectivity.py `
  --base-url https://api.bytick.com `
  --timeout-seconds 30
```

Choose one host that succeeds. Do not combine hosts in one run.

The canonical capture command will then be issued by PM with the selected host.

## Required Codex return

Return text only:

```text
commit hash or clean source ZIP SHA-256
changed text files
git diff --stat
numeric environment output
pip check output
no-live output
06.3A output
06.3A.1 output
06.3B output
06.3B.1 output
06.3B.2 focused output
full pytest output
Ruff output
git diff --check output
shared semantic validator design
exact schema/canonical JSONL summary
plan-consumption summary
capture-plan provenance summary
cross-plan/page-count derivation summary
funding observation audit summary
reproducibility derivation summary
network probe and timeout-context summary
builder/checker atomicity summary
source hygiene summary
all guardrail values
```
