# Sprint 06.4A.3.5 — Honest Material Tests, Atomic Store Graph and Semantic Seed-Pack Closure

## 0. PM authorization and branch discipline

Sprint 06.3B remains accepted and frozen.

Sprint 06.4A.3.4 is rejected after review of merged PR #66.

Frozen reviewed refs:

```text
REJECTED_PR = 66
REJECTED_HEAD_SHA = 984cabb932680fbdcbcfa252cbd0a3ac8cbcdc47
REJECTED_MERGE_SHA = ae47603ca34030f6a019a9eeb5d99699bbeee570
STORE_SCHEMA_VERSION = bybit_public_parquet_store_v1
```

Create exactly this branch from current `main`:

```text
codex/sprint-06-4a-3-5-honest-material-semantic-pack
```

Open a **draft PR**. Do not merge it. Do not mark it ready for review until every command in this prompt passes.

Do not rewrite or force-push `main`.

## 1. Frozen safety boundary

Permitted:

```text
public-batch synthetic no-network fixture
local tmp_path files
Parquet and in-memory DuckDB under tests/tmp_path
GitHub source/test/document changes
```

Forbidden:

```text
real owner review pack
real network request
private Bybit endpoint
API key or secret
account/wallet/order/position/grid operation
Telegram
live execution
parameter selection
profitability/PnL/EV/ROI claim
committed generated Parquet/ZIP/DuckDB/JSON evidence
```

Do not change accepted `src/bybit_grid/data/public_batch/*` semantics except for a narrowly required bytes-reader API that preserves all existing canonical output bytes and tests.

## 2. Mandatory first action — delete the renamed padding tests

Delete the current contents of:

```text
tests/test_sprint_06_4a_3_4_schema_plan_writer.py
tests/test_sprint_06_4a_3_4_import_audit.py
tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py
tests/test_sprint_06_4a_3_4_semantic_pack_cli.py
```

Recreate these files with the exact test names listed in Section 15. Every test must perform its named production mutation.

Forbidden test structure:

```python
StoreVersion(...)
audit_market_store(tmp_path / "missing")
assert N >= 1
```

Forbidden acceptance evidence:

```text
generic dispatcher
one helper selected by behavior ID
constant-only assertions
missing-path audit used for an unrelated behavior
same body with changed numeric/string literals
manifest self-validation as proof of production behavior
```

Shared fixture creation helpers are allowed. A test may call a fixture helper, but it must directly call or subprocess-execute the production symbol named by its behavior contract and assert the exact result.

## 3. Fix the behavior manifest and verifier

### 3.1 Hard-code expected production symbols by behavior ID

In `src/bybit_grid/common/pytest_coverage_map.py`, add a frozen mapping:

```python
REQUIRED_PRODUCTION_SYMBOLS_064A35: Mapping[str, tuple[str, ...]]
```

The manifest must not choose its own proof target. For every behavior ID, its `production_symbols` field must equal the frozen mapping exactly.

Use this exact symbol mapping:

```text
GOV-EXACT-ID-SET
  verify_required_behavior_json

GOV-MISSING-NODE
  verify_required_behavior_json

GOV-NOOP-REJECTED
  verify_required_behavior_json

CLI-HELP-ALL
  subprocess.run

CLI-MISSING-ARGS-ALL
  subprocess.run

DECIMAL-MAX-BOUNDARY
DECIMAL-MIN-BOUNDARY
DECIMAL-ROUNDING-REJECTED
  ensure_decimal128_38_18

PLAN-INSTRUMENT-SNAPSHOT
PLAN-KLINE-CROSS-MONTH
PLAN-FUNDING-FOUR-MONTHS
PLAN-MULTI-SYMBOL-REJECTED
  partition_validated_rows

PREFLIGHT-INVALID-ROW-ZERO-WRITES
PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES
PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES
  build_import_preflight_plan
  snapshot_tree

CHUNK-EARLY-CLEANUP
CHUNK-MID-CLEANUP
CHUNK-LATE-CLEANUP
  write_chunk_atomic
  snapshot_tree

CHUNK-CANONICAL-MANIFEST
CHUNK-ACTUAL-PATH-MATCH
CHUNK-PK-SCHEMA-MATCH
CHUNK-EXISTING-CORRUPTION-REJECTED
  write_chunk_atomic
  read_and_validate_chunk

IMPORT-SYNTHETIC-REAL-SHAPE
IMPORT-SOURCE-BYTES-IMMUTABLE
IMPORT-RECEIPT-LAST
IMPORT-NOOP-TYPED
IMPORT-NOOP-ZERO-MUTATION
IMPORT-NOOP-CORRUPT-CHUNK-REJECTED
IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED
  import_validated_public_batch_to_store

AUDIT-EMPTY-REJECTED
AUDIT-VERSION-TAMPER-REJECTED
AUDIT-ORPHAN-CHUNK-REJECTED
AUDIT-ORPHAN-EVIDENCE-REJECTED
AUDIT-RECEIPT-TAMPER-REJECTED
AUDIT-GLOBAL-DUPLICATE-REJECTED
AUDIT-GLOBAL-CONFLICT-REJECTED
AUDIT-UNEXPECTED-ENTRY-REJECTED
AUDIT-STALE-STAGING-REJECTED
  audit_market_store

REPLAY-SNAPSHOT-REQUIRED
REPLAY-SNAPSHOT-ROW-RETURNED
REPLAY-COMPLETE-TRADE-MARK
REPLAY-FUNDING-MARK-JOIN
REPLAY-MISSING-MARK-JOIN-REJECTED
  read_replay_slice

COVERAGE-STRICT-INPUTS
COVERAGE-OUT-OF-WINDOW-REJECTED
COVERAGE-GAP-WINDOWS
  scan_minute_coverage

RESUME-INCLUSIVE-1000
RESUME-MONTH-YEAR-LEAP
  plan_bounded_resume_windows

FUNDING-STRICT-TIMESTAMPS
  scan_funding_observed_range

DUCKDB-FOUR-VIEWS
DUCKDB-DECIMAL-TYPES
DUCKDB-CONNECTION-CLOSED
  open_readonly_duckdb_views
  duckdb_smoke_audit

PACK-BUILDER-BAD-STORE-REJECTED
PACK-EXACT-MEMBER-SET
PACK-EMPTY-MANIFEST-REJECTED
PACK-REHASHED-FAKE-REJECTED
PACK-NESTED-EVIDENCE-VALIDATED
PACK-REPORT-TAMPER-REJECTED
PACK-TEMP-CLEANUP
  make_seed_review_pack
  check_seed_review_pack

CLI-FULL-LIFECYCLE-BYBIT-HOST
CLI-FULL-LIFECYCLE-BYTICK-HOST
  subprocess.run
```

The manifest may include additional symbols only when explicitly frozen in this mapping. It may not use `StoreVersion` or `audit_market_store` as a universal substitute.

### 3.2 Exact traceability text

For each manifest row, write concrete values:

```text
fixture: exact fixture/helper and data shape
mutation: exact modified file/row/input/failpoint
expected: exact return value or exact MarketStoreError message
```

Reject these phrases:

```text
specific deterministic fixture
specific material mutation
exact stable assertion
production path exercises
the contract returns
```

### 3.3 Strong duplicate-body normalization

Normalize all irrelevant constants before comparing test bodies:

```text
integer literals
float literals
arbitrary string literals
UUID/path suffixes
```

Preserve only:

```text
called production symbol names
exception class
exact expected error string
structural control flow
```

The current `assert N >= 1` technique must produce duplicate-body errors.

Reject a mapped test when:

```text
it calls only StoreVersion and audit_market_store(missing_path)
its required production symbol appears only in an import, not in a Call node
its expected error string is absent
its only assertion is a constant comparison
its only filesystem mutation is creation of an unused path
```

### 3.4 Verifier regressions

Add tests proving the verifier rejects:

```text
56 tests with the same body and changed integer constants
manifest mapping DECIMAL behavior to StoreVersion
manifest mapping PACK behavior to audit_market_store
function importing but not calling its required symbol
function calling required symbol but making no assertion
function asserting only 17 >= 1
```

## 4. Immutable review-pack bytes

Keep the path loader as a one-read wrapper:

```python
source_bytes = Path(path).read_bytes()
return load_validated_public_replay_batch_from_review_pack_bytes(...)
```

The bytes loader must perform all validation and reconstruction from the same immutable bytes.

Add or use a public-batch byte-reader abstraction so validation does not require a separately mutable original path.

If a temporary file is still required for compatibility:

```text
write source_bytes once
fsync and close
validate only that temporary file
reconstruct only from source_bytes or the same temporary bytes
remove in finally
```

Test replacing/deleting the original source path immediately after the one read. Imported source archive and reconstructed rows must remain unchanged.

## 5. Complete committed-row conflict preflight

Before returning `ImportPreflightPlan`, build an existing row registry from all relevant committed chunks:

```python
(dataset, primary_key) -> complete immutable semantic row
```

For every incoming row:

```text
key absent                     -> new row
key present + rows identical   -> reusable row
key present + rows differ      -> raise MarketStoreError("store_row_conflict")
duplicate incoming key         -> raise MarketStoreError("duplicate_incoming_key")
duplicate existing key         -> raise MarketStoreError("duplicate_committed_key")
```

This must happen before creating:

```text
store root
store_version.json
transaction directory
chunk directory
evidence directory
receipt directory
```

`build_planned_chunk()` path reuse is not sufficient because changed rows generate a new logical hash/path.

## 6. Transaction state machine

### 6.1 New store

For a nonexistent target:

1. Complete all validation and planning in memory.
2. Create one sibling transaction directory.
3. Materialize the complete candidate store under the transaction root.
4. Write the receipt last inside the candidate store.
5. Run full store-graph audit against the candidate transaction root.
6. Atomically rename the complete candidate root to the final store path.
7. On any exception, remove the transaction root and leave the final path nonexistent.

Do not publish `store_version.json` separately before the root rename.

### 6.2 Existing valid store append

For append:

1. Audit the existing store.
2. Complete incoming-versus-existing conflict preflight.
3. Stage only new immutable chunks/evidence/receipt in a sibling transaction root.
4. Validate every staged object.
5. Build a candidate overlay inventory and run full graph validation before publishing the receipt.
6. Publish new chunk directories atomically.
7. Publish evidence directory atomically or fully validate an existing identical directory.
8. Publish the receipt last.
9. There must be no expected validation step after receipt publication that can fail.

### 6.3 Failure cleanup

For every failpoint before receipt publication:

```text
new store: final path remains nonexistent
existing store: exact before/after snapshot_tree equality
no .txn-* sibling
no .building
no empty partition parents
no new version/evidence/chunk/receipt
```

For an injected process-crash simulation that intentionally leaves orphan immutable objects, audit must return `ok=false` with exact orphan/stale failures. Normal caught exceptions must clean up.

## 7. Verified no-op

When the exact receipt exists, execute these checks in order:

1. Snapshot the full tree.
2. Strict-parse canonical `store_version.json`.
3. Strict-parse the receipt at the exact path implied by its run ID and SHA.
4. Compare receipt model and exact receipt bytes with the regenerated plan.
5. Validate every referenced chunk using `read_and_validate_chunk(expected_manifest=...)`.
6. Verify there are no missing or extra receipt-owned chunks.
7. Verify there are no conflicting/orphan chunks anywhere in the store.
8. Read evidence archive bytes and compare with immutable source bytes.
9. Verify evidence SHA-256.
10. Strict-parse and compare evidence reference bytes/model.
11. Run the accepted nested public review-pack semantic checker.
12. Run full store-graph audit.
13. Regenerate the receipt bytes.
14. Snapshot the tree again.
15. Require exact inventory equality, including paths, file hashes, sizes and mtimes.
16. Return exact typed `StoreImportReceipt`.

Any corruption must fail before return:

```text
version
receipt
manifest
Parquet
evidence archive
evidence reference
nested public evidence
orphan object
unexpected entry
```

## 8. Full store-graph audit

Audit must reject:

```text
missing root
empty root
version-only root
chunks without receipt
receipt without chunks
receipt path not matching model run_id/source SHA
evidence path not matching source SHA
missing archive or reference
archive SHA mismatch
nested public semantic failure
unexpected root or nested entry
symlink/junction/non-regular entry
stale sibling transaction or in-root staging
moved/path-rewritten chunk
duplicate key across chunks
same key with conflicting row
chunk owned by zero receipts
chunk owned by more than one receipt
evidence owned by zero receipts
evidence owned by more than one incompatible receipt
partial seed import missing one of the four datasets
```

For every receipt, require exactly the intended dataset kinds:

```text
instrument_snapshot
trade_kline_1m
mark_kline_1m
funding_rate
```

Validate the archived public pack using its receipt run ID and source SHA.

Audit output must remain deterministic and use exact ordered failure strings.

## 9. Chunk contract

`read_and_validate_chunk()` must continue to rederive the expected path from rows and logical hash.

Also require:

```text
exact dataset directory kind equals manifest.dataset
exact partition values equal row values
instrument snapshot has one exact snapshot timestamp and may contain many symbols
time-series chunk has exactly one symbol and one UTC month
exact primary-key schema
exact two regular members
canonical manifest bytes
Parquet SHA
Arrow schema
row ordering/count/bounds/logical hash
```

`write_chunk_atomic()` existing-path reuse must call `read_and_validate_chunk()` rather than the weaker private validator.

## 10. Semantic seed-review-pack contract

Replace the current hash-only implementation.

### 10.1 Typed manifest

Create a strict immutable model and parser with exact fields:

```text
schema = bybit_public_parquet_seed_review_pack_v1
storage_schema_version
run_id
source_review_pack_sha256
members: immutable mapping relative_path -> lowercase SHA-256
```

Require canonical JSON bytes and exact keys/types.

### 10.2 Exact member set

Include only objects owned by the selected receipt:

```text
store/store_version.json
store/<each receipt-owned chunk>/data.parquet
store/<each receipt-owned chunk>/chunk_manifest.json
store/<evidence path>/review_pack.zip
store/<evidence path>/evidence_reference.json
store/<receipt path>/import_receipt.json
store_audit.json
round_trip_audit.json
minute_replay_coverage_audit.json
funding_observed_range_audit.json
duckdb_smoke_audit.json
reproducibility_audit.json
risk_guardrail_report.md
review_pack_manifest.json
```

Do not recursively include arbitrary files.

### 10.3 Derived artifacts

Build all derived artifacts twice independently and compare exact bytes before ZIP publication.

Required semantics:

```text
store audit is ok
round-trip logical hashes equal receipt/chunk hashes
trade/mark requested window is complete and equal
funding observed range is reported but completeness remains false
DuckDB has exactly four views and DECIMAL market types
reproducibility values are derived from A/B comparison
risk/guardrail report keeps private/live/parameter/profitability claims false
```

### 10.4 Standalone checker

The checker must:

1. Strictly reject duplicate/unsafe/directory/non-regular ZIP members.
2. Strict-parse the typed manifest.
3. Require the exact member set.
4. Verify every member SHA.
5. Extract with containment checks to a fresh temporary directory.
6. Validate nested public review-pack semantics.
7. Run full store-graph audit against extracted `store/`.
8. Rerun round-trip, coverage, funding and DuckDB audits.
9. Rebuild every derived artifact and compare exact bytes.
10. Remove the temporary directory on success and failure.

A fully rehashed fabricated ZIP containing arbitrary `datasets/...` files must fail.

## 11. DuckDB smoke

`duckdb_smoke_audit()` must return a frozen deterministic audit containing:

```text
four exact view names
row count per dataset
min/max timestamp per time dataset
duplicate-key count per dataset
DuckDB type per Decimal column
all_decimal_types_ok
persistent_database_created_bool = false
```

Reject any market Decimal column reported as `DOUBLE`, `FLOAT`, or `REAL`.

Close the connection on success and every failure.

## 12. Use the real synthetic fixture

Keep and use `build_synthetic_public_review_pack()` from:

```text
tests/helpers/synthetic_market_store_fixture.py
```

Every import/lifecycle test must use the canonical 18-member output created through the public-batch production runner and builder.

Required shape:

```text
instruments = 721
trade rows = 1001
mark rows = 1001
funding rows = 300 spanning at least four UTC months
base_url parameterized separately:
  https://api.bybit.com
  https://api.bytick.com
```

The fixture itself must have a focused test proving:

```text
18 canonical members
semantic public checker ok
expected counts
unaligned server-time snapshot preserved exactly
```

## 13. Exact material tests — governance and CLI

Recreate `tests/test_sprint_06_4a_3_4_governance_cli.py` with these exact contracts:

### `test_gov_exact_id_set`

```text
call verify_required_behavior_json with actual collected node IDs
assert all 61 IDs in exact order
assert no errors
```

### `test_gov_missing_node_rejected`

```text
replace one node ID with a nonexistent node
assert exact missing_node error
```

### `test_gov_noop_node_rejected`

Create a test source that calls only:

```python
StoreVersion(...)
audit_market_store(tmp_path / "missing")
assert 1 >= 1
```

Map a non-audit behavior to it. Assert verifier rejects it as unrelated/no-op/duplicate.

### `test_cli_help_all_five_scripts`

Run all five scripts with `--help`; assert exit 0 and no traceback.

### `test_cli_missing_args_all_five_scripts`

Run all five scripts without args; assert exit 2, exactly one canonical JSON line, `ok=false`, and empty stderr.

## 14. Exact material tests — schema, planner and writer

Recreate `tests/test_sprint_06_4a_3_4_schema_plan_writer.py`.

Each test must directly call the named function.

```text
test_decimal_max_boundary
  call ensure_decimal128_38_18(max exact value); assert identity

test_decimal_min_boundary
  call ensure_decimal128_38_18(min exact value); assert identity

test_decimal_rounding_rejected
  call with scale 19; assert MarketStoreError("decimal_rounding_required")

test_plan_instrument_snapshot_multi_symbol_single_partition
  use >=2 symbols with one snapshot timestamp; call partition_validated_rows;
  assert one instrument partition containing both symbols

test_plan_kline_cross_month_two_partitions
  rows on both sides of UTC month boundary; assert two ordered partitions

test_plan_funding_four_months_four_partitions
  funding rows in four UTC months; assert four exact partition keys

test_plan_entry_mixed_timeseries_symbols_rejected
  pass mixed-symbol rows directly to build_planned_chunk/write_chunk_atomic;
  assert mixed_symbols and zero filesystem change

test_preflight_invalid_row_zero_writes
  mutate one projected row to invalid Decimal/type; call build_import_preflight_plan;
  assert exact error and target path absent

test_preflight_incoming_duplicate_zero_writes
  duplicate one incoming primary key; assert duplicate_incoming_key and target absent

test_preflight_committed_conflict_zero_writes
  create valid store, construct second evidence with same PK/different row;
  assert store_row_conflict and exact before/after inventory equality

test_chunk_early_failure_cleanup
  write_chunk_atomic(fail_at="early"); assert target absent

test_chunk_mid_failure_cleanup
  fail_at="mid"; assert no .building and target absent

test_chunk_late_failure_cleanup
  fail_at="late"; assert no .building and target absent

test_chunk_manifest_is_canonical
  write valid chunk; parse canonical manifest; assert canonical bytes equality

test_chunk_actual_path_mismatch_rejected
  move chunk and rewrite only manifest.relative_path canonically; assert chunk_path_semantic_mismatch

test_chunk_primary_key_schema_mismatch_rejected
  rewrite primary_key_columns canonically; assert primary_key_schema_invalid

test_existing_chunk_corruption_rejected
  corrupt data.parquet; repeat same write; assert parquet_sha256_mismatch
```

## 15. Exact material tests — import and audit

Recreate `tests/test_sprint_06_4a_3_4_import_audit.py`.

```text
test_import_synthetic_owner_shape_succeeds
  build canonical synthetic pack; load bytes; import;
  assert typed receipt, 7 expected chunks for the frozen fixture shape,
  all four datasets and audit.ok=true

test_import_archives_identical_source_bytes
  assert archived review_pack.zip bytes exactly equal fixture.bytes

test_import_receipt_is_last_commit_marker
  inject every pre-receipt failpoint; assert no receipt and exact cleanup;
  successful run has receipt

test_reimport_returns_typed_receipt
  import twice; assert exact StoreImportReceipt equality

test_reimport_zero_filesystem_mutation
  snapshot before/after second import; assert exact equality including mtimes

test_reimport_corrupt_chunk_rejected
  corrupt one referenced Parquet; assert exact parquet_sha256_mismatch/store_audit failure

test_reimport_corrupt_evidence_rejected
  corrupt archived public pack; assert evidence_archive_mismatch or semantic failure

test_audit_empty_store_rejected
  empty directory; assert empty_store_root

test_audit_version_tamper_rejected
  tamper canonical version; assert store_version_invalid

test_audit_orphan_chunk_rejected
  copy one valid chunk not referenced by receipt; assert orphan_chunk

test_audit_orphan_evidence_rejected
  add unowned evidence directory; assert orphan_evidence

test_audit_receipt_tamper_rejected
  reserialize changed receipt canonically; assert receipt_invalid/ownership mismatch

test_audit_global_duplicate_rejected
  add duplicate identical PK in another valid chunk; assert duplicate_committed_key

test_audit_global_conflict_rejected
  add same PK with changed row; assert store_row_conflict

test_audit_unexpected_entry_rejected
  add root and nested unexpected entries; assert exact unexpected-entry failures

test_audit_stale_staging_rejected
  create sibling transaction residue and/or in-root staging; assert stale_transaction
```

## 16. Exact material tests — replay, coverage, resume and DuckDB

Recreate `tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py`.

```text
test_replay_snapshot_required_and_unaligned_snapshot_allowed
  use exact unaligned synthetic server-time snapshot; succeeds;
  missing/wrong snapshot fails instrument_snapshot_match_invalid

test_replay_returns_exact_instrument_snapshot_row
  assert returned instrument symbol/snapshot/provenance exact

test_replay_complete_trade_mark_grids
  assert 1001/1001 exact timestamp equality

test_replay_funding_mark_join
  assert expected observation count and mark_open exact

test_replay_missing_mark_join_rejected
  remove referenced mark minute; assert funding_mark_join_missing or incomplete_mark_coverage as frozen

test_coverage_strict_inputs
  parameterize bool/string/float/negative/unaligned/unsafe symbol; assert exact errors

test_coverage_out_of_window_rejected
  include observed timestamp outside window; assert timestamp_out_of_window

test_coverage_gap_windows
  first/middle/last/disjoint gaps; assert exact intervals

test_resume_inclusive_1000
  1001 missing rows; assert windows 1000 + 1 with exact inclusive bounds

test_resume_month_year_leap_boundaries
  test month/year/leap-day transitions with no overlap/omission

test_funding_strict_timestamps
  reject bool/string/negative/unaligned; report exact observed range for valid tuple

test_duckdb_four_views
  valid store; assert exact four view names and row counts

test_duckdb_decimal_types
  assert all market numeric columns are DECIMAL and not DOUBLE/FLOAT/REAL

test_duckdb_connection_closed_on_success_and_failure
  test smoke helper closes; inject invalid store and prove failure path closes
```

## 17. Exact material tests — semantic pack and CLI lifecycle

Recreate `tests/test_sprint_06_4a_3_4_semantic_pack_cli.py`.

```text
test_pack_builder_rejects_bad_store
  empty/version-only/tampered store; assert store_audit_failed and no output/temp

test_pack_exact_member_set
  build valid pack; assert exact derived + owned store member set

test_pack_empty_manifest_rejected
  create manifest with zero members; assert empty_manifest/manifest contract error

test_pack_rehashed_fake_rejected
  fabricate datasets path and recompute all hashes; assert semantic checker failure

test_pack_nested_public_evidence_validated
  tamper nested public pack and update outer hashes; assert nested semantic failure

test_pack_report_tamper_rejected_after_rehash
  tamper one derived audit/report and rehash; assert derived semantic mismatch

test_pack_temp_cleanup_on_failure
  inject self-check failure; assert temp ZIP removed and existing destination unchanged

test_cli_full_lifecycle_bybit_host_offline
  subprocess: import -> audit -> second import -> repair plan -> pack build -> pack check;
  assert compact JSON, all success, no network, base provenance api.bybit.com

test_cli_full_lifecycle_bytick_host_offline
  same lifecycle with api.bytick.com provenance
```

## 18. Required production changes by file

At minimum modify:

```text
src/bybit_grid/common/pytest_coverage_map.py
src/bybit_grid/data/market_store/transaction.py
src/bybit_grid/data/market_store/audit.py
src/bybit_grid/data/market_store/evidence.py
src/bybit_grid/data/market_store/import_public_batch.py
src/bybit_grid/data/market_store/writer.py
src/bybit_grid/data/market_store/duckdb_views.py
src/bybit_grid/data/market_store/models.py
src/bybit_grid/data/market_store/parsing.py
scripts/check_behavior_coverage_maps.py
docs/sprint_06_4a_3_required_behaviors.json
five 06_4a_3_4 test modules
```

Do not claim completion when only tests/manifest changed.

## 19. Required commands

Run exactly:

```text
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py
python -m compileall -q src tests scripts
ruff check .
python scripts/check_behavior_coverage_maps.py --collect-command "python -m pytest --collect-only -q"

python -m pytest tests/test_sprint_06_4a_3_4_governance_cli.py -q
python -m pytest tests/test_sprint_06_4a_3_4_schema_plan_writer.py -q
python -m pytest tests/test_sprint_06_4a_3_4_import_audit.py -q
python -m pytest tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py -q
python -m pytest tests/test_sprint_06_4a_3_4_semantic_pack_cli.py -q
python -m pytest tests/test_sprint_06_3b_*.py -q
python -m pytest -q

git diff --check
```

Add GitHub Actions for pull requests if absent. The workflow must run at least:

```text
pip check
no-live audit
coverage verifier
focused 06.4A.3.4 tests
full pytest
Ruff
```

Do not merge without green Actions.

## 20. Required Codex report

Return exactly:

```text
branch name
draft PR number and URL
head commit SHA
changed production files
changed test files
git diff --stat
numeric environment output
pip check output
no-live output
compileall output
Ruff output
coverage-verifier JSON
five focused pytest outputs
upstream 06.3B output
full pytest output
GitHub Actions run URL/status
exact 61 behavior ID -> node -> direct production calls -> mutation -> expected result table
preflight conflict algorithm
new-store transaction algorithm
append transaction algorithm
verified-no-op 16-step result
store-graph audit contract
semantic seed-pack exact member list
rehashed fake tamper results
two offline CLI lifecycle outputs
known remaining limitations
all private/live/parameter/profitability guardrails
```

## 21. Definition of done

All must be true:

```text
56 renamed padding tests are gone
all 61 IDs map to actual material production/CLI mutations
manifest cannot select an unrelated proof symbol
integer/string padding cannot bypass duplicate-body detection
real canonical synthetic fixture is used by lifecycle tests
committed conflicts fail during zero-write preflight
new-store failures leave no final root
append failures leave exact prior inventory
receipt is last and no expected validation can fail afterward
no-op revalidates the entire graph and changes nothing
version-only/partial/orphan/conflicting stores fail audit
nested public evidence is semantically validated
seed pack checker reconstructs semantics, not just hashes
rehashed fabricated and report-tampered packs fail
DuckDB smoke verifies four views and DECIMAL types
both offline host-provenance CLI lifecycles pass
GitHub Actions is green
no network/private/live capability is introduced
```

## 22. Owner action

No local owner action is authorized in this sprint.

Submit an unmerged draft PR and provide its URL for PM review. Do not merge it.
