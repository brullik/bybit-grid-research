from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .models import MarketStoreAudit, STORE_SCHEMA_VERSION
from .reader import _read_chunk, row_key
from .canonical import canonical_json_bytes


def audit_market_store(root):
    root = Path(root)
    failures = []
    chunks = 0
    receipts = 0
    keys = {}
    if not root.exists():
        return MarketStoreAudit(False, ("store_root_missing",), 0, 0)
    allowed = {"store_version.json", "datasets", "imports", "evidence", ".building"}
    entries = list(root.iterdir())
    if not entries:
        failures.append("empty_store_root")
    for p in entries:
        if p.name not in allowed:
            failures.append(f"unexpected_root_entry:{p.name}")
        if p.is_symlink():
            failures.append(f"unsafe_symlink:{p.relative_to(root).as_posix()}")
        if p.name == ".building" and p.exists() and any(p.iterdir()):
            failures.append("stale_building_entry")
    ver = root / "store_version.json"
    if not ver.exists():
        failures.append("store_version_missing")
    else:
        try:
            if ver.read_bytes() != canonical_json_bytes({"storage_schema_version": STORE_SCHEMA_VERSION}):
                failures.append("store_version_invalid")
        except Exception:
            failures.append("store_version_invalid")
    receipt_chunks = set()
    for d in (root / "datasets").glob("**/chunk=*") if (root / "datasets").exists() else []:
        chunks += 1
        try:
            kind = d.parts[d.parts.index("datasets") + 1]
            rows = _read_chunk(d, kind)
            mf = json.loads((d / "chunk_manifest.json").read_text())
            rel = d.relative_to(root).as_posix()
            if mf.get("relative_path") != rel:
                failures.append("chunk_path_mismatch")
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
            raw = json.loads(rr.read_text())
            if set(raw) != {"chunks", "run_id", "source_review_pack_sha256", "storage_schema_version"}:
                failures.append("receipt_schema_invalid")
                continue
            if raw["storage_schema_version"] != STORE_SCHEMA_VERSION:
                failures.append("receipt_schema_invalid")
            if rr.read_bytes() != canonical_json_bytes(raw):
                failures.append("receipt_canonical_mismatch")
            sha = raw.get("source_review_pack_sha256")
            evzip = root / "evidence" / str(sha) / "review_pack.zip"
            evref = root / "evidence" / str(sha) / "evidence_reference.json"
            if not evzip.exists() or not evref.exists():
                failures.append("receipt_evidence_missing")
            elif hashlib.sha256(evzip.read_bytes()).hexdigest() != sha:
                failures.append("evidence_archive_sha256_mismatch")
            for c in raw.get("chunks", []):
                rel = c.get("relative_path")
                receipt_chunks.add(rel)
                if not rel or not (root / rel).exists():
                    failures.append("receipt_chunk_missing")
        except Exception as e:
            failures.append(f"receipt_invalid:{e}")
    actual_chunks = {p.relative_to(root).as_posix() for p in (root / "datasets").glob("**/chunk=*")} if (root / "datasets").exists() else set()
    if chunks and not receipts:
        failures.append("chunks_without_receipt")
    if receipts and not chunks:
        failures.append("receipt_without_chunks")
    for rel in sorted(actual_chunks - receipt_chunks):
        failures.append(f"orphan_chunk:{rel}")
    if (root / "evidence").exists() and not receipts:
        failures.append("evidence_without_receipt")
    if chunks == 0:
        failures.append("no_committed_chunks")
    if receipts == 0:
        failures.append("no_import_receipts")
    return MarketStoreAudit(not failures, tuple(failures), chunks, receipts)
