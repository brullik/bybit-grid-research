# Sprint 06.4A.3.2 — Production Store Graph and Semantic Pack Closure

## PM authorization

Sprint 06.3B remains accepted and frozen. Sprint 06.4A.3.1 is rejected.

Reviewed rejected identities:

```text
REJECTED_UPLOADED_ZIP_SHA256 = 685826e144912ab3dff38070ab283de2247912685828c47a0bc21b52c037665e
REJECTED_SOURCE_TREE_SHA256 = 8f7cf5fa73646eca8210c6ed90827b5d9d7d31fe6861fe7f096823b161bd8470
REJECTED_ARCHIVE_COMMIT_COMMENT = ef1523c9475b51bdc67714beca4720605f6b04da
REJECTED_PYTEST_COLLECTION = 503
```

Frozen upstream identities:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

Codex must not receive, open, import, or depend on the real owner pack. Use deterministic no-network synthetic evidence only.

## Gate status

```text
SPRINT 06.4A.3.1: REJECTED
OWNER OFFLINE SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK / PRIVATE / LIVE / TELEGRAM: CLOSED
ONLY AUTHORIZED WORK: THIS CORRECTIVE SPRINT
```

# 1. Non-negotiable production-first rule

Do not start by editing the behavior manifest, verifier, test names, or test counts.

The previous revision added 61 test names but only 10 unique bodies. Thirty unrelated behavior IDs invoked the same missing-argument audit CLI. That is acceptance padding.

Mandatory first implementation work must materially change all applicable production modules below:

```text
src/bybit_grid/data/market_store/audit.py
src/bybit_grid/data/market_store/import_public_batch.py
src/bybit_grid/data/market_store/reader.py
src/bybit_grid/data/market_store/writer.py
src/bybit_grid/data/market_store/coverage.py
src/bybit_grid/data/market_store/evidence.py
src/bybit_grid/data/market_store/canonical.py
src/bybit_grid/data/market_store/models.py
src/bybit_grid/data/market_store/resume.py
```

A submission that only or mainly changes governance/test files is an automatic fail.

Delete:

```text
tests/test_sprint_06_4a_3_material_behaviors.py
```

Do not retain it by renaming. Replace it with real tests grouped by production boundary.

# 2. Preserve confirmed fixes

Do not regress:

- exact acceptance of both decimal128(38,18) boundaries;
- rejection of scale > 18 and rounding requirements;
- bounded inclusive resume windows of at most 1000 rows;
- CLI `--help` exit 0;
- compact JSON missing-argument failure with nonzero exit;
- monthly partition planning;
- immutable source bytes held by the validated public-evidence loader;
- no-network/no-private/no-live guardrails.

# 3. Canonical models and serialization

## 3.1 Replace `dataclasses.asdict()` at the canonical boundary

Current failure:

```text
canonical_json_bytes(StoreRoundTripAudit(...MappingProxyType...))
→ TypeError: cannot pickle 'mappingproxy' object
```

Implement a recursive serializer using `dataclasses.fields()` and direct `getattr()`. It must:

- preserve `MappingProxyType` without deepcopy/pickle;
- accept only exact nonempty string mapping keys;
- validate keys before sorting;
- recursively freeze/validate nested mappings and sequences;
- reject mutable nested lists/dicts in immutable audit models unless converted at construction;
- reject float, bytes, Path, set, unknown types;
- serialize Decimal as exact canonical strings;
- serialize enums by exact scalar value;
- emit final newline and canonical sorted compact JSON.

## 3.2 Exact parsers

Implement strict canonical parsers for:

```text
store_version.json
chunk_manifest.json
evidence_reference.json
import_receipt.json
portable-pack audit JSON files
portable review_pack_manifest.json
```

Every parser must enforce:

- exact key set;
- exact bool/int/string/list identity; bool must never alias int;
- exact schema/version values;
- lowercase 64-character SHA-256;
- safe nonempty strings;
- canonical bytes equal to reserialization;
- nested receipt chunks converted to `tuple[StoreChunkManifest, ...]`;
- stable `MarketStoreError` codes.

# 4. Writer and chunk contract

`write_chunk_atomic()` must independently reject:

```text
mixed symbols
mixed UTC months
mixed instrument snapshot timestamps
empty input unless documented no-op
duplicate incoming keys
unknown fields or wrong exact types
unsafe partition values
```

Mixed BTCUSDT/ETHUSDT rows must fail before staging creation.

Strict chunk read-back must verify:

1. exact two regular members: `data.parquet`, `chunk_manifest.json`;
2. no symlink/junction/non-regular entry;
3. canonical manifest bytes and exact typed model;
4. dataset and primary-key columns equal the frozen dataset spec;
5. manifest `relative_path` equals the actual store-relative chunk path;
6. expected path rederived from typed rows and logical hash equals actual path;
7. Parquet SHA-256;
8. exact Arrow schema;
9. sorted unique row keys;
10. exact row count/min/max;
11. exact partition symbol/snapshot/month values;
12. logical rows SHA-256.

Existing chunk reuse must run the complete validation before returning.

Failure seams `early`, `mid`, and `late` must leave no staging tree or committed partial chunk.

# 5. Complete zero-write preflight

Before creating the target root, `store_version.json`, `.building`, datasets, evidence, references, or receipt:

1. validate detached immutable source bytes;
2. reconstruct and validate every row;
3. build the complete deterministic partition plan;
4. derive every expected manifest and path;
5. validate existing version if present;
6. load the complete committed store inventory;
7. build a global primary-key registry;
8. detect incoming duplicates, committed duplicates, and semantic conflicts;
9. validate evidence and receipt target ownership;
10. prove all deterministic failures before the first filesystem mutation.

Conflict policy:

```text
same key + identical complete row -> reusable
same key + semantic difference    -> store_row_conflict
incoming duplicate                -> duplicate_incoming_key
committed duplicate               -> duplicate_committed_key
```

Required test: scale-19 funding row must raise `decimal_rounding_required` while the previously absent store root remains absent.

Required test: if a target root already exists, a deterministic preflight failure leaves its complete path/byte/size/mtime inventory unchanged.

# 6. Receipt-last atomic commit

Implement one transaction-like import lifecycle:

```text
preflight
→ stage version if needed
→ stage all new chunks
→ semantic read-back all staged chunks
→ stage exact source archive
→ stage evidence reference
→ stage receipt
→ publish version/chunks/evidence/reference
→ publish receipt last
```

Use same-volume temporary paths and atomic replacements.

Normal caught failures at every phase must clean temporary entries and leave no partial committed import.

Receipt is the only commit marker. A store with chunks but no valid receipt must audit invalid.

# 7. Verified no-op re-import

The existing-receipt branch must not be an early JSON return.

Before returning a typed receipt it must validate:

- canonical store version;
- canonical receipt bytes and nested typed chunk manifests;
- every referenced chunk through strict semantic reader;
- exact receipt chunk set;
- source evidence archive bytes and SHA-256;
- canonical evidence reference;
- nested public review pack through its semantic checker;
- absence of orphan chunks/evidence/references/receipts for this import;
- global duplicate/conflicting keys;
- exact regenerated receipt bytes.

Snapshot the entire store inventory before and after verified no-op:

```text
relative paths
file types
bytes/SHA-256
sizes
mtimes
```

The inventory must be identical.

Corrupting any referenced Parquet, chunk manifest, evidence archive, evidence reference, receipt, or version must make re-import fail without mutation.

# 8. Full store-graph audit

`audit_market_store()` must validate the full graph, not only individual chunks.

For invalid readable stores, return typed:

```python
MarketStoreAudit(ok=False, failures=(...))
```

Reserve exceptions for unsafe/unreadable invocation failures.

Validate:

```text
canonical version
exact allowed root entries and regular-file safety
no stale .building content
every chunk through strict reader
actual chunk path equals manifest/row-derived path
global duplicate/conflicting primary keys
every canonical receipt
every evidence reference/archive
nested public review-pack semantics
exact one-to-one receipt/evidence/chunk ownership
orphan chunks/evidence/references/receipts
unexpected entries and symlinks
frozen false guardrails
```

The following must all return `ok=false` with stable failure codes:

```text
empty root
chunks without receipt/evidence
receipt without chunks/evidence
evidence without receipt
bad store_version.json
tampered receipt
tampered evidence archive
tampered evidence reference
copied/path-mismatched chunk
global exact duplicate key
global same-key different-row conflict
stale staging
unexpected root entry
```

# 9. Replay contract

`read_replay_slice()` must validate:

- exact safe symbol;
- exact nonnegative aligned integer timestamps;
- `start_ms <= end_ms`;
- exact requested instrument snapshot timestamp.

It must load exactly one instrument row matching both:

```text
snapshot_server_time_ms
symbol
```

Missing or duplicate match fails.

Return an immutable replay object containing:

```text
instrument
trade_klines
mark_klines
funding_observations
```

Trade and mark must be complete ascending 1m grids and have identical timestamp sets.

Each funding observation must be exactly:

```text
funding_time_ms
funding_rate
mark_open
```

The mark row must have the exact same timestamp. Missing or duplicate mark join fails.

Do not return raw unjoined funding rows.

# 10. Coverage and resume

Create shared exact validators used by both coverage and resume.

Reject:

```text
unsafe symbol
bool/string/float timestamp aliases
negative timestamps
unaligned timestamps
reversed ranges
timestamps outside requested window
duplicate timestamps
wrong audit model types
symbol/window mismatch
max_rows outside 1..1000
```

Current remaining failure to fix:

```text
observed timestamp=1 is accepted by plan_bounded_resume_windows()
```

Coverage must not silently filter supplied out-of-window timestamps.

Funding observed-range scanner must validate every timestamp as exact nonnegative minute-aligned int and only claim observed range, never historical completeness.

Test gap windows at:

```text
first minute
middle minute
last minute
multiple disjoint gaps
1000/1001/2000/2001 rows
UTC month rollover
UTC year rollover
leap day
```

# 11. DuckDB

Before creating views, require a valid audited store or an exact validated inventory.

Preserve:

- in-memory connection only;
- no persistent DB file;
- no extensions/network;
- exact four view names;
- exact Decimal column types;
- escaped store-owned Parquet paths;
- close on success and every failure.

Tests must query:

```text
row counts
min/max timestamps
duplicate key counts
DECIMAL types
both approved host provenance values
```

# 12. Semantic portable seed review pack

## 12.1 Builder

Builder must require `audit_market_store(store_root).ok is True` before creating a temporary ZIP.

Do not recursively include arbitrary files. Derive the exact member set from validated receipt ownership.

Required derived artifacts:

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

Validate the temporary ZIP semantically, then atomically replace destination. Clean temporary ZIP on every failure.

## 12.2 Standalone checker

Checker must:

1. reject duplicate/unsafe/directory/non-regular members;
2. strict-parse canonical manifest;
3. require exact nonempty member set;
4. verify hashes;
5. reconstruct an isolated temporary store only from ZIP members;
6. run the full store-graph audit;
7. validate nested public evidence;
8. regenerate every derived artifact and compare bytes;
9. verify frozen false risk/live guardrails;
10. clean temporary extraction on success and failure.

It must reject, even after all manifest hashes are recalculated:

```text
empty manifest
arbitrary fabricated file
missing receipt
missing evidence
modified Parquet
modified chunk manifest
modified store audit
modified round-trip audit
modified replay coverage audit
modified funding audit
modified DuckDB audit
modified reproducibility audit
modified risk report
extra member
```

# 13. CLI lifecycle

Keep all five CLI wrappers strict and compact.

Add real subprocess tests for the complete no-network lifecycle:

```text
synthetic public pack
→ import CLI
→ audit CLI
→ repair-plan CLI
→ portable-pack builder CLI
→ standalone checker CLI
```

Run once with source provenance:

```text
https://api.bybit.com
```

and once with:

```text
https://api.bytick.com
```

The host is persisted provenance only; tests perform no network calls.

`CLI-FULL-LIFECYCLE-*` cannot be satisfied by `--help`.

# 14. Anti-padding test architecture

Create these real test modules:

```text
tests/test_sprint_06_4a_3_2_writer_preflight_atomicity.py
tests/test_sprint_06_4a_3_2_import_noop_store_graph.py
tests/test_sprint_06_4a_3_2_replay_coverage_resume.py
tests/test_sprint_06_4a_3_2_semantic_seed_pack.py
tests/test_sprint_06_4a_3_2_cli_lifecycle.py
```

Every test node referenced by the 61 frozen behavior IDs must:

- call the relevant production function or subprocess CLI;
- create the behavior-specific fixture;
- apply the behavior-specific mutation;
- assert the exact expected success/failure;
- not rely on manifest wording;
- not use only `--help` or missing arguments unless the ID is specifically a CLI boundary ID;
- not share an AST-identical body with an unrelated behavior ID.

Helpers are encouraged, but test parameters must carry distinct mutations and exact expected codes.

The governance manifest remains traceability documentation. It is not proof by itself.

The verifier must additionally reject:

- governance-only nodes;
- duplicate node IDs;
- AST-identical test bodies mapped to different behavior categories;
- mapped tests that import/call none of the approved production modules or subprocess scripts;
- CLI full-lifecycle mappings whose command contains only `--help` or omits required arguments;
- manifest material/expected strings that merely repeat the behavior ID.

Do not reduce, rename, reorder, or replace the exact 61 behavior IDs.

# 15. Mandatory direct regressions

The following current rejected outcomes must be converted to failing regression tests before fixes, then pass after implementation:

```text
audit bad version                    currently ok=true
audit chunks without receipt         currently ok=true
audit tampered evidence              currently ok=true
audit tampered receipt               currently ok=true
audit copied path                    currently ok=true
audit global conflict                currently ok=true
reimport corrupt Parquet              currently accepted
portable empty manifest              currently accepted
portable rehashed fake               currently accepted
builder empty store                  currently accepted
replay snapshot=123                  currently accepted
mixed-symbol writer                  currently accepted
preflight invalid row                currently leaves .building + version
coverage unsafe reversed             currently complete=true
coverage out-of-window               currently complete=true
coverage unaligned timestamp         currently accepted
funding bool/string/negative/unaligned currently accepted
canonical MappingProxy dataclass     currently TypeError
resume unaligned observed timestamp  currently accepted
```

Use the PM reproduction JSON as a description only; do not copy its expected bad outcomes into success tests.

# 16. Definition of done

The sprint is complete only when all are true:

```text
[ ] required production modules materially changed
[ ] old padded material-behaviors file deleted
[ ] exact 61 behavior IDs mapped to real material nodes
[ ] coverage verifier passes
[ ] direct rejected-outcome regression tests pass with fail-closed results
[ ] synthetic canonical-shape import succeeds
[ ] verified no-op succeeds with byte-for-byte zero mutation
[ ] every no-op tamper fails
[ ] full store-graph audit rejects all orphan/tamper cases
[ ] replay returns instrument and joined funding observations
[ ] coverage/resume strictness complete
[ ] DuckDB four-view smoke succeeds
[ ] semantic portable pack rejects rehashed fabrications
[ ] both host-provenance subprocess lifecycles pass offline
[ ] numeric environment passes
[ ] pip check passes
[ ] no-live audit passes
[ ] Ruff passes
[ ] git diff --check passes
[ ] full pytest passes
[ ] clean source ZIP contains no caches/evidence/data/secrets
```

# 17. Required Codex report

Report exactly:

```text
1. production files changed and what invariant each implements;
2. old padded test file deletion;
3. exact behavior-map verifier output;
4. focused pytest node count and result;
5. full pytest count and result;
6. five CLI help and missing-argument outputs;
7. two full offline subprocess lifecycle outputs;
8. direct tamper matrix result;
9. numeric environment;
10. pip check;
11. no-live audit;
12. Ruff;
13. git diff --check;
14. source-tree SHA-256;
15. final uploaded source ZIP SHA-256 computed after packaging.
```

Do not perform a real owner import. Do not access the network. Do not add private/live execution capability.
