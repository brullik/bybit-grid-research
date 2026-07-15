# Sprint 06.4A.3.4 — Real Material Lifecycle and Semantic Store Evidence Closure

## 0. PM state and source pin

Repository:

```text
brullik/bybit-grid-research
```

Rejected reviewed commits:

```text
main merge commit: b7051a41014fe69e5cb67f65c4ed38ff96a12dec
implementation commit: 66a190da7f147002bad750576cd6f34743a5c02f
PR: #65
```

Sprint 06.3B public-response evidence remains accepted and frozen.

Sprint 06.4A.3.3 is rejected because:

1. all 61 mapped tests use a generic `_exercise(label)` dispatcher;
2. most labels execute only `canonical_json_bytes(StoreVersion(...))`;
3. the synthetic public fixture is not a valid canonical 18-member public review pack;
4. the portable seed checker is hash-only;
5. store audit is not a complete graph audit;
6. source review-pack loading reopens a mutable path after reading source bytes;
7. append/import transaction semantics for an existing store are not implemented.

Gate state:

```text
SPRINT 06.4A.3.3: REJECTED
SPRINT 06.4A.3.4: AUTHORIZED
OWNER OFFLINE SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK: CLOSED
PRIVATE API: CLOSED
LIVE EXECUTION: CLOSED
TELEGRAM: CLOSED
PARAMETER RESEARCH: CLOSED
```

## 1. Branch and delivery rules

Create a new branch:

```text
codex/sprint-06-4a-3-4-real-material-lifecycle
```

Do not merge the PR.

Open a draft PR against `main` after all required commands pass.

Do not rewrite or weaken accepted `src/bybit_grid/data/public_batch/*` contracts.

Do not add generated Parquet, ZIP, JSON evidence, DuckDB database, `.env`, API key, owner bundle, cache, `.pyc`, or `__pycache__` files to Git.

Do not use the real owner review pack in Codex. Build deterministic synthetic public evidence entirely in tests under `tmp_path`.

Do not make any network request in tests or implementation.

## 2. Frozen identifiers and safety values

Keep these constants:

```text
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
PUBLIC_REVIEW_PACK_SCHEMA = bybit_public_batch_review_pack_v1
SYNTHETIC_RUN_ID_BYBIT = synthetic_public_batch_064a34_bybit
SYNTHETIC_RUN_ID_BYTICK = synthetic_public_batch_064a34_bytick
SYMBOL = BTCUSDT
KLINE_ROW_COUNT = 1001
FUNDING_ROW_COUNT = 300
INSTRUMENT_ROW_COUNT = 721
PRIMARY_KLINE_LIMIT = 1000
ALTERNATE_KLINE_LIMIT = 251
PRIMARY_INSTRUMENT_LIMIT = 1000
ALTERNATE_INSTRUMENT_LIMIT = 200
PRIMARY_FUNDING_LIMIT = 200
ALTERNATE_FUNDING_TARGET = 100
APPROVED_BASE_URLS = (
  https://api.bybit.com,
  https://api.bytick.com,
)
```

All of the following remain false in every audit/report:

```text
historical_market_data_coverage_proven_bool
funding_coverage_proven_bool
delisted_history_complete_bool
point_in_time_instrument_metadata_complete_bool
risk_budget_proven_bool
native_equivalence_proven_bool
parameter_selection_authorized_bool
sufficient_for_parameter_selection_bool
live_authorized_bool
live_execution_present_bool
private_api_used_bool
contains_credentials
```

The only positive engineering guardrails allowed are:

```text
sufficient_for_parquet_storage_engineering_bool = true
sufficient_for_bulk_download_engineering_bool = true
sufficient_for_resume_gap_repair_engineering_bool = true
```

No guardrail may be written as an unconditional literal before the corresponding derivation succeeds.

# Part A — remove test padding and make governance truthful

## 3. Delete the generic dispatcher test architecture

Delete every duplicated `_exercise(label)` implementation from:

```text
tests/test_sprint_06_4a_3_3_governance_cli.py
tests/test_sprint_06_4a_3_3_schema_plan_writer.py
tests/test_sprint_06_4a_3_3_import_audit.py
tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py
tests/test_sprint_06_4a_3_3_semantic_pack_cli.py
```

Forbidden test patterns:

```text
_exercise(label)
dispatch_behavior(label)
run_behavior(label)
assert_behavior(label)
a switch based only on behavior-id prefix
a default branch that checks StoreVersion serialization
one helper that substitutes unrelated behavior for most IDs
manifest-only self-validation used as behavior evidence
```

Shared fixtures and narrow helpers are allowed, but each mapped test must directly call the production function or subprocess CLI named by its behavior.

Examples of allowed helpers:

```text
build_real_synthetic_public_pack(...)
import_synthetic_store(...)
snapshot_store_tree(...)
mutate_file_bytes(...)
rewrite_zip_member_and_rehash(...)
assert_cli_json_failure(...)
```

Examples of forbidden helpers:

```text
exercise_requirement(id)
run_material_case(id)
assert_contract(id)
```

## 4. Strengthen behavior-map verifier

Update:

```text
src/bybit_grid/common/pytest_coverage_map.py
scripts/check_behavior_coverage_maps.py
```

The verifier must continue checking exact 61 behavior IDs and collected node IDs.

Add source-AST checks for every mapped node:

1. resolve the exact source file and function name;
2. reject a mapped function that only calls one helper and performs no independent assertion;
3. reject calls to helper names matching:

```text
_exercise
dispatch_behavior
run_behavior
assert_behavior
material_contract
```

4. reject a mapped test whose AST body is identical to another mapped test after normalizing only line numbers and literal behavior IDs;
5. reject a test that does not contain either:
   - a direct call to a market-store production function, or
   - a `subprocess.run` call targeting one of the five frozen CLI scripts;
6. reject a mapped test that contains no assertion or no exact `pytest.raises(..., match=...)` contract;
7. reject generic manifest text such as:

```text
Production path exercises <test name>
The contract returns the asserted success or stable failure
```

The required-behavior JSON row schema becomes:

```json
{
  "behavior_id": "...",
  "nodeid": "tests/...::test_...",
  "production_symbols": ["fully.qualified.symbol"],
  "fixture": "specific fixture name and shape",
  "mutation": "specific material mutation",
  "expected": "specific exact return field or exact error string"
}
```

Required row keys are exact. `production_symbols` is a nonempty JSON array of unique strings.

The verifier must check that at least one listed production symbol appears as a direct call/reference in the mapped test AST.

## 5. Keep manifest as traceability, not proof

Update:

```text
docs/sprint_06_4a_3_required_behaviors.json
```

Keep the exact existing order and exact 61 behavior IDs. Do not add, remove, rename, reorder, or alias IDs.

No row may point to a governance-only manifest-schema test.

# Part B — build a real no-network public review-pack fixture

## 6. Replace the invalid three-member synthetic fixture

Replace:

```text
tests/helpers/synthetic_market_store_fixture.py
```

The current fixture writing only three members is forbidden.

Create a deterministic fixture through accepted public-batch production modules. Use an injected fake public transport/opener; do not call the internet.

The generated public review pack must contain exactly these 18 members in canonical order:

```text
public_batch_run_status.json
capture_plan.json
server_time.json
recorded_public_responses.jsonl
instrument_records.jsonl
instrument_universe_audit.json
trade_klines.jsonl
mark_klines.jsonl
funding_rates.jsonl
funding_observations.jsonl
request_page_audits.jsonl
public_batch_audit.json
cross_plan_reconciliation_audit.json
reproducibility_audit.json
capture_summary.json
public_batch_report.md
risk_budget_readiness_report.md
review_pack_manifest.json
```

The fixture must be accepted by the existing public `validate_review_pack()` without monkeypatching that validator.

## 7. Exact synthetic public dataset

Create two packs, differing only in approved host provenance and run ID:

```text
pack A: https://api.bybit.com
pack B: https://api.bytick.com
```

Each pack contains:

### Instruments

```text
721 unique normalized linear instruments
BTCUSDT appears exactly once
all symbols unique
617 or more replay-eligible USDT perpetual rows
primary instrument plan page count = 1
alternate instrument plan page sizes = 200, 200, 200, 121
primary/alternate normalized equality = true
```

### Trade and mark

```text
1001 ascending unique complete one-minute rows
same timestamps between trade and mark
primary page sizes = 1000, 1
alternate page sizes = 251, 251, 251, 248
primary/alternate normalized equality = true
all candles closed according to the recorded server-time cutoff
```

Choose the 1001-row window inside one UTC month for the full import lifecycle. A separate planner test covers kline month crossing.

### Funding

```text
300 ascending unique rows
rows span exactly four UTC months
primary backward plan has at least 2 nonempty pages plus documented terminal behavior
alternate plan has exactly 4 deterministic chunks where permitted by the public contract
primary/alternate normalized equality = true
at least 2 funding timestamps fall inside the 1001-minute replay window
both in-window funding timestamps have exact mark candle joins
funding_coverage_proven_bool = false
```

### Recorded responses

```text
all response IDs contiguous
all plan IDs frozen and known
all endpoints public /v5/market/*
all HTTP statuses 200
strict UTF-8 JSON bodies
SHA-256 valid
no credentials/private/account/order data
```

## 8. Synthetic fixture API

Expose test-only helpers:

```python
build_synthetic_public_review_pack(
    tmp_path: Path,
    *,
    base_url: Literal["https://api.bybit.com", "https://api.bytick.com"],
) -> SyntheticPublicPack
```

`SyntheticPublicPack` is a frozen test dataclass containing:

```text
path
bytes
sha256
run_id
base_url
symbol
server_time_ms
snapshot_server_time_ms
window_start_ms
window_end_ms
expected_instrument_count
expected_trade_count
expected_mark_count
expected_funding_count
expected_funding_observation_count
```

No test may replace public validation with monkeypatch success.

# Part C — immutable source loading and strict models

## 9. Eliminate source path TOCTOU

Refactor:

```text
src/bybit_grid/data/market_store/import_public_batch.py
```

Add:

```python
load_validated_public_replay_batch_from_review_pack_bytes(
    source_bytes: bytes,
    *,
    expected_run_id: str,
    expected_sha256: str | None = None,
) -> ValidatedPublicBatchEvidence
```

The path API must perform exactly one file read and delegate:

```python
source_bytes = path.read_bytes()
return load_validated_public_replay_batch_from_review_pack_bytes(...)
```

All validation and reconstruction must use only `source_bytes`.

Do not reopen the source path.

Use `io.BytesIO(source_bytes)` with a byte-backed reader or a fresh private temporary file whose bytes are written from `source_bytes` and deleted in `finally`. The semantic identity is the byte buffer, never the mutable path.

`ValidatedPublicBatchEvidence` becomes a frozen validated model with `__post_init__`:

```text
run_id: exact safe nonempty string
review_pack_sha256: lowercase 64-character SHA-256
batch: exact accepted public batch model type
reconstructed: deeply immutable mapping
source_bytes: exact nonempty bytes
```

Require:

```text
sha256(source_bytes) == review_pack_sha256
status == complete
public semantic validation ok
all private/live/parameter guardrails false
sufficient_for_parquet_storage_engineering_bool == true
```

## 10. Strict deep immutability

`freeze_immutable()` must validate mapping keys for both `dict` and `MappingProxyType` branches.

Allowed scalar types:

```text
None
exact str
exact int
exact bool
Decimal
Enum
```

Allowed containers:

```text
MappingProxyType with exact nonempty string keys
tuple
frozen validated dataclass
```

Rejected recursively:

```text
list
mutable dict remaining after conversion
float
bytes inside canonical model fields unless the field contract explicitly requires bytes
bytearray
Path
set/frozenset
unknown objects
mixed/empty mapping keys
```

Every public model accepting mappings must deep-freeze nested values and reject mutable nested lists.

## 11. Complete model invariants

Add or complete `__post_init__` for:

```text
CoverageInterval
MissingMinuteWindow
MinuteCoverageAudit
ReplayPairCoverageAudit
FundingObservedRangeAudit
MarketStoreAudit
StoreChunkInventoryRow
FundingReplayObservation
ReplaySlice
```

Required invariants:

### CoverageInterval / MissingMinuteWindow

```text
exact nonnegative int timestamps
minute alignment
start <= end
row_count > 0
row_count == (end - start) / 60000 + 1
```

### MinuteCoverageAudit

```text
safe symbol
aligned start/end
start <= end
exact tuple element types
present/missing intervals ordered, nonoverlapping and inside window
no duplicate timestamp aliases
complete_bool == (missing_windows == ())
historical coverage proven remains false
```

### ReplayPairCoverageAudit

```text
safe symbol
exact bool fields
replay_ready_bool == trade_complete and mark_complete and timestamp_sets_equal
```

### FundingObservedRangeAudit

```text
safe symbol
observed_count >= 0
None/None iff count == 0
min <= max for nonempty
exact aligned timestamps
unique sorted duplicate_timestamps
funding coverage remains false
```

### MarketStoreAudit

Add deterministic graph fields, at minimum:

```text
ok
failures
chunk_count
receipt_count
evidence_archive_count
evidence_reference_count
orphan_chunk_count
orphan_evidence_count
stale_transaction_count
dataset_row_counts immutable mapping
historical/funding/live false guardrails
```

`ok` must equal `not failures`.

# Part D — exact chunk semantics

## 12. One frozen dataset specification source

Create or consolidate a single `DatasetSpec` per dataset containing:

```text
dataset enum
Arrow schema
exact field names
primary-key field names
timestamp field
partition kind
Decimal fields
```

Use the same spec for:

```text
row field-set validation
row type validation
row key
partition key
logical canonical JSONL
Arrow table construction
Parquet read-back
path derivation
audit duplicate registry
DuckDB smoke key queries
```

Remove duplicated PK/field definitions that can diverge.

## 13. Planned chunk must be semantically self-validated in memory

`build_planned_chunk()` must:

1. validate exact dataset and exact row mappings;
2. reject empty input;
3. reject incoming duplicate keys;
4. require one snapshot timestamp for instrument snapshot;
5. allow multiple instrument symbols;
6. require one symbol and one UTC month for time-series chunks;
7. sort by primary key;
8. construct Arrow table using explicit schema;
9. construct Parquet bytes;
10. read those bytes back through `pa.BufferReader`;
11. validate exact schema, rows, key ordering and logical hash;
12. derive exact relative path from typed rows and logical hash;
13. build canonical manifest;
14. parse canonical manifest bytes through strict parser;
15. return immutable `PlannedChunk`.

No filesystem write is allowed in `build_planned_chunk()`.

## 14. Re-derive chunk path during every read

`read_and_validate_chunk()` must not trust the manifest path merely because it equals the actual directory.

After reading typed rows and logical hash, derive:

```text
expected_relative_path = rel_chunk_path(... rows ..., logical_hash)
```

Require:

```text
manifest.relative_path == actual_relative_path == expected_relative_path
```

Also require partition values in every row to match the actual path:

```text
instrument snapshot timestamp
symbol
UTC year
UTC month
min/max key
logical-hash prefix
```

A moved chunk with a rewritten canonical manifest must fail `chunk_path_semantic_mismatch`.

## 15. Unify existing-chunk validation

Delete or stop using weaker `_semantic_validate_chunk_dir()` paths.

Every reuse path must call only:

```python
read_and_validate_chunk(store_root, chunk_dir, expected_manifest=...)
```

This applies to:

```text
write_chunk_atomic existing path
build_planned_chunk reuse detection
transaction no-op
store audit
portable checker
```

# Part E — complete preflight and transaction

## 16. Pure preflight contract

`build_import_preflight_plan()` must perform zero filesystem mutation.

Before returning, prove:

```text
source bytes validated and detached
all projected rows validated
all partition plans built
all planned Parquet bytes semantically read back
all manifests canonical
all target paths safe
existing store fully audited if present
existing global PK registry built
incoming duplicates rejected
committed duplicate/conflict policy resolved
all reuse chunks fully validated
source evidence target derived
receipt target derived
receipt bytes canonical
```

Record in `ImportPreflightPlan`:

```text
validated evidence
store root
store-existed bool
exact preflight inventory
new planned chunks
reused manifests
new evidence archive bool
new evidence reference bool
receipt
canonical receipt bytes
canonical version bytes
canonical evidence-reference bytes
source archive bytes
ordered publish operations
```

No field may be a mutable list/dict.

## 17. Support both new-store and append transactions

Do not replace an existing store root with `os.replace(tmp, final)`.

Required object-level transaction:

### New store

```text
preflight with root absent
create sibling transaction root
stage and verify all new immutable objects
publish store_version atomically
publish chunk directories atomically
publish evidence directory atomically
publish receipt last atomically
remove transaction root
run final full audit
```

### Existing valid store, new disjoint import

```text
preflight exact existing graph
preserve all existing committed objects
stage only new objects
validate all reused objects
publish only new chunk/evidence objects atomically
publish new receipt last
never replace root
run final full audit
```

### Existing exact receipt

Run verified no-op sequence in Part F.

## 18. Exact controlled-failure cleanup

Expose test-only keyword:

```python
fail_at: Literal[
  "before_transaction_root",
  "after_transaction_root",
  "after_stage_chunks",
  "after_stage_evidence",
  "after_stage_reference",
  "after_stage_receipt",
  "after_publish_version",
  "after_publish_first_chunk",
  "after_publish_all_chunks",
  "after_publish_evidence",
  "before_publish_receipt",
  "after_publish_receipt",
] | None
```

The implementation must execute the named failure at the named boundary.

For all controlled failures before receipt publication:

```text
no receipt
no newly committed object remains
existing store inventory unchanged
transaction root removed
```

For `after_publish_receipt`, the import is committed and full audit must pass; returning an injected error after commit is forbidden. Instead return the committed receipt or use a separate crash-simulation test outside normal exception handling.

Do not make several labels point to the same phase.

## 19. Receipt-last rule

The receipt is the only commit marker.

A normal successful import must produce a deterministic publish trace ending exactly with:

```text
imports/run_id=<RUN_ID>/source_sha256=<SHA>/import_receipt.json
```

No canonical store audit may return `ok=true` for newly published chunks/evidence without a receipt.

# Part F — verified no-op

## 20. Exact no-op verification sequence

When the target receipt exists, perform these steps in order:

1. take full safe inventory snapshot A;
2. strict-parse canonical store version;
3. strict-parse canonical receipt;
4. require receipt bytes equal regenerated expected receipt bytes;
5. require receipt run ID and source SHA equal current validated evidence;
6. validate every receipt-referenced chunk through strict reader;
7. require actual chunk manifests equal receipt manifests;
8. validate exact evidence directory path;
9. require archived source bytes equal current immutable source bytes;
10. require archived SHA equals receipt SHA;
11. strict-parse exact evidence reference;
12. require evidence reference equals expected model/bytes;
13. run public semantic review-pack validation on archived bytes;
14. run complete store-graph audit;
15. reject unexpected, orphan or conflicting objects;
16. take full safe inventory snapshot B;
17. require inventory A == inventory B including path, type, size, hash and mtime;
18. return exact typed `StoreImportReceipt`.

A mutation to any referenced or unreferenced canonical object must fail.

# Part G — full store-graph audit

## 21. Exact allowed root graph

For a committed seed store, allowed root entries are exactly:

```text
store_version.json
datasets/
evidence/
imports/
```

`.building` or transaction directories are forbidden in a committed audit, even if empty.

Reject all unexpected top-level or nested files/directories, symlinks, junctions and non-regular entries.

## 22. Version and path grammar

Require exact canonical `store_version.json`.

Validate every path against frozen grammar:

```text
datasets/instrument_snapshot/snapshot_server_time_ms=<MS>/chunk=<HASH16>/...
datasets/<time_series>/symbol=<SYMBOL>/year=<YYYY>/month=<MM>/chunk=<MIN>-<MAX>-<HASH16>/...
evidence/sha256=<SHA>/review_pack.zip
evidence/sha256=<SHA>/evidence_reference.json
imports/run_id=<RUN_ID>/source_sha256=<SHA>/import_receipt.json
```

Receipt path components must equal the parsed receipt fields.

Evidence path component must equal parsed reference and archive SHA.

## 23. Chunk graph

For every chunk:

```text
strict read/semantic validation
row-derived path equality
global primary-key registry
no duplicate same rows across chunks
no conflicting same keys across chunks
exact dataset inventory
```

A seed store must contain nonempty committed rows for all four datasets:

```text
instrument_snapshot
trade_kline_1m
mark_kline_1m
funding_rate
```

## 24. Receipt/evidence ownership

Build exact sets:

```text
actual chunks
receipt-referenced chunks
actual evidence archives
actual evidence references
receipt-required evidence
actual receipts
```

Require:

```text
actual chunks == union(receipt chunks)
actual evidence archives == receipt-required archives
actual evidence references == receipt-required references
no chunk referenced by incompatible receipts
no receipt path mismatch
no orphan receipt/evidence/chunk
```

Each archived public pack must pass the accepted semantic public checker from its bytes.

## 25. Seed-specific audit

For each receipt/source pack:

1. reconstruct source public batch;
2. compare instrument/trade/mark/funding source rows with store rows carrying that source SHA;
3. compare logical hashes;
4. require exact row counts;
5. require replay-ready trade/mark window;
6. derive exact in-window funding observations;
7. run DuckDB smoke;
8. keep all completeness/risk/live guardrails false.

# Part H — replay, coverage, resume and DuckDB

## 26. Replay

`read_replay_slice()` must:

```text
require safe symbol
require aligned start/end
allow unaligned exact snapshot_server_time_ms
require exactly one instrument row for snapshot + symbol
return that exact instrument row
require complete trade grid
require complete mark grid
require exact timestamp equality
join each in-window funding event to exact mark timestamp
return FundingReplayObservation(funding_time_ms, funding_rate, mark_open)
reject missing/duplicate join
return deeply immutable ReplaySlice
```

## 27. Coverage/resume

All public coverage/resume functions require exact validated models and inputs.

Reject:

```text
bool/string/float timestamp aliases
negative timestamps
unaligned minute timestamps
start > end
out-of-window observed timestamp
unsafe symbol
duplicate observed timestamps where uniqueness is required
wrong audit model type
trade/mark symbol or window mismatch
```

Test exact inclusive splitting at 1000 rows.

Test month-end, year-end and leap-day boundaries.

## 28. DuckDB

`open_readonly_duckdb_views()` must first require full audit `ok=true`.

Create exactly four views in an in-memory database.

Run and return deterministic smoke audit containing:

```text
view names
row counts
min/max timestamps
duplicate primary-key counts
column logical types
all Decimal market columns are DECIMAL, never DOUBLE
source host provenance values
persistent_database_created_bool = false
network_extension_used_bool = false
```

Close connection on every failure and in the smoke helper after success.

# Part I — semantic portable seed review pack

## 29. Exact ZIP layout

Use this exact prefix layout:

```text
store/store_version.json
store/datasets/.../data.parquet
store/datasets/.../chunk_manifest.json
store/evidence/.../review_pack.zip
store/evidence/.../evidence_reference.json
store/imports/.../import_receipt.json
audits/store_audit.json
audits/round_trip_audit.json
audits/minute_replay_coverage_audit.json
audits/funding_observed_range_audit.json
audits/duckdb_smoke_audit.json
audits/reproducibility_audit.json
risk_guardrail_report.md
review_pack_manifest.json
```

Include only objects owned by validated receipts. Never recursively include arbitrary store files.

## 30. Seed manifest schema

Exact JSON schema:

```json
{
  "schema": "bybit_public_parquet_seed_review_pack_v1",
  "storage_schema_version": "bybit_public_parquet_store_v1",
  "run_ids": ["..."],
  "source_review_pack_sha256": ["..."],
  "members": ["ordered", "member", "names"],
  "member_sha256": {"member": "64-lowercase-hex"},
  "guardrails": {"exact": false}
}
```

Rules:

```text
exact key set
run_ids/source hashes exact nonempty sorted unique arrays
members exact ordered array
member_sha256 keys equal all non-manifest members
no manifest self-hash
canonical bytes
all guardrails exact
```

## 31. Required derived audits

Create strict frozen models and canonical bytes for:

```text
StoreRoundTripAudit
MinuteReplayCoverageAudit
FundingObservedRangeAudit
DuckDBSmokeAudit
StoreReproducibilityAudit
```

`round_trip_audit` must compare validated source typed rows with Parquet read-back rows.

`reproducibility_audit` must derive:

```text
derived build A member names/hashes
derived build B member names/hashes
exact equality booleans
verified no-op inventory equality
checker reconstruction equality
```

No success literal before comparison.

## 32. Builder lifecycle

```text
full source-store graph audit
build derived artifacts A
build derived artifacts B
compare exact bytes
assemble exact members in memory
write temporary ZIP in destination directory
run standalone semantic checker on temporary ZIP
atomic replace destination
remove temporary ZIP on every failure
```

Existing destination remains unchanged if any failure occurs.

## 33. Standalone checker lifecycle

```text
strict ZIP open
reject duplicate/unsafe/directory/nonregular members
strict canonical seed manifest parser
require exact derived + receipt-owned member set
verify SHA-256
extract under fresh temporary directory with containment checks
rebuild store tree from store/ prefix
run full store graph audit
run nested public semantic validation
run round-trip/replay/coverage/funding/DuckDB audits
regenerate derived audit/report bytes
compare exact bytes
remove temporary extraction on success and failure
return typed semantic result
```

The checker must reject a fully rehashed semantic fake.

# Part J — five CLIs

## 34. Frozen CLI interfaces

### Import

```text
python scripts/import_bybit_public_review_pack_to_store.py \
  --review-pack <path> \
  --store-root <path> \
  --expected-run-id <run_id> \
  [--expected-sha256 <sha>] \
  [--debug]
```

### Audit

```text
python scripts/audit_bybit_public_parquet_store.py \
  --store-root <path> \
  [--debug]
```

### Repair plan

```text
python scripts/plan_bybit_public_store_repairs.py \
  --store-root <path> \
  --symbol <symbol> \
  --start-ms <aligned-int> \
  --end-ms <aligned-int> \
  --dataset {trade_kline_1m,mark_kline_1m} \
  [--debug]
```

### Pack builder

```text
python scripts/make_bybit_public_parquet_seed_review_pack.py \
  --store-root <path> \
  --output <zip> \
  [--debug]
```

### Pack checker

```text
python scripts/check_bybit_public_parquet_seed_review_pack.py \
  --zip <zip> \
  [--debug]
```

Every CLI:

```text
performs no work at import
uses strict named arguments
emits exactly one compact JSON object and final newline
returns 0 only on semantic success
returns 1 on production/semantic failure
returns 2 on argparse failure
no traceback unless --debug
stderr empty for expected failures
no network
```

# Part K — exact 61 behavior tests

## 35. Required direct test mappings

Keep these exact node names. Implement the exact material setup, mutation and assertion listed below.

### Governance and CLI

1. `GOV-EXACT-ID-SET`  
   Node: `tests/test_sprint_06_4a_3_4_governance_cli.py::test_gov_exact_id_set`  
   Call `verify_required_behavior_json`; assert exact ordered 61 IDs and no error.

2. `GOV-MISSING-NODE`  
   Node: `...::test_gov_missing_node_rejected`  
   Create temporary manifest with one nonexistent node; assert exact `missing_node:` error.

3. `GOV-NOOP-REJECTED`  
   Node: `...::test_gov_noop_node_rejected`  
   Create a mapped test source containing generic `_exercise`; assert verifier exact `generic_dispatcher_node` error.

4. `CLI-HELP-ALL`  
   Node: `...::test_cli_help_all_five_scripts`  
   Subprocess all five scripts with `--help`; assert rc 0, no traceback.

5. `CLI-MISSING-ARGS-ALL`  
   Node: `...::test_cli_missing_args_all_five_scripts`  
   Subprocess all five without args; assert rc 2, one canonical JSON failure line, stderr empty.

### Decimal, planning and chunks

6. `DECIMAL-MAX-BOUNDARY` → `tests/test_sprint_06_4a_3_4_schema_plan_writer.py::test_decimal_max_boundary`  
   Exact max accepted and Arrow array construction succeeds.

7. `DECIMAL-MIN-BOUNDARY` → `...::test_decimal_min_boundary`  
   Exact min accepted.

8. `DECIMAL-ROUNDING-REJECTED` → `...::test_decimal_rounding_rejected`  
   Scale-19 nonzero digit fails exact `decimal_rounding_required`.

9. `PLAN-INSTRUMENT-SNAPSHOT` → `...::test_plan_instrument_snapshot_multi_symbol_single_partition`  
   721 unique symbols, one unaligned server snapshot timestamp → exactly one snapshot partition.

10. `PLAN-KLINE-CROSS-MONTH` → `...::test_plan_kline_cross_month_two_partitions`  
    Rows straddling UTC month → exact two ordered partitions with no loss/duplication.

11. `PLAN-FUNDING-FOUR-MONTHS` → `...::test_plan_funding_four_months_four_partitions`  
    300 rows over four months → exact four ordered partitions and total 300.

12. `PLAN-MULTI-SYMBOL-REJECTED` → `...::test_plan_entry_mixed_timeseries_symbols_rejected`  
    Direct one-chunk BTC+ETH time-series input → exact `mixed_symbols`.

13. `PREFLIGHT-INVALID-ROW-ZERO-WRITES` → `...::test_preflight_invalid_row_zero_writes`  
    Invalid Decimal/timestamp → root remains absent and inventory unchanged.

14. `PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES` → `...::test_preflight_incoming_duplicate_zero_writes`  
    Duplicate PK → exact error and zero writes.

15. `PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES` → `...::test_preflight_committed_conflict_zero_writes`  
    Valid existing store plus changed row same PK → exact `store_row_conflict`; inventory identical.

16. `CHUNK-EARLY-CLEANUP` → `...::test_chunk_early_failure_cleanup`  
    Inject before staging; no path changes.

17. `CHUNK-MID-CLEANUP` → `...::test_chunk_mid_failure_cleanup`  
    Inject after staged Parquet; transaction directory removed.

18. `CHUNK-LATE-CLEANUP` → `...::test_chunk_late_failure_cleanup`  
    Inject after staged manifest/read-back but before publish; no committed chunk.

19. `CHUNK-CANONICAL-MANIFEST` → `...::test_chunk_manifest_is_canonical`  
    Parse exact bytes, mutate whitespace/key order and assert canonical rejection.

20. `CHUNK-ACTUAL-PATH-MATCH` → `...::test_chunk_actual_path_mismatch_rejected`  
    Move chunk and rewrite manifest relative path; strict reader rejects row-derived path mismatch.

21. `CHUNK-PK-SCHEMA-MATCH` → `...::test_chunk_primary_key_schema_mismatch_rejected`  
    Rehash canonical manifest with wrong PK columns; strict reader rejects exact error.

22. `CHUNK-EXISTING-CORRUPTION-REJECTED` → `...::test_existing_chunk_corruption_rejected`  
    Corrupt data.parquet then attempt reuse; exact SHA/semantic error.

### Import and audit

23. `IMPORT-SYNTHETIC-REAL-SHAPE` → `tests/test_sprint_06_4a_3_4_import_audit.py::test_import_synthetic_owner_shape_succeeds`  
    Real 18-member synthetic pack → 721/1001/1001/300 rows, 7 chunks, full audit true.

24. `IMPORT-SOURCE-BYTES-IMMUTABLE` → `...::test_import_archives_identical_source_bytes`  
    Load evidence; replace/delete source path; import archives original immutable bytes.

25. `IMPORT-RECEIPT-LAST` → `...::test_import_receipt_is_last_commit_marker`  
    Assert publish trace final item is exact receipt; pre-receipt failure leaves no committed objects.

26. `IMPORT-NOOP-TYPED` → `...::test_reimport_returns_typed_receipt`  
    Second import returns exact typed receipt with tuple manifests.

27. `IMPORT-NOOP-ZERO-MUTATION` → `...::test_reimport_zero_filesystem_mutation`  
    Full inventory including mtimes identical before/after.

28. `IMPORT-NOOP-CORRUPT-CHUNK-REJECTED` → `...::test_reimport_corrupt_chunk_rejected`  
    Corrupt referenced Parquet; second import fails.

29. `IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED` → `...::test_reimport_corrupt_evidence_rejected`  
    Corrupt archive/reference/nested pack; second import fails.

30. `AUDIT-EMPTY-REJECTED` → `...::test_audit_empty_store_rejected`  
    Missing/version-only stores are not ok.

31. `AUDIT-VERSION-TAMPER-REJECTED` → `...::test_audit_version_tamper_rejected`  
    Canonical and noncanonical version tamper cases fail.

32. `AUDIT-ORPHAN-CHUNK-REJECTED` → `...::test_audit_orphan_chunk_rejected`  
    Copy valid chunk not referenced by receipt; fail exact orphan.

33. `AUDIT-ORPHAN-EVIDENCE-REJECTED` → `...::test_audit_orphan_evidence_rejected`  
    Extra evidence SHA directory; fail.

34. `AUDIT-RECEIPT-TAMPER-REJECTED` → `...::test_audit_receipt_tamper_rejected`  
    Rehashed canonical receipt semantic tamper; fail.

35. `AUDIT-GLOBAL-DUPLICATE-REJECTED` → `...::test_audit_global_duplicate_rejected`  
    Two chunks with identical PK+row; fail duplicate.

36. `AUDIT-GLOBAL-CONFLICT-REJECTED` → `...::test_audit_global_conflict_rejected`  
    Same PK different row; fail conflict.

37. `AUDIT-UNEXPECTED-ENTRY-REJECTED` → `...::test_audit_unexpected_entry_rejected`  
    Test top-level and nested unexpected regular files/directories.

38. `AUDIT-STALE-STAGING-REJECTED` → `...::test_audit_stale_staging_rejected`  
    Empty and nonempty transaction/staging roots are rejected in committed store.

### Replay, coverage, resume and DuckDB

39. `REPLAY-SNAPSHOT-REQUIRED` → `tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py::test_replay_snapshot_required_and_unaligned_snapshot_allowed`  
    Unaligned exact snapshot accepted; missing/wrong snapshot rejected.

40. `REPLAY-SNAPSHOT-ROW-RETURNED` → `...::test_replay_returns_exact_instrument_snapshot_row`  
    Returned row equals requested symbol+snapshot row.

41. `REPLAY-COMPLETE-TRADE-MARK` → `...::test_replay_complete_trade_mark_grids`  
    Exact 1001 grids; remove one boundary from each side and reject.

42. `REPLAY-FUNDING-MARK-JOIN` → `...::test_replay_funding_mark_join`  
    Exact observations with `mark_open` values.

43. `REPLAY-MISSING-MARK-JOIN-REJECTED` → `...::test_replay_missing_mark_join_rejected`  
    Funding timestamp without mark row rejects.

44. `COVERAGE-STRICT-INPUTS` → `...::test_coverage_strict_inputs`  
    Parameterize bool/string/float/negative/unaligned/reversed/unsafe inputs with exact errors.

45. `COVERAGE-OUT-OF-WINDOW-REJECTED` → `...::test_coverage_out_of_window_rejected`  
    First and last out-of-window observed timestamps reject.

46. `COVERAGE-GAP-WINDOWS` → `...::test_coverage_gap_windows`  
    First/middle/last/disjoint/coalesced gaps exact.

47. `RESUME-INCLUSIVE-1000` → `...::test_resume_inclusive_1000`  
    2001 missing rows split 1000/1000/1 with exact boundaries.

48. `RESUME-MONTH-YEAR-LEAP` → `...::test_resume_month_year_leap_boundaries`  
    Month, year and leap-day boundaries exact.

49. `FUNDING-STRICT-TIMESTAMPS` → `...::test_funding_strict_timestamps`  
    Reject bool/string/float/negative/unaligned; report exact duplicates/range.

50. `DUCKDB-FOUR-VIEWS` → `...::test_duckdb_four_views`  
    Full valid store only, exact view names and row counts.

51. `DUCKDB-DECIMAL-TYPES` → `...::test_duckdb_decimal_types`  
    Every market numeric column is DECIMAL, none DOUBLE.

52. `DUCKDB-CONNECTION-CLOSED` → `...::test_duckdb_connection_closed_on_success_and_failure`  
    Instrument connection close via wrapper/probe for success and injected failure.

### Portable pack and full CLI lifecycle

53. `PACK-BUILDER-BAD-STORE-REJECTED` → `tests/test_sprint_06_4a_3_4_semantic_pack_cli.py::test_pack_builder_rejects_bad_store`  
    Empty/tampered/orphan stores rejected; no output/temp residue.

54. `PACK-EXACT-MEMBER-SET` → `...::test_pack_exact_member_set`  
    Exact store-owned + derived member set and order.

55. `PACK-EMPTY-MANIFEST-REJECTED` → `...::test_pack_empty_manifest_rejected`  
    Empty manifest rejected.

56. `PACK-REHASHED-FAKE-REJECTED` → `...::test_pack_rehashed_fake_rejected`  
    Fully rehashed fabricated store/report pack rejected semantically.

57. `PACK-NESTED-EVIDENCE-VALIDATED` → `...::test_pack_nested_public_evidence_validated`  
    Rehashed nested public pack tamper rejected by public semantic checker.

58. `PACK-REPORT-TAMPER-REJECTED` → `...::test_pack_report_tamper_rejected_after_rehash`  
    Change derived audit/report and manifest hash; checker rebuild mismatch.

59. `PACK-TEMP-CLEANUP` → `...::test_pack_temp_cleanup_on_failure`  
    Builder and checker remove temporary ZIP/extraction and preserve existing destination.

60. `CLI-FULL-LIFECYCLE-BYBIT-HOST` → `...::test_cli_full_lifecycle_bybit_host_offline`  
    Five subprocess CLIs with real synthetic `api.bybit.com` pack.

61. `CLI-FULL-LIFECYCLE-BYTICK-HOST` → `...::test_cli_full_lifecycle_bytick_host_offline`  
    Same for `api.bytick.com`.

# Part L — required regression attacks beyond the 61 map

## 36. Additional mandatory tests

Add explicit tests for:

```text
source path replaced between initial read and validation
receipt file placed under wrong run_id/sha path
extra evidence directory while another receipt exists
extra nested file under datasets/imports/evidence
valid chunk moved to wrong symbol/year/month with rewritten manifest
store containing only version
store containing one dataset and otherwise valid receipt/evidence
append second disjoint validated pack to existing store
existing store append preserves old receipt/evidence/chunks
controlled failure during append restores old inventory
same chunk referenced by incompatible receipts
parent-directory symlink/junction below datasets
strict seed-manifest duplicate key/float/noncanonical bytes
```

# Part M — required commands

## 37. Environment and static checks

Run:

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m compileall -q src tests scripts
ruff check .
git diff --check
```

## 38. Governance

Run:

```text
python scripts/check_behavior_coverage_maps.py \
  --collect-command "python -m pytest --collect-only -q"
```

Required output:

```json
{
  "ok": true,
  "required_064a3_count": 61,
  "mapped_material_nodes": 61,
  "generic_dispatcher_nodes": 0,
  "duplicate_normalized_test_bodies": 0,
  "errors": []
}
```

## 39. Focused tests

Run each:

```text
python -m pytest tests/test_sprint_06_4a_3_4_governance_cli.py -q
python -m pytest tests/test_sprint_06_4a_3_4_schema_plan_writer.py -q
python -m pytest tests/test_sprint_06_4a_3_4_import_audit.py -q
python -m pytest tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py -q
python -m pytest tests/test_sprint_06_4a_3_4_semantic_pack_cli.py -q
```

## 40. Upstream regressions

Run all accepted public-batch tests:

```text
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_persisted_public_batch_evidence.py -q
python -m pytest tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_2_true_semantic_closure.py -q
python -m pytest tests/test_sprint_06_3b_3_owner_lifecycle_executability.py -q
python -m pytest tests/test_sprint_06_3b_3_1_evidence_truthfulness.py -q
python -m pytest tests/test_sprint_06_3b_3_2_reproducibility_and_lifecycle.py -q
```

## 41. Full suite

```text
python -m pytest -q
```

No skipped behavior test is accepted. Platform-capability skips outside the mapped 61 must be listed explicitly.

## 42. Source identity

After all edits and tests:

```text
python scripts/hash_source_tree.py --root .
git rev-parse HEAD
git status --short
git diff --stat main...HEAD
git diff --check
```

Create source ZIP only after the final commit. Compute SHA-256 after packaging.

# Part N — Codex return format

## 43. Required final text report

Return exactly these sections:

```text
1. branch name
2. commit SHA
3. changed files
4. git diff --stat
5. source-tree SHA-256
6. final packaged source ZIP SHA-256
7. numeric environment output
8. pip check output
9. no-live output
10. compileall output
11. Ruff output
12. git diff --check output
13. behavior verifier complete JSON
14. pytest collection count
15. five focused test outputs
16. accepted public-batch regression outputs
17. full pytest output
18. synthetic public-pack exact member/count summary
19. new-store transaction trace
20. append transaction trace
21. verified no-op inventory A/B result
22. full store-audit attack matrix
23. replay/coverage/resume results
24. DuckDB smoke result
25. semantic seed-pack attack matrix
26. exact 61 behavior ID → node mapping
27. all guardrail values
28. known remaining limitations
```

Do not claim a behavior is implemented unless the mapped test directly executes it.

# Definition of Done

Sprint 06.4A.3.4 passes only if all are true:

```text
no generic behavior dispatcher remains in mapped tests;
all 61 behavior IDs map to distinct material production/CLI tests;
real canonical 18-member synthetic public packs exist for both approved hosts;
loader validates/reconstructs only one immutable byte buffer;
new-store import succeeds with 721/1001/1001/300 source shape;
append disjoint import preserves existing committed store;
preflight is zero-write;
receipt is the last commit marker;
controlled failures clean every newly published object before receipt;
verified no-op performs the exact full validation sequence and zero mutation;
chunk path is rederived from rows/hash;
full store audit rejects version-only, partial, orphan, moved, conflicting and tampered stores;
nested public review pack is semantically validated;
replay returns exact snapshot and funding mark-open observations;
coverage/resume are strict and deterministic;
DuckDB runs only on full audit-valid store and preserves DECIMAL;
portable seed checker reconstructs semantics and rejects fully rehashed fakes;
all upstream tests, focused tests and full suite pass;
no network/private/live capability is added;
no generated artifacts are committed.
```

## Owner action

No owner/local action is authorized during this sprint.

Do not generate a PowerShell owner script.

PM will review the unmerged draft PR and independently attack the implementation. Only a later explicit PM acceptance may authorize offline owner seed import.

