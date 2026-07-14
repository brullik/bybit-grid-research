# Sprint 06.4A.3 — Fail-Closed Store Graph, Replay and Semantic Pack Closure

## PM authorization

Sprint 06.3B remains accepted and frozen. Sprint 06.4A.2 is rejected.

Reviewed rejected identities:

```text
REJECTED_SOURCE_ZIP_SHA256 = fe15792234c82f6a469f48cf58707fd5b0e0e0b5a7e4f9e516c64b4d340efcf6
REJECTED_SOURCE_TREE_SHA256 = ab00b1689fa690c1770b9f276eea9ae7390e85f66da2e2ebd21f2c223e40f3c5
```

Frozen upstream identities:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

Codex must not receive, open, import or depend on the real owner pack. Use deterministic no-network synthetic evidence only.

## Gate status

```text
SPRINT 06.4A.2: REJECTED
OWNER OFFLINE SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK / PRIVATE / LIVE / TELEGRAM: CLOSED
ONLY AUTHORIZED WORK: THIS SPRINT
```

## Objective

Deliver one executable offline lifecycle whose correctness is based on semantic reconstruction, not filenames, receipt presence or hashes alone:

```text
synthetic canonical public pack bytes
-> immutable one-read loader
-> zero-write complete preflight
-> deterministic partition/conflict plan
-> strict immutable chunks
-> exact evidence archive/reference
-> receipt-last commit
-> verified no-op re-import
-> full store-graph audit
-> strict replay/coverage/resume
-> in-memory DuckDB smoke
-> semantic portable seed pack
-> independent standalone checker
```

Preserve all accepted `src/bybit_grid/data/public_batch/*` behavior and all no-private/no-live guardrails.

# Part A — truthful governance, no numeric padding

The previous 72/82 row-count mechanism is retired because it encouraged padding and was silently weakened to 8/8.

Create a machine-readable frozen required behavior set, for example:

```text
docs/sprint_06_4a_3_required_behaviors.json
```

The verifier must require the **exact behavior IDs** listed below, exactly once each, and each ID must map to an actually collected material production/CLI test node. It must reject unknown, missing and duplicate IDs, missing nodes, skipped/unconditional dummy tests and forbidden no-op patterns.

Required IDs:

```text
GOV-EXACT-ID-SET
GOV-MISSING-NODE
GOV-NOOP-REJECTED
CLI-HELP-ALL
CLI-MISSING-ARGS-ALL
DECIMAL-MAX-BOUNDARY
DECIMAL-MIN-BOUNDARY
DECIMAL-ROUNDING-REJECTED
PLAN-INSTRUMENT-SNAPSHOT
PLAN-KLINE-CROSS-MONTH
PLAN-FUNDING-FOUR-MONTHS
PLAN-MULTI-SYMBOL-REJECTED
PREFLIGHT-INVALID-ROW-ZERO-WRITES
PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES
PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES
CHUNK-EARLY-CLEANUP
CHUNK-MID-CLEANUP
CHUNK-LATE-CLEANUP
CHUNK-CANONICAL-MANIFEST
CHUNK-ACTUAL-PATH-MATCH
CHUNK-PK-SCHEMA-MATCH
CHUNK-EXISTING-CORRUPTION-REJECTED
IMPORT-SYNTHETIC-REAL-SHAPE
IMPORT-SOURCE-BYTES-IMMUTABLE
IMPORT-RECEIPT-LAST
IMPORT-NOOP-TYPED
IMPORT-NOOP-ZERO-MUTATION
IMPORT-NOOP-CORRUPT-CHUNK-REJECTED
IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED
AUDIT-EMPTY-REJECTED
AUDIT-VERSION-TAMPER-REJECTED
AUDIT-ORPHAN-CHUNK-REJECTED
AUDIT-ORPHAN-EVIDENCE-REJECTED
AUDIT-RECEIPT-TAMPER-REJECTED
AUDIT-GLOBAL-DUPLICATE-REJECTED
AUDIT-GLOBAL-CONFLICT-REJECTED
AUDIT-UNEXPECTED-ENTRY-REJECTED
AUDIT-STALE-STAGING-REJECTED
REPLAY-SNAPSHOT-REQUIRED
REPLAY-SNAPSHOT-ROW-RETURNED
REPLAY-COMPLETE-TRADE-MARK
REPLAY-FUNDING-MARK-JOIN
REPLAY-MISSING-MARK-JOIN-REJECTED
COVERAGE-STRICT-INPUTS
COVERAGE-OUT-OF-WINDOW-REJECTED
COVERAGE-GAP-WINDOWS
RESUME-INCLUSIVE-1000
RESUME-MONTH-YEAR-LEAP
FUNDING-STRICT-TIMESTAMPS
DUCKDB-FOUR-VIEWS
DUCKDB-DECIMAL-TYPES
DUCKDB-CONNECTION-CLOSED
PACK-BUILDER-BAD-STORE-REJECTED
PACK-EXACT-MEMBER-SET
PACK-EMPTY-MANIFEST-REJECTED
PACK-REHASHED-FAKE-REJECTED
PACK-NESTED-EVIDENCE-VALIDATED
PACK-REPORT-TAMPER-REJECTED
PACK-TEMP-CLEANUP
CLI-FULL-LIFECYCLE-BYBIT-HOST
CLI-FULL-LIFECYCLE-BYTICK-HOST
```

A test may be parameterized only when each parameter performs a distinct mutation and has a stable exact expected result. Do not restore one-test-per-ID constant assertions.

# Part B — one strict persisted model/parser layer

Implement strict immutable models and exact canonical parsers for:

```text
store_version.json
evidence_reference.json
chunk_manifest.json
import_receipt.json
all portable-pack audits
portable review_pack_manifest.json
```

Requirements:

- exact key sets and canonical bytes;
- exact bool/int/string/tuple/model types; bool never aliases int;
- lowercase 64-character SHA-256;
- exact schema/version values;
- immutable mappings with exact nonempty string keys;
- nested receipt chunks parsed to `tuple[StoreChunkManifest, ...]`;
- no `str(k)` conversion in canonical/strict CLI serialization;
- stable specific `MarketStoreError` values.

Every audit/result model must validate its complete invariant set. No mutable dict field may remain in a frozen persisted model.

# Part C — exact Decimal semantics

Keep all Decimal work inside a sufficiently precise `localcontext()`, including scaling/counting significant digits.

Must accept exactly:

```text
 99999999999999999999.999999999999999999
-99999999999999999999.999999999999999999
```

Reject non-Decimal, non-finite, scale > 18, precision overflow and any required rounding. Never convert through float.

# Part D — dataset specification and strict chunks

Use one dataset specification per dataset to drive:

```text
exact fields
Arrow schema
primary key
partition key
typed validation
logical JSONL
Parquet construction
read-back comparison
```

`write_chunk_atomic()` must independently reject:

- empty unless explicitly documented as no-op;
- mixed symbols;
- mixed UTC months;
- mixed snapshot timestamps;
- duplicate keys;
- unknown fields/types;
- unsafe paths.

Strict read-back must verify:

- exact regular two-member chunk directory;
- canonical exact manifest bytes/model;
- manifest dataset and PK columns;
- manifest `relative_path` equals actual store-relative directory;
- expected path rederived from typed rows and logical hash;
- Parquet SHA;
- exact Arrow schema;
- exact row order and logical bytes/hash;
- row count/min/max/partition values.

Existing chunk reuse must run this full validation before returning.

# Part E — complete zero-write preflight and conflict graph

Before creating `store_version.json`, `.building`, chunks, evidence or receipt:

1. Validate immutable source bytes and reconstruct detached rows.
2. Validate all rows and build the complete partition plan.
3. Derive every target manifest and path.
4. Strictly validate any existing store version.
5. Read relevant committed partitions and build a global primary-key registry.
6. Apply conflict policy:

```text
same key + identical complete row -> reusable
same key + semantic difference    -> store_row_conflict
incoming duplicate                -> duplicate_incoming_key
committed duplicate               -> duplicate_committed_key
```

7. Validate exact evidence and receipt targets.
8. Prove every deterministic error before any committed write.

An injected deterministic preflight failure must leave the store path absent or byte-for-byte unchanged, including no empty `.building` and no version file.

# Part F — receipt-last publication and verified no-op

Use validated temporary files and same-volume atomic replacement for version, evidence archive, evidence reference and receipt. Receipt is always last.

Define explicit import failure seams before/after each publication phase. On normal caught failure, clean newly created staging. If a simulated crash leaves published chunks/evidence without receipt, audit must mark them orphaned.

Existing receipt path:

- strict parse canonical receipt;
- validate version;
- validate every referenced chunk;
- validate exact archive hash/bytes and evidence reference;
- rerun nested public review-pack semantic checker;
- detect missing/extra/orphan objects affecting the import;
- regenerate exact receipt bytes;
- snapshot complete committed member set, hashes and mtimes before/after;
- return typed receipt only if absolutely unchanged.

Corrupting any referenced Parquet/manifest/evidence file must make the second import fail.

# Part G — full store-graph audit

Audit policy: return a typed `MarketStoreAudit(ok=False, failures=...)` for invalid stores; reserve exceptions for unsafe/unreadable invocation failures. Document and use consistently.

Audit must validate:

- canonical version;
- exact allowed root graph and regular-entry safety;
- every chunk through strict reader;
- global duplicate/conflicting keys;
- every canonical receipt and referenced chunk set;
- every evidence reference/archive and nested public-pack semantics;
- one-to-one receipt/evidence/chunk ownership for the seed import;
- orphan chunks, evidence, references and receipts;
- stale `.building`;
- exact accepted seed replay-pair coverage;
- observed funding range only;
- frozen false guardrails.

Empty, partial, chunk-only, receipt-only and evidence-only roots must all be `ok=false` in the production audit. Low-level chunk tests may call a separate chunk validator, not weaken the store audit.

# Part H — replay, coverage and resume

## Replay

Validate exact safe symbol, exact nonnegative aligned ints and `start <= end`.

Load and return exactly one instrument row matching both requested `snapshot_server_time_ms` and symbol. Missing/duplicate snapshot rows fail.

Require complete ascending trade/mark minute grids and exact timestamp equality.

Build immutable funding observations by joining every included funding timestamp to the exact mark candle at the same timestamp. Each observation includes:

```text
funding_time_ms
funding_rate
mark_open
```

Missing mark join fails.

## Coverage/resume

`resume.py` must be implemented.

Reject unsafe symbol, bool/string/float aliases, negative/unaligned timestamps, reversed ranges and supplied timestamps outside the requested window.

Implement exact bounded inclusive windows with maximum 1000 rows. Test first, middle, last and disjoint gaps, UTC month/year transition and leap day.

Trade/mark repair planning must require exact audit model types and matching symbol/window. Funding scanner validates exact timestamps and reports observed range only.

# Part I — DuckDB

Preserve the working in-memory views and DECIMAL types. Add strict prevalidation through the full store audit or exact dataset validators.

Required:

- exact four view names;
- no persistent database/extension/network;
- row counts, min/max and duplicate queries;
- alternate approved host provenance queryable;
- connection closed on every failure and in smoke helper.

# Part J — semantic portable seed pack

Builder must first require full `audit.ok=true` and derive the exact member set from validated receipts/evidence/chunks; never recursively include arbitrary store files.

Generate canonical derived artifacts:

```text
store_audit.json
round_trip_audit.json
minute_replay_coverage_audit.json
funding_observed_range_audit.json
duckdb_smoke_audit.json
reproducibility_audit.json
risk_guardrail_report.md
review_pack_manifest.json
```

Rebuild all derived artifacts twice and compare exact bytes before publication.

Standalone checker must:

1. reject duplicate/unsafe/directory/symlink/non-regular ZIP members;
2. strict-parse canonical manifest and require exact member set;
3. extract with containment checks to a fresh temporary root;
4. validate nested public review-pack semantics;
5. run the complete store audit;
6. rerun round-trip, replay coverage, funding and DuckDB audits;
7. regenerate every derived artifact and compare exact bytes;
8. reject empty manifest and fully rehashed semantic fakes;
9. clean extraction/temp ZIP on success and failure.

Builder flow:

```text
full store validation
-> temporary ZIP
-> standalone semantic self-check
-> atomic replace destination
-> cleanup every failure path
```

# Part K — required synthetic lifecycle tests

Create a deterministic no-network public review-pack fixture matching the accepted shape:

```text
instruments > 500
trade = 1001 rows crossing a UTC month boundary
mark = 1001 matching rows
funding = 300 rows spanning at least four UTC months
host provenance parameterized for api.bybit.com and api.bytick.com
```

Commit a full subprocess CLI lifecycle for both hosts:

```text
synthetic public review pack
-> import CLI
-> audit CLI
-> second verified-no-op import CLI
-> repair-plan CLI
-> replay/funding join
-> DuckDB smoke
-> seed-pack builder CLI
-> standalone checker CLI
```

Also commit exact regressions for every PM reproduction:

- valid Decimal max/min;
- deterministic preflight leaves zero writes;
- corrupt chunk accepted by no-op (must now reject);
- bad version accepted by audit (must now reject);
- orphan chunks accepted by audit (must now reject);
- tampered evidence accepted by audit (must now reject);
- copied/path-mismatched chunk accepted (must now reject);
- same-key different-row chunks accepted (must now reject);
- mixed-symbol writer accepted (must now reject);
- nonexistent snapshot accepted (must now reject);
- reversed/out-of-window/unsafe coverage accepted (must now reject);
- string/bool funding timestamps accepted (must now reject);
- empty and arbitrary rehashed packs accepted (must now reject);
- empty-store builder accepted (must now reject).

Tests must assert stable exact errors and real production outputs. Do not use `raises(Exception)` or constant-only assertions.

# Part L — documentation

Update `docs/bybit_public_parquet_store_contract_v1.md` only after executable behavior matches it. Include exact schemas, paths, preflight state machine, crash/orphan policy, verified no-op, audit graph, replay funding join, resume semantics, DuckDB and semantic pack contract.

Retain verbatim:

```text
Parquet file bytes are not claimed to be canonical across PyArrow/platform versions.
Canonical identity is the logical row hash plus strict schema, manifest and semantic read-back.
```

# Required commands

Run and report exact outputs:

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python scripts/check_behavior_coverage_maps.py --collect-command "python -m pytest --collect-only -q"

python scripts/import_bybit_public_review_pack_to_store.py --help
python scripts/audit_bybit_public_parquet_store.py --help
python scripts/plan_bybit_public_store_repairs.py --help
python scripts/make_bybit_public_parquet_seed_review_pack.py --help
python scripts/check_bybit_public_parquet_seed_review_pack.py --help

# Also run each CLI with missing arguments and report exit/stdout/stderr.

python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_2_true_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_3_owner_lifecycle_executability.py -q
python -m pytest tests/test_sprint_06_3b_3_1_evidence_truthfulness.py -q
python -m pytest tests/test_sprint_06_3b_3_2_reproducibility_and_lifecycle.py -q
python -m pytest tests/test_sprint_06_4a_*.py -q
python -m pytest -q
ruff check .
git diff --check
python scripts/hash_source_tree.py --root .
```

Do not run the real owner pack, any owner PowerShell script or any network probe.

# Definition of done

The code gate opens only when all PM attacks fail closed, the full synthetic subprocess lifecycle passes for both approved host provenances, the store audit validates the complete receipt/evidence/chunk graph, the second import is verified and mutation-free, replay requires a real snapshot and produces mark-joined funding observations, `resume.py` is implemented, and the portable checker reconstructs semantics rather than trusting hashes.

## Owner action after PM review

No owner/local action is authorized in this sprint. PM will independently review and attack the clean source ZIP. Only a later explicit acceptance may authorize a local offline seed-import PowerShell script.
