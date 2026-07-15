from __future__ import annotations
import hashlib
from pathlib import Path
from .models import MarketStoreAudit
from .reader import read_and_validate_chunk, row_key
from .parsing import parse_import_receipt_bytes, parse_store_version_bytes, parse_evidence_reference_bytes


def audit_market_store(root):
    root = Path(root)
    failures = []
    chunks = 0
    receipts = 0
    keys = {}
    if not root.exists():
        return MarketStoreAudit(False, ("store_root_missing",), 0, 0)
    allowed = {"store_version.json", "datasets", "imports", "evidence"}
    entries = list(root.iterdir())
    if not entries:
        failures.append("empty_store_root")
    for p in entries:
        if p.name not in allowed:
            failures.append(f"unexpected_root_entry:{p.name}")
        if p.is_symlink():
            failures.append(f"unsafe_symlink:{p.relative_to(root).as_posix()}")
        if p.name.startswith(".building") or ".txn-" in p.name:
            failures.append("stale_transaction_entry")
    ver = root / "store_version.json"
    if not ver.exists():
        failures.append("store_version_missing")
    else:
        try:
            parse_store_version_bytes(ver.read_bytes())
        except Exception:
            failures.append("store_version_invalid")
    receipt_chunks = set()
    for d in (root / "datasets").glob("**/chunk=*") if (root / "datasets").exists() else []:
        chunks += 1
        try:
            kind = d.parts[d.parts.index("datasets") + 1]
            mf_obj, rows = read_and_validate_chunk(root, d)
            rel = d.relative_to(root).as_posix()
            for r in rows:
                k = (kind, row_key(kind, r))
                if k in keys:
                    failures.append("duplicate_committed_key" if keys[k] == r else "store_row_conflict")
                keys[k] = r
        except Exception as e:
            failures.append(str(e))
    for rr in (root / "imports").glob("**/import_receipt.json") if (root / "imports").exists() else []:
        receipts += 1
        try:
            receipt = parse_import_receipt_bytes(rr.read_bytes())
            sha = receipt.source_review_pack_sha256
            evzip = root / "evidence" / f"sha256={sha}" / "review_pack.zip"
            evref = root / "evidence" / f"sha256={sha}" / "evidence_reference.json"
            if not evzip.exists() or not evref.exists():
                failures.append(f"receipt_evidence_missing:{rr.relative_to(root).as_posix()}")
            elif hashlib.sha256(evzip.read_bytes()).hexdigest() != sha:
                failures.append(f"evidence_archive_sha256_mismatch:{sha}")
            else:
                try:
                    ref = parse_evidence_reference_bytes(evref.read_bytes())
                    if ref.run_id != receipt.run_id or ref.source_review_pack_sha256 != sha:
                        failures.append(f"evidence_reference_invalid:{evref.relative_to(root).as_posix()}:mismatch")
                except Exception as e:
                    failures.append(f"evidence_reference_invalid:{evref.relative_to(root).as_posix()}:{e}")
            for c in receipt.chunks:
                receipt_chunks.add(c.relative_path)
                if not (root / c.relative_path).exists():
                    failures.append("receipt_chunk_missing")
                else:
                    try:
                        read_and_validate_chunk(root, root / c.relative_path, expected_manifest=c)
                    except Exception as e:
                        failures.append(f"receipt_chunk_manifest_mismatch:{c.relative_path}:{e}")
        except Exception as e:
            failures.append(f"receipt_invalid:{rr.relative_to(root).as_posix()}:{e}")
    actual_chunks = {p.relative_to(root).as_posix() for p in (root / "datasets").glob("**/chunk=*")} if (root / "datasets").exists() else set()
    if chunks and not receipts:
        failures.append("chunks_without_receipt")
    if receipts and not chunks:
        failures.append("receipt_without_chunks")
    for rel in sorted(actual_chunks - receipt_chunks):
        failures.append(f"orphan_chunk:{rel}")
    actual_evidence_archives = {p.parent.relative_to(root).as_posix() for p in (root / "evidence").glob("sha256=*/review_pack.zip")} if (root / "evidence").exists() else set()
    actual_evidence_refs = {p.parent.relative_to(root).as_posix() for p in (root / "evidence").glob("sha256=*/evidence_reference.json")} if (root / "evidence").exists() else set()
    required_evidence = set()
    for rr in (root / "imports").glob("**/import_receipt.json") if (root / "imports").exists() else []:
        try:
            r = parse_import_receipt_bytes(rr.read_bytes())
            required_evidence.add(f"evidence/sha256={r.source_review_pack_sha256}")
        except Exception:
            pass
    orphan_evidence = (actual_evidence_archives | actual_evidence_refs) - required_evidence
    for rel in sorted(orphan_evidence):
        failures.append(f"orphan_evidence:{rel}")
    if (root / "evidence").exists() and not receipts:
        failures.append("evidence_without_receipt")
    dataset_counts = {}
    for (_kind, _key), _row in keys.items():
        dataset_counts[_kind] = dataset_counts.get(_kind, 0) + 1
    return MarketStoreAudit(not failures, tuple(failures), chunks, receipts, len(actual_evidence_archives), len(actual_evidence_refs), len(actual_chunks - receipt_chunks), len(orphan_evidence), sum(1 for f in failures if "stale_transaction" in f), dataset_counts)

# Sprint 06.4A.3.6 audit contract: store graph validation is fail-closed and deterministic.
