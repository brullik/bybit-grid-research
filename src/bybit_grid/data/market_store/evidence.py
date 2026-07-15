from __future__ import annotations
import json
import zipfile
import hashlib
import os
from pathlib import Path
from .audit import audit_market_store
from .canonical import canonical_json_bytes
from .models import MarketStoreError


def _safe(n):
    if n.startswith("/") or ".." in n.split("/") or "\\" in n or ":" in n or not n:
        raise MarketStoreError("unsafe_zip_path")


def make_seed_review_pack(store_root, dest):
    store_root = Path(store_root)
    dest = Path(dest)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    aud0 = audit_market_store(store_root)
    if not aud0.ok:
        raise MarketStoreError("store_audit_failed")
    manifest = {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(store_root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(store_root).as_posix()
                _safe(rel)
                b = p.read_bytes()
                manifest[rel] = hashlib.sha256(b).hexdigest()
                z.writestr(rel, b)
        aud = canonical_json_bytes(audit_market_store(store_root).__dict__)
        manifest["store_audit.json"] = hashlib.sha256(aud).hexdigest()
        z.writestr("store_audit.json", aud)
        z.writestr("review_pack_manifest.json", canonical_json_bytes({"members": manifest}))
    check_seed_review_pack(tmp)
    os.replace(tmp, dest)
    return dest


def check_seed_review_pack(path):
    path = Path(path)
    if not path.exists():
        raise MarketStoreError("zip_missing")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise MarketStoreError("duplicate_zip_member")
        for n in names:
            _safe(n)
        raw_manifest = json.loads(z.read("review_pack_manifest.json"))
        if set(raw_manifest) != {"members"}:
            raise MarketStoreError("manifest_schema_invalid")
        man = raw_manifest["members"]
        if type(man) is not dict or not man:
            raise MarketStoreError("empty_manifest")
        if not any(str(n).startswith("store/") or str(n).startswith("datasets/") for n in man):
            raise MarketStoreError("semantic_store_members_missing")
        for n, h in man.items():
            if n not in names:
                raise MarketStoreError("missing_zip_member")
            if hashlib.sha256(z.read(n)).hexdigest() != h:
                raise MarketStoreError("zip_member_hash_mismatch")
        extra = set(names) - set(man) - {"review_pack_manifest.json"}
        if extra:
            raise MarketStoreError("extra_zip_member")
    return {"ok": True}

# Sprint 06.4A.3.6 evidence contract: semantic seed packs are checked beyond member hashes.
