# Frozen task contract: P0 committed-key preflight

Task ID: `p0-committed-key-preflight`
Issue: `#157`
Contract version: `committed-key-preflight-v1`
RED sentinel: `committed_key_preflight_contract_unavailable`
Audit source baseline named by issue `#157`: `f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`
Task-definition base: `c0f1a58f0efdb5afcdb0f128ce3d896d689d32aa`

This task removes a P0 canonical-store integrity defect. A stale or different import can currently
publish chunks, evidence, and a receipt before the store audit notices an overlap with an already
committed primary key. Once the receipt is published, cleanup is disabled and the failed call can
leave an invalid store. The frozen outcome requires every such conflict to fail before a
transaction root is created and before any store byte or inventory entry changes.

## Exact implementation scope

The implementation PR must change all and only these four paths:

1. `src/bybit_grid/data/market_store/models.py`
2. `src/bybit_grid/data/market_store/import_public_batch.py`
3. `src/bybit_grid/data/market_store/transaction.py`
4. `tests/test_store_committed_key_preflight.py`

The last path is new. No reader, writer, schema, other model, planner, audit, inventory, workflow,
dependency, PM checker, historical artifact, transport, recovery policy, live-execution, or
trading change is authorized. Crash cleanup and retry recovery after a publication failure remain
issue `#159`; padded behavior evidence remains issue `#160`. Historical branch code is not an
implementation source and must not be executed.

## Availability gate and mandatory RED

The frozen suite contains exactly 20 collected nodes: one harness node and 19 embedded ordinary
nodes. Every complete `test_*` function calls `_available()` as its first statement. Availability
requires one exact top-level literal assignment in each production path:

```python
COMMITTED_KEY_PREFLIGHT_CONTRACT = "committed-key-preflight-v1"
```

The ordinary test requires one exact top-level literal assignment:

```python
COMMITTED_KEY_PREFLIGHT_TEST_CONTRACT = "committed-key-preflight-v1"
```

Its complete UTF-8/LF raw bytes are embedded once as `ORDINARY_TEST_SOURCE` and pinned at SHA-256
`2477ebbc0f011521805a5e3787eff7629639f7226f030afcd337d91f33cafb02`.
The complete frozen-suite raw bytes are SHA-256
`64e91cce985763c95c76d571c11ddf6844cf23e15d61abb469be0426383693f4`.

After task-definition merge, a mandatory fresh Draft `probe/` PR changes all four required paths
and no others. The three production paths receive inert comment-only edits, and the new ordinary
test path contains inert probe content. On every supported Python matrix the frozen suite must
yield exactly 20 sentinel failures, zero frozen passes, and no unrelated failure,
collection/setup/teardown error, skip, xfail/xpass, or deselection. Ordinary/control suites must
remain green. The probe is closed unmerged and is never marked Ready.

## Evidence revalidation

`ValidatedPublicBatchEvidence` is an input claim, not a trust boundary. Before projecting rows,
preflight must revalidate the exact instance from its immutable `source_bytes`: the bytes are
nonempty and hash to `review_pack_sha256`; the canonical review-pack validation binds the declared
`run_id`; reconstruction is deterministic; and the four projected dataset batches from the
supplied instance equal the projection rebuilt from the archive. A forged byte payload fails with
the existing typed source-hash error, a forged reconstructed projection fails with
`evidence_projection_mismatch`, and a forged run binding fails typed. Preflight uses the canonical
rebuilt evidence after successful validation.

The revalidation operation is deterministic and offline. It performs no request and does not read
credentials. It does not weaken the existing evidence validation, provenance, or public-batch
guardrails.

## Platform path model

`ImportPreflightPlan.store_root` accepts a normal concrete `pathlib.Path` implementation for the
current platform (`PosixPath` or `WindowsPath`) and still rejects non-path inputs. The current
exact-type check compares the concrete object to the abstract `Path` factory and makes every real
preflight plan unconstructable. The correction is limited to this prerequisite model invariant;
no other model or schema behavior changes.

## Exact accepted-evidence no-op

Exact reimport is the only committed-key overlap that is not an error. Before overlap rejection,
an existing canonical receipt at the exact `(run_id, source_review_pack_sha256)` identity is
accepted only after the store version, receipt model and raw bytes, every declared chunk and
manifest, evidence archive, evidence reference, complete store audit, and byte-for-byte inventory
are revalidated. It returns the existing `StoreImportReceipt` type and changes nothing.

This recognition is repeated at commit time so a receipt that appears after plan construction is
also a typed no-op. A matching receipt with mismatched bytes, graph, chunk, archive, reference, or
audit is not a no-op and fails before mutation.

## Deterministic committed-key registry

For a nonempty valid store, scan all four `MarketDatasetKind` values in enum order and all validated
committed rows in canonical primary-key order. The registry key is
`(dataset_kind.value, row_key(dataset_kind, row))`. Registry rows are the complete immutable
canonical stored mappings.

After incoming duplicate validation and deterministic chunk planning, compare every planned row
to that registry:

- an equal key and equal complete row, including all provenance fields, raises exactly
  `duplicate_committed_key`;
- an equal key and any different complete row, including a provenance difference, raises exactly
  `store_row_conflict`.

The equality definition intentionally matches `audit_market_store`; it does not introduce a
payload-only alternative. The accepted receipt/evidence graph is checked first, so exact reimport
remains a no-op. Incoming duplicates within the new evidence retain their existing
`duplicate_incoming_key` contract.

## Pre-transaction recheck and immutable paths

Plan construction performs the registry comparison without creating the store root, a sibling
`*.txn-*` root, or any file. Commit repeats the exact accepted-no-op validation, current store
audit, committed-key registry comparison, and immutable destination-path check immediately before
creating its transaction root. This makes a plan stale-safe when another import appears after the
plan was built.

Every non-reused planned chunk destination must be absent. A present destination raises exactly
`immutable_chunk_path_conflict` before staging, publication, cleanup, or removal of the existing
chunk. On every rejection, `snapshot_tree(store_root)` is byte-for-byte identical before and after
the call and no sibling transaction directory remains or was required.

## Determinism and safety boundary

The same valid store and evidence produce the same registry traversal, first error, and no-op
decision. Acceptance covers all four dataset kinds, full-row equal and unequal overlaps, a real
second evidence source, a plan made stale after construction, forged source identity and
reconstruction, a forged immutable-path collision, and both immediate and late exact no-op paths.

All frozen and ordinary acceptance uses self-contained synthetic canonical rows, opaque local
evidence bytes, temporary stores, and in-process monkeypatching. It imports no test helper or
script module and performs no public/private Bybit request, credential read, live
execution, Telegram action, order, grid, position, wallet, or trading mutation.
