# Sprint 06.4A.2 — Real Store Lifecycle and Semantic Pack Closure

## PM authorization

Sprint 06.3B remains accepted and frozen. Sprint 06.4A.1 is rejected because the submitted code is not owner-executable and the newly reported 154 behavior tests are no-op padding.

Reviewed rejected identities:

```text
REJECTED_SOURCE_ZIP_SHA256 = f9df3d2659faa7dbb9315e540e4e96ea1fb1b8ff7e5f3d68bf5c2d82567ac238
REJECTED_SOURCE_TREE_SHA256 = 25a1b197b4a23819f11886343cb8c5bfbc0c00e6bb4ceb93ce9f9fae279334d4
```

Frozen upstream identities:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

Codex must not receive, open, embed, import, or depend on the real owner bundle/review pack. Use deterministic no-network synthetic public evidence only.

## Gate status

```text
SPRINT 06.4A.1: REJECTED
OWNER SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK / PRIVATE / LIVE / TELEGRAM: CLOSED
ONLY AUTHORIZED WORK: THIS SPRINT
```

## Objective

Deliver one executable, fail-closed, offline lifecycle:

```text
synthetic canonical public review pack bytes
-> strict immutable loader
-> complete import preflight
-> deterministic partition plan
-> month/snapshot-partitioned immutable chunks
-> semantic Parquet read-back
-> exact source-byte archive
-> receipt-last commit
-> verified no-op second import
-> strict full-store audit
-> coverage/resume/replay/funding audits
-> working in-memory DuckDB views
-> portable semantic seed-store pack
-> standalone semantic checker
-> executable CLIs
```

Preserve every accepted `src/bybit_grid/data/public_batch/*` byte/behavior unless a strictly additive import-safe helper is unavoidable.

## Frozen safety rules

- No network call.
- No private Bybit endpoint or credential.
- No account, order, position, grid, Telegram, or live execution.
- No bulk history download.
- No parameter selection, PnL, ROI, EV, profitability, or risk-readiness claim.
- Do not commit generated Parquet, ZIP, DuckDB, SQLite, JSON evidence, caches, `.env`, or owner artifacts.
- Parquet is durable canonical storage; DuckDB is in-memory read/query only.
- Historical/funding/delisted/metadata/risk/native/parameter/live completeness guardrails remain false.

# Part A — remove false test governance

## A1. Delete the no-op padding file

Delete:

```text
tests/test_sprint_06_behavior_coverage_material_nodes.py
```

No replacement may merely assert an ID, constant, index, enum value, file name, or row count.

The final total must not rely on one-test-per-document-row padding.

## A2. Replace both coverage maps truthfully

Rewrite:

```text
docs/sprint_06_3b_3_2_behavior_coverage.md
docs/sprint_06_4a_behavior_coverage.md
```

Every row must reference an actually collected node that performs the stated material setup/mutation against production code or a production CLI and asserts the exact success value/error.

Explicitly forbidden in a map row or mapped test:

```text
material_contract
binds to an executable node
validates collected closure row
fixture = {"id": ...}
assert fixture["id"] == ...
assert index >= 0
schema/version constant-only checks used as behavioral coverage
```

Distinct behaviors may map to parameterized nodes only when each parameter performs a distinct named mutation with a distinct expected result. The exact parameter ID must appear in the map.

## A3. Harden the map verifier

The verifier must additionally reject:

- either forbidden test file/name pattern above;
- generic fixture/mutation text;
- rows whose expected column merely repeats the behavior ID;
- duplicate production behavior mappings hidden behind different no-op node names;
- a map node that is collected only because of a skipped/unconditional dummy test.

Add verifier tests proving all these cases fail.

# Part B — make every CLI executable first

## B1. Add a real shared CLI module

Provide an import-safe canonical helper in a package module, preferably:

```text
src/bybit_grid/common/strict_cli.py
```

Do not rely on an untracked `scripts/_cli_common.py` import.

It must serialize dataclasses/enums/Decimal/tuples into compact canonical JSON, emit one JSON object on stdout, use nonzero exit on failure, suppress tracebacks unless `--debug`, and perform no work at import.

## B2. Required CLI smoke gates

All five commands must make it through `--help` with exit 0:

```text
scripts/import_bybit_public_review_pack_to_store.py
scripts/audit_bybit_public_parquet_store.py
scripts/plan_bybit_public_store_repairs.py
scripts/make_bybit_public_parquet_seed_review_pack.py
scripts/check_bybit_public_parquet_seed_review_pack.py
```

Each missing-input invocation must return nonzero and exactly one parseable compact JSON failure object on stdout, with no traceback on stderr.

# Part C — strict immutable models and parsers

## C1. Replace monkey-patched dataclass initialization

Use normal `__post_init__` or strict factories. Do not assign `__init__`/`__post_init__` after class creation.

All production models must validate:

- exact enum/model types;
- `type(v) is int`, never bool aliases;
- `type(v) is bool` for booleans;
- exact safe nonempty strings;
- lowercase 64-character SHA-256;
- exact tuples containing exact model types;
- immutable mappings with exact string keys and validated values;
- range/order/count/guardrail relationships.

## C2. Strict persisted parsers

Implement exact-key canonical JSON parsers for:

```text
store_version.json
chunk_manifest.json
evidence_reference.json
import_receipt.json
portable review-pack manifest and audits
```

Unknown/missing keys, bool/int aliases, list/tuple confusion, malformed nested manifests, noncanonical bytes, and schema/version mismatch must fail with stable errors.

## C3. Strict typed rows / one projection source

Provide a single dataset specification per dataset that drives:

```text
exact field set
typed row validation
primary key
partition key
Arrow schema
canonical logical JSONL
Parquet table construction
read-back reconstruction/comparison
```

Unknown fields must fail before creating `.building`.

Time-series rows in one candidate chunk must have exactly one symbol and one UTC month. Instrument rows in one chunk must have exactly one snapshot timestamp.

# Part D — Decimal correctness

Use `decimal.localcontext()` with enough precision and traps configured explicitly.

The validator must accept both exact boundaries:

```text
 99999999999999999999.999999999999999999
-99999999999999999999.999999999999999999
```

and reject:

- non-Decimal;
- NaN/Infinity;
- nonzero scale beyond 18;
- integer/precision overflow;
- any required rounding.

No float conversion is permitted.

# Part E — deterministic partition planner and conflict preflight

## E1. Add a pure partition planner

Before any committed write, partition detached validated rows as:

```text
instrument_snapshot -> snapshot_server_time_ms
trade_kline_1m      -> symbol / UTC year / UTC month
mark_kline_1m       -> symbol / UTC year / UTC month
funding_rate        -> symbol / UTC year / UTC month
```

The canonical synthetic fixture must include funding rows across at least four UTC months and kline rows crossing a month boundary. Tests must prove exact chunk counts and path order.

## E2. Complete import preflight

Before publishing `store_version.json`, any chunk, evidence, or receipt:

- validate all source bytes and detached rows;
- build the complete partition plan;
- calculate target manifests/paths;
- validate existing canonical roots;
- scan relevant committed partitions for duplicate/conflicting keys;
- verify exact source archive target and receipt target;
- prove no deterministic semantic error remains.

The accepted real-pack shape must be represented synthetically as:

```text
instrument count > 500
trade rows = 1001
mark rows = 1001
funding rows = 300 spanning multiple UTC months
```

No real owner bytes are required.

## E3. Conflict policy

Before publication:

```text
same primary key + same complete semantic row -> reusable identical data
same primary key + any semantic difference -> store_row_conflict
new disjoint primary key -> write
incoming duplicate key -> duplicate_incoming_key
committed duplicate/conflict across chunks -> audit failure
```

A chunk containing multiple symbols must fail before staging.

# Part F — strict chunk contract

## F1. Existing and new chunks

For every chunk, validate:

- exact regular directory entries;
- exact canonical manifest bytes/schema;
- manifest dataset and exact dataset-specific primary-key columns;
- manifest `relative_path` equals actual relative path;
- expected path rederived from typed rows and logical hash;
- Parquet SHA-256;
- exact Arrow schema;
- exact typed projected rows and sequence;
- strict key order/uniqueness;
- row count/min/max/logical hash;
- partition values equal row values.

## F2. Failure cleanup

Keep deterministic early/mid/late seams. On failure, remove the exact staging root. Tests must assert no stale staging and no final publication.

# Part G — immutable source bytes, atomic receipt-last import

## G1. Loader

`ValidatedPublicBatchEvidence` must contain immutable exact source bytes, not a path used later for copying. The loader must:

- read source bytes exactly once;
- hash those same bytes;
- semantically validate those same bytes;
- reconstruct from those same bytes;
- return detached immutable typed rows/provenance/source bytes.

A source-file deletion or mutation after load must not change imported archive bytes.

## G2. Import publication

Use validated temporary files plus same-volume atomic replace for:

```text
store_version.json
archived review_pack.zip
evidence_reference.json
import_receipt.json
```

The receipt is written last. No receipt may exist after any injected failure.

Published orphan chunks caused by a simulated process interruption must be detected explicitly by audit and safely reusable only after complete validation.

## G3. Verified no-op re-import

On an existing receipt:

- strict-parse canonical receipt bytes;
- reconstruct nested `StoreChunkManifest` tuple models;
- validate store version;
- validate every referenced chunk and exact source archive/reference;
- rerun nested public-pack semantic validation;
- reject extra/missing/conflicting/orphan objects affecting the import;
- regenerate exact receipt bytes;
- prove no file contents, mtimes, or committed member set changed.

Return a typed `StoreImportReceipt`.

# Part H — full store audit

An empty directory, missing version, partial failed import, or arbitrary junk must not be `ok=true`.

The audit must enforce:

- exact version schema/canonical bytes;
- approved direct root entries only;
- safe regular entries, no symlink/junction/non-regular entry;
- no unexpected files/directories;
- every chunk through strict reader validation;
- global duplicate/conflicting key detection;
- exact evidence archive/reference and nested public-pack semantic validation;
- exact typed receipts and references;
- orphan chunks/evidence/references/receipts;
- stale `.building` entries;
- committed seed replay-pair coverage;
- observed funding range only;
- frozen false guardrails.

Document whether invalid input returns a typed audit with failures or raises; use one stable policy consistently.

# Part I — reader, replay, coverage, resume

## I1. Replay slice

Validate exact symbol/start/end/snapshot arguments. Load and return the exact instrument snapshot row for the requested symbol.

Require:

- complete ascending trade grid;
- complete ascending mark grid;
- exact timestamp equality;
- no duplicates/conflicts;
- funding observations joined to the exact included mark candle by timestamp;
- each observation includes funding rate and mark open;
- missing mark join fails.

Return immutable typed output.

## I2. Coverage and resume

Implement `resume.py`; it may not be empty.

Reject:

- unsafe symbol;
- bool/string/float timestamp aliases;
- negative/unaligned timestamps;
- `start > end`;
- out-of-window supplied timestamps;
- wrong audit model types;
- mismatched trade/mark symbol/window;
- overlapping/omitted repair windows.

Test first/last/middle/disjoint gaps, inclusive 1000-row splitting, UTC month/year boundaries and leap day.

Funding scan validates exact timestamps and reports observed range only; it never proves global completeness.

# Part J — working DuckDB views

Do not use a prepared parameter in `CREATE VIEW`.

Use safely escaped store-owned paths or register validated Arrow/Parquet relations through a DuckDB-supported API.

Requirements:

- prevalidate all four required datasets before creating any view;
- in-memory connection only;
- exact four view names;
- close connection on every failure and inside smoke helper;
- Hive partitions and `union_by_name=true` where applicable;
- row counts, min/max timestamps and duplicate-key queries;
- market columns remain DuckDB `DECIMAL`, never `DOUBLE`;
- no persistent database file or extension/network action;
- alternate approved host provenance remains queryable.

# Part K — semantic portable seed-store pack

## K1. Builder input gate

The builder must first require `audit.ok=true`. It must never package an empty, partial, orphaned, tampered, or unexpected store.

Do not recursively include arbitrary files. Derive the exact member set from validated store models/receipts/evidence.

## K2. Required generated artifacts

Include exact committed store members plus canonical:

```text
store audit
round-trip audit
minute/replay-pair coverage audit
funding observed-range audit
DuckDB smoke audit
reproducibility audit
risk/guardrail report
review-pack manifest
```

Exclude `.building`, junk, orphans, unrelated files and arbitrary store content.

## K3. Standalone checker

The checker must:

1. reject duplicate/unsafe/absolute/backslash/drive/`..`/directory/symlink/non-regular ZIP entries;
2. require exact canonical manifest schema/bytes and exact derived member set;
3. extract into a fresh temporary directory with containment checks;
4. validate nested public review-pack semantics;
5. run the full store audit;
6. rerun round-trip, coverage, funding and DuckDB audits;
7. regenerate every report and compare exact bytes;
8. reject empty manifests and fully rehashed semantic fakes;
9. clean temporary extraction on success and failure.

Builder flow:

```text
strict store validation
-> temporary ZIP
-> standalone semantic self-check
-> atomic destination replace
-> temporary cleanup on every failure
```

# Part L — real tests and required attack cases

## L1. Required production lifecycle tests

Add a deterministic synthetic no-network public-pack fixture and test the full CLI lifecycle for both approved provenance hosts:

```text
synthetic public capture/review pack
-> import CLI
-> audit CLI
-> verified no-op import CLI
-> repair-plan CLI
-> replay slice
-> DuckDB smoke
-> seed-pack builder CLI
-> standalone checker CLI
```

The fixture must materially exercise multi-month funding partitioning.

## L2. Required exact regression tests

At minimum commit tests for every reproduced PM defect:

1. each CLI `--help` succeeds;
2. each CLI missing path gives strict JSON nonzero failure;
3. full synthetic CLI lifecycle succeeds;
4. valid Decimal max/min accepted;
5. real-shape 300 funding rows split by month before publication;
6. deterministic cross-month preflight leaves zero committed files;
7. partial/orphan store audit fails;
8. empty store audit fails;
9. empty-manifest portable pack rejected;
10. arbitrary rehashed portable pack rejected;
11. receipt JSON parses to typed tuple manifests;
12. verified no-op second import preserves hashes/mtimes/member set;
13. source mutation after load cannot change archived bytes;
14. same-key different-row conflict rejected before publish;
15. duplicate/conflict across chunks detected by audit;
16. multi-symbol candidate chunk rejected;
17. manifest actual-path mismatch rejected;
18. explicit nonexistent instrument snapshot rejected;
19. funding/mark join generated and missing join rejected;
20. reversed/unaligned/out-of-range/bool coverage inputs rejected;
21. funding invalid timestamp aliases rejected;
22. `resume.py` produces exact bounded windows;
23. DuckDB views open and smoke audit closes connection;
24. DuckDB market types are DECIMAL;
25. builder rejects `audit.ok=false` store;
26. builder/checker temp cleanup on failure;
27. rehashed tampering of every generated audit/report rejected;
28. unexpected root entry, symlink and stale staging rejected;
29. governance verifier rejects no-op material tests/maps;
30. maps reference actual material nodes only.

Tests must assert stable exact errors, not merely `raises(Exception)`.

# Part M — documentation

Expand `docs/bybit_public_parquet_store_contract_v1.md` so it exactly matches the implementation, including schemas, strict models, Decimal algorithm, partition grammar, preflight/commit states, receipt/no-op parsing, orphan policy, replay funding joins, coverage/resume, DuckDB and portable pack semantics.

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
python -m pytest tests/test_sprint_06_4a_2_real_store_lifecycle.py -q
python -m pytest -q
ruff check .
git diff --check
python scripts/hash_source_tree.py --root .
```

Do not run the real owner pack, an owner PowerShell script, or any network probe.

# Definition of done

The code gate opens only when:

```text
the 154 no-op behavior tests are removed;
coverage maps point only to material production tests;
all five CLIs import and execute;
valid decimal128 boundary values pass;
complete partition planning occurs before publication;
multi-month funding imports as deterministic monthly chunks;
conflicts and partition-key mixing fail before publication;
source bytes are immutable after load;
receipt-last import is atomic and second import is a verified typed no-op;
empty/partial/orphan/tampered stores fail audit;
reader requires and returns an actual instrument snapshot;
funding observations are mark-joined;
coverage/resume rejects aliases and invalid ranges;
DuckDB views execute and preserve DECIMAL;
portable pack checker reconstructs semantics and rejects empty/rehashed fakes;
all generated report values are derived;
all accepted upstream tests remain passing;
no network/private/live capability is introduced.
```

## Owner action after PM review

There is no owner/local action in this sprint. After Codex submits a clean source ZIP and exact outputs, PM will independently attack the implementation. Only explicit later acceptance may authorize a local offline owner seed-import PowerShell script.
