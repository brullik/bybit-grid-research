from __future__ import annotations
import os
import shutil
import uuid
from pathlib import Path
from .models import (
    ImportPreflightPlan,
    MarketStoreError,
    StoreVersion,
    StoreEvidenceReference,
    StoreImportReceipt,
    STORE_SCHEMA_VERSION,
)
from .canonical import canonical_json_bytes
from .paths import receipt_rel, evidence_rel
from .writer import build_planned_chunk
from .audit import audit_market_store


def build_import_preflight_plan(evidence, store_root: Path) -> ImportPreflightPlan:
    from .import_public_batch import ValidatedPublicBatchEvidence, _project_planned_rows

    if type(evidence) is not ValidatedPublicBatchEvidence:
        raise MarketStoreError("evidence_type_invalid")
    store_root = Path(store_root)
    if store_root.exists() and any(store_root.iterdir()):
        aud = audit_market_store(store_root)
        if not aud.ok:
            raise MarketStoreError(";".join(aud.failures) or "store_audit_failed")
    chunks = []
    seen = {}
    for kind, rows in _project_planned_rows(evidence):
        for r in rows:
            from .canonical import row_key

            k = (kind.value, row_key(kind, r))
            if k in seen:
                raise MarketStoreError("duplicate_incoming_key")
            seen[k] = r
        chunks.append(
            build_planned_chunk(
                kind, rows, existing_store_root=store_root if store_root.exists() else None
            )
        )
    version = StoreVersion(STORE_SCHEMA_VERSION)
    evref = StoreEvidenceReference(evidence.run_id, evidence.review_pack_sha256)
    receipt = StoreImportReceipt(
        evidence.run_id, evidence.review_pack_sha256, tuple(c.manifest for c in chunks)
    )
    return ImportPreflightPlan(
        evidence,
        store_root,
        version,
        tuple(chunks),
        evref,
        receipt,
        canonical_json_bytes(receipt),
        canonical_json_bytes(evref),
        evidence.source_bytes,
        store_root.exists(),
    )


def _write_plan_to_root(plan, root: Path, *, include_receipt: bool):
    root.mkdir(parents=True, exist_ok=True)
    (root / "store_version.json").write_bytes(canonical_json_bytes(plan.version))
    for c in plan.chunks:
        d = root / c.manifest.relative_path
        d.mkdir(parents=True, exist_ok=True)
        (d / "data.parquet").write_bytes(c.parquet_bytes)
        (d / "chunk_manifest.json").write_bytes(c.manifest_bytes)
    er = root / evidence_rel(plan.evidence.review_pack_sha256)
    er.mkdir(parents=True, exist_ok=True)
    (er / "review_pack.zip").write_bytes(plan.source_archive_bytes)
    (er / "evidence_reference.json").write_bytes(plan.evidence_reference_bytes)
    if include_receipt:
        rr = root / receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
        rr.parent.mkdir(parents=True, exist_ok=True)
        rr.write_bytes(plan.receipt_bytes)


def _publish_file_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _remove_new_objects(plan: ImportPreflightPlan):
    root = plan.store_root
    rr = root / receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
    if rr.exists():
        return
    for c in plan.chunks:
        d = root / c.manifest.relative_path
        if d.exists() and not c.reuse_existing_bool:
            shutil.rmtree(d, ignore_errors=True)
    er = root / evidence_rel(plan.evidence.review_pack_sha256)
    if er.exists():
        shutil.rmtree(er, ignore_errors=True)
    # prune empty directories bottom-up but never remove store root
    for base in (root / "datasets", root / "evidence", root / "imports"):
        if base.exists():
            for d in sorted(
                [x for x in base.rglob("*") if x.is_dir()], key=lambda x: len(x.parts), reverse=True
            ):
                try:
                    d.rmdir()
                except OSError:
                    pass


def commit_import_preflight_plan(
    plan: ImportPreflightPlan, *, fail_at: str | None = None
) -> StoreImportReceipt:
    if type(plan) is not ImportPreflightPlan:
        raise MarketStoreError("plan_invalid")
    final = plan.store_root
    rr = final / receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
    if rr.exists():
        from .inventory import snapshot_tree
        from .parsing import (
            parse_import_receipt_bytes,
            parse_store_version_bytes,
            parse_evidence_reference_bytes,
        )

        before = snapshot_tree(final)
        parse_store_version_bytes((final / "store_version.json").read_bytes())
        existing = parse_import_receipt_bytes(rr.read_bytes())
        if existing != plan.receipt or rr.read_bytes() != plan.receipt_bytes:
            raise MarketStoreError("receipt_mismatch")
        from .reader import read_and_validate_chunk

        for c in plan.chunks:
            mf, _ = read_and_validate_chunk(
                final, final / c.manifest.relative_path, expected_manifest=c.manifest
            )
            if mf != c.manifest:
                raise MarketStoreError("chunk_manifest_mismatch")
        er = final / evidence_rel(plan.evidence.review_pack_sha256)
        if (er / "review_pack.zip").read_bytes() != plan.source_archive_bytes:
            raise MarketStoreError("evidence_archive_mismatch")
        ref = parse_evidence_reference_bytes((er / "evidence_reference.json").read_bytes())
        if (
            ref != plan.evidence_reference
            or (er / "evidence_reference.json").read_bytes() != plan.evidence_reference_bytes
        ):
            raise MarketStoreError("evidence_reference_mismatch")
        aud = audit_market_store(final)
        if not aud.ok:
            raise MarketStoreError(";".join(aud.failures) or "store_audit_failed")
        if snapshot_tree(final) != before:
            raise MarketStoreError("noop_inventory_changed")
        return existing
    if fail_at == "before_transaction_root":
        raise MarketStoreError("injected_import_failure_before_transaction_root")
    txn = final.parent / (final.name + f".txn-{uuid.uuid4().hex}")
    published = False
    try:
        txn.mkdir(parents=True, exist_ok=False)
        if fail_at == "after_transaction_root":
            raise MarketStoreError("injected_import_failure_after_transaction_root")
        for c in plan.chunks:
            if c.reuse_existing_bool:
                continue
            d = txn / c.manifest.relative_path
            d.mkdir(parents=True, exist_ok=True)
            (d / "data.parquet").write_bytes(c.parquet_bytes)
            (d / "chunk_manifest.json").write_bytes(c.manifest_bytes)
        if fail_at == "after_stage_chunks":
            raise MarketStoreError("injected_import_failure_after_stage_chunks")
        er = txn / evidence_rel(plan.evidence.review_pack_sha256)
        er.mkdir(parents=True, exist_ok=True)
        (er / "review_pack.zip").write_bytes(plan.source_archive_bytes)
        if fail_at == "after_stage_evidence":
            raise MarketStoreError("injected_import_failure_after_stage_evidence")
        (er / "evidence_reference.json").write_bytes(plan.evidence_reference_bytes)
        if fail_at == "after_stage_reference":
            raise MarketStoreError("injected_import_failure_after_stage_reference")
        tr = txn / receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
        tr.parent.mkdir(parents=True, exist_ok=True)
        tr.write_bytes(plan.receipt_bytes)
        if fail_at == "after_stage_receipt":
            raise MarketStoreError("injected_import_failure_after_stage_receipt")
        final.mkdir(parents=True, exist_ok=True)
        if not (final / "store_version.json").exists():
            _publish_file_atomic(final / "store_version.json", canonical_json_bytes(plan.version))
        if fail_at == "after_publish_version":
            raise MarketStoreError("injected_import_failure_after_publish_version")
        first = True
        for c in plan.chunks:
            if c.reuse_existing_bool:
                continue
            dest = final / c.manifest.relative_path
            if dest.exists():
                raise MarketStoreError("immutable_chunk_path_conflict")
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(txn / c.manifest.relative_path, dest)
            if first and fail_at == "after_publish_first_chunk":
                raise MarketStoreError("injected_import_failure_after_publish_first_chunk")
            first = False
        if fail_at == "after_publish_all_chunks":
            raise MarketStoreError("injected_import_failure_after_publish_all_chunks")
        dest_er = final / evidence_rel(plan.evidence.review_pack_sha256)
        if not dest_er.exists():
            dest_er.parent.mkdir(parents=True, exist_ok=True)
            os.replace(er, dest_er)
        if fail_at == "after_publish_evidence":
            raise MarketStoreError("injected_import_failure_after_publish_evidence")
        if fail_at == "before_publish_receipt":
            raise MarketStoreError("injected_import_failure_before_publish_receipt")
        _publish_file_atomic(rr, plan.receipt_bytes)
        published = True
        aud = audit_market_store(final)
        if not aud.ok:
            raise MarketStoreError(";".join(aud.failures) or "store_audit_failed")
        return plan.receipt
    except Exception:
        if not published:
            _remove_new_objects(plan)
        raise
    finally:
        shutil.rmtree(txn, ignore_errors=True)
