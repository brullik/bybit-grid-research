# Sprint 06.4A.1 — Executable Canonical Store and Semantic Evidence Closure

## PM authorization

Sprint 06.3B remains accepted and closed. Sprint 06.4A was rejected at code review because the submitted implementation passed a shallow test suite but did not implement the frozen atomic store, semantic audit, portable evidence, CLI, and behavior-matrix contracts.

Reviewed rejected source identities:

```text
REJECTED_SOURCE_ZIP_SHA256 = f3e8970b784faca17445e9f676e2c74252c5a56f3aff6228da48ac7a5c12700f
REJECTED_SOURCE_TREE_SHA256 = 7d2dc62647947684abce723d564eba7b4660249c4f2a96a97b5fe10a3d1efecd
```

Accepted upstream identities remain frozen:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
OWNER_BUNDLE_SHA256 = 0858bcad00e9ba2a57b6da1cba472cac0cd938c334b795eea0ebc4cf42a9875f
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
PUBLIC_STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

Codex must not receive, open, import, or embed the real owner bundle or real public review pack. All tests must use deterministic synthetic evidence and `tmp_path` only.

## Gate status

```text
SPRINT 06.4A: BLOCKED
SPRINT 06.4B OWNER IMPORT: NOT AUTHORIZED
NETWORK / PRIVATE / LIVE / TELEGRAM: CLOSED
ONLY AUTHORIZED WORK: THIS CLOSURE SPRINT
```

## Objective

Replace the current scaffold with an executable, fail-closed, independently auditable local Parquet-store lifecycle:

```text
synthetic validated public review pack
-> detached typed evidence
-> strict preflight
-> month-partitioned immutable chunks
-> semantic Parquet read-back
-> exact source archive
-> atomic receipt-last commit
-> verified no-op re-import
-> full store audit
-> replay/coverage/funding audits
-> working in-memory DuckDB views
-> portable semantic review pack
-> standalone checker
```

Preserve all accepted `src/bybit_grid/data/public_batch/*` behavior and bytes.

## Frozen safety rules

- No real network calls.
- No private Bybit endpoints or credentials.
- No API key, secret, account, wallet, order, position, grid creation, Telegram, or live execution.
- No bulk history download.
- No parameter search, PnL, EV, ROI, profitability, or live-readiness claim.
- No generated Parquet, ZIP, DuckDB database, SQLite database, JSON evidence, owner artifacts, or caches committed to source.
- Parquet remains canonical durable storage; DuckDB remains an in-memory read/query helper.
- All historical/funding/metadata/risk/native/parameter/live completeness guardrails remain false.

## Mandatory correction 0 — truthful governance maps

### 0.1 Repair Sprint 06.3B map

`docs/sprint_06_3b_3_2_behavior_coverage.md` currently references nonexistent nodes named:

```text
test_accepted_lifecycle_behavior[...]
```

Replace every row with an actually collected exact pytest node ID. Each row must state:

```text
behavior ID;
exact pytest node ID including parameter ID;
exact fixture/setup;
material mutation/failure;
exact expected success value or error string.
```

Do not invent tests or use generic text.

### 0.2 Replace Sprint 06.4A placeholder map

`docs/sprint_06_4a_behavior_coverage.md` currently references nonexistent `tests/test_sprint_06_4a_contract_matrix.py` nodes. Replace it with exact mappings for all 82 frozen behaviors from Sprint 06.4A.

### 0.3 Add a coverage-map verifier

Add an import-safe verifier and CLI, for example:

```text
src/bybit_grid/common/pytest_coverage_map.py
scripts/check_behavior_coverage_maps.py
```

It must:

- parse the checked-in map format deterministically;
- reject duplicate behavior IDs and duplicate node mappings where distinct tests are required;
- reject placeholder phrases;
- compare every node ID against a supplied/collected `pytest --collect-only -q` node list;
- require exact expected behavior counts: 72 for Sprint 06.3B and 82 for Sprint 06.4A;
- emit compact canonical JSON and nonzero exit on failure;
- make no network call and perform no work at import.

A test must prove that a nonexistent node causes failure.

## Mandatory correction 1 — exact immutable models

Refactor `market_store/models.py` so all production models validate themselves in `__post_init__` or are constructed by strict validated factories.

Requirements:

- exact enums only;
- `type(v) is int` for integer fields, never bool aliases;
- `type(v) is bool` for booleans;
- exact nonempty strings;
- exact lowercase 64-character SHA-256 where required;
- safe symbol/path/run-id/source-name rules;
- tuple fields must be exact tuples containing exact model types;
- mappings inside frozen models must be immutable, have exact string keys, and have validated values;
- reject unknown fields when parsing persisted JSON;
- validate row counts, key ordering, min/max consistency, schema version, dataset kind, and guardrail relationships.

Add strict typed storage-row models or exact field-set validators for all four datasets. Unknown and missing row fields must fail before hashing or writing.

## Mandatory correction 2 — exact Decimal and canonical row semantics

### 2.1 Decimal representability

Implement an exact `decimal128(38,18)` validator with a controlled local Decimal context. It must:

- accept the full valid positive and negative range, including `99999999999999999999.999999999999999999`;
- reject non-Decimal, non-finite, rounding-required, scale > 18 with nonzero discarded digits, and precision/integer overflow;
- never convert through float;
- preserve negative funding rates;
- canonicalize semantic negative zero to `0` only in logical text, not by lossy conversion.

### 2.2 Dataset-specific projection

Create one frozen projection definition per dataset. The exact same projection must drive:

```text
field-set validation;
primary-key extraction;
canonical logical JSONL;
Arrow table construction;
Parquet read-back comparison.
```

Do not hash unknown fields and then silently discard them. Unknown fields must fail `store_row_field_set_invalid` before any staging directory is created.

Canonical JSONL must use exact sorted primary-key order, compact UTF-8, final newline, nonempty string keys, Decimal semantic strings, and no floats/bytes/Path/set/unknown types.

## Mandatory correction 3 — strict paths and month partitioning

All path functions must reject aliases rather than call `int(...)` on arbitrary values.

Validate exactly:

- dataset enum;
- symbol;
- run ID;
- source SHA-256;
- logical SHA-256;
- timestamps as exact nonnegative ints;
- minute alignment where applicable;
- `min_ms <= max_ms`;
- same UTC year/month for one time-series chunk;
- snapshot chunks contain exactly one snapshot timestamp;
- native path remains contained under the selected store root.

Before writing, group incoming rows into deterministic chunks by:

```text
instrument_snapshot: snapshot_server_time_ms
trade_kline_1m: symbol / UTC year / UTC month
mark_kline_1m: symbol / UTC year / UTC month
funding_rate: symbol / UTC year / UTC month
```

No time-series chunk may cross a UTC month boundary.

## Mandatory correction 4 — fail-closed chunk writer

Refactor the writer into explicit phases and add deterministic failure-injection seams used only by tests:

```text
validate/project/sort rows
preflight target and committed overlap
create one recorded staging root
write Parquet
write canonical manifest
semantic read-back
publish with same-volume atomic rename
cleanup exact staging root in finally
```

Before publication, read back and prove:

- exact Arrow schema;
- exact row count;
- exact typed projected rows;
- exact primary-key sequence and strict ordering;
- min/max key;
- logical row SHA-256;
- Parquet SHA-256;
- exact manifest schema and canonical bytes;
- final relative path implied by rows and logical hash.

An existing final chunk may be reused only after the same complete validation. A corrupted Parquet file or modified manifest must never be accepted because the logical hash field happens to match.

On any early/mid/late exception, remove the exact staging root. Do not generate a new UUID during cleanup. Stale staging must never be treated as committed.

## Mandatory correction 5 — overlap and conflict preflight

Before publishing any new chunk, scan only relevant committed partitions and build exact primary-key/semantic-row indexes.

Policy:

- identical existing key and identical semantic row: reuse;
- new disjoint key: write;
- same key with any semantic difference: fail `store_row_conflict` before publication;
- duplicate incoming key: fail;
- duplicate/conflicting key across committed chunks: store audit fails;
- overlapping time ranges are allowed only when actual primary-key sets are disjoint.

Do not rely on a later reader failure to detect a conflict.

## Mandatory correction 6 — atomic import and verified idempotency

Refactor `ValidatedPublicBatchEvidence` and `import_validated_public_batch_to_store()`.

### 6.1 Loader

The loader must:

- read exact source bytes once;
- calculate SHA-256 from those bytes;
- run the accepted semantic public-pack validator;
- require complete status and frozen guardrails;
- reconstruct from persisted raw responses;
- return detached immutable typed evidence plus immutable source bytes/provenance;
- avoid a path time-of-check/time-of-use gap.

### 6.2 Preflight

Before writing any committed member:

- validate exact `store_version.json` state;
- validate all incoming rows and month partitions;
- validate all existing canonical roots and relevant overlaps;
- calculate all target chunk manifests and receipt content;
- validate source archive bytes and expected hash;
- reject unsafe/non-regular/symlink entries.

### 6.3 Commit

- write/validate chunks through the strict writer;
- archive exact source bytes atomically and read them back;
- write canonical `evidence_reference.json` atomically;
- write canonical `import_receipt.json` last using temporary file plus atomic replace;
- never overwrite a committed object with different bytes/semantics;
- no receipt on any failure.

Published chunks left without a receipt after a simulated process failure must be explicit orphans in the audit and must be safely reusable only after complete validation.

### 6.4 Verified no-op re-import

When the exact receipt path already exists, do not simply deserialize and return it. Verify:

- canonical receipt schema/bytes;
- typed nested `StoreChunkManifest` values;
- exact store version;
- every referenced chunk and source evidence;
- full source hash and semantic validation;
- no extra/missing referenced chunks;
- no conflicts/orphans affecting the import;
- regenerated receipt bytes equal persisted bytes.

Only then return a typed `StoreImportReceipt` and prove no new chunks/files/mtime changes were required.

## Mandatory correction 7 — strict typed reader and replay slice

`_read_chunk()` must validate the entire chunk contract, not only two hashes:

- chunk directory has exactly `data.parquet` and `chunk_manifest.json`;
- manifest strict parser, exact keys, canonical bytes, schema version and dataset;
- manifest relative path equals actual path;
- Parquet SHA-256;
- exact Arrow schema;
- projected typed rows;
- strict primary-key ordering, row count, min/max keys and logical hash;
- partition values agree with row values.

Readers must prune by dataset/symbol/year/month and request only needed columns where practical.

`read_replay_slice()` must:

- validate exact symbol/start/end/snapshot arguments;
- load an exact explicit instrument snapshot row for the symbol and return it;
- require complete ascending trade and mark minute grids and exact timestamp equality;
- reject duplicates/conflicts;
- derive funding observations by joining each included funding timestamp to the exact mark candle and using mark `open`;
- reject a funding observation without a matching mark candle;
- return deterministic immutable typed tuples/models with provenance.

## Mandatory correction 8 — complete store audit

Replace the shallow audit with a canonical full scan.

It must validate:

- exact `store_version.json` schema and canonical bytes;
- canonical root set and safe regular paths;
- no unexpected files/directories, symlinks, junctions, or non-regular entries;
- every chunk through strict `_read_chunk()`;
- duplicate/conflicting primary keys across all chunks;
- exact evidence archive/reference and semantic nested public-pack validation;
- exact typed receipts and all references;
- no receipt referencing staging or missing objects;
- orphan chunks, orphan evidence, orphan references, orphan receipts, and stale staging reported explicitly;
- replay-pair coverage for committed seed imports;
- funding observed range only;
- all frozen guardrails.

A missing store version, empty arbitrary directory, tampered manifest metadata, duplicate key across chunks, or unexpected entry must make `ok=False` or raise the named fail-closed error according to one documented policy.

## Mandatory correction 9 — coverage, resume, and repair APIs

Implement `resume.py`; it must not remain empty.

All coverage/planning APIs must validate:

- exact safe symbol;
- exact aligned integer timestamps, no bool/string/float aliases;
- `start <= end`;
- every supplied minute timestamp is aligned and lies within the requested window;
- sorted uniqueness or an exact duplicate error;
- trade and mark audits refer to the same symbol/window;
- exact audit model types;
- `max_rows` exact positive int;
- no gap-window overlap or omission.

Cover first/last/middle gaps, coalescing, disjoint gaps, 1000-row inclusive splitting, month boundary, year boundary, leap day, trade-only gap, mark-only gap, and reversed/unaligned/out-of-range/bool inputs.

Funding scanning reports exact observed min/max/count/duplicates only and never proves global completeness.

## Mandatory correction 10 — working DuckDB views and smoke audit

Fix the current runtime failure:

```text
BinderException: Unexpected prepared parameter. This type of statement can't be prepared!
```

Create views using safely constructed/escaped store-owned glob paths or another DuckDB-supported mechanism. Do not interpolate arbitrary user-controlled SQL identifiers or paths.

Requirements:

- in-memory connection only;
- close connection on all failures and in audit helpers;
- fail closed before creating partial views if any required dataset is empty/invalid;
- Hive partition discovery and `union_by_name=true`;
- exact four view names;
- row count, min/max timestamp, duplicate-key and schema/type smoke queries;
- assert market values are DuckDB DECIMAL, never DOUBLE;
- no persistent database file;
- no network extension;
- alternate-host provenance remains queryable.

## Mandatory correction 11 — semantic portable seed-store evidence

Replace the hash-only builder/checker.

### 11.1 Required generated artifacts

The portable pack must contain, with safe normalized POSIX relative names:

- exact committed `store_version.json`;
- archived validated public review pack and evidence reference;
- all committed seed Parquet chunks and strict manifests;
- typed import receipt;
- canonical store audit;
- round-trip audit;
- minute coverage/replay-pair audit;
- funding observed-range audit;
- DuckDB smoke audit;
- reproducibility audit;
- risk/guardrail report;
- exact canonical review-pack manifest hashing every non-manifest member.

Do not include `.building`, unrelated files, orphan objects, or arbitrary store contents.

### 11.2 Reproducibility

Build independent semantic result A and B and derive, never assert:

- same typed input rows -> same logical hashes;
- same input -> same chunk paths and canonical manifests;
- verified no-op second import -> no new committed chunks;
- read-back -> same logical hashes;
- audit A/B -> exact same canonical bytes;
- checker reconstruction -> same semantic results.

### 11.3 Standalone checker

The checker must:

1. reject missing, duplicate, unsafe, absolute, `..`, backslash, drive-letter, directory, symlink and non-regular ZIP entries;
2. require exact manifest schema/canonical bytes and exact expected member set derived from the packed store contract;
3. extract only into a fresh temporary directory with containment checks;
4. semantic-check the archived nested public review pack;
5. run the full strict store audit from extracted Parquet bytes;
6. rerun round-trip, coverage, funding and DuckDB audits;
7. regenerate canonical reports and compare exact bytes;
8. reject an empty manifest pack and every fully rehashed semantic fake;
9. clean extraction on success and failure.

Builder flow:

```text
strictly validate source store
-> build temporary ZIP
-> standalone semantic self-check
-> atomic replace destination
-> remove temporary ZIP on every failure
```

## Mandatory correction 12 — executable CLIs

Replace all five success-returning stubs with real strict CLIs:

```text
scripts/import_bybit_public_review_pack_to_store.py
scripts/audit_bybit_public_parquet_store.py
scripts/plan_bybit_public_store_repairs.py
scripts/make_bybit_public_parquet_seed_review_pack.py
scripts/check_bybit_public_parquet_seed_review_pack.py
```

Requirements:

- named required arguments; no catch-all `paths nargs="*"`;
- call the production implementation;
- compact canonical JSON success/failure on stdout;
- nonzero exit on any missing input or semantic failure;
- no traceback by default;
- optional `--debug` traceback;
- no work at import;
- no network.

A test must run every CLI against a missing path and assert nonzero strict JSON failure. Another test must run the full successful synthetic lifecycle through the CLIs.

## Mandatory correction 13 — exact contract documentation

Expand `docs/bybit_public_parquet_store_contract_v1.md` into the actual versioned contract. It must specify exact:

- dataset fields, Arrow types, nullability and primary keys;
- typed row/model schemas;
- Decimal representability algorithm;
- canonical logical projection and JSONL format;
- partition/chunk path grammar;
- chunk manifest, store version, evidence reference and receipt JSON schemas;
- staging and atomic publication states;
- idempotent/no-op verification;
- conflict/overlap/orphan policies;
- reader and replay-slice behavior;
- coverage/resume/funding limitations;
- DuckDB view and smoke-audit contract;
- portable pack members, manifest and checker algorithm;
- reproducibility derivation;
- every frozen guardrail.

Keep the required statement:

```text
Parquet file bytes are not claimed to be canonical across PyArrow/platform versions.
Canonical identity is the logical row hash plus strict schema, manifest and semantic read-back.
```

## Mandatory correction 14 — real tests, no matrix padding

Retain the four required Sprint 06.4A test modules and add shared deterministic fixtures/modules as needed.

The suite must implement all 82 frozen behaviors from the original Sprint 06.4A prompt as real collected nodes. Each node must perform a material setup/mutation and assert an exact result. Do not create a generic parameterized counter test or map rows to nonexistent tests.

At minimum, add full no-network lifecycle tests for both approved public host provenance values:

```text
synthetic RecordingPublicClient capture
-> public review pack
-> market-store CLI import
-> strict audit
-> verified no-op second import
-> exact receipt comparison
-> coverage/repair plan
-> replay-ready slice
-> DuckDB smoke
-> portable pack CLI builder
-> standalone CLI checker
```

Add deterministic failure seams/tests for:

- unknown row field before staging;
- early/mid/late chunk failures and exact staging cleanup;
- early/mid/late import failures and no receipt;
- source deleted/tampered after load;
- valid decimal maximum;
- bool/string/float aliases;
- cross-month chunk splitting;
- existing corrupted chunk reuse attempt;
- duplicate/conflicting keys across chunks;
- tampered store version, chunk manifest fields, Parquet, receipt, evidence reference and nested pack;
- missing/extra/symlink/non-regular store entries;
- reversed/unaligned/out-of-range coverage inputs;
- nonexistent instrument snapshot;
- missing funding/mark join;
- DuckDB DECIMAL and no persistent file;
- empty/rehashed fake portable pack;
- temporary ZIP/extraction cleanup;
- atomic output replacement only after self-check;
- missing-path failure for every CLI;
- source-tree and coverage-map verifier failures.

## Required commands

Run and report exact outputs:

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python scripts/check_behavior_coverage_maps.py --collect-command "python -m pytest --collect-only -q"
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_2_true_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_3_owner_lifecycle_executability.py -q
python -m pytest tests/test_sprint_06_3b_3_1_evidence_truthfulness.py -q
python -m pytest tests/test_sprint_06_3b_3_2_reproducibility_and_lifecycle.py -q
python -m pytest tests/test_sprint_06_4a_parquet_store_contract.py -q
python -m pytest tests/test_sprint_06_4a_atomic_import_and_roundtrip.py -q
python -m pytest tests/test_sprint_06_4a_coverage_resume_gap_repair.py -q
python -m pytest tests/test_sprint_06_4a_store_evidence_pack.py -q
python -m pytest -q
ruff check .
git diff --check
python scripts/hash_source_tree.py --root .
```

Do not run the real owner pack, any public network probe, or any owner PowerShell script.

## Definition of done

The code gate opens only when all of the following are true:

```text
all accepted upstream tests unchanged and passing;
all 82 Sprint 06.4A behavior rows map to actual collected material tests;
72-row Sprint 06.3B map is truthful and verifier-clean;
all five CLIs perform real work and fail nonzero on missing input;
strict models and exact Decimal policy pass boundary tests;
rows are split by exact UTC month and projected once consistently;
writer validates semantic read-back before atomic publish;
staging cleanup is exact on every failure;
existing chunks are fully revalidated before reuse;
conflicts fail before publication;
source archive and receipt-last commit are atomic and exact;
second import is a fully verified typed no-op;
reader requires a real explicit instrument snapshot and derives funding observations;
full audit rejects missing version, unexpected entries, conflicts, tampering and orphans;
coverage/resume rejects aliases and handles all boundaries;
DuckDB views execute successfully and preserve DECIMAL;
portable pack checker reconstructs semantics and rejects an empty/rehashed fake;
reproducibility values are independently derived;
no generated artifacts are committed;
no network/private/live capability is introduced.
```

## Owner action after PM review

There is no owner/local action during this sprint.

After Codex submits a clean source ZIP and all required outputs, PM will independently review and attack the implementation. Only a later explicit PM acceptance may authorize Sprint 06.4B and provide a local-only owner seed-import PowerShell script.
