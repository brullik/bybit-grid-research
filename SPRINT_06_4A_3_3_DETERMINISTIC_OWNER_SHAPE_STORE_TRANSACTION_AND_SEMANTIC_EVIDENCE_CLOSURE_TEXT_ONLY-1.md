# Sprint 06.4A.3.3 — Deterministic Owner-Shape Store Transaction and Semantic Evidence Closure

## 0. PM authorization and frozen context

Sprint 06.3B remains accepted and frozen. Sprint 06.4A.3.2 is rejected.

Reviewed rejected revision:

```text
REJECTED_UPLOADED_ZIP_SHA256 = 17752d6798b9c53399888a27d998578f1e8da748e9e375b97939df8b414046c4
REJECTED_SOURCE_TREE_SHA256 = 1bd401aef3aab9f1144aa968b98f9f5f08ea54416c6ef283f0c102ee2056b1d5
REJECTED_ARCHIVE_COMMIT_COMMENT = db4df380cfc47acbfcbc4e937197ba20a77b34b2
REJECTED_PYTEST_COLLECTION = 449
REJECTED_FOCUSED_064A_COLLECTION = 18
```

Frozen accepted upstream identity:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

The real owner review pack must **not** be opened, copied, imported, downloaded, requested, or used by Codex. All implementation and tests must be deterministic, no-network synthetic work.

## Gate status

```text
SPRINT 06.4A.3.2: REJECTED
OWNER OFFLINE SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK: FORBIDDEN
PRIVATE API: FORBIDDEN
LIVE EXECUTION: FORBIDDEN
TELEGRAM: OUT OF SCOPE
ONLY AUTHORIZED WORK: THIS CORRECTIVE SPRINT
```

# 1. Current deterministic failures that must be treated as regression inputs

Do not debate, reinterpret, or weaken these failures. Convert each into a real failing test before or alongside the production fix.

## 1.1 Real owner-shaped import failure

Offline reconstruction of the already accepted public evidence yielded:

```text
instrument rows = 721
trade rows      = 1001
mark rows       = 1001
funding rows    = 300
```

Current production import fails:

```text
MarketStoreError: mixed_symbols
```

and leaves:

```text
.building/
store_version.json
```

The required semantics are:

- an `instrument_snapshot` chunk may and normally will contain many symbols;
- every row in that chunk must share exactly one `snapshot_server_time_ms`;
- `(snapshot_server_time_ms, symbol)` keys must be sorted and unique;
- trade, mark, and funding chunks must contain exactly one symbol and one UTC month.

## 1.2 Valid imported store fails its own audit

Current synthetic import produces a receipt and four chunks, but audit returns:

```text
receipt_invalid:mutable_sequence_forbidden
orphan_chunk:<every chunk>
```

Cause: raw JSON lists are not converted to typed tuples before canonical reserialization.

## 1.3 Coverage map fails

The current exact verifier command returns 61 `missing_node` errors because the JSON manifest still points to the deleted file:

```text
tests/test_sprint_06_4a_3_material_behaviors.py
```

The final revision must not contain a mapping to that file.

## 1.4 Semantic fabrication remains accepted

The current seed-pack checker accepts a ZIP containing only:

```text
arbitrary.txt
review_pack_manifest.json
```

when the hash is recalculated.

## 1.5 Existing-receipt path accepts tampering

Current no-op re-import accepts:

```text
tampered evidence_reference.json
changed receipt chunk metadata
unexpected root file
orphan chunk
receipt redirected to a copied chunk path
```

## 1.6 Accepted snapshot timestamp is rejected

A real accepted snapshot value such as:

```text
1783973985593
```

is an exact nonnegative millisecond observation and is not minute-aligned. It must be accepted as `snapshot_server_time_ms`. Only kline/funding minute timestamps and replay window bounds require minute alignment.

## 1.7 Additional current failures

```text
writer mid/late failure leaves .building/
DuckDB opens a store whose audit is false
coverage planner accepts a SimpleNamespace instead of MinuteCoverageAudit
trade and mark audits with different symbols can produce replay_ready_bool=true
nested mutable values survive inside MappingProxyType audit models
strict_cli still fails on MappingProxyType dataclasses via dataclasses.asdict()
```

# 2. Non-negotiable implementation policy

## 2.1 Production-first

Before editing the behavior manifest or claiming test completion, materially implement the production lifecycle.

The final diff must materially change all applicable modules below:

```text
src/bybit_grid/common/strict_cli.py
src/bybit_grid/data/market_store/canonical.py
src/bybit_grid/data/market_store/models.py
src/bybit_grid/data/market_store/paths.py
src/bybit_grid/data/market_store/planner.py
src/bybit_grid/data/market_store/writer.py
src/bybit_grid/data/market_store/reader.py
src/bybit_grid/data/market_store/import_public_batch.py
src/bybit_grid/data/market_store/audit.py
src/bybit_grid/data/market_store/coverage.py
src/bybit_grid/data/market_store/resume.py
src/bybit_grid/data/market_store/duckdb_views.py
src/bybit_grid/data/market_store/evidence.py
```

Create these exact new modules unless an equivalent already exists and is fully reused:

```text
src/bybit_grid/data/market_store/parsing.py
src/bybit_grid/data/market_store/inventory.py
src/bybit_grid/data/market_store/transaction.py
```

A submission that mainly changes tests, manifests, counts, or verifier wording is an automatic fail.

## 2.2 No placeholders and no claimed-but-unexecuted paths

Forbidden:

```text
pass
TODO
NotImplementedError
hard-coded ok=true
audit booleans assigned without derivation
checker that validates only hashes
builder that recursively packs arbitrary files
manifest-only acceptance tests
--help used as a full lifecycle test
missing-argument calls mapped to unrelated behavior IDs
network calls
real owner evidence access
private API or live execution code
```

## 2.3 Preserve confirmed fixes

Do not regress:

- exact decimal128(38,18) max/min boundaries;
- scale > 18 rejection;
- no float coercion;
- monthly time-series partitioning;
- inclusive repair windows capped at 1000 rows;
- strict CLI `--help` behavior;
- compact JSON argument errors;
- no-live guardrails;
- public-batch semantic checker behavior from Sprint 06.3B.

# 3. Exact source and model contracts

## 3.1 Add exact immutable models

Add these frozen dataclasses to `models.py` with exact `__post_init__` validation:

```python
@dataclass(frozen=True)
class StoreVersion:
    storage_schema_version: str

@dataclass(frozen=True)
class StoreEvidenceReference:
    run_id: str
    source_review_pack_sha256: str

@dataclass(frozen=True)
class StoreFileInventoryEntry:
    relative_path: str
    entry_type: str          # exactly "file" or "directory"
    size: int
    sha256: str | None       # file only
    mtime_ns: int

@dataclass(frozen=True)
class PlannedChunk:
    dataset: MarketDatasetKind
    rows: tuple[MappingProxyType, ...]
    manifest: StoreChunkManifest
    parquet_bytes: bytes
    manifest_bytes: bytes
    reuse_existing_bool: bool

@dataclass(frozen=True)
class ImportPreflightPlan:
    evidence: ValidatedPublicBatchEvidence
    store_root: Path
    version: StoreVersion
    chunks: tuple[PlannedChunk, ...]
    evidence_reference: StoreEvidenceReference
    receipt: StoreImportReceipt
    receipt_bytes: bytes
    evidence_reference_bytes: bytes
    source_archive_bytes: bytes
    existing_store_bool: bool
```

`Path` is allowed in the in-memory `ImportPreflightPlan` only. It must never be serialized by canonical JSON.

Update existing models so every field is validated with exact type identity:

- bool is not int;
- every tuple field must be exact tuple;
- every mapping field must be a recursively immutable `MappingProxyType`;
- every SHA is lowercase `[0-9a-f]{64}`;
- every relative path is safe POSIX relative text;
- all proof/live/risk guardrails remain exact `False` unless the frozen contract explicitly permits otherwise.

## 3.2 Deep immutability

Replace shallow `_strict_mapping()` behavior.

Implement one recursive `freeze_immutable(value, *, field_name)` policy:

```text
MappingProxyType -> recursively copy/freeze keys and values
exact dict       -> recursively copy/freeze, then MappingProxyType
exact tuple      -> recursively freeze members
exact list       -> reject in model constructors unless parsing JSON into tuple
str/int/bool/None/Decimal/Enum -> accept under field-specific rules
float/bytes/bytearray/Path/set/frozenset/unknown -> reject
```

After model construction, mutating an external source dict or nested list must not change the model.

# 4. Canonical JSON and strict parsing

## 4.1 Canonical serializer

`canonical.py` must use `dataclasses.fields()` plus direct `getattr()`. Do not call `dataclasses.asdict()` anywhere in the canonical or CLI serialization boundary.

Canonical output rules:

```text
UTF-8
compact separators
sort_keys=True
ensure_ascii=False
allow_nan=False
exact final newline
Decimal -> exact normalized plain string
-0 -> 0
Enum -> exact scalar .value
MappingProxyType -> sorted exact nonempty string keys
Tuple -> JSON array
bool distinct from int
```

Reject:

```text
float
bytes / bytearray
Path
set / frozenset
unknown objects
mapping keys that are non-string or empty
mutable list or dict presented directly to the immutable serializer
```

For canonical logical row hashing, convert validated row mappings to recursively frozen mappings before serialization. Do not weaken the immutable artifact serializer merely to accept `json.loads()` output.

## 4.2 Strict JSON loader

Create `parsing.py` with these exact public functions:

```python
def strict_json_object_bytes(data: bytes, *, context: str) -> MappingProxyType: ...
def parse_store_version_bytes(data: bytes) -> StoreVersion: ...
def parse_chunk_manifest_bytes(data: bytes) -> StoreChunkManifest: ...
def parse_evidence_reference_bytes(data: bytes) -> StoreEvidenceReference: ...
def parse_import_receipt_bytes(data: bytes) -> StoreImportReceipt: ...
def parse_seed_manifest_bytes(data: bytes) -> MappingProxyType: ...
```

`strict_json_object_bytes()` must:

- require exact `bytes`;
- decode strict UTF-8;
- reject duplicate keys with `object_pairs_hook`;
- reject floats with `parse_float`;
- reject NaN/Infinity with `parse_constant`;
- require a JSON object root;
- recursively convert JSON arrays to tuples and objects to `MappingProxyType`;
- preserve exact bool/int identity.

Every typed parser must:

1. enforce an exact key set;
2. build the typed model;
3. reserialize the typed model with `canonical_json_bytes()`;
4. require exact byte equality with input;
5. return the typed model.

Stable errors must include the artifact context, for example:

```text
store_version_schema_invalid
store_version_canonical_mismatch
chunk_manifest_schema_invalid
chunk_manifest_canonical_mismatch
evidence_reference_schema_invalid
evidence_reference_canonical_mismatch
receipt_schema_invalid
receipt_canonical_mismatch
seed_manifest_schema_invalid
seed_manifest_canonical_mismatch
json_duplicate_key
json_float_token
json_non_finite_token
```

## 4.3 Strict CLI serialization

Update `src/bybit_grid/common/strict_cli.py` to use field-based recursion, not `asdict()`.

It must serialize `StoreRoundTripAudit` and `StoreReproducibilityAudit` containing `MappingProxyType` without error.

CLI output may convert tuples to JSON arrays. It must still reject floats and non-finite decimals.

# 5. Exact partition and chunk semantics

## 5.1 Instrument snapshot partition

`partition_validated_rows(MarketDatasetKind.instrument_snapshot, rows)` must:

- accept many different symbols;
- group only by exact `snapshot_server_time_ms`;
- return one `PartitionPlanEntry` per snapshot timestamp;
- sort rows by `(snapshot_server_time_ms, symbol)`;
- reject duplicate `(snapshot_server_time_ms, symbol)` keys;
- require all rows in an entry to have the same provenance fields for run/pack/plan/source/schema;
- not require snapshot timestamp minute alignment.

## 5.2 Time-series partitions

Trade, mark, and funding inputs may contain multiple symbols and months at the raw-import level. The planner must split them by:

```text
(symbol, UTC year, UTC month)
```

Every resulting plan entry must contain exactly one symbol and one month.

`PLAN-MULTI-SYMBOL-REJECTED` means a **single validated time-series plan entry or direct writer call** containing mixed symbols must fail. It does not mean raw import input with multiple symbols is forbidden.

## 5.3 Deterministic in-memory chunk artifacts

Add a pure function in `writer.py` or `transaction.py`:

```python
def build_planned_chunk(kind, rows, *, existing_store_root: Path | None) -> PlannedChunk: ...
```

It must perform all row, partition, schema, key, path, logical-hash, Parquet serialization, and manifest derivation without mutating the target store.

Use a PyArrow in-memory buffer to obtain deterministic candidate Parquet bytes for preflight. The contract does not claim cross-version Parquet byte canonicality, but the current import transaction must know the exact bytes it will publish.

The function must derive:

- exact sorted rows;
- logical row SHA-256;
- exact relative path;
- exact Parquet bytes;
- Parquet SHA-256;
- exact typed `StoreChunkManifest`;
- canonical manifest bytes.

# 6. Writer and strict chunk reader

## 6.1 Direct writer preconditions

`write_chunk_atomic()` must reject before creating any path:

```text
empty input
wrong row type or field set
mixed symbols for trade/mark/funding
mixed UTC months for trade/mark/funding
mixed snapshot timestamps for instrument snapshots
duplicate keys
unsafe symbol/path value
wrong schema version
Decimal not exactly representable
unaligned trade/mark/funding timestamp
```

Instrument snapshot rows may contain multiple symbols.

## 6.2 Exact chunk validation

Create one shared strict reader function and use it from writer reuse, import no-op, audit, regular reader, and portable checker:

```python
def read_and_validate_chunk(
    store_root: Path,
    chunk_dir: Path,
    *,
    expected_manifest: StoreChunkManifest | None = None,
) -> tuple[StoreChunkManifest, tuple[MappingProxyType, ...]]:
    ...
```

It must verify, in this order:

1. `store_root` and `chunk_dir` are safe;
2. `chunk_dir` is a real directory, not symlink/junction;
3. exactly two real regular files exist: `chunk_manifest.json`, `data.parquet`;
4. neither file is symlink/non-regular;
5. manifest strict parser and canonical bytes;
6. manifest dataset and `primary_key_columns` equal frozen dataset constants;
7. manifest `relative_path` equals `chunk_dir.relative_to(store_root).as_posix()`;
8. Parquet SHA-256;
9. exact Arrow schema;
10. nonempty rows;
11. every row exact-valid;
12. sorted unique keys;
13. exact row count/min/max;
14. exact instrument snapshot or time-series partition identity;
15. logical row SHA-256;
16. expected path rederived from rows and logical hash equals actual path;
17. if `expected_manifest` was supplied, exact typed equality with the parsed manifest.

No caller may use the old shallow `_read_chunk()` path.

## 6.3 Failure cleanup

For direct writer failure seams `early`, `mid`, and `late`:

- a previously absent target root remains absent;
- a previously existing root has byte/path/size/mtime inventory unchanged;
- no `.building` directory or transaction subdirectory remains;
- no parent partition directories remain if they were created only by the failed call.

# 7. Pure zero-write import preflight

Create:

```python
def build_import_preflight_plan(
    evidence: ValidatedPublicBatchEvidence,
    store_root: Path,
) -> ImportPreflightPlan:
    ...
```

This function must not create, modify, touch, chmod, rename, or delete any filesystem entry.

Required steps:

1. require `type(evidence) is ValidatedPublicBatchEvidence`;
2. validate `evidence.run_id`, SHA, exact source bytes, immutable reconstructed mapping, exact public batch type;
3. recompute SHA-256 of `source_bytes` and require equality;
4. project every public row to the exact store schema;
5. build all partition entries;
6. build all `PlannedChunk` objects in memory;
7. validate existing store version if the target exists;
8. reject any existing nonempty store whose full graph audit is invalid;
9. build a global registry of all committed keys and complete rows;
10. detect incoming duplicates;
11. detect committed exact duplicates and semantic conflicts;
12. determine reusable chunks only after full strict validation;
13. derive exact evidence archive/reference targets;
14. derive exact sorted receipt chunks and canonical receipt bytes;
15. reject existing receipt/evidence/path ownership inconsistencies;
16. return the immutable plan.

Conflict rules:

```text
incoming same key twice                -> duplicate_incoming_key
committed same key twice               -> duplicate_committed_key
incoming key equals committed key,
complete rows equal                    -> exact reusable row/chunk only
incoming key equals committed key,
complete rows differ                   -> store_row_conflict
```

Mandatory zero-write checks:

- invalid scale-19 funding row;
- duplicate incoming key;
- committed semantic conflict;
- malformed existing version;
- malformed existing receipt/evidence;
- owner-shaped multi-symbol instrument snapshot must **not** be rejected.

# 8. Receipt-last transaction

Implement:

```python
def commit_import_preflight_plan(
    plan: ImportPreflightPlan,
    *,
    fail_at: str | None = None,
) -> StoreImportReceipt:
    ...
```

Supported deterministic failure seams:

```text
before_stage
stage_chunks
stage_evidence
stage_reference
stage_receipt
publish_chunks
publish_evidence
publish_reference
before_receipt
publish_receipt
```

## 8.1 New target root

For a previously absent root:

1. create a sibling temporary root under the same parent;
2. write the complete candidate store into the sibling root;
3. validate every staged artifact and full staged graph;
4. write receipt last inside the staged root;
5. validate the complete staged root again;
6. atomically rename the staged root to the final root;
7. on caught failure, remove the sibling root and leave final root absent.

## 8.2 Existing valid store

For an existing valid store:

1. stage only new objects in one transaction directory outside committed paths;
2. validate staged bytes;
3. publish immutable chunks/evidence/reference with atomic file/directory replacements;
4. track every newly published path;
5. publish receipt last;
6. on any caught failure before receipt publication, remove all newly published objects and empty parents;
7. leave all pre-existing entries byte/path/size/mtime identical.

Receipt is the only commit marker. Chunks/evidence without a valid owning receipt are invalid and must be detected by audit.

# 9. Verified no-op re-import

If the exact receipt path already exists, do **not** return early.

Perform this exact sequence:

1. snapshot full store inventory including path, entry type, size, SHA-256, and mtime_ns;
2. run `audit_market_store()` and require `ok is True`;
3. strict-parse canonical version;
4. strict-parse canonical receipt;
5. require receipt path components equal receipt fields;
6. regenerate the complete import preflight plan from the supplied evidence;
7. require exact typed receipt equality and exact receipt bytes;
8. validate every receipt chunk with `expected_manifest`;
9. validate exact receipt chunk set and ownership;
10. validate evidence archive SHA and byte equality to `evidence.source_bytes`;
11. strict-parse evidence reference and require exact run/SHA equality;
12. run the nested public review-pack semantic checker;
13. reject any orphan chunk/evidence/reference/receipt or unexpected entry;
14. run full audit again;
15. snapshot inventory again;
16. require exact inventory equality;
17. return the typed existing receipt.

The following must fail without mutation:

```text
corrupt Parquet
corrupt chunk manifest
receipt metadata changed
receipt noncanonical bytes
receipt redirected to copied path
evidence archive changed
evidence reference changed
unexpected root file
orphan chunk
orphan evidence
stale staging
```

# 10. Full store-graph audit

`audit_market_store(root)` must validate a complete committed store graph.

Content faults return:

```python
MarketStoreAudit(ok=False, failures=(stable_codes...), ...)
```

Unsafe invocation failures may raise `MarketStoreError`.

Required graph checks:

- exact allowed root members;
- no symlink/junction/non-regular entry anywhere;
- canonical `store_version.json`;
- no `.building` after successful commit;
- every chunk strict-valid;
- global key registry across all chunks;
- exact duplicate key versus semantic conflict distinction;
- every receipt strict-valid and path-consistent;
- every receipt chunk model equals actual manifest;
- every evidence reference strict-valid and path-consistent;
- every evidence archive SHA-valid;
- every nested public review pack semantically valid for receipt run ID;
- exact one-to-one ownership of receipts, evidence references/archives, and chunks;
- no orphan chunk/evidence/reference/receipt;
- no unexpected nested file;
- frozen false guardrails.

Stable failures must include at least:

```text
empty_store_root
store_version_missing
store_version_invalid
stale_building_entry
unexpected_root_entry:<name>
unsafe_store_entry:<path>
chunk_invalid:<path>:<code>
chunks_without_receipt
receipt_without_chunks
receipt_invalid:<path>:<code>
receipt_path_mismatch:<path>
receipt_chunk_manifest_mismatch:<path>
receipt_evidence_missing:<path>
evidence_archive_sha256_mismatch:<sha>
evidence_reference_invalid:<path>:<code>
nested_public_evidence_invalid:<sha>:<code>
orphan_chunk:<path>
orphan_evidence:<path>
orphan_receipt:<path>
duplicate_committed_key:<dataset>:<key>
store_row_conflict:<dataset>:<key>
```

A correctly imported synthetic owner-shaped store must return:

```text
ok = true
chunk_count = 7
receipt_count = 1
failures = ()
```

# 11. Replay contract

## 11.1 Argument validation

For `read_replay_slice()`:

```text
symbol: exact safe uppercase symbol
start_ms: exact nonnegative minute-aligned int
end_ms: exact nonnegative minute-aligned int
start_ms <= end_ms
snapshot_server_time_ms: exact nonnegative int, NOT required to be minute-aligned
```

## 11.2 Store and snapshot validation

Before reading replay data:

- require full store audit success;
- load exactly one instrument row matching both requested symbol and exact snapshot timestamp;
- missing or duplicate match fails.

## 11.3 Return type

Return exact `ReplaySlice`, not a mutable dict.

```text
instrument              -> MappingProxyType
trade_klines             -> tuple[MappingProxyType, ...]
mark_klines              -> tuple[MappingProxyType, ...]
funding_observations      -> tuple[FundingReplayObservation, ...]
```

Trade and mark must:

- cover every inclusive minute;
- be strictly ascending;
- be duplicate-free;
- have exactly equal timestamp sets.

Funding observation must contain exactly:

```text
funding_time_ms
funding_rate
mark_open
```

Join to the mark row at the identical timestamp. Missing or duplicate mark join fails.

# 12. Coverage and resume

Use one shared validator based on `paths.safe_symbol()`.

All coverage models require strict `__post_init__` invariants:

- safe symbol;
- exact nonnegative aligned timestamps where applicable;
- start <= end;
- row_count exact and consistent with interval bounds;
- exact tuple element types;
- duplicate timestamps sorted/unique;
- exact booleans;
- proof flags frozen false.

`plan_missing_minute_windows()` requires exact `MinuteCoverageAudit`.

`plan_trade_mark_repairs()` requires:

- exact `MinuteCoverageAudit` models;
- identical symbol/start/end;
- max_rows exact int in 1..1000.

Reject supplied observed timestamps outside the requested range; never silently filter them.

Mandatory gap tests:

```text
first minute
middle minute
last minute
multiple disjoint gaps
1000 rows
1001 rows
2000 rows
2001 rows
UTC month rollover
UTC year rollover
leap day
```

Funding observed-range scanner:

- exact safe symbol;
- every timestamp exact nonnegative minute-aligned int;
- bool/string/float/negative/unaligned rejected;
- reports observed range only;
- never sets global coverage proof true.

# 13. DuckDB contract

`open_readonly_duckdb_views()` must require a valid audited store before opening views.

Requirements:

```text
in-memory database only
no persistent DB file
no extensions
no network
exact four view names
only audited store-owned Parquet paths
Hive partitioning + union_by_name
exact Decimal columns remain DECIMAL(38,18)
```

If connection or view creation fails, close the connection before re-raising.

`duckdb_smoke_audit()` must close on success and failure and derive:

- exact row counts;
- min/max timestamps;
- duplicate primary-key counts;
- Decimal type checks.

# 14. Semantic portable seed review pack

## 14.1 Exact pack layout

The pack contains exactly the committed objects owned by one selected receipt, prefixed by `store/`, plus these fixed derived artifacts:

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

Committed store members are derived from the validated receipt only:

```text
store/store_version.json
store/<each receipt-owned chunk>/chunk_manifest.json
store/<each receipt-owned chunk>/data.parquet
store/<receipt path>
store/<evidence path>/review_pack.zip
store/<evidence path>/evidence_reference.json
```

Do not recursively include arbitrary files.

## 14.2 Exact manifest schema

`review_pack_manifest.json` must be canonical and have exactly:

```json
{
  "members": {"<member except manifest>": "<lowercase sha256>"},
  "run_id": "<run id>",
  "schema": "bybit_public_parquet_seed_review_pack_v1",
  "source_review_pack_sha256": "<sha256>",
  "storage_schema_version": "bybit_public_parquet_store_v1"
}
```

No unknown keys. Manifest does not hash itself.

## 14.3 Derived artifacts

Build derived artifacts from production functions, not literals.

`store_audit.json`:
- canonical `MarketStoreAudit`.

`round_trip_audit.json` exact keys:

```text
ok
failures
dataset_hashes
```

`minute_replay_coverage_audit.json` exact keys:

```text
symbol
snapshot_server_time_ms
start_open_time_ms
end_open_time_ms
trade_complete_bool
mark_complete_bool
timestamp_sets_equal_bool
replay_ready_bool
historical_market_data_coverage_proven_bool
```

`funding_observed_range_audit.json`:
- canonical `FundingObservedRangeAudit`.

`duckdb_smoke_audit.json` exact keys:

```text
ok
failures
view_row_counts
view_min_max_timestamps
duplicate_key_counts
decimal_type_checks
```

`reproducibility_audit.json` exact keys:

```text
ok
failures
core_key_sets_equal_bool
core_bytes_equal_bool
rebuilt_derived_artifacts_twice_bool
derived_artifact_count
```

`risk_guardrail_report.md` must list every frozen guardrail literally. At minimum all remain false:

```text
historical_market_data_coverage_proven_bool
funding_coverage_proven_bool
delisted_completeness_proven_bool
point_in_time_metadata_completeness_proven_bool
risk_budget_proven_bool
native_equivalence_proven_bool
parameter_selection_authorized_bool
live_authorized_bool
live_execution_present_bool
```

Only storage/resume engineering sufficiency may be true.

## 14.4 Two-build reproducibility

Build all derived artifact bytes twice from independently reread store state.

Derive, do not assert:

```text
core_key_sets_equal_bool
core_bytes_equal_bool
rebuilt_derived_artifacts_twice_bool
ok
```

Any mismatch fails before ZIP publication.

## 14.5 ZIP publication

- use safe POSIX names;
- reject duplicate/directory/absolute/traversal/backslash/drive names;
- use deterministic member order;
- use fixed ZIP metadata timestamp and permissions;
- write a temporary ZIP;
- run standalone semantic checker on the temporary ZIP;
- atomically replace destination;
- remove temporary ZIP on every failure.

## 14.6 Standalone checker

The checker must:

1. strict-parse canonical manifest;
2. require exact nonempty member set;
3. verify every hash;
4. reject extras/missing/unsafe/non-regular members;
5. extract only `store/` members to a temporary isolated root;
6. run full store audit;
7. validate nested public evidence;
8. reconstruct replay, coverage, funding, DuckDB, round-trip, reproducibility, and risk artifacts;
9. compare exact bytes for every derived artifact;
10. clean extraction on success and failure.

It must reject a fully rehashed mutation of any member.

# 15. CLI requirements

Preserve these exact five scripts:

```text
scripts/import_bybit_public_review_pack_to_store.py
scripts/audit_bybit_public_parquet_store.py
scripts/plan_bybit_public_store_repairs.py
scripts/make_bybit_public_parquet_seed_review_pack.py
scripts/check_bybit_public_parquet_seed_review_pack.py
```

For each:

- import-safe;
- `--help` exit 0;
- missing required args exit 2;
- exactly one compact JSON failure line;
- no traceback unless `--debug`;
- success output exactly one compact JSON line;
- no network/private/live behavior.

The repair CLI must require a valid audited store.

# 16. Mandatory deterministic synthetic fixture

Create:

```text
tests/helpers/synthetic_market_store_fixture.py
```

It must reuse the existing public-batch recording/capture/review-pack production path and perform no network calls.

Frozen fixture shape:

```text
run_id = synthetic_public_batch_064a33
symbol = BTCUSDT
base_url variants = https://api.bybit.com, https://api.bytick.com
server_time_ms = END + 60000 + 12345   # intentionally not minute aligned
last closed open time = END
instrument count >= 201
instrument snapshot includes BTCUSDT plus at least 200 distinct symbols
trade kline count = 1001
mark kline count = 1001
funding row count = 301
funding period spans exactly four UTC months
expected store chunks = 7
  1 instrument snapshot chunk
  1 trade chunk
  1 mark chunk
  4 funding month chunks
```

The helper must expose exact functions:

```python
def build_synthetic_public_review_pack(tmp_path: Path, *, base_url: str) -> Path: ...
def load_synthetic_validated_evidence(tmp_path: Path, *, base_url: str) -> ValidatedPublicBatchEvidence: ...
def import_synthetic_store(tmp_path: Path, *, base_url: str) -> tuple[Path, StoreImportReceipt, ValidatedPublicBatchEvidence]: ...
def snapshot_tree(root: Path) -> tuple[StoreFileInventoryEntry, ...]: ...
def mutate_zip_and_rehash(source: Path, destination: Path, *, member: str, mutator) -> Path: ...
```

Do not use the real owner pack or its bytes.

# 17. Exact 61 behavior-to-test mapping

Delete stale references to `tests/test_sprint_06_4a_3_material_behaviors.py`.

Create the exact test modules and exact node names below. Update `docs/sprint_06_4a_3_required_behaviors.json` to point one-to-one to these nodes in this exact order.

## 17.1 `tests/test_sprint_06_4a_3_3_governance_cli.py`

```text
GOV-EXACT-ID-SET
  ::test_gov_exact_id_set

GOV-MISSING-NODE
  ::test_gov_missing_node_rejected

GOV-NOOP-REJECTED
  ::test_gov_noop_node_rejected

CLI-HELP-ALL
  ::test_cli_help_all_five_scripts

CLI-MISSING-ARGS-ALL
  ::test_cli_missing_args_all_five_scripts
```

## 17.2 `tests/test_sprint_06_4a_3_3_schema_plan_writer.py`

```text
DECIMAL-MAX-BOUNDARY
  ::test_decimal_max_boundary

DECIMAL-MIN-BOUNDARY
  ::test_decimal_min_boundary

DECIMAL-ROUNDING-REJECTED
  ::test_decimal_rounding_rejected

PLAN-INSTRUMENT-SNAPSHOT
  ::test_plan_instrument_snapshot_multi_symbol_single_partition

PLAN-KLINE-CROSS-MONTH
  ::test_plan_kline_cross_month_two_partitions

PLAN-FUNDING-FOUR-MONTHS
  ::test_plan_funding_four_months_four_partitions

PLAN-MULTI-SYMBOL-REJECTED
  ::test_plan_entry_mixed_timeseries_symbols_rejected

PREFLIGHT-INVALID-ROW-ZERO-WRITES
  ::test_preflight_invalid_row_zero_writes

PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES
  ::test_preflight_incoming_duplicate_zero_writes

PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES
  ::test_preflight_committed_conflict_zero_writes

CHUNK-EARLY-CLEANUP
  ::test_chunk_early_failure_cleanup

CHUNK-MID-CLEANUP
  ::test_chunk_mid_failure_cleanup

CHUNK-LATE-CLEANUP
  ::test_chunk_late_failure_cleanup

CHUNK-CANONICAL-MANIFEST
  ::test_chunk_manifest_is_canonical

CHUNK-ACTUAL-PATH-MATCH
  ::test_chunk_actual_path_mismatch_rejected

CHUNK-PK-SCHEMA-MATCH
  ::test_chunk_primary_key_schema_mismatch_rejected

CHUNK-EXISTING-CORRUPTION-REJECTED
  ::test_existing_chunk_corruption_rejected
```

## 17.3 `tests/test_sprint_06_4a_3_3_import_audit.py`

```text
IMPORT-SYNTHETIC-REAL-SHAPE
  ::test_import_synthetic_owner_shape_succeeds

IMPORT-SOURCE-BYTES-IMMUTABLE
  ::test_import_archives_identical_source_bytes

IMPORT-RECEIPT-LAST
  ::test_import_receipt_is_last_commit_marker

IMPORT-NOOP-TYPED
  ::test_reimport_returns_typed_receipt

IMPORT-NOOP-ZERO-MUTATION
  ::test_reimport_zero_filesystem_mutation

IMPORT-NOOP-CORRUPT-CHUNK-REJECTED
  ::test_reimport_corrupt_chunk_rejected

IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED
  ::test_reimport_corrupt_evidence_rejected

AUDIT-EMPTY-REJECTED
  ::test_audit_empty_store_rejected

AUDIT-VERSION-TAMPER-REJECTED
  ::test_audit_version_tamper_rejected

AUDIT-ORPHAN-CHUNK-REJECTED
  ::test_audit_orphan_chunk_rejected

AUDIT-ORPHAN-EVIDENCE-REJECTED
  ::test_audit_orphan_evidence_rejected

AUDIT-RECEIPT-TAMPER-REJECTED
  ::test_audit_receipt_tamper_rejected

AUDIT-GLOBAL-DUPLICATE-REJECTED
  ::test_audit_global_duplicate_rejected

AUDIT-GLOBAL-CONFLICT-REJECTED
  ::test_audit_global_conflict_rejected

AUDIT-UNEXPECTED-ENTRY-REJECTED
  ::test_audit_unexpected_entry_rejected

AUDIT-STALE-STAGING-REJECTED
  ::test_audit_stale_staging_rejected
```

## 17.4 `tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py`

```text
REPLAY-SNAPSHOT-REQUIRED
  ::test_replay_snapshot_required_and_unaligned_snapshot_allowed

REPLAY-SNAPSHOT-ROW-RETURNED
  ::test_replay_returns_exact_instrument_snapshot_row

REPLAY-COMPLETE-TRADE-MARK
  ::test_replay_complete_trade_mark_grids

REPLAY-FUNDING-MARK-JOIN
  ::test_replay_funding_mark_join

REPLAY-MISSING-MARK-JOIN-REJECTED
  ::test_replay_missing_mark_join_rejected

COVERAGE-STRICT-INPUTS
  ::test_coverage_strict_inputs

COVERAGE-OUT-OF-WINDOW-REJECTED
  ::test_coverage_out_of_window_rejected

COVERAGE-GAP-WINDOWS
  ::test_coverage_gap_windows

RESUME-INCLUSIVE-1000
  ::test_resume_inclusive_1000

RESUME-MONTH-YEAR-LEAP
  ::test_resume_month_year_leap_boundaries

FUNDING-STRICT-TIMESTAMPS
  ::test_funding_strict_timestamps

DUCKDB-FOUR-VIEWS
  ::test_duckdb_four_views

DUCKDB-DECIMAL-TYPES
  ::test_duckdb_decimal_types

DUCKDB-CONNECTION-CLOSED
  ::test_duckdb_connection_closed_on_success_and_failure
```

## 17.5 `tests/test_sprint_06_4a_3_3_semantic_pack_cli.py`

```text
PACK-BUILDER-BAD-STORE-REJECTED
  ::test_pack_builder_rejects_bad_store

PACK-EXACT-MEMBER-SET
  ::test_pack_exact_member_set

PACK-EMPTY-MANIFEST-REJECTED
  ::test_pack_empty_manifest_rejected

PACK-REHASHED-FAKE-REJECTED
  ::test_pack_rehashed_fake_rejected

PACK-NESTED-EVIDENCE-VALIDATED
  ::test_pack_nested_public_evidence_validated

PACK-REPORT-TAMPER-REJECTED
  ::test_pack_report_tamper_rejected_after_rehash

PACK-TEMP-CLEANUP
  ::test_pack_temp_cleanup_on_failure

CLI-FULL-LIFECYCLE-BYBIT-HOST
  ::test_cli_full_lifecycle_bybit_host_offline

CLI-FULL-LIFECYCLE-BYTICK-HOST
  ::test_cli_full_lifecycle_bytick_host_offline
```

Every mapped node must call a relevant production function or real subprocess CLI, build a behavior-specific fixture/mutation, and assert an exact result. The governance JSON is traceability only.

# 18. Governance verifier

Keep the exact 61 behavior IDs and order.

The verifier must reject:

- missing mapped node;
- duplicate behavior ID;
- duplicate node ID;
- governance-only node;
- stale/deleted file reference;
- mapped node outside the exact five 06.4A.3.3 test modules, except the three governance tests;
- placeholder wording;
- behavior ID merely repeated as expected result;
- `CLI-FULL-LIFECYCLE-*` mapped to a help or missing-args test.

The exact command must pass:

```bash
python scripts/check_behavior_coverage_maps.py \
  --collect-command "python -m pytest --collect-only -q"
```

Expected JSON characteristics:

```text
ok = true
errors = []
docs/sprint_06_4a_3_required_behaviors.json count = 61
```

Add a normal pytest regression that executes the verifier against actual collected nodes. A plain schema/order test is insufficient.

# 19. Required direct tamper matrix

Create a deterministic test that reports and asserts every row below:

| Mutation | Required result |
|---|---|
| owner-shaped multi-symbol instrument snapshot | import succeeds |
| invalid scale-19 funding before absent root | error, root absent |
| duplicate incoming key | error, zero mutation |
| committed same-key different-row | `store_row_conflict`, zero mutation |
| writer early/mid/late injected failure | no residue |
| version changed | audit false and no-op import fails |
| receipt changed and canonicalized | audit false and no-op import fails |
| receipt chunk metadata changed | audit false and no-op import fails |
| receipt redirected to copied path | audit false and no-op import fails |
| evidence archive changed | audit false and no-op import fails |
| evidence reference changed | audit false and no-op import fails |
| orphan chunk | audit false and no-op import fails |
| orphan evidence | audit false and no-op import fails |
| unexpected root file | audit false and no-op import fails |
| stale staging | audit false and no-op import fails |
| duplicate committed row | audit false |
| conflicting committed row | audit false |
| accepted nonaligned snapshot server time | replay succeeds |
| missing mark at funding timestamp | replay fails |
| fake rehashed ZIP | checker fails |
| derived report changed and all hashes recalculated | checker fails |
| nested public evidence changed and all hashes recalculated | checker fails |
| builder failure after temp ZIP creation | temp removed |

# 20. Required offline subprocess lifecycle

Run the exact five CLI sequence twice, once per persisted host provenance:

```text
https://api.bybit.com
https://api.bytick.com
```

Sequence:

```text
synthetic public review-pack builder
→ import_bybit_public_review_pack_to_store.py
→ audit_bybit_public_parquet_store.py
→ plan_bybit_public_store_repairs.py
→ make_bybit_public_parquet_seed_review_pack.py
→ check_bybit_public_parquet_seed_review_pack.py
```

Assertions:

```text
no network
all success exit codes 0
all outputs one compact JSON line
store audit ok=true
receipt typed and 7 chunks
repair plan deterministic
portable pack semantic checker ok=true
host provenance survives inside nested public evidence
```

# 21. Required commands before reporting completion

Run from a clean environment:

```bash
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
ruff check .
python -m compileall -q src
python scripts/check_behavior_coverage_maps.py --collect-command "python -m pytest --collect-only -q"
python -m pytest tests/test_sprint_06_4a_3_3_governance_cli.py -q
python -m pytest tests/test_sprint_06_4a_3_3_schema_plan_writer.py -q
python -m pytest tests/test_sprint_06_4a_3_3_import_audit.py -q
python -m pytest tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py -q
python -m pytest tests/test_sprint_06_4a_3_3_semantic_pack_cli.py -q
python -m pytest tests/test_sprint_06_3a_*.py tests/test_sprint_06_3b_*.py -q
python -m pytest -q
git diff --check
python scripts/hash_source_tree.py --root .
```

Also run for each of the five scripts:

```text
--help
missing required arguments
```

# 22. Clean source archive

The final uploaded source ZIP must contain no:

```text
.env
API credentials
owner evidence
*.parquet
*.duckdb
*.pyc
__pycache__
.pytest_cache
.ruff_cache
.building
import receipts
portable packs
```

Compute the source ZIP SHA-256 **after final packaging**. Do not report a pre-packaging or prior-revision hash.

# 23. Definition of done

The sprint is complete only if every item is true:

```text
[ ] real production modules materially changed
[ ] accepted owner shape represented by deterministic synthetic fixture
[ ] multi-symbol instrument snapshot imports successfully
[ ] nonaligned snapshot server time replays successfully
[ ] preflight deterministic failures create zero target writes
[ ] caught transaction failures leave zero residue
[ ] valid import audit returns ok=true
[ ] expected synthetic import has exactly 7 chunks and 1 receipt
[ ] receipt is the last commit marker
[ ] verified no-op performs zero filesystem mutation
[ ] all no-op tamper cases fail
[ ] full graph audit rejects all orphan/tamper cases
[ ] strict typed parsers canonicalize raw JSON arrays through tuples
[ ] deep immutability regression passes
[ ] strict_cli MappingProxy dataclass regression passes
[ ] replay returns exact immutable model and joined funding observations
[ ] coverage/resume exact model and window contracts pass
[ ] DuckDB refuses invalid store and closes on all paths
[ ] portable pack builder derives exact owned member set
[ ] portable checker reconstructs and semantically validates store
[ ] fully rehashed fake/tampered packs fail
[ ] exact 61 behavior IDs point to existing real material nodes
[ ] coverage verifier passes with no errors
[ ] both offline host-provenance CLI lifecycles pass
[ ] numeric, pip, no-live, Ruff, compileall, git diff checks pass
[ ] full pytest passes
[ ] final archive is clean
[ ] final archive SHA is computed after packaging
```

# 24. Required Codex completion report — exact format

Return exactly these sections:

```text
1. SOURCE IDENTITY
   - git commit
   - clean source-tree SHA-256 and file count
   - final uploaded ZIP SHA-256 computed after packaging

2. PRODUCTION IMPLEMENTATION
   - each changed production file
   - exact invariant implemented
   - no placeholders confirmation

3. OWNER-SHAPE SYNTHETIC LIFECYCLE
   - instrument/trade/mark/funding row counts
   - snapshot_server_time_ms and proof it is nonaligned
   - partition/chunk counts
   - store audit result
   - replay result

4. TRANSACTION / NO-OP
   - zero-write preflight results
   - failure-seam cleanup results
   - receipt-last proof
   - before/after no-op inventory equality

5. TAMPER MATRIX
   - every mutation from Section 19
   - exact error/failure result

6. PORTABLE PACK
   - exact member count and names
   - two-build reproducibility result
   - fake/rehashed/report/nested-evidence tamper results

7. BEHAVIOR GOVERNANCE
   - exact verifier JSON
   - 61 IDs / 61 existing material nodes
   - stale node count = 0

8. CLI
   - five help results
   - five missing-args results
   - full bybit-host lifecycle JSON
   - full bytick-host lifecycle JSON

9. TESTS AND STATIC CHECKS
   - numeric environment
   - pip check
   - no-live audit
   - Ruff
   - compileall
   - git diff --check
   - each focused module result
   - upstream 06.3 contract result
   - full pytest count/result

10. SAFETY
   - no network performed
   - no real owner pack accessed
   - no private/live capability added
   - clean archive scan result
```

Do not claim completion if the behavior verifier, owner-shaped synthetic import, valid-store audit, semantic pack checker, or full suite was not actually executed.
