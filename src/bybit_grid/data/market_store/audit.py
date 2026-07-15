from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .models import MarketStoreAudit
from .parsing import (
    parse_evidence_reference_bytes,
    parse_import_receipt_bytes,
    parse_store_version_bytes,
)
from .paths import evidence_rel, receipt_rel
from .reader import read_and_validate_chunk, row_key


_ROOT_ENTRIES = frozenset({"store_version.json", "datasets", "imports", "evidence"})


def _scan_tree(root: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    failures: list[str] = []
    stack = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            failures.append(f"store_scan_invalid:{prefix or '.'}")
            continue
        for entry in children:
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                if entry.is_symlink():
                    entries[rel] = "symlink"
                    failures.append(f"unsafe_store_entry:{rel}")
                    failures.append(f"unsafe_symlink:{rel}")
                elif entry.is_dir(follow_symlinks=False):
                    entries[rel] = "directory"
                    stack.append((Path(entry.path), rel))
                elif entry.is_file(follow_symlinks=False):
                    entries[rel] = "file"
                else:
                    entries[rel] = "special"
                    failures.append(f"unsafe_store_entry:{rel}")
            except OSError:
                entries[rel] = "invalid"
                failures.append(f"unsafe_store_entry:{rel}")
    return entries, failures


def _expect(expected: dict[str, str], relative_path: str, entry_type: str) -> None:
    parts = relative_path.split("/")
    for index in range(1, len(parts)):
        expected.setdefault("/".join(parts[:index]), "directory")
    expected[relative_path] = entry_type


def _is_receipt_file(relative_path: str, entry_type: str) -> bool:
    parts = relative_path.split("/")
    return (
        entry_type == "file"
        and len(parts) == 4
        and parts[0] == "imports"
        and parts[1].startswith("run_id=")
        and parts[2].startswith("source_sha256=")
        and parts[3] == "import_receipt.json"
    )


def _is_chunk_dir(relative_path: str, entry_type: str) -> bool:
    parts = relative_path.split("/")
    return (
        entry_type == "directory"
        and len(parts) >= 3
        and parts[0] == "datasets"
        and parts[-1].startswith("chunk=")
    )


def _is_evidence_member(relative_path: str, entry_type: str, member: str) -> bool:
    parts = relative_path.split("/")
    return (
        entry_type == "file"
        and len(parts) == 3
        and parts[0] == "evidence"
        and parts[1].startswith("sha256=")
        and parts[2] == member
    )


def audit_market_store(root):
    root = Path(root)
    try:
        if root.is_symlink():
            return MarketStoreAudit(False, ("unsafe_store_root",), 0, 0)
        if not root.exists():
            return MarketStoreAudit(False, ("store_root_missing",), 0, 0)
        if not root.is_dir():
            return MarketStoreAudit(False, ("unsafe_store_root",), 0, 0)
    except OSError:
        return MarketStoreAudit(False, ("unsafe_store_root",), 0, 0)

    entries, failures = _scan_tree(root)
    if not entries:
        failures.append("empty_store_root")

    expected: dict[str, str] = {
        "store_version.json": "file",
        "datasets": "directory",
        "imports": "directory",
        "evidence": "directory",
    }
    for rel in entries:
        if "/" not in rel and rel not in _ROOT_ENTRIES:
            failures.append(f"unexpected_root_entry:{rel}")

    stale_paths = {
        rel
        for rel in entries
        if any(part.startswith(".building") or ".txn-" in part for part in rel.split("/"))
    }
    for rel in stale_paths:
        failures.append(f"stale_transaction_entry:{rel}")

    if entries.get("store_version.json") != "file":
        failures.append("store_version_missing")
    else:
        try:
            parse_store_version_bytes((root / "store_version.json").read_bytes())
        except Exception:
            failures.append("store_version_invalid")

    actual_chunk_dirs = {
        rel for rel, entry_type in entries.items() if _is_chunk_dir(rel, entry_type)
    }
    keys = {}

    receipt_files = {
        rel for rel, entry_type in entries.items() if _is_receipt_file(rel, entry_type)
    }
    receipt_identities: dict[tuple[str, str], str] = {}
    receipt_chunks: set[str] = set()
    required_evidence: set[str] = set()
    for rel in sorted(receipt_files):
        try:
            receipt = parse_import_receipt_bytes((root / rel).read_bytes())
        except Exception as exc:
            failures.append(f"receipt_invalid:{rel}:{exc}")
            continue

        canonical_receipt_rel = receipt_rel(
            receipt.run_id, receipt.source_review_pack_sha256
        ).as_posix()
        _expect(expected, canonical_receipt_rel, "file")
        if rel != canonical_receipt_rel:
            failures.append(f"receipt_path_mismatch:{rel}")
        identity = (receipt.run_id, receipt.source_review_pack_sha256)
        if identity in receipt_identities:
            failures.append(f"duplicate_receipt_identity:{rel}")
        else:
            receipt_identities[identity] = rel

        source_sha = receipt.source_review_pack_sha256
        evidence_dir_rel = evidence_rel(source_sha).as_posix()
        required_evidence.add(evidence_dir_rel)
        _expect(expected, f"{evidence_dir_rel}/review_pack.zip", "file")
        _expect(expected, f"{evidence_dir_rel}/evidence_reference.json", "file")

        archive_rel = f"{evidence_dir_rel}/review_pack.zip"
        reference_rel = f"{evidence_dir_rel}/evidence_reference.json"
        if entries.get(archive_rel) != "file" or entries.get(reference_rel) != "file":
            failures.append(f"receipt_evidence_missing:{rel}")
        else:
            try:
                archive_bytes = (root / archive_rel).read_bytes()
                if hashlib.sha256(archive_bytes).hexdigest() != source_sha:
                    failures.append(f"evidence_archive_sha256_mismatch:{source_sha}")
            except OSError:
                failures.append(f"evidence_archive_invalid:{archive_rel}")
            try:
                reference = parse_evidence_reference_bytes((root / reference_rel).read_bytes())
                if (
                    reference.run_id != receipt.run_id
                    or reference.source_review_pack_sha256 != source_sha
                ):
                    failures.append(f"evidence_reference_invalid:{reference_rel}:mismatch")
            except Exception as exc:
                failures.append(f"evidence_reference_invalid:{reference_rel}:{exc}")

        declared_chunks: set[str] = set()
        for manifest in receipt.chunks:
            chunk_rel = manifest.relative_path
            manifest_rel = f"{chunk_rel}/chunk_manifest.json"
            data_rel = f"{chunk_rel}/data.parquet"
            if chunk_rel in declared_chunks:
                failures.append(f"duplicate_receipt_chunk:{rel}:{chunk_rel}")
            declared_chunks.add(chunk_rel)
            receipt_chunks.add(chunk_rel)
            _expect(expected, chunk_rel, "directory")
            _expect(expected, manifest_rel, "file")
            _expect(expected, data_rel, "file")
            if entries.get(chunk_rel) != "directory":
                failures.append(f"receipt_chunk_missing:{chunk_rel}")
                continue
            if entries.get(manifest_rel) != "file" or entries.get(data_rel) != "file":
                continue
            try:
                _manifest, rows = read_and_validate_chunk(
                    root, root / chunk_rel, expected_manifest=manifest
                )
                kind = chunk_rel.split("/", 2)[1]
                for row in rows:
                    key = (kind, row_key(kind, row))
                    if key in keys:
                        failures.append(
                            "duplicate_committed_key"
                            if keys[key] == row
                            else "store_row_conflict"
                        )
                    keys[key] = row
                if any(
                    row["source_run_id"] != receipt.run_id
                    or row["source_review_pack_sha256"] != source_sha
                    for row in rows
                ):
                    failures.append(f"receipt_chunk_provenance_mismatch:{chunk_rel}")
            except Exception as exc:
                failures.append(f"receipt_chunk_manifest_mismatch:{chunk_rel}:{exc}")

    chunks = len(actual_chunk_dirs)
    receipts = len(receipt_files)
    if not chunks:
        failures.append("committed_chunks_missing")
    if not receipts:
        failures.append("import_receipts_missing")
    if chunks and not receipts:
        failures.append("chunks_without_receipt")
    if receipts and not chunks:
        failures.append("receipt_without_chunks")

    orphan_chunks = actual_chunk_dirs - receipt_chunks
    for rel in sorted(orphan_chunks):
        failures.append(f"orphan_chunk:{rel}")

    actual_evidence_archives = {
        str(Path(rel).parent).replace("\\", "/")
        for rel, entry_type in entries.items()
        if _is_evidence_member(rel, entry_type, "review_pack.zip")
    }
    actual_evidence_refs = {
        str(Path(rel).parent).replace("\\", "/")
        for rel, entry_type in entries.items()
        if _is_evidence_member(rel, entry_type, "evidence_reference.json")
    }
    orphan_evidence = (actual_evidence_archives | actual_evidence_refs) - required_evidence
    for rel in sorted(orphan_evidence):
        failures.append(f"orphan_evidence:{rel}")
    if (actual_evidence_archives or actual_evidence_refs) and not receipts:
        failures.append("evidence_without_receipt")

    for rel in sorted(set(entries) - set(expected)):
        failures.append(f"unexpected_store_entry:{rel}")
    for rel in sorted(set(expected) - set(entries)):
        failures.append(f"missing_store_entry:{rel}")
    for rel in sorted(set(entries) & set(expected)):
        if entries[rel] != expected[rel]:
            failures.append(f"store_entry_type_mismatch:{rel}")

    dataset_counts = {}
    for (kind, _key), _row in keys.items():
        dataset_counts[kind] = dataset_counts.get(kind, 0) + 1
    canonical_failures = tuple(sorted(set(failures)))
    return MarketStoreAudit(
        not canonical_failures,
        canonical_failures,
        chunks,
        receipts,
        len(actual_evidence_archives),
        len(actual_evidence_refs),
        len(orphan_chunks),
        len(orphan_evidence),
        len(stale_paths),
        dataset_counts,
    )
