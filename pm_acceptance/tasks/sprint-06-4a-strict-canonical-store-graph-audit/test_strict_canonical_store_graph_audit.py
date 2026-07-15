from __future__ import annotations

import hashlib
import os
import shutil
from decimal import Decimal
from pathlib import Path

from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    StoreEvidenceReference,
    StoreImportReceipt,
    StoreVersion,
)
from bybit_grid.data.market_store.parsing import parse_import_receipt_bytes
from bybit_grid.data.market_store.paths import evidence_rel, receipt_rel
from bybit_grid.data.market_store.writer import write_chunk_atomic


KIND = MarketDatasetKind.funding_rate
RUN_ID = "capture-001"
FUNDING_TIME_MS = 1_704_067_200_000
SOURCE_BYTES = b"synthetic-public-review-pack-v1\n"


def _funding_row(source_sha: str) -> dict[str, object]:
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "funding_time_ms": FUNDING_TIME_MS,
        "funding_rate": Decimal("0.0001"),
        "source_run_id": RUN_ID,
        "source_review_pack_sha256": source_sha,
        "source_plan_id": "funding_primary_backward_200",
        "source_name": "bybit_public_batch",
        "storage_schema_version": STORE_SCHEMA_VERSION,
    }


def _canonical_store(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "store"
    source_sha = hashlib.sha256(SOURCE_BYTES).hexdigest()
    manifest = write_chunk_atomic(root, KIND, (_funding_row(source_sha),))
    building = root / ".building"
    if building.exists():
        building.rmdir()

    (root / "store_version.json").write_bytes(
        canonical_json_bytes(StoreVersion(STORE_SCHEMA_VERSION))
    )

    evidence_dir = root / evidence_rel(source_sha)
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "review_pack.zip").write_bytes(SOURCE_BYTES)
    (evidence_dir / "evidence_reference.json").write_bytes(
        canonical_json_bytes(StoreEvidenceReference(RUN_ID, source_sha))
    )

    receipt_path = root / receipt_rel(RUN_ID, source_sha)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(
        canonical_json_bytes(StoreImportReceipt(RUN_ID, source_sha, (manifest,)))
    )
    return root, source_sha, receipt_path


def test_canonical_minimal_store_is_accepted_with_exact_graph_counts(tmp_path):
    root, _, _ = _canonical_store(tmp_path)

    audit = audit_market_store(root)

    assert audit.ok is True
    assert audit.failures == ()
    assert audit.chunk_count == 1
    assert audit.receipt_count == 1
    assert audit.evidence_archive_count == 1
    assert audit.evidence_reference_count == 1
    assert audit.orphan_chunk_count == 0
    assert audit.orphan_evidence_count == 0
    assert dict(audit.dataset_row_counts) == {KIND.value: 1}


def test_receipt_moved_under_wrong_run_id_is_rejected(tmp_path):
    root, source_sha, receipt = _canonical_store(tmp_path)
    moved = root / receipt_rel("wrong-run", source_sha)
    moved.parent.mkdir(parents=True)
    receipt.replace(moved)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"receipt_path_mismatch:{moved.relative_to(root).as_posix()}" in audit.failures


def test_receipt_moved_under_wrong_source_sha_is_rejected(tmp_path):
    root, _, receipt = _canonical_store(tmp_path)
    wrong_sha = "b" * 64
    moved = root / receipt_rel(RUN_ID, wrong_sha)
    moved.parent.mkdir(parents=True)
    receipt.replace(moved)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"receipt_path_mismatch:{moved.relative_to(root).as_posix()}" in audit.failures


def test_alias_copy_of_receipt_is_rejected(tmp_path):
    root, source_sha, receipt = _canonical_store(tmp_path)
    alias = root / receipt_rel("alias-run", source_sha)
    alias.parent.mkdir(parents=True)
    shutil.copyfile(receipt, alias)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"receipt_path_mismatch:{alias.relative_to(root).as_posix()}" in audit.failures


def test_unexpected_nested_file_is_rejected(tmp_path):
    root, _, _ = _canonical_store(tmp_path)
    extra = root / "datasets" / "extra.bin"
    extra.write_bytes(b"not-store-data")

    audit = audit_market_store(root)

    assert audit.ok is False
    assert "unexpected_store_entry:datasets/extra.bin" in audit.failures


def test_unexpected_empty_nested_directory_is_rejected(tmp_path):
    root, _, _ = _canonical_store(tmp_path)
    extra = root / "datasets" / KIND.value / "orphan-empty"
    extra.mkdir(parents=True)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"unexpected_store_entry:{extra.relative_to(root).as_posix()}" in audit.failures


def test_missing_declared_chunk_member_is_rejected_by_exact_path(tmp_path):
    root, _, receipt_path = _canonical_store(tmp_path)
    receipt = parse_import_receipt_bytes(receipt_path.read_bytes())
    missing = root / receipt.chunks[0].relative_path / "data.parquet"
    missing.unlink()

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"missing_store_entry:{missing.relative_to(root).as_posix()}" in audit.failures


def test_nested_stale_transaction_directory_is_rejected(tmp_path):
    root, _, _ = _canonical_store(tmp_path)
    stale = root / "datasets" / ".txn-abandoned"
    stale.mkdir()

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"stale_transaction_entry:{stale.relative_to(root).as_posix()}" in audit.failures


def test_nested_special_entry_is_rejected(tmp_path):
    root, _, _ = _canonical_store(tmp_path)
    special = root / "datasets" / "unexpected.pipe"
    os.mkfifo(special)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"unsafe_store_entry:{special.relative_to(root).as_posix()}" in audit.failures


def test_evidence_symlink_is_rejected_without_reading_target(tmp_path, monkeypatch):
    root, source_sha, _ = _canonical_store(tmp_path)
    outside = tmp_path / "outside-review-pack.zip"
    outside.write_bytes(SOURCE_BYTES)
    link = root / evidence_rel(source_sha) / "review_pack.zip"
    link.unlink()
    link.symlink_to(outside)
    original_read_bytes = Path.read_bytes
    read_attempts = []

    def guarded_read_bytes(path):
        if path == link:
            read_attempts.append(path)
            raise AssertionError("symlink_target_read")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    audit = audit_market_store(root)

    assert audit.ok is False
    assert f"unsafe_store_entry:{link.relative_to(root).as_posix()}" in audit.failures
    assert read_attempts == []


def test_chunk_row_provenance_must_match_committing_receipt(tmp_path):
    root, source_sha, receipt_path = _canonical_store(tmp_path)
    shutil.rmtree(root / "datasets")
    row = _funding_row(source_sha)
    row["source_run_id"] = "different-capture"
    manifest = write_chunk_atomic(root, KIND, (row,))
    (root / ".building").rmdir()
    receipt_path.write_bytes(
        canonical_json_bytes(StoreImportReceipt(RUN_ID, source_sha, (manifest,)))
    )

    audit = audit_market_store(root)

    assert audit.ok is False
    assert (
        f"receipt_chunk_provenance_mismatch:{manifest.relative_path}"
        in audit.failures
    )


def test_duplicate_chunk_declaration_in_receipt_is_rejected(tmp_path):
    root, source_sha, receipt_path = _canonical_store(tmp_path)
    receipt = parse_import_receipt_bytes(receipt_path.read_bytes())
    manifest = receipt.chunks[0]
    receipt_path.write_bytes(
        canonical_json_bytes(
            StoreImportReceipt(RUN_ID, source_sha, (manifest, manifest))
        )
    )

    audit = audit_market_store(root)

    assert audit.ok is False
    assert (
        f"duplicate_receipt_chunk:{receipt_path.relative_to(root).as_posix()}"
        f":{manifest.relative_path}"
        in audit.failures
    )


def test_version_only_store_is_not_a_committed_store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    (root / "store_version.json").write_bytes(
        canonical_json_bytes(StoreVersion(STORE_SCHEMA_VERSION))
    )

    audit = audit_market_store(root)

    assert audit.ok is False
    assert "committed_chunks_missing" in audit.failures
    assert "import_receipts_missing" in audit.failures


def test_failures_are_sorted_unique_and_repeatable(tmp_path):
    root, _, _ = _canonical_store(tmp_path)
    (root / "z-extra").write_bytes(b"z")
    (root / "a-extra").write_bytes(b"a")

    first = audit_market_store(root)
    second = audit_market_store(root)

    assert first == second
    assert first.failures == tuple(sorted(set(first.failures)))
    assert "unexpected_store_entry:a-extra" in first.failures
    assert "unexpected_store_entry:z-extra" in first.failures
