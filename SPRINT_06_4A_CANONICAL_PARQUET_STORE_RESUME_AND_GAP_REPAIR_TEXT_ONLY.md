# Sprint 06.4A — Canonical Parquet Store, Atomic Import, Resume and Gap-Repair Planning

## PM authorization

Sprint 06.3B is accepted and closed after a real owner-side public-only canonical capture.

Accepted immutable identities:

```text
RUN_ID = bybit_public_batch_063b_btcusdt_v1
OWNER_BUNDLE_SHA256 = 0858bcad00e9ba2a57b6da1cba472cac0cd938c334b795eea0ebc4cf42a9875f
PUBLIC_REVIEW_PACK_SHA256 = 20b2a62cd72ac0bd1e27baf852eccb7c481a826ec1ebcf37073a9ebfacea419a
REVIEWED_SOURCE_ZIP_SHA256 = e02d8812a2c499143b73fb6987f50a85975c3d9017161aead3e342207f09a7bb
PUBLIC_STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

The accepted real pack contains 721 instruments, 1001 BTCUSDT trade candles, 1001 matching mark candles, 300 funding rows and 25 persisted public responses. It is suitable for Parquet storage engineering only.

Codex must not receive, commit or embed the real ZIP. Tests must construct deterministic synthetic evidence in `tmp_path` and use the same public-batch semantic APIs.

## Sprint objective

Build a lossless, fail-closed, query-efficient local market-data store that can:

1. accept only a semantically validated public review pack or an already validated `BybitPublicReplayBatch`;
2. persist instruments, trade 1m, mark 1m and funding rows in versioned Parquet chunks;
3. preserve exact provenance through canonical manifests and logical row hashes;
4. publish chunks and import receipts atomically and idempotently;
5. read rows back with exact semantic Decimal equality and frozen types;
6. detect duplicate/conflicting keys, missing 1m candles and incomplete replay pairs;
7. plan bounded resume/gap-repair windows without making a network call;
8. expose read-only DuckDB views over the store;
9. build and independently check a portable seed-store review pack.

This is not a bulk historical download sprint.

## Frozen rules — do not change

Do not change accepted behavior in:

```text
src/bybit_grid/data/public_batch/*
neutral-grid geometry/accounting
OHLC/OLHC minimal path semantics
funding-before-price ordering
termination semantics
outcome/scoring formulas
range detection
```

A narrowly required public-batch read API may be added, but existing accepted evidence bytes and checker behavior must remain unchanged.

## Safety guardrails

- No real network calls in Codex or pytest.
- No private Bybit endpoints.
- No API key, secret, account, wallet, order, position or native grid call.
- No Telegram.
- No bulk download.
- No parameter search or selection.
- No PnL, ROI, EV, profitability or live-readiness claim.
- No generated Parquet, ZIP, JSON evidence, SQLite or DuckDB database committed to Git.
- Temporary generated files are allowed only under pytest `tmp_path`.
- Parquet is the durable data source; DuckDB is a read/query engine, not the canonical source.
- PostgreSQL and live-state SQLite remain out of scope.

Required false guardrails after this sprint:

```text
historical_market_data_coverage_proven_bool = false
funding_coverage_proven_bool = false
delisted_history_complete_bool = false
point_in_time_instrument_metadata_complete_bool = false
risk_budget_proven_bool = false
native_equivalence_proven_bool = false
parameter_selection_authorized_bool = false
sufficient_for_parameter_selection_bool = false
live_authorized_bool = false
live_execution_present_bool = false
```

A successful seed import may set only:

```text
sufficient_for_bulk_download_engineering_bool = true
sufficient_for_resume_gap_repair_engineering_bool = true
```

## Task 0 — Close governance and provenance debt

### 0.1 Exact Sprint 06.3B coverage map

Update:

```text
docs/sprint_06_3b_3_2_behavior_coverage.md
```

Every one of the 72 behavior rows must identify:

```text
exact pytest node id;
exact fixture or setup;
material mutation/failure injected;
exact expected error or success assertion.
```

Forbidden placeholders:

```text
focused sprint tests
corresponding named behavior test
equivalent coverage
covered elsewhere
```

If multiple behavior rows use one parameterized test, identify the exact parameter ID for each row.

### 0.2 Deterministic source-tree identity

Add an import-safe source-tree manifest utility and CLI, for example:

```text
src/bybit_grid/common/source_tree.py
scripts/hash_source_tree.py
```

Contract:

- scan only frozen deterministic source roots and root project text files;
- include `.py`, `.md`, `.toml`, `.yml`, `.yaml`, `.json.example`, `.gitignore` where applicable;
- exclude `.git`, `.venv`, data, reports, logs, caches, generated evidence and owner scripts unless explicitly selected;
- normalize text line endings to LF and UTF-8;
- reject duplicate/unsafe paths, symlinks and non-regular entries;
- emit canonical JSON containing every relative path and normalized-text SHA-256;
- derive a single tree SHA-256 from the canonical manifest bytes;
- no wall-clock field in canonical output;
- import makes no filesystem scan.

Future owner scripts will record this tree hash instead of relying only on a small critical-file list.

### 0.3 Project board

Replace the stale Sprint 01-only `PROJECT_BOARD.md` with:

```text
Accepted history: Sprints 01 through 06.3B
Now: Sprint 06.4A
Next: 06.4B owner seed import
Later: bounded historical downloader, data coverage gate, parameter research
Closed: private/live/Telegram
```

Do not delete historical milestones; move them to a concise accepted-history section.

## Task 1 — Versioned storage contract document

Create:

```text
docs/bybit_public_parquet_store_contract_v1.md
```

Document exactly:

- datasets and Arrow schemas;
- physical directory layout;
- partition and chunk naming;
- logical row canonicalization and SHA-256 policy;
- Decimal precision/scale policy;
- immutable chunk semantics;
- staging, atomic publication and commit-receipt semantics;
- idempotent re-import;
- duplicate and conflicting-overlap policy;
- store scan and orphan policy;
- 1m coverage and gap planning;
- funding limitations;
- instrument-snapshot limitations;
- DuckDB view contract;
- portable seed-store review-pack contract;
- all frozen guardrails.

Required statement:

```text
Parquet file bytes are not claimed to be canonical across PyArrow/platform versions.
Canonical identity is the logical row hash plus strict schema, manifest and semantic read-back.
```

## Task 2 — New package

Create:

```text
src/bybit_grid/data/market_store/
  __init__.py
  models.py
  schemas.py
  canonical.py
  paths.py
  writer.py
  reader.py
  import_public_batch.py
  coverage.py
  resume.py
  duckdb_views.py
  audit.py
  evidence.py
```

All modules must be import-safe. No import may read files, open DuckDB or create directories.

## Task 3 — Strict immutable models

Use frozen dataclasses and exact enums. Reject bool-as-int, floats, empty strings, unsafe symbols/paths and unknown enum values.

Minimum models:

```text
MarketDatasetKind
StoreChunkManifest
StoreImportReceipt
StoreChunkInventoryRow
CoverageInterval
MissingMinuteWindow
MinuteCoverageAudit
ReplayPairCoverageAudit
FundingObservedRangeAudit
MarketStoreAudit
StoreRoundTripAudit
StoreReproducibilityAudit
```

Datasets:

```text
instrument_snapshot
trade_kline_1m
mark_kline_1m
funding_rate
```

Primary keys:

```text
instrument_snapshot: (snapshot_server_time_ms, symbol)
trade_kline_1m: (symbol, open_time_ms)
mark_kline_1m: (symbol, open_time_ms)
funding_rate: (symbol, funding_time_ms)
```

## Task 4 — Exact Arrow/Parquet schemas

Define explicit `pyarrow.Schema` objects. Never infer production schemas from Python dictionaries or Polars.

Use:

```text
integer millisecond times: int64
booleans: bool
text/provenance/enums: non-null UTF-8 string
all numeric market values: decimal128(38, 18)
```

Decimal fields:

```text
instrument: tick_size, qty_step, min_order_qty, min_notional_value,
            min_leverage, max_leverage, leverage_step
trade: open, high, low, close, volume, turnover
mark: open, high, low, close
funding: funding_rate
```

Before writing, fail closed if a Decimal cannot be represented exactly as `decimal128(38,18)` without rounding or overflow. Never convert through float.

Required common provenance columns:

```text
source_run_id
source_review_pack_sha256
source_plan_id
source_name
storage_schema_version
```

Parquet writer settings are frozen:

```text
compression = zstd
compression_level = 6
use_dictionary = true for strings
write_statistics = true
row_group_size = 131072
```

Do not treat resulting Parquet bytes as cross-platform canonical identity.

## Task 5 — Canonical logical row identity

Implement a separate storage logical canonicalizer.

Rules:

- deterministic dataset-specific row projection;
- exact sorted row order by primary key;
- exact non-empty string mapping keys;
- no float, bytes, Path, set or unknown object;
- integers are exact non-bool integers;
- Decimal is rendered as a plain non-exponent normalized semantic string;
- trailing fractional zeroes are removed;
- `-0` canonicalizes to `0`;
- no lossy quantization;
- canonical UTF-8 compact sorted-key JSONL with final newline;
- SHA-256 of canonical logical JSONL is `logical_rows_sha256`.

The same typed rows must produce the same logical hash before write and after Parquet read-back.

## Task 6 — Physical layout and immutable atomic chunks

Frozen layout:

```text
<store_root>/
  store_version.json
  evidence/
    sha256=<review_pack_sha256>/
      review_pack.zip
      evidence_reference.json
  datasets/
    instrument_snapshot/
      snapshot_server_time_ms=<MS>/
        chunk=<logical_hash_prefix>/
          data.parquet
          chunk_manifest.json
    trade_kline_1m/
      symbol=<SYMBOL>/year=<YYYY>/month=<MM>/
        chunk=<min_ms>-<max_ms>-<logical_hash_prefix>/
          data.parquet
          chunk_manifest.json
    mark_kline_1m/
      symbol=<SYMBOL>/year=<YYYY>/month=<MM>/
        chunk=<min_ms>-<max_ms>-<logical_hash_prefix>/
          data.parquet
          chunk_manifest.json
    funding_rate/
      symbol=<SYMBOL>/year=<YYYY>/month=<MM>/
        chunk=<min_ms>-<max_ms>-<logical_hash_prefix>/
          data.parquet
          chunk_manifest.json
  imports/
    run_id=<RUN_ID>/source_sha256=<PACK_SHA>/
      import_receipt.json
  .building/
```

Path components must be generated by code, never trusted from arbitrary user text. Use POSIX relative names inside portable packs and native paths on disk.

Publication rules:

1. validate all input before writing;
2. write under a unique sibling `.building` tree;
3. write Parquet and canonical manifest;
4. read Parquet back and revalidate schema, row count, keys and logical hash;
5. publish each immutable chunk directory with an atomic same-volume rename;
6. archive and hash the exact source review pack;
7. write the canonical import receipt last as the commit marker;
8. on failure, remove staging and never publish a receipt;
9. a retry may reuse already-published byte/manifest-identical chunks;
10. an existing path with different bytes or semantics fails closed.

No overwrite of committed immutable chunks.

## Task 7 — Validated public-pack loader and importer

Expose a public, no-network API that semantically validates a review pack and returns its reconstructed typed batch plus frozen metadata. Do not weaken `validate_review_pack()`.

Example:

```python
load_validated_public_replay_batch_from_review_pack(
    path: Path,
    *,
    expected_run_id: str,
    expected_sha256: str | None = None,
) -> ValidatedPublicBatchEvidence
```

Requirements:

- calculate the pack SHA-256 from bytes;
- run the existing semantic persisted-input-first validator;
- reconstruct from `recorded_public_responses.jsonl` and `capture_plan.json`;
- require `status=complete`;
- require all private/live/parameter guardrails false;
- require `sufficient_for_parquet_storage_engineering_bool=true`;
- return detached immutable models;
- no network.

Implement:

```python
import_validated_public_batch_to_store(...)
```

The importer must persist:

```text
all 721 instrument rows from the accepted shape;
primary trade rows;
primary mark rows;
primary normalized funding rows;
source pack archive/reference;
chunk manifests;
final import receipt.
```

Do not persist funding observations as an independent source dataset; reconstruct them from funding plus mark rows for audits.

A second identical import must be a verified no-op with no new chunk, no modified mtime requirement and the same canonical receipt bytes.

## Task 8 — Overlap, duplicate and conflict policy

When importing rows into an existing store:

- exact same source pack already committed: verified no-op;
- existing identical primary-key row: reuse, do not write a duplicate;
- new non-overlapping key: write it;
- same primary key with any different semantic field: fail `store_row_conflict`;
- duplicate key inside incoming rows: fail;
- duplicate key across committed chunks: store audit fails;
- overlapping time ranges are allowed only when actual primary-key sets are disjoint;
- symlink/junction/non-regular entry anywhere under canonical store roots fails audit.

The importer must not silently choose one row over another.

## Task 9 — Reader and semantic round-trip

Implement typed readers for each dataset and a replay-ready slice reader.

Required behavior:

- select by exact symbol and inclusive time range;
- read only required Parquet columns/partitions;
- verify strict schema and manifest before exposing rows;
- return deterministic ascending immutable tuples;
- reconstruct exact semantic Decimal values;
- reject duplicate/conflicting keys;
- preserve source provenance;
- derive funding observations by joining the funding minute to mark candle `open`;
- require complete trade and mark 1m coverage and exact timestamp equality for a replay-ready slice;
- require the caller to select an explicit instrument snapshot; do not infer historical point-in-time metadata.

The seed round-trip audit must prove semantic equality between the validated public batch rows and rows read back from Parquet.

## Task 10 — Coverage, resume and gap-repair planner

Implement pure planning APIs with no networking:

```python
scan_minute_coverage(...)
plan_missing_minute_windows(..., max_rows=1000)
plan_trade_mark_repairs(..., max_rows=1000)
scan_funding_observed_range(...)
```

Minute coverage rules:

- exact inclusive minute grid;
- sorted unique timestamps;
- derive maximal contiguous present intervals;
- derive maximal contiguous missing intervals;
- split request windows so each has at most `max_rows` inclusive rows;
- preserve exact boundaries without overlap or omission;
- support month/year boundaries;
- reject bool/float/string aliases for integer limits/timestamps;
- trade and mark readiness requires both complete and exact timestamp equality.

Funding rules:

- report observed min/max/count/duplicates;
- do not infer missing funding events from a globally fixed interval;
- do not set `funding_coverage_proven_bool=true`;
- the current instrument funding interval may be recorded as context only.

Required seed result:

```text
trade missing windows: []
mark missing windows: []
trade/mark replay-ready: true
funding observed rows: 300 in the accepted real pack shape
historical coverage proven: false
```

## Task 11 — Read-only DuckDB views

Add an import-safe helper that opens an in-memory DuckDB connection only when called and registers read-only views over `**/data.parquet` using Hive partition discovery and `union_by_name=true`.

Views:

```text
bybit_instrument_snapshots
bybit_trade_kline_1m
bybit_mark_kline_1m
bybit_funding_rates
```

Requirements:

- no persistent `.duckdb` file by default;
- no write statements;
- no network extensions;
- exact row-count/min/max/duplicate smoke queries;
- Decimal remains DuckDB DECIMAL, not DOUBLE;
- empty store produces a named fail-closed error rather than an invalid broad glob.

## Task 12 — Store audit

Implement a full audit that scans the committed store, not only the import receipt.

It must verify:

- exact `store_version.json` schema;
- safe regular paths only;
- no unexpected files/directories under canonical roots;
- every chunk has exactly `data.parquet` and `chunk_manifest.json`;
- exact Arrow schema;
- file SHA-256 matches manifest;
- logical row hash matches read-back rows;
- primary keys and row ordering;
- no duplicate/conflicting keys across chunks;
- receipt references existing exact chunks and source evidence;
- archived source review pack hash and semantic validation;
- no committed receipt references staging;
- orphan chunks/staging are reported explicitly;
- replay-pair coverage for the seed window;
- all guardrails.

A successful audit must not claim full historical/funding/metadata completeness.

## Task 13 — Portable seed-store review pack

Add:

```text
scripts/import_bybit_public_review_pack_to_store.py
scripts/audit_bybit_public_parquet_store.py
scripts/plan_bybit_public_store_repairs.py
scripts/make_bybit_public_parquet_seed_review_pack.py
scripts/check_bybit_public_parquet_seed_review_pack.py
```

All CLIs:

- import-safe;
- strict argparse;
- compact canonical JSON success/failure on stdout;
- non-zero exit on failure;
- no traceback by default;
- optional `--debug` may show traceback;
- no network.

The portable seed review pack must contain a safe relative copy of:

```text
store_version.json
archived accepted/synthetic public review pack
all committed seed Parquet chunks and chunk manifests
import receipt
store audit
round-trip audit
coverage audit
DuckDB smoke audit
reproducibility audit
risk/guardrail report
review-pack manifest with SHA-256 for every non-manifest member
```

Nested paths are allowed only as normalized POSIX relative paths. Reject absolute paths, `..`, backslashes, drive letters, duplicate names, symlinks and non-regular entries.

The standalone checker must:

1. validate member names and hashes;
2. extract only into a fresh temporary directory;
3. semantic-check the archived public review pack;
4. run the full store audit from Parquet bytes;
5. rerun round-trip, coverage and DuckDB smoke;
6. compare generated canonical audit/report bytes;
7. reject a fully rehashed semantic fake;
8. clean temporary extraction on success and failure.

Builder flow:

```text
validate source store
write temporary ZIP
standalone-check temporary ZIP
atomic replace destination
remove temporary ZIP on all failures
```

## Task 14 — Reproducibility semantics

Parquet bytes are not the reproducibility target.

Reproducibility audit must derive, not assert:

```text
same input typed rows -> same logical row hashes
same input -> same chunk relative paths
same input -> same canonical chunk manifests
second identical import -> no new committed chunks
read-back rows -> same logical hashes
store audit A/B -> same canonical audit bytes
portable pack checker reconstruction -> same semantic results
```

Do not write unconditional success literals. Build twice, compare exact canonical values/bytes, then emit the audit.

## Task 15 — Tests

Create at minimum:

```text
tests/test_sprint_06_4a_parquet_store_contract.py
tests/test_sprint_06_4a_atomic_import_and_roundtrip.py
tests/test_sprint_06_4a_coverage_resume_gap_repair.py
tests/test_sprint_06_4a_store_evidence_pack.py
```

All tests use deterministic synthetic public evidence and `tmp_path`. No real network and no committed generated files.

Required concrete behaviors:

### Schema and Decimal

1. exact Arrow schema for all four datasets;
2. no inferred schema path;
3. bool-as-int rejected;
4. float rejected;
5. decimal exactly representable at scale 18 accepted;
6. rounding-required decimal rejected;
7. precision overflow rejected;
8. negative funding rate preserved;
9. `-0` canonical logical value becomes `0`;
10. semantic Decimal equality after read-back.

### Paths and publication

11. safe BTCUSDT month path;
12. unsafe symbol/path rejected;
13. staging directory used;
14. chunk manifest written before publish;
15. read-back validation before publish;
16. atomic final directory publication;
17. receipt written last;
18. early failure leaves no receipt;
19. mid failure leaves no receipt;
20. late failure leaves no receipt;
21. stale staging not treated as committed;
22. existing mismatched final path rejected;
23. symlink/non-regular store entry rejected;
24. source evidence archived with exact SHA.

### Idempotency and conflicts

25. first import commits;
26. second same import is verified no-op;
27. second import creates no new chunks;
28. identical existing row reused;
29. duplicate incoming key rejected;
30. conflicting existing key rejected;
31. disjoint repair row accepted;
32. duplicate key across chunks audit fails;
33. modified Parquet bytes rejected;
34. modified chunk manifest rehashed but semantically false rejected;
35. modified receipt rejected;
36. modified archived source review pack rejected.

### Round-trip and replay readiness

37. instrument rows round-trip;
38. 1001 trade rows round-trip;
39. 1001 mark rows round-trip;
40. funding rows round-trip;
41. trade/mark exact timestamp equality;
42. funding observation uses mark open;
43. missing mark boundary rejected;
44. incomplete trade coverage rejected;
45. incomplete mark coverage rejected;
46. explicit instrument snapshot required;
47. historical metadata completeness remains false.

### Coverage and planning

48. complete 1001 window has no gaps;
49. missing first minute planned;
50. missing last minute planned;
51. missing middle minute planned;
52. multi-minute gap coalesced;
53. disjoint gaps remain separate;
54. max 1000 inclusive rows split exactly;
55. month boundary split/coverage correct;
56. leap-day boundary correct;
57. duplicate timestamp fails;
58. trade-only gap makes pair not ready;
59. mark-only gap makes pair not ready;
60. funding scan reports observed range only;
61. funding completeness remains false.

### DuckDB

62. all four views register;
63. exact seed row counts;
64. min/max timestamp query correct;
65. Decimal type is not DOUBLE;
66. duplicate smoke query clean;
67. empty store fails closed;
68. no persistent DB file created.

### Evidence pack and provenance

69. exact source-tree manifest deterministic;
70. source-tree unsafe entry rejected;
71. full synthetic import -> audit -> pack -> checker succeeds;
72. same lifecycle succeeds with approved alternate host provenance;
73. unsafe ZIP path rejected;
74. duplicate ZIP member rejected;
75. missing Parquet member rejected;
76. extra unexpected member rejected;
77. rehashed Parquet semantic tamper rejected;
78. rehashed audit/report tamper rejected;
79. temporary ZIP removed on builder failure;
80. existing output replaced only after successful self-check;
81. checker missing ZIP returns strict JSON failure;
82. no network/private/live implementation present.

Do not pad the matrix with repeated constant-only parametrization. Each numbered behavior must map to an exact pytest node in a checked-in coverage document:

```text
docs/sprint_06_4a_behavior_coverage.md
```

## Task 16 — Required commands

Codex must run:

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
python -m pytest tests/test_sprint_06_4a_parquet_store_contract.py -q
python -m pytest tests/test_sprint_06_4a_atomic_import_and_roundtrip.py -q
python -m pytest tests/test_sprint_06_4a_coverage_resume_gap_repair.py -q
python -m pytest tests/test_sprint_06_4a_store_evidence_pack.py -q
python -m pytest -q
ruff check .
git diff --check
```

Codex must not run the real owner review pack or make any network call.

## Definition of done / code gate

```text
all existing accepted tests unchanged and passing;
all Sprint 06.4A tests passing;
no-live and numeric environment checks pass;
Ruff and git diff --check pass;
exact 06.3B coverage map debt closed;
deterministic full source-tree identity implemented;
strict Arrow schemas and Decimal policy implemented;
validated public pack can be imported without network;
Parquet read-back is semantically equal;
logical hashes stable across independent builds;
second import is a true verified no-op;
conflicts fail closed;
complete/gapped minute coverage and bounded repair plans correct;
DuckDB views are read-only and Decimal-preserving;
portable seed-store pack self-checks semantically;
rehashed semantic tampering is rejected;
no generated artifacts committed;
all risk/parameter/live guardrails remain closed.
```

## Owner action after PM code review

Do not run anything locally during Codex implementation.

After PM accepts the 06.4A code gate, PM will provide a public/local-only PowerShell script that:

1. verifies the new source-tree hash;
2. extracts the already accepted nested public review pack from the owner bundle;
3. imports it into a fresh seed Parquet store;
4. runs full store audit and idempotent re-import;
5. runs coverage and DuckDB smoke;
6. builds and checks the portable seed-store review pack;
7. outputs one upload ZIP.

That owner run will use no network, API key, private endpoint or live execution.
