# Sprint 06.3B.3.2 — Reproducibility Reporting and Committed Lifecycle Closure

## Status

Mandatory narrow closure sprint.

Do not start Sprint 06.4, Parquet storage, parameter research, private API integration, Telegram, or live execution.

Codex must not make real network calls and must not run the canonical owner capture. The owner connectivity probe has already succeeded. The current source revision can execute a PM-built synthetic lifecycle, but that lifecycle is not committed and the reproducibility reporting sequence remains incorrect.

## Safety constraints

Preserve all existing guardrails:

- public Bybit `GET /v5/market/*` only;
- no API keys, secrets, cookies, credentials, `.env` reads, or private headers;
- no account/order/grid/position/wallet endpoints;
- no live execution;
- no Telegram;
- no parameter selection;
- no profitability/live-readiness claims;
- no real network calls in pytest;
- approved hosts only:
  - `https://api.bybit.com`
  - `https://api.bytick.com`;
- no automatic host fallback;
- canonical owner arguments remain frozen:
  - `run_id=bybit_public_batch_063b_btcusdt_v1`
  - `symbol=BTCUSDT`
  - `kline_row_count=1001`
  - `funding_lookback_days=100`.

## Task 1 — correct the two-phase artifact architecture

Refactor `src/bybit_grid/data/public_batch/reconstruct.py` so artifacts are built in this exact sequence:

1. Build immutable core candidate A.
2. Independently build immutable core candidate B from the same reconstructed inputs.
3. Compare exact core key sets.
4. Compare exact core bytes.
5. Derive named booleans from those comparisons.
6. Fail closed if either comparison is false.
7. Build final reproducibility model from the derived values.
8. Build `reproducibility_audit.json`, `capture_summary.json`, and `public_batch_report.md` only after step 5.
9. Independently build final derived map A and final derived map B.
10. Compare all 15 derived artifact names and bytes.
11. Fail closed on any difference.

The pre-comparison core must not include:

```text
reproducibility_audit.json
capture_summary.json
public_batch_report.md
```

It may include the remaining deterministic derived artifacts.

Do not use a shallow copy as the second build.

## Task 2 — persist derived reproducibility variables, not pre-asserted literals

Use explicit variables such as:

```python
core_key_sets_equal_bool = set(core_a) == set(core_b)
core_bytes_equal_bool = (
    core_key_sets_equal_bool
    and all(core_a[name] == core_b[name] for name in core_a)
)
reproducibility_audit_ok = core_key_sets_equal_bool and core_bytes_equal_bool
rebuilt_derived_artifacts_twice_bool = reproducibility_audit_ok
```

Fail before publication when false.

Persist the derived variables in the exact audit schema:

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

Do not restore the old misleading key `rebuilt_non_status_artifacts_twice_bool`.

## Task 3 — make summary and report post-comparison artifacts

`capture_summary.json` must include exact fields derived after the comparison:

```text
source_artifact_count
rebuilt_derived_artifact_count or derived_artifact_count
non_status_artifact_count
reproducibility_audit_ok
rebuilt_derived_artifacts_twice_bool
```

Keep all existing canonical capture, row-count, guardrail, and host fields.

`public_batch_report.md` must include stable lines generated from the same derived model:

```text
- source_artifact_count: 1
- derived_artifact_count: 15
- non_status_artifact_count: 16
- reproducibility_audit_ok: true
- rebuilt_derived_artifacts_twice_bool: true
```

It must continue to include server time, cutoff, page counts/sizes, row counts, funding comparison, cross-plan comparisons, public audit result, and guardrails.

The validator must byte-compare the rebuilt summary and report.

Update `docs/bybit_public_batch_input_contract_v1.md` so it matches the real build order exactly.

## Task 4 — one canonical production report path

Remove disconnected report-generation paths.

Requirements:

- production `artifact_bytes(...)` must call canonical report helpers;
- tests must assert the exact bytes emitted by the production artifact map;
- do not test an unused helper as a proxy for production output;
- `risk_budget_readiness_report.md` must enumerate every `GUARDRAILS` key/value in frozen order and retain all non-proof statements;
- `public_batch_report.md` must be built from the final derived summary/reconciliation/reproducibility models.

## Task 5 — commit a full no-network synthetic lifecycle fixture

Create a reusable deterministic fixture capable of producing public responses for the real code path.

Minimum fixture data:

- at least 201 valid unique linear instruments, including exactly one `BTCUSDT`;
- 1001 closed 1m trade candles;
- 1001 matching closed 1m mark candles;
- 100-day funding range with at least 301 8-hour observations;
- primary instrument limit 1000;
- alternate instrument limit 200 with at least two pages;
- trade and mark primary pages `[1000, 1]`;
- trade and mark alternate pages `[251, 251, 251, 248]`;
- at least two primary backward funding pages;
- at least two alternate funding chunks;
- funding timestamps inside the kline window join to matching mark candles;
- canonical UTF-8 raw response bodies;
- exact response recording and contiguous request sequence ids.

The fixture must use the real current runner and recording/replay boundary. It must not bypass persisted raw responses by injecting already-normalized rows into the final validator.

## Task 6 — commit the complete lifecycle for both hosts

Add tests that execute:

```text
run_bybit_public_batch_evidence._run
→ exact persisted directory validation
→ make_bybit_public_batch_review_pack.main
→ temporary ZIP semantic self-check
→ atomic ZIP publication
→ check_bybit_public_batch_review_pack.main
```

Run the lifecycle separately for:

```text
https://api.bybit.com
https://api.bytick.com
```

For each host assert:

- exact 18 final files;
- `status=complete`;
- selected host preserved in capture plan and every raw response;
- all recorded responses consumed;
- exact page sizes/counts;
- source count 1;
- derived count 15;
- non-status count 16;
- final summary/report contain derived reproducibility values;
- builder succeeds;
- standalone checker returns strict JSON success.

## Task 7 — lifecycle atomicity regressions

Add real tests for:

1. early failure cleanup;
2. mid failure cleanup;
3. late failure cleanup;
4. existing final directory rejected before client/network use;
5. stale building directory not reused;
6. validation failure never publishes final directory;
7. builder validation failure removes temporary ZIP;
8. successful builder atomically replaces an existing output file.

Every test must exercise materially different behavior.

## Task 8 — reproducibility mismatch regressions

Add deterministic tests proving fail-closed behavior when:

1. core candidate B has a missing key;
2. core candidate B has one changed byte;
3. final candidate B has a missing key;
4. final candidate B has one changed byte;
5. persisted audit says true but reconstructed result differs;
6. old misleading audit key is used;
7. summary reproducibility field is changed and manifest is rehashed;
8. report reproducibility line is changed and manifest is rehashed.

Provide a clean test seam for injecting a second-build mutation. Do not rely on nondeterministic globals or time.

## Task 9 — retain and complete the prior 72-behavior matrix

The previous Sprint 06.3B.3.1 behavior list remains mandatory.

Create a checked-in coverage map, for example:

```text
docs/sprint_06_3b_3_2_behavior_coverage.md
```

For every behavior id 1–72, record:

```text
behavior id
short requirement
test module
test function/node family
material mutation performed
expected rejection/success
```

Rules:

- one test may cover multiple behavior ids only when it actually performs and asserts each distinct mutation;
- member-name enumeration, constant enumeration, and simple collection-count checks do not satisfy lifecycle/tamper behaviors;
- parametrization is allowed only when each parameter creates a materially distinct request, artifact, or invariant;
- no no-op/count-inflation tests.

At minimum, the suite must include all lifecycle, directory/ZIP, reproducibility, provenance/records, page-audit, semantic tamper, report, status, and fully rehashed fake-pack cases listed in Sprint 06.3B.3.1.

## Task 10 — production artifact tests, not helper-only tests

Replace helper-only assertions with tests over the actual output of `artifact_bytes(...)` and the full persisted lifecycle.

Explicitly verify:

- every exact guardrail line appears in the produced `risk_budget_readiness_report.md`;
- every exact reproducibility line appears in the produced `public_batch_report.md`;
- a one-byte/report-line mutation is rejected after manifest rehash;
- a capture-summary reproducibility mutation is rejected after manifest rehash;
- directory and ZIP validators produce the same semantic decision.

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
python -m pytest tests/test_sprint_06_3b_3_2_reproducibility_and_lifecycle.py -q
python -m pytest -q
ruff check .
git diff --check
```

Do not run:

```text
scripts/probe_bybit_public_connectivity.py
scripts/run_bybit_public_batch_evidence.py  # against real network
```

The runner may be invoked only with the deterministic injected synthetic public transport in tests.

## Acceptance criteria before owner capture

All must be true:

```text
full committed lifecycle passes for both approved hosts
summary and public report are built only after reproducibility comparison
summary and report contain exact derived reproducibility values
no pre-asserted reproducibility success literals remain
all 15 derived artifacts are independently built and byte-compared
production report functions are the functions tested
72-behavior coverage map is complete and truthful
all required tamper/atomicity/status cases pass
standalone checker rejects fully rehashed semantic fabrications
full suite, Ruff, pip check, no-live and diff check pass
source archive is clean
no real network or private/live action was run by Codex
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
focused collection count
behavior-coverage map summary
all focused pytest outputs
full pytest output
Ruff output
git diff --check output
two-phase build design summary
exact derived-variable flow summary
summary/report schema summary
full synthetic lifecycle summary for both hosts
atomicity matrix summary
reproducibility mismatch matrix summary
semantic tamper matrix summary
source hygiene summary
confirmation that no real network or private/live action was run
```
