# Sprint 06.3B.3.1 — Evidence Truthfulness and Real Regression Closure

## Status

Mandatory narrow closure sprint.

Do not start Sprint 06.4, Parquet storage, parameter research, private API integration, Telegram, or live execution.

Codex must not make real network calls and must not run the canonical owner capture. The owner public connectivity probe has already succeeded on both approved hosts and must not be repeated by Codex.

## Motivation

Sprint 06.3B.3 repaired the deterministic runner failures. Independent PM testing confirmed that the full synthetic lifecycle is executable for both approved hosts and that temporary lifecycle cleanup works.

However, the canonical evidence cannot be accepted because:

1. the reproducibility audit claims 16 non-status artifacts were rebuilt twice while the checker reports only 15 rebuilt artifacts;
2. reproducibility success values are still written as unconditional literals before the comparison is known;
3. 37 of the claimed 81 focused cases are no-op count inflation;
4. unexpected directories are ignored by directory validation;
5. unknown/wrong page audits are not rejected;
6. the risk report does not enumerate every exact guardrail key/value.

This sprint must close those issues without changing accepted Bybit parsing, pagination, OHLC replay, funding, or neutral-grid formulas.

## Non-negotiable safety constraints

- Public Bybit `GET /v5/market/*` only.
- No API keys, secrets, cookies, credentials, `.env` access, or private headers.
- No account/order/grid/position/wallet endpoints.
- No live execution.
- No Telegram.
- No parameter selection.
- No profitability or live-readiness claims.
- No real network calls in pytest.
- Preserve both approved base URLs without automatic fallback.
- Preserve `funding_coverage_proven_bool=false`.
- Preserve canonical owner arguments:
  - `run_id=bybit_public_batch_063b_btcusdt_v1`
  - `symbol=BTCUSDT`
  - `kline_row_count=1001`
  - `funding_lookback_days=100`

## Task 1 — define source and derived evidence sets exactly

Keep:

```python
NON_STATUS_ARTIFACT_COUNT = len(CANONICAL_MEMBERS) - 2  # 16
```

This is the count of every canonical member except manifest and status.

Add frozen explicit sets/tuples such as:

```python
SOURCE_ARTIFACT_MEMBERS = (
    "recorded_public_responses.jsonl",
)

DERIVED_ARTIFACT_MEMBERS = tuple(
    name
    for name in CANONICAL_MEMBERS
    if name not in {
        "review_pack_manifest.json",
        "public_batch_run_status.json",
        *SOURCE_ARTIFACT_MEMBERS,
    }
)
```

Expected current counts:

```text
source artifact count = 1
derived artifact count = 15
non-status artifact count = 16
```

Validate these relationships with exact assertions at import/test time without using them as fake test-count inflation.

Do not claim that persisted raw responses are reconstructed from typed rows. They are independently validated as canonical source evidence and replayed to reconstruct derived evidence.

## Task 2 — implement truthful two-phase reproducibility derivation

Delete unconditional reproducibility success assignments from the artifact builder.

Required architecture:

1. A pure `_build_core_derived_artifacts(...)` builds deterministic derived bytes that do not depend on a pre-asserted reproducibility result.
2. Invoke that pure core builder independently twice from immutable reconstructed inputs.
3. Compare exact key sets and exact bytes.
4. Derive:

```text
reproducibility_audit_ok
rebuilt_derived_artifacts_twice_bool
derived_artifact_count
source_artifact_count
non_status_artifact_count
```

5. Fail closed if the independent builds differ.
6. Only after the comparison, build final:

```text
reproducibility_audit.json
capture_summary.json
public_batch_report.md
```

7. The final deterministic artifact map must itself be independently invokable and byte-identical on repeat invocation.

The audit schema must use truthful names. Recommended exact schema:

```json
{
  "run_id": "...",
  "reproducibility_audit_ok": true,
  "rebuilt_derived_artifacts_twice_bool": true,
  "source_artifact_count": 1,
  "derived_artifact_count": 15,
  "non_status_artifact_count": 16
}
```

Do not retain the misleading key:

```text
rebuilt_non_status_artifacts_twice_bool
```

Update schemas, docs, reports, builder, checker, and tests consistently.

## Task 3 — derive funding and cross-plan success values rather than assign literals

The final artifact builder must receive or calculate exact derived values for:

```text
funding_observation_times_equal_bool
instrument_primary_alternate_equal_bool
trade_primary_alternate_equal_bool
mark_primary_alternate_equal_bool
funding_primary_alternate_equal_bool
```

Do not assign these fields using unconditional `True` literals.

Acceptable pattern:

```python
funding_times_equal = actual_obs == expected_obs
if not funding_times_equal:
    fail
```

Then persist the derived variable.

Report lines may display `true` only by formatting the derived variable.

## Task 4 — reject every unexpected directory entry

Change `DirectoryEvidenceReader` and/or shared validation so the run directory must contain exactly 18 direct regular files and nothing else.

Reject:

- extra directory;
- symlink/junction;
- named pipe/socket/device where detectable;
- nested path;
- missing canonical file;
- extra regular file.

Do not silently filter non-files out of `names()`.

Add explicit tests for an extra directory and symlink. Skip the symlink test only when the platform genuinely cannot create one, and document the skip reason.

## Task 5 — strengthen page-audit invariants

Create one pure validator used by artifact generation and semantic validation.

Require every entry to be exact type `PublicRequestPageAudit`.

Reject:

- unknown `plan_id`;
- missing plan;
- wrong endpoint for plan;
- wrong limit for plan;
- negative or over-limit row count;
- wrong category or symbol for plan;
- extra server-time audit;
- wrong fixed trade/mark page sizes;
- broken instrument cursor chain;
- broken funding range progression where represented by the audit fields.

Preserve required acceptance rules:

```text
server_time_snapshot response count == 1
instrument_primary_1000 page count >= 1
instrument_alternate_200 page count >= 2
trade_primary_1000 page sizes == [1000, 1]
trade_alternate_251 page sizes == [251, 251, 251, 248]
mark_primary_1000 page sizes == [1000, 1]
mark_alternate_251 page sizes == [251, 251, 251, 248]
funding_primary_backward_200 page count >= 2
funding_alternate_chunked_100 chunk count >= 2
```

The persisted page-count values must come from this validated result.

## Task 6 — deterministic exact guardrail reports

Build both Markdown reports from exact derived models.

`risk_budget_readiness_report.md` must include one stable line for every `GUARDRAILS` key, in a frozen deterministic order, for example:

```text
- contains_credentials: false
- private_api_used_bool: false
- live_execution_present_bool: false
- risk_budget_proven_bool: false
- native_equivalence_proven_bool: false
- funding_coverage_proven_bool: false
- parameter_selection_authorized_bool: false
- sufficient_for_parameter_selection_bool: false
- live_authorized_bool: false
- sufficient_for_parquet_storage_engineering_bool: true
```

It must also retain the exact non-proof statements covering profitability, parameter suitability, native grid equivalence, native quantity mapping, liquidation behavior, funding-history completeness, 5 USDT maximum-loss budget, and live readiness.

`public_batch_report.md` must format all cross-plan, page, funding, public-audit, and reproducibility values from derived variables. No hardcoded success text.

Both reports remain byte-compared by directory and ZIP semantic validation.

## Task 7 — replace the padded focused suite with real behavior

Delete:

```python
@pytest.mark.parametrize("index", range(37))
def test_closure_matrix_case_count_regression(...):
    ...
```

No replacement test may exist solely to increase collection count.

Add a deterministic fixture capable of generating enough public responses to execute the real current code path without network:

```text
run_bybit_public_batch_evidence._run
→ persisted directory
→ shared validator
→ make_bybit_public_batch_review_pack.main
→ temporary ZIP self-check
→ check_bybit_public_batch_review_pack.main
```

Run this lifecycle for:

```text
https://api.bybit.com
https://api.bytick.com
```

The synthetic fixture must produce:

- at least 201 valid linear instruments so alternate limit 200 has at least two pages;
- exactly 1001 trade candles;
- exactly 1001 mark candles;
- at least two backward funding pages;
- at least two alternate funding chunks;
- funding records that join to mark candles where timestamps fall inside the kline window.

Success assertions:

```text
18 exact final files
status=complete
selected host preserved in every raw record
all records consumed
correct page sizes/counts
source/derived/non-status counts are truthful
all guardrail lines present
builder succeeds
standalone checker succeeds
```

## Task 8 — required real regression matrix

The focused closure suite must contain real tests for at least the following behaviors. Parametrization is allowed only when each parameter produces a materially distinct input/invariant.

### Lifecycle and atomicity

1. full lifecycle `api.bybit.com`;
2. full lifecycle `api.bytick.com`;
3. early failure cleanup;
4. mid failure cleanup;
5. late failure cleanup;
6. existing final directory rejected before client use;
7. validation failure never publishes final;
8. stale building directory not reused;
9. builder removes temporary ZIP on validation failure;
10. successful builder atomically replaces output.

### Directory/ZIP membership

11. alphabetical directory enumeration accepted;
12. extra regular file rejected;
13. extra directory rejected;
14. symlink rejected;
15. missing member rejected;
16. duplicate ZIP name rejected;
17. unsafe ZIP path rejected;
18. ZIP directory entry rejected.

### Reproducibility truthfulness

19. source count exact 1;
20. derived count exact 15;
21. non-status count exact 16;
22. second core build mismatch rejected;
23. second final build mismatch rejected;
24. old misleading reproducibility key rejected;
25. hardcoded/tampered reproducibility true rejected after rehash;
26. checker output reports truthful rebuilt derived count.

### Plan/provenance/records

27. both approved hosts round-trip;
28. mixed host record rejected;
29. wrong capture-plan host rejected;
30. wrong timeout type/range rejected;
31. plan order violation rejected;
32. missing plan records rejected;
33. unconsumed tail record rejected;
34. non-contiguous sequence rejected;
35. wrong endpoint for plan rejected;
36. wrong params for plan rejected;
37. bool/int parsed-payload alias rejected;
38. noncanonical raw-record JSONL rejected;
39. duplicate raw JSON key rejected;
40. float/non-finite token rejected.

### Page audits

41. exact trade primary sizes accepted;
42. exact trade alternate sizes accepted;
43. exact mark primary sizes accepted;
44. exact mark alternate sizes accepted;
45. wrong fixed size rejected for each kline plan;
46. unknown plan audit rejected;
47. wrong endpoint rejected;
48. wrong limit rejected;
49. over-limit row count rejected;
50. missing server-time audit rejected;
51. extra server-time audit rejected;
52. instrument alternate one-page result rejected;
53. funding primary one-page result rejected;
54. funding alternate one-chunk result rejected;
55. cursor-chain break rejected;
56. funding progression break rejected.

### Semantic/tamper/report guards

57. raw-body tamper with old hash rejected;
58. raw-body and hash tamper without derived updates rejected;
59. normalized artifact tamper plus manifest rehash rejected;
60. capture summary tamper plus manifest rehash rejected;
61. cross-plan audit tamper plus manifest rehash rejected;
62. public report tamper plus manifest rehash rejected;
63. risk report tamper plus manifest rehash rejected;
64. failed status pack rejected;
65. building status pack rejected by standalone checker;
66. every exact guardrail appears in risk report;
67. a guardrail value tamper is rejected;
68. funding expected/actual timestamp mismatch rejected;
69. alternate row inequality rejected;
70. fake fully rehashed non-reconstructable pack rejected;
71. noncanonical JSON rejected;
72. noncanonical JSONL rejected.

Additional real cases are welcome. A numeric collection target does not replace this behavioral list.

## Task 9 — exact status and checker output

Keep lifecycle status count:

```text
non_status_artifact_count = 16
```

Update checker output to distinguish:

```json
{
  "ok": true,
  "members": 18,
  "non_status_artifact_count": 16,
  "source_artifact_count": 1,
  "rebuilt_derived_artifact_count": 15
}
```

Names may vary only if equally explicit and documented. Do not use `rebuilt_artifacts` without defining whether raw source evidence is included.

## Task 10 — documentation

Update:

```text
docs/bybit_public_batch_input_contract_v1.md
```

It must state:

- raw response JSONL is canonical source evidence;
- 15 artifacts are derived from that source;
- manifest and status are lifecycle members;
- reproducibility compares independently built derived artifacts;
- directory evidence forbids extra non-file entries;
- the standalone checker reconstructs from persisted raw source bytes.

## Required commands

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
python -m pytest tests/test_sprint_06_3b_3_1_evidence_truthfulness.py -q
python -m pytest -q
ruff check .
git diff --check
```

Do not run:

```text
scripts/probe_bybit_public_connectivity.py
scripts/run_bybit_public_batch_evidence.py  # against real network
```

The runner may be invoked only with the deterministic injected synthetic client in pytest.

## Acceptance criteria before owner capture

All must be true:

```text
full synthetic lifecycle is committed and passes for both hosts
no counter-only/no-op test inflation exists
source/derived/non-status counts are exact and truthful
no unconditional reproducibility success values remain
funding/cross-plan booleans are derived
extra directories and symlinks are rejected
unknown/wrong page audits are rejected
reports enumerate all exact guardrails and derived values
standalone checker rejects all rehashed semantic tampering
full suite, Ruff, pip check, no-live and diff check pass
source archive is clean
no real network capture was run by Codex
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
focused collection count and named behavioral coverage summary
all focused pytest outputs
full pytest output
Ruff output
git diff --check output
source/derived/member-count design summary
two-phase reproducibility derivation summary
directory exact-entry validation summary
page-audit validation summary
report guardrail summary
full synthetic lifecycle summary for both hosts
tamper matrix summary
source hygiene summary
confirmation that no real network or private/live action was run
```
