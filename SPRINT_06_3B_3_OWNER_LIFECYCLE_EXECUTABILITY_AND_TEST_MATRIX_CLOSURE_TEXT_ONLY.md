# Sprint 06.3B.3 — Owner Lifecycle Executability and Closure Matrix

## Status

Mandatory closure sprint.

Do not start Sprint 06.4, Parquet storage, parameter research, private API integration or live execution.

Codex must not make real network calls and must not run the canonical owner capture.

## Motivation

Sprint 06.3B.2 introduced the shared semantic validator and public connectivity probe, but the canonical owner lifecycle is still not executable. Two deterministic runtime failures were reproduced during PM review:

```text
recorded_response_key_set_invalid
DirectoryEvidenceReader.names() order mismatch
```

The sprint also retains prohibited mapping-key conversion, non-independent reproducibility, hardcoded reconciliation success, unenforced page-count rules and an incomplete regression matrix.

The purpose of 06.3B.3 is to make the full synthetic lifecycle executable and independently tested before any canonical owner network capture.

## Non-negotiable safety constraints

- Public Bybit `GET /v5/market/*` only.
- No API keys, secrets, cookies or credentials.
- No private/account/order/grid/position/wallet endpoints.
- No live execution.
- No Telegram.
- No parameter selection.
- No profitability or live-readiness claims.
- No real network calls in pytest.
- Do not alter accepted neutral-grid/OHLC replay formulas or accepted fixtures.
- Preserve `funding_coverage_proven_bool=false`.

## PM-reproduced failures that must become regression tests

### Failure 1 — runner rejects its own recorded rows

`canonical_jsonl_bytes(client.records)` emits `base_url`. The runner then calls `records_from_jsonl()` without `capture_plan`, causing:

```text
PublicBatchError: recorded_response_key_set_invalid
```

### Failure 2 — directory validator can never accept canonical members

`DirectoryEvidenceReader.names()` returns alphabetical filesystem order, while the shared validator compares it to the non-alphabetical `CANONICAL_MEMBERS` tuple.

### Failure 3 — alternate host is discarded in reconstructed model

`records_from_jsonl()` does not pass persisted `base_url` into `RecordedPublicResponse`, so `api.bytick.com` falls back to the dataclass default.

### Failure 4 — prohibited MappingProxy integer conversion remains

`canonical_json_bytes(MappingProxyType({480: 1}))` currently succeeds. It must fail.

## Task 1 — make reader member validation order-independent and exact

Change the shared validator so directory/ZIP member validation enforces:

```text
exact set
exact count
no duplicates
no unsafe names
no non-file directory members
```

Do not require filesystem order equality.

After validation, always read in `CANONICAL_MEMBERS` order:

```python
actual_names = reader.names()
if len(actual_names) != len(set(actual_names)):
    fail
if set(actual_names) != set(CANONICAL_MEMBERS):
    fail
member_bytes = {name: reader.read_bytes(name) for name in CANONICAL_MEMBERS}
```

ZIP entry order may be recorded for diagnostics but must not replace exact set semantics.

Add a regression proving a valid directory passes despite alphabetical enumeration.

## Task 2 — freeze and persist capture plan before replay parsing

Expose a public pure builder such as:

```python
def build_capture_plan(
    *, run_id: str, symbol: str, base_url: str, timeout_seconds: int
) -> dict:
    ...
```

The owner runner must:

1. validate exact canonical arguments before network activity;
2. create a clean temporary run directory;
3. write `status=building`;
4. write canonical `capture_plan.json` before or immediately after raw capture;
5. persist canonical `recorded_public_responses.jsonl`;
6. read `capture_plan.json` back from persisted bytes;
7. call `records_from_jsonl(raw_bytes, capture_plan=persisted_plan)`;
8. reconstruct only from persisted bytes.

Remove any canonical runner path that parses recorded rows without the persisted plan.

`records_from_jsonl()` must always preserve:

```python
base_url=d["base_url"]
```

inside `RecordedPublicResponse`.

Add end-to-end tests for both approved hosts.

## Task 3 — exact canonical owner arguments

The canonical owner run is frozen to:

```text
run_id=bybit_public_batch_063b_btcusdt_v1
symbol=BTCUSDT
kline_row_count=1001
funding_lookback_days=100
```

Only these may vary:

```text
base_url in {https://api.bybit.com, https://api.bytick.com}
timeout_seconds exact int in 1..120
output_root
```

Reject wrong run ID, symbol, row count and lookback before network activity.

## Task 4 — atomic published lifecycle

Implement a clean sibling temporary directory, for example:

```text
<output_root>/.<run_id>.building.<pid-or-uuid>/
```

Requirements:

- Refuse an existing final `<output_root>/<run_id>` before network activity unless an explicit safe owner cleanup mode is separately designed and tested.
- Never reuse stale files.
- Build all candidate artifacts in the temporary directory.
- Derive complete status count from `NON_STATUS_ARTIFACT_COUNT`; never write literal `16` in runner logic.
- Build manifest from candidate complete bytes.
- Run the same shared validator with `require_complete_status=True` against the temporary directory.
- Only after validation succeeds, atomically publish/rename the temporary directory to final run directory on the same volume.
- A final published directory must appear only as semantically complete.
- On exception, remove the temporary candidate or publish a separate exact failed directory/status without ever leaving stale `complete`.
- No duplicate complete-status write.
- Failure context must contain no credentials.

Add injected early-, mid- and late-failure tests.

## Task 5 — reject every non-string mapping key

Canonical JSON object keys must be exact non-empty strings for every mapping type, including `MappingProxyType`.

Delete the special integer-key conversion branch. Do not call `str(k)` in the canonical serializer.

Because `funding_interval_counts` is currently `Mapping[int, int]`, change the audit/model source representation so it is constructed losslessly with canonical string keys before serialization, for example:

```text
"60"
"240"
"480"
```

The source conversion must validate collisions and exact positive integer semantics before producing strings.

Required regressions:

```python
{1: "a"}
{True: "a"}
MappingProxyType({480: 1})
{1: "a", "1": "b"}
{False: "a", "False": "b"}
```

All canonical serializer calls above must fail.

A real `BybitInstrumentUniverseAudit` must still serialize successfully because its model now contains string keys.

Rewrite the old test that expects MappingProxy integer conversion.

## Task 6 — exact successful-response evidence policy

Freeze exact `RecordedPublicResponse` field types and values.

For canonical successful evidence require at least:

```text
http_status exact int and equal to 200
content_type exact non-empty string whose media type is application/json
raw_body_text exact str
parsed_payload exact dict
base_url exact approved host
plan_id exact frozen ID
```

Keep recorder retry behavior restricted to 429/5xx. Preserve the actual final HTTP error body for downstream failure, but such a response must not become accepted canonical evidence.

Handle invalid UTF-8 for normal and `HTTPError` bodies with deterministic `PublicBatchError` context.

## Task 7 — enforce page-count and page-size acceptance rules

Create one pure derivation/validation function used by artifact construction and shared validation.

Require exactly:

```text
instrument_primary_1000 page count >= 1
instrument_alternate_200 page count >= 2
trade_primary_1000 page sizes == [1000, 1]
trade_alternate_251 page sizes == [251, 251, 251, 248]
mark_primary_1000 page sizes == [1000, 1]
mark_alternate_251 page sizes == [251, 251, 251, 248]
funding_primary_backward_200 page count >= 2
funding_alternate_chunked_100 chunk count >= 2
server_time_snapshot response count == 1
```

Reject missing, extra or wrong plan audits.

Do not merely persist these values; enforce them.

## Task 8 — derive cross-plan equality without literals

Preserve both primary and alternate normalized row sets long enough to compute exact canonical equality results:

```text
instrument_primary_alternate_equal_bool
trade_primary_alternate_equal_bool
mark_primary_alternate_equal_bool
funding_primary_alternate_equal_bool
```

Each value must be derived from actual normalized canonical bytes/typed rows. If any is false, fail closed.

The persisted cross-plan audit may contain `true`, but no artifact builder may assign these fields with unconditional literals.

Add a test that monkeypatches or injects one unequal alternate row and proves both failure and a derived false comparison before failure, as appropriate to the design.

## Task 9 — real independent reproducibility derivation

Delete:

```python
rebuilt2 = dict(rebuilt)
```

and all unconditional reproducibility success values.

Recommended design:

1. pure builder A independently creates the deterministic non-status artifact byte map from reconstructed typed evidence;
2. pure builder B independently invokes the same builder again from immutable reconstructed inputs;
3. compare exact keys and bytes;
4. derive `reproducibility_audit_ok` and `rebuilt_non_status_artifacts_twice_bool` from that comparison;
5. persist the exact derived member count;
6. fail if any byte differs.

Avoid circular self-inclusion by building the reproducibility audit after comparing a clearly defined pre-reproducibility artifact map, or by using a documented two-phase deterministic construction.

Add a test that forces the second build to differ and proves failure.

## Task 10 — deterministic reports from exact derived values

`public_batch_report.md` must have stable individual lines for every plan page count/page sizes. Do not embed a Python dict `repr`.

`risk_budget_readiness_report.md` must enumerate every exact `GUARDRAILS` key/value and all non-proof statements required by 06.3B.2.

Both reports must be rebuilt from typed/derived evidence and compared byte-for-byte by the shared validator.

## Task 11 — records parser must enforce canonical bytes in every caller

`records_from_jsonl()` must itself enforce:

```text
strict UTF-8
final newline
no blank lines
strict duplicate-key/float/non-finite rejection
exact line key set
canonical line byte equality
contiguous sequence
exact plan order
exact selected base URL
```

Do not depend on an outer validator to make runner use safe.

## Task 12 — full synthetic lifecycle test is mandatory

Create deterministic public-response fixtures sufficient to execute, without network:

```text
runner
-> persisted temporary directory
-> semantic directory validation
-> atomic final directory publication
-> review-pack builder preflight
-> temporary ZIP semantic self-check
-> standalone checker
```

The success test must assert:

```text
18 exact final members
status=complete
non_status_artifact_count derived
selected base_url preserved
all raw records consumed once
expected page sizes/counts
all output artifacts equal independently rebuilt bytes
ZIP checker succeeds
```

Run the same lifecycle for both approved base URLs.

## Task 13 — complete focused regression matrix

The previous 8-case file is not acceptable. Implement all 72 scenarios required by Sprint 06.3B.2 plus the new runtime regressions in this prompt.

At minimum, pytest collection for the focused closure files must report **72 or more executed cases**, not merely 72 conceptual bullets hidden inside a few unexecuted helpers.

Add explicit regressions for:

1. directory enumeration order;
2. runner recorded JSONL with base URL;
3. `api.bytick.com` round trip;
4. clean temporary directory lifecycle;
5. existing final run refusal before network;
6. complete never published on validation failure;
7. non-string MappingProxy key failure;
8. model-level string funding interval counts;
9. exact page-size enforcement;
10. independent second-build mismatch;
11. full directory-builder-ZIP-checker lifecycle;
12. failed status package rejection;
13. fully rehashed semantic fabrication rejection;
14. stale/extra directory member rejection;
15. invalid success HTTP status/content type rejection.

No real network in pytest.

## Task 14 — source hygiene and return evidence

The clean source ZIP must contain none of:

```text
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
owner_probe_artifacts/
owner logs
run data
generated review packs
.env
```

If Git is unavailable, return SHA-256 of the clean source ZIP.

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
python -m pytest tests/test_sprint_06_3b_3_owner_lifecycle_executability.py -q
python -m pytest -q
ruff check .
git diff --check
```

Codex must not run real:

```text
scripts/run_bybit_public_batch_evidence.py
```

## Acceptance criteria before canonical owner capture

All must be true:

```text
runner can parse its own persisted recorded JSONL
directory validator accepts canonical set independent of filesystem order
api.bytick.com provenance survives persisted reconstruction
canonical serializer rejects every non-string mapping key
funding interval count model uses canonical string keys
complete status is derived and atomically published only after validation
stale final run is rejected before network
response status/content-type policy is exact
all mandatory page counts/sizes are enforced
cross-plan booleans are derived
reproducibility is based on two independent builds
reports contain exact derived fields and all guardrails
records parser enforces canonical bytes itself
full synthetic runner-directory-builder-ZIP-checker lifecycle passes for both hosts
focused closure suite executes at least 72 cases
full suite, Ruff, pip check, no-live and diff check pass
clean source archive contains no caches, run data, probes or credentials
```

## Required Codex return

Return text only:

```text
commit hash or clean source ZIP SHA-256
changed text files
git diff --stat
numeric environment output
pip check output
no-live output
all focused outputs including executed case counts
full pytest output
Ruff output
git diff --check output
runner persisted-plan fix summary
directory reader fix summary
alternate-host provenance summary
atomic lifecycle summary
mapping-key/model migration summary
HTTP status/content-type policy summary
page-count invariant summary
cross-plan derivation summary
independent reproducibility summary
full synthetic lifecycle summary
source hygiene summary
all guardrail values
confirmation that no real network capture was run
```
