# Sprint 06.4A.3.1 — Material Store Graph Implementation and Anti-Padding Closure

## PM authorization

Sprint 06.3B remains accepted and frozen. Sprint 06.4A.3 is rejected.

Reviewed rejected identities:

```text
REJECTED_SOURCE_ZIP_SHA256 = f8ebba9a77199f6d38a8cda8122aa0f1255b17fe278f4a5cff8750122cab4e55
REJECTED_SOURCE_TREE_SHA256 = 570be3b55ca125371b7a0b664d96eb519123ce12bbe6a757071c38a7c5b3c830
REJECTED_PYTEST_COLLECTION = 502
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
SPRINT 06.4A.3: REJECTED
OWNER OFFLINE SEED IMPORT: NOT AUTHORIZED
SPRINT 06.4B: CLOSED
NETWORK / PRIVATE / LIVE / TELEGRAM: CLOSED
ONLY AUTHORIZED WORK: THIS CORRECTIVE SPRINT
```

# 1. Anti-padding rule — mandatory first action

The current 61-case test is invalid acceptance evidence:

```text
tests/test_sprint_06_4a_3_required_behaviors.py::test_required_behavior_material[...]
```

It only checks manifest strings. Delete it or retain it solely as a small manifest-schema unit test that is **not referenced by any required behavior ID**.

Every row in:

```text
docs/sprint_06_4a_3_required_behaviors.json
```

must map to a real collected test node that executes production code or a subprocess CLI and performs the behavior-specific mutation.

Forbidden mappings include:

- a test that reads the behavior manifest and asserts its own wording;
- a single generic test repeated once per ID without distinct production mutation;
- constant-only assertions;
- tests whose only purpose is proving a node ID exists;
- `assert behavior_id == ...`, string containment checks, or fixture-label checks;
- generic `pytest.raises(Exception)`;
- tests that mock the function under test instead of the external boundary;
- tests that do not import/call a market-store production module or subprocess CLI.

Parameterization is allowed only when every parameter has a distinct input mutation and exact stable expected result.

The verifier must reject node IDs from governance-only test modules such as `test_sprint_06_4a_3_required_behaviors.py`. It must also reject duplicate function bodies/material mappings. The manifest is documentation and traceability, not proof by itself.

Preserve the exact 61 behavior IDs frozen in the original Sprint 06.4A.3 prompt. Do not add, remove, rename, or reorder them.

# 2. Complete the production implementation

The previous submission changed almost no required production code. Implement the original Sprint 06.4A.3 contract in the modules below.

## 2.1 Strict persisted models and parsers

Implement exact canonical parser/serializer functions for:

```text
store_version.json
chunk_manifest.json
evidence_reference.json
import_receipt.json
all portable-pack audit JSON files
portable review_pack_manifest.json
```

Requirements:

- exact key sets;
- canonical byte equality;
- exact bool/int/string/tuple/model identity; bool never aliases int;
- lowercase 64-character SHA-256;
- exact schema/version constants;
- exact safe nonempty strings;
- immutable nested structures, not only a shallow `MappingProxyType` wrapper;
- nested receipt chunks parsed to `tuple[StoreChunkManifest, ...]`;
- stable specific `MarketStoreError` values.

Do not use `dataclasses.asdict()` on dataclasses containing immutable mapping proxies. Implement a recursive dataclass-field serializer that preserves immutable mappings without deepcopy/pickle behavior.

Validate mapping keys before sorting so mixed key types produce a stable `mapping_key_invalid`, not Python `TypeError`.

## 2.2 Exact Decimal semantics

Keep all operations, including scaling and integer conversion, inside a sufficiently precise `localcontext()`.

Must accept exactly:

```text
 99999999999999999999.999999999999999999
-99999999999999999999.999999999999999999
```

Reject non-Decimal, non-finite, scale greater than 18, precision overflow, and any rounding requirement. Never convert through float.

## 2.3 Dataset specifications and writer

Create one exact dataset specification per dataset driving:

```text
field names and exact types
Arrow schema
primary key
partition key
row validation
canonical logical JSONL
Parquet construction
semantic read-back
```

`write_chunk_atomic()` must independently reject:

```text
empty input unless explicitly documented as no-op
mixed symbols
mixed UTC months
mixed instrument snapshot timestamps
duplicate keys
unknown fields/types
unsafe paths
```

Strict chunk validation must verify:

```text
exact regular two-member directory
canonical manifest bytes and exact model
manifest dataset and PK columns
manifest relative_path equals actual store-relative directory
expected path rederived from typed rows and logical hash
Parquet SHA-256
exact Arrow schema
row order and logical bytes/hash
row count/min/max/partition values
```

Existing chunk reuse must execute the complete validation before returning.

## 2.4 Complete zero-write preflight

Before creating the root, `store_version.json`, `.building`, any chunk, evidence, reference, or receipt:

1. validate immutable source bytes and reconstruct detached rows;
2. validate every row;
3. construct the complete deterministic partition plan;
4. derive every expected manifest and path;
5. validate any existing version;
6. inspect relevant committed partitions and build a global PK registry;
7. detect incoming duplicates, committed duplicates, and semantic conflicts;
8. validate exact evidence and receipt targets;
9. prove every deterministic failure before any committed write.

Required exact conflict policy:

```text
same key + identical complete row -> reusable
same key + semantic difference    -> store_row_conflict
incoming duplicate                -> duplicate_incoming_key
committed duplicate               -> duplicate_committed_key
```

An invalid deterministic row must leave the target path absent or byte-for-byte unchanged. No empty `.building` and no version file may remain.

## 2.5 Receipt-last publication and verified no-op

Use same-volume temporary files/directories and atomic replacement for version, chunks, evidence archive, evidence reference, and receipt. Receipt is always last.

Add deterministic failure seams before and after each phase and clean normal caught failures. Crash-orphan objects may remain only for explicit simulated crash tests and must make audit fail.

Existing receipt path must:

- strict-parse canonical receipt;
- validate exact version;
- validate every referenced chunk semantically;
- validate archive bytes/hash and evidence reference;
- rerun nested public review-pack semantic checker;
- detect missing, extra, and orphan objects affecting the import;
- regenerate exact receipt bytes;
- snapshot complete member paths, bytes/hashes, sizes, and mtimes before/after;
- return a typed receipt only if absolutely unchanged.

Corrupting a referenced Parquet, manifest, evidence archive, evidence reference, receipt, or version must make the second import fail.

## 2.6 Full store-graph audit

`audit_market_store()` must return a typed `MarketStoreAudit(ok=False, failures=...)` for an invalid readable store. Reserve exceptions for unsafe/unreadable invocation failures.

It must validate:

```text
canonical version
exact allowed root graph and regular-entry safety
every chunk through strict reader
global duplicate/conflicting primary keys
every canonical receipt and its exact referenced chunk set
every evidence reference/archive and nested public-pack semantics
one-to-one seed import ownership across receipt/evidence/chunks
orphan chunks/evidence/references/receipts
stale .building
unexpected entries and symlinks
accepted replay-pair coverage
observed funding range only
frozen false guardrails
```

These must all produce `ok=false`:

```text
empty root
chunk-only root
receipt-only root
evidence-only root
bad version
tampered receipt
tampered evidence
copied/path-mismatched chunk
global duplicate key
global same-key different-row conflict
stale staging
unexpected entry
```

Do not weaken the production audit to support low-level chunk tests. Use a separate chunk validator in those tests.

## 2.7 Replay, coverage, and resume

Implement `resume.py`; it must not remain empty.

Replay must validate exact safe symbol, exact nonnegative aligned integer times, and `start <= end`.

It must load and return exactly one instrument row matching both requested snapshot timestamp and symbol. Missing or duplicate matches fail.

Require complete ascending trade and mark minute grids with exact timestamp equality.

Return immutable funding observations joined to the exact mark candle at the same timestamp:

```text
funding_time_ms
funding_rate
mark_open
```

A missing mark join must fail.

Coverage and resume must reject:

```text
unsafe symbol
bool/string/float timestamp aliases
negative timestamps
unaligned timestamps
reversed ranges
supplied timestamps outside the requested window
wrong audit model types
symbol/window mismatch
```

Implement bounded inclusive repair windows of at most 1000 rows. Test first, middle, last, disjoint gaps, UTC month/year rollover, and leap day.

Funding observed-range scanner must validate exact timestamps and claim observed range only.

## 2.8 DuckDB

Preserve in-memory, read-only behavior and exact DECIMAL types. Prevalidate the store through the complete audit or strict validated dataset inventory.

Test:

```text
exact four view names
row counts/min/max/duplicate queries
DECIMAL column types
both approved host provenance values queryable
no persistent database/extensions/network
connection closed after success and every failure
```

## 2.9 Semantic portable seed pack

The builder must first require `audit.ok is True` and derive the exact member set only from validated receipt/evidence/chunk ownership. Never recursively include arbitrary files.

Required generated derived artifacts:

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

1. reject duplicate, unsafe, directory, symlink, and non-regular ZIP entries;
2. strict-parse canonical manifest and require the exact member set;
3. reject empty manifest;
4. extract with containment checks to a fresh temporary root;
5. validate nested public review-pack semantics;
6. run complete store-graph audit;
7. rerun round-trip, replay/coverage, funding, and DuckDB audits;
8. regenerate every derived artifact and compare exact bytes;
9. reject fully rehashed semantic fakes and report tampering;
10. clean all temporary files on success and failure.

Builder lifecycle:

```text
full store audit
-> derived build A
-> derived build B
-> byte comparison
-> temporary ZIP
-> standalone semantic self-check
-> atomic destination replace
-> cleanup every failure path
```

# 3. Mandatory material regression tests

Create deterministic no-network synthetic public review packs matching the accepted shape:

```text
instruments > 500
trade = 1001 rows crossing a UTC month boundary
mark = 1001 matching rows
funding = 300 rows spanning at least four UTC months
host provenance parameterized for api.bybit.com and api.bytick.com
```

Commit a subprocess lifecycle for both hosts:

```text
synthetic public pack
-> import CLI
-> audit CLI
-> verified-no-op second import CLI
-> repair-plan CLI
-> replay with instrument and funding/mark join
-> DuckDB smoke
-> seed-pack builder CLI
-> standalone checker CLI
```

Every original 61 behavior ID must map to one of these real tests or a specific lower-level production mutation test.

Mandatory regressions include the exact current PM reproductions:

```text
bad version accepted by audit
tampered receipt accepted by audit
tampered evidence accepted by audit
chunks without receipt/evidence accepted by audit
copied/path-mismatched chunk accepted by audit
global duplicate/conflict accepted by audit
corrupt Parquet accepted by no-op re-import
empty manifest pack accepted
arbitrary fully rehashed pack accepted
empty-store builder accepted
nonexistent snapshot accepted
funding returned without mark_open
reversed/unsafe/out-of-window coverage accepted
valid decimal max/min rejected
mixed-symbol writer accepted
invalid row leaves .building and version
MappingProxyType audit model serialization failure
nested mutable audit mapping value
```

Tests must assert exact stable errors and real production outputs. No `raises(Exception)`, no constant-only assertions, no manifest-self-tests as material evidence.

# 4. Required commands and reported outputs

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
```

Run each CLI with missing arguments and report exact exit code/stdout/stderr.

Run:

```text
python -m pytest tests/test_sprint_06_3a_bybit_public_batch_input_contract.py -q
python -m pytest tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py -q
python -m pytest tests/test_sprint_06_3b_*.py -q
python -m pytest tests/test_sprint_06_4a_*.py -q
python -m pytest -q
ruff check .
git diff --check
python scripts/hash_source_tree.py --root .
```

Also report:

```text
exact collected test count
exact list of required behavior IDs and mapped node IDs
proof that no required ID maps to a governance-only test
source ZIP SHA-256
source-tree SHA-256
```

Do not run the real owner pack, any owner PowerShell script, or any network probe.

# Definition of done

The code gate opens only when:

- all 61 behavior IDs map to material production/CLI tests;
- the manifest-only padding test is not used as behavior evidence;
- all PM attacks fail closed with exact expected results;
- invalid deterministic import has zero writes;
- second import is a verified mutation-free no-op;
- complete store graph audit detects all tampering/orphans/conflicts;
- replay requires and returns a real instrument snapshot and joined funding observations;
- strict resume/gap planning is implemented;
- semantic portable pack rejects empty and rehashed fabricated packs;
- full subprocess lifecycle passes for both approved host provenances;
- no-private/no-live guardrails remain intact.

## Owner action after PM review

No owner/local action is authorized in this sprint. PM will independently review and attack the clean source ZIP. A later explicit acceptance is required before any offline owner seed-import PowerShell script is issued.
