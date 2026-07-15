from __future__ import annotations
import os
import shutil
import uuid
from pathlib import Path
from .models import ImportPreflightPlan, MarketStoreError, StoreVersion, StoreEvidenceReference, StoreImportReceipt, STORE_SCHEMA_VERSION
from .canonical import canonical_json_bytes
from .paths import receipt_rel, evidence_rel
from .writer import build_planned_chunk
from .audit import audit_market_store


def build_import_preflight_plan(evidence, store_root: Path) -> ImportPreflightPlan:
    from .import_public_batch import ValidatedPublicBatchEvidence, _project_planned_rows
    if type(evidence) is not ValidatedPublicBatchEvidence:
        raise MarketStoreError('evidence_type_invalid')
    store_root = Path(store_root)
    if store_root.exists() and any(store_root.iterdir()):
        aud = audit_market_store(store_root)
        if not aud.ok:
            raise MarketStoreError(';'.join(aud.failures) or 'store_audit_failed')
    chunks=[]
    seen={}
    for kind, rows in _project_planned_rows(evidence):
        for r in rows:
            from .canonical import row_key
            k=(kind.value,row_key(kind,r))
            if k in seen:
                raise MarketStoreError('duplicate_incoming_key')
            seen[k]=r
        chunks.append(build_planned_chunk(kind, rows, existing_store_root=store_root if store_root.exists() else None))
    version=StoreVersion(STORE_SCHEMA_VERSION)
    evref=StoreEvidenceReference(evidence.run_id, evidence.review_pack_sha256)
    receipt=StoreImportReceipt(evidence.run_id, evidence.review_pack_sha256, tuple(c.manifest for c in chunks))
    return ImportPreflightPlan(evidence, store_root, version, tuple(chunks), evref, receipt, canonical_json_bytes(receipt), canonical_json_bytes(evref), evidence.source_bytes, store_root.exists())


def _write_plan_to_root(plan, root: Path, *, include_receipt: bool):
    root.mkdir(parents=True, exist_ok=True)
    (root/'store_version.json').write_bytes(canonical_json_bytes(plan.version))
    for c in plan.chunks:
        d=root/c.manifest.relative_path
        d.mkdir(parents=True, exist_ok=True)
        (d/'data.parquet').write_bytes(c.parquet_bytes)
        (d/'chunk_manifest.json').write_bytes(c.manifest_bytes)
    er=root/evidence_rel(plan.evidence.review_pack_sha256)
    er.mkdir(parents=True, exist_ok=True)
    (er/'review_pack.zip').write_bytes(plan.source_archive_bytes)
    (er/'evidence_reference.json').write_bytes(plan.evidence_reference_bytes)
    if include_receipt:
        rr=root/receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
        rr.parent.mkdir(parents=True, exist_ok=True)
        rr.write_bytes(plan.receipt_bytes)


def commit_import_preflight_plan(plan: ImportPreflightPlan, *, fail_at: str | None = None) -> StoreImportReceipt:
    if type(plan) is not ImportPreflightPlan:
        raise MarketStoreError('plan_invalid')
    if fail_at == 'before_stage':
        raise MarketStoreError('injected_import_failure_before_stage')
    final=plan.store_root
    rr=final/receipt_rel(plan.evidence.run_id, plan.evidence.review_pack_sha256)
    if rr.exists():
        before = None
        from .inventory import snapshot_tree
        from .parsing import parse_import_receipt_bytes, parse_store_version_bytes, parse_evidence_reference_bytes
        before=snapshot_tree(final)
        aud=audit_market_store(final)
        if not aud.ok:
            raise MarketStoreError('store_audit_failed')
        parse_store_version_bytes((final/'store_version.json').read_bytes())
        existing=parse_import_receipt_bytes(rr.read_bytes())
        if existing != plan.receipt or rr.read_bytes() != plan.receipt_bytes:
            raise MarketStoreError('receipt_mismatch')
        for c in plan.chunks:
            from .reader import read_and_validate_chunk
            read_and_validate_chunk(final, final/c.manifest.relative_path, expected_manifest=c.manifest)
        er=final/evidence_rel(plan.evidence.review_pack_sha256)
        if (er / 'review_pack.zip').read_bytes() != plan.source_archive_bytes:
            raise MarketStoreError('evidence_archive_mismatch')
        parse_evidence_reference_bytes((er/'evidence_reference.json').read_bytes())
        if snapshot_tree(final) != before:
            raise MarketStoreError('noop_inventory_changed')
        return existing
    tmp=final.parent/(final.name+f'.txn-{uuid.uuid4().hex}')
    try:
        if fail_at == 'stage_chunks':
            raise MarketStoreError('injected_import_failure_stage_chunks')
        _write_plan_to_root(plan,tmp,include_receipt=False)
        if fail_at in ('stage_evidence','stage_reference','stage_receipt','publish_chunks','publish_evidence','publish_reference','before_receipt','publish_receipt'):
            raise MarketStoreError(f'injected_import_failure_{fail_at}')
        _write_plan_to_root(plan,tmp,include_receipt=True)
        aud=audit_market_store(tmp)
        if not aud.ok:
            raise MarketStoreError(';'.join(aud.failures))
        os.replace(tmp, final)
        return plan.receipt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
