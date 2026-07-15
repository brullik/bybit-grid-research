from __future__ import annotations

import hashlib
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import stat
import zipfile

import pytest

from bybit_grid.data.market_store import evidence as seed_evidence
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.evidence import (
    check_seed_review_pack,
    make_seed_review_pack,
)
from bybit_grid.data.market_store.models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    MarketStoreError,
    StoreEvidenceReference,
    StoreImportReceipt,
    StoreVersion,
)
from bybit_grid.data.market_store.paths import evidence_rel, receipt_rel
from bybit_grid.data.market_store.writer import write_chunk_atomic
from bybit_grid.data.public_batch.models import PublicBatchError


SEED_SCHEMA = "bybit_public_parquet_seed_review_pack_v1"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

RUN_ID = "bybit_public_batch_063b_btcusdt_v1"


def _row(source_sha: str):
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "open_time_ms": 0,
        "open": Decimal("1"),
        "high": Decimal("1"),
        "low": Decimal("1"),
        "close": Decimal("1"),
        "volume": Decimal("2"),
        "turnover": Decimal("2"),
        "closed_bool": True,
        "source_run_id": RUN_ID,
        "source_review_pack_sha256": source_sha,
        "source_plan_id": "trade_primary_1000",
        "source_name": "recorded_public_responses.jsonl",
        "storage_schema_version": STORE_SCHEMA_VERSION,
    }


def build_store(root, source_bytes=b"synthetic-public-review-pack"):
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    root.mkdir()
    (root / "store_version.json").write_bytes(
        canonical_json_bytes(StoreVersion(STORE_SCHEMA_VERSION))
    )
    manifest = write_chunk_atomic(
        root,
        MarketDatasetKind.trade_kline_1m,
        [_row(source_sha)],
    )
    (root / ".building").rmdir()
    evidence_dir = root / evidence_rel(source_sha)
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "review_pack.zip").write_bytes(source_bytes)
    (evidence_dir / "evidence_reference.json").write_bytes(
        canonical_json_bytes(StoreEvidenceReference(RUN_ID, source_sha))
    )
    receipt = StoreImportReceipt(
        RUN_ID,
        source_sha,
        (manifest,),
        STORE_SCHEMA_VERSION,
    )
    receipt_path = root / receipt_rel(RUN_ID, source_sha)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    return source_sha


def _regular_info(name):
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _typed_info(name, mode):
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = mode << 16
    return info


def _write_zip(path, payloads, *, modes=None):
    modes = modes or {}
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(payloads):
            mode = modes.get(name)
            info = _regular_info(name) if mode is None else _typed_info(name, mode)
            archive.writestr(info, payloads[name])


def _manifest(source_sha, members):
    return {
        "members": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()},
        "run_id": RUN_ID,
        "schema": SEED_SCHEMA,
        "source_review_pack_sha256": source_sha,
        "storage_schema_version": STORE_SCHEMA_VERSION,
    }


def _manual_pack(root, path, source_sha):
    members = {
        file.relative_to(root).as_posix(): file.read_bytes()
        for file in sorted(root.rglob("*"))
        if file.is_file()
    }
    members["store_audit.json"] = canonical_json_bytes(audit_market_store(root))
    payloads = dict(members)
    payloads["review_pack_manifest.json"] = canonical_json_bytes(_manifest(source_sha, members))
    _write_zip(path, payloads)
    return payloads


def _load_pack(path):
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _canonical_pack(tmp_path):
    root = tmp_path / "store"
    source_sha = build_store(root)
    pack = tmp_path / "seed.zip"
    payloads = _manual_pack(root, pack, source_sha)
    return root, source_sha, pack, payloads


def _accept_nested(monkeypatch, calls=None):
    def fake(path, run_id):
        if calls is not None:
            calls.append((path.read_bytes(), run_id))
        return {"ok": True}

    monkeypatch.setattr(seed_evidence, "validate_review_pack", fake, raising=False)


def _assert_error(code, callable_):
    with pytest.raises(MarketStoreError) as caught:
        callable_()
    assert str(caught.value) == code


def _assert_no_seed_temps(root):
    assert list(root.rglob(".bybit-grid-seed-*.tmp")) == []
    assert list(root.rglob("seed.zip.tmp")) == []


def test_canonical_builder_roundtrip_and_identity(tmp_path, monkeypatch):
    root = tmp_path / "store"
    source_sha = build_store(root)
    _accept_nested(monkeypatch)
    pack = make_seed_review_pack(root, tmp_path / "seed.zip")
    result = check_seed_review_pack(pack)
    assert result == {
        "ok": True,
        "run_id": RUN_ID,
        "source_review_pack_sha256": source_sha,
        "storage_schema_version": STORE_SCHEMA_VERSION,
        "member_count": 7,
    }


def test_builder_emits_exact_canonical_manifest_and_hash_set(tmp_path, monkeypatch):
    root = tmp_path / "store"
    source_sha = build_store(root)
    _accept_nested(monkeypatch)
    pack = make_seed_review_pack(root, tmp_path / "seed.zip")
    payloads = _load_pack(pack)
    manifest_bytes = payloads.pop("review_pack_manifest.json")
    manifest = json.loads(manifest_bytes)
    assert manifest_bytes == canonical_json_bytes(manifest)
    assert set(manifest) == {
        "members",
        "run_id",
        "schema",
        "source_review_pack_sha256",
        "storage_schema_version",
    }
    assert manifest["schema"] == SEED_SCHEMA
    assert manifest["run_id"] == RUN_ID
    assert manifest["source_review_pack_sha256"] == source_sha
    assert manifest["storage_schema_version"] == STORE_SCHEMA_VERSION
    assert manifest["members"] == {
        name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()
    }


def test_builder_emits_sorted_explicit_regular_members(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    pack = make_seed_review_pack(root, tmp_path / "seed.zip")
    with zipfile.ZipFile(pack) as archive:
        infos = archive.infolist()
    assert [info.filename for info in infos] == sorted(info.filename for info in infos)
    assert all(info.date_time == FIXED_ZIP_TIME for info in infos)
    assert all(stat.S_ISREG(info.external_attr >> 16) for info in infos)
    assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
    assert all(info.compress_size == info.file_size for info in infos)
    assert all(info.create_version == 20 for info in infos)
    assert all(info.extract_version == 20 for info in infos)


def test_manual_canonical_pack_is_accepted(tmp_path, monkeypatch):
    _root, source_sha, pack, payloads = _canonical_pack(tmp_path)
    _accept_nested(monkeypatch)
    result = check_seed_review_pack(pack)
    assert result["ok"] is True
    assert result["source_review_pack_sha256"] == source_sha
    assert result["member_count"] == len(payloads) - 1


@pytest.mark.parametrize(
    "bad_name",
    [
        "/absolute",
        "../escape",
        "a/../escape",
        "a/./member",
        "a//member",
        "C:/drive",
        "a\\member",
        "a/\x01member",
    ],
)
def test_all_nonportable_member_paths_are_rejected(tmp_path, bad_name):
    _root, source_sha, pack, payloads = _canonical_pack(tmp_path)
    payloads[bad_name] = b"bad"
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"][bad_name] = hashlib.sha256(b"bad").hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("unsafe_zip_path", lambda: check_seed_review_pack(pack))


def test_duplicate_member_is_rejected_before_payload_read(tmp_path, monkeypatch):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    name = next(name for name in payloads if name != "review_pack_manifest.json")
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(pack, "a") as archive:
            archive.writestr(_regular_info(name), payloads[name])
    _assert_error("duplicate_zip_member", lambda: check_seed_review_pack(pack))


@pytest.mark.parametrize(
    "mode",
    [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o700, stat.S_IFIFO | 0o600],
)
def test_non_regular_zip_entries_are_rejected_before_payload_read(tmp_path, monkeypatch, mode):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    payloads["bad-entry"] = b"payload"
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"]["bad-entry"] = hashlib.sha256(b"payload").hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads, modes={"bad-entry": mode})
    original = zipfile.ZipFile.read
    reads = []

    def tracked(self, name, *args, **kwargs):
        reads.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", tracked)
    _assert_error("zip_member_type_invalid", lambda: check_seed_review_pack(pack))
    assert reads == []


def test_manifest_missing_member_is_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    victim = next(
        name for name in payloads if name not in {"review_pack_manifest.json", "store_audit.json"}
    )
    del payloads[victim]
    _write_zip(pack, payloads)
    _assert_error("seed_manifest_member_set_invalid", lambda: check_seed_review_pack(pack))


def test_manifest_extra_member_is_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    payloads["extra"] = b"extra"
    _write_zip(pack, payloads)
    _assert_error("seed_manifest_member_set_invalid", lambda: check_seed_review_pack(pack))


def test_manifest_hash_mismatch_is_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    victim = next(
        name for name in payloads if name not in {"review_pack_manifest.json", "store_audit.json"}
    )
    payloads[victim] += b"tamper"
    _write_zip(pack, payloads)
    _assert_error("zip_member_hash_mismatch", lambda: check_seed_review_pack(pack))


def test_noncanonical_manifest_bytes_are_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    manifest = json.loads(payloads["review_pack_manifest.json"])
    payloads["review_pack_manifest.json"] = json.dumps(manifest, indent=2).encode()
    _write_zip(pack, payloads)
    _assert_error("seed_manifest_canonical_mismatch", lambda: check_seed_review_pack(pack))


def test_duplicate_manifest_key_is_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    canonical = payloads["review_pack_manifest.json"]
    payloads["review_pack_manifest.json"] = canonical.replace(
        b'{"members":', b'{"schema":"duplicate","members":', 1
    )
    _write_zip(pack, payloads)
    _assert_error("seed_manifest:json_duplicate_key", lambda: check_seed_review_pack(pack))


def test_rehashed_fake_store_version_is_rejected_by_graph_audit(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    payloads["store_version.json"] = b'{"storage_schema_version":"fake"}\n'
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"]["store_version.json"] = hashlib.sha256(
        payloads["store_version.json"]
    ).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("seed_store_audit_failed", lambda: check_seed_review_pack(pack))


def test_rehashed_moved_receipt_is_rejected_by_graph_audit(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    receipt = next(name for name in payloads if name.endswith("/import_receipt.json"))
    moved = "imports/run_id=alias/source_sha256=" + "0" * 64 + "/import_receipt.json"
    payloads[moved] = payloads.pop(receipt)
    manifest = json.loads(payloads["review_pack_manifest.json"])
    del manifest["members"][receipt]
    manifest["members"][moved] = hashlib.sha256(payloads[moved]).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("seed_store_audit_failed", lambda: check_seed_review_pack(pack))


def test_rehashed_tampered_store_audit_is_rejected_by_recomputation(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    payloads["store_audit.json"] = b'{"ok":true}\n'
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"]["store_audit.json"] = hashlib.sha256(
        payloads["store_audit.json"]
    ).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("seed_store_audit_mismatch", lambda: check_seed_review_pack(pack))


def test_nested_public_pack_is_validated_with_receipt_identity(tmp_path, monkeypatch):
    _root, source_sha, pack, _payloads = _canonical_pack(tmp_path)
    calls = []
    _accept_nested(monkeypatch, calls)
    check_seed_review_pack(pack)
    assert calls == [(b"synthetic-public-review-pack", RUN_ID)]
    assert hashlib.sha256(calls[0][0]).hexdigest() == source_sha


def test_nested_public_pack_failure_is_normalized(tmp_path, monkeypatch):
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)

    def reject(_path, _run_id):
        raise PublicBatchError("semantic_fake")

    monkeypatch.setattr(seed_evidence, "validate_review_pack", reject, raising=False)
    _assert_error("nested_public_review_pack_invalid", lambda: check_seed_review_pack(pack))


def test_corrupt_zip_native_error_is_normalized(tmp_path):
    pack = tmp_path / "bad.zip"
    pack.write_bytes(b"not-a-zip")
    _assert_error("seed_zip_invalid", lambda: check_seed_review_pack(pack))


def test_outer_pack_symlink_is_rejected(tmp_path, monkeypatch):
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)
    alias = tmp_path / "alias.zip"
    alias.symlink_to(pack)
    _assert_error("unsafe_seed_pack_path", lambda: check_seed_review_pack(alias))


def test_outer_pack_fifo_rebind_before_open_is_rejected_without_blocking(tmp_path, monkeypatch):
    assert "_open_regular_no_follow" in check_seed_review_pack.__globals__
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)
    replacement = tmp_path / "replacement.fifo"
    os.mkfifo(replacement)
    original_lstat = Path.lstat
    pack_lstat_calls = 0

    def replace_after_helper_lstat(path):
        nonlocal pack_lstat_calls
        result = original_lstat(path)
        if path == pack:
            pack_lstat_calls += 1
            if pack_lstat_calls == 2:
                os.replace(replacement, pack)
        return result

    class BlockedOpen(BaseException):
        pass

    def reject_blocked_open(_signum, _frame):
        raise BlockedOpen

    monkeypatch.setattr(Path, "lstat", replace_after_helper_lstat)
    previous_handler = signal.signal(signal.SIGALRM, reject_blocked_open)
    signal.setitimer(signal.ITIMER_REAL, 0.5)
    try:
        try:
            _assert_error("unsafe_seed_pack_path", lambda: check_seed_review_pack(pack))
        except BlockedOpen:
            pytest.fail("outer-pack FIFO rebind blocked while opening the checker input")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)

    assert pack_lstat_calls == 2
    assert stat.S_ISFIFO(original_lstat(pack).st_mode)


def test_outer_pack_in_place_mutation_with_restored_mtime_is_rejected(tmp_path, monkeypatch):
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)
    before = pack.stat()
    observed_after_mutation = []

    def mutate_outer_pack(_nested_path, _run_id):
        with pack.open("r+b") as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(b"X" if first != b"X" else b"Y")
        os.utime(pack, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = pack.stat()
        observed_after_mutation.append((after.st_size, after.st_mtime_ns))
        return {"ok": True}

    monkeypatch.setattr(
        seed_evidence,
        "validate_review_pack",
        mutate_outer_pack,
        raising=False,
    )
    _assert_error("unsafe_seed_pack_path", lambda: check_seed_review_pack(pack))
    assert observed_after_mutation == [(before.st_size, before.st_mtime_ns)]


def test_outer_pack_pathname_rebind_during_validation_is_rejected(tmp_path, monkeypatch):
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)
    original_bytes = pack.read_bytes()
    replacement = tmp_path / "replacement.zip"
    replacement.write_bytes(original_bytes)
    original_inode = pack.stat().st_ino

    def rebind_outer_pack(_nested_path, _run_id):
        os.replace(replacement, pack)
        return {"ok": True}

    monkeypatch.setattr(
        seed_evidence,
        "validate_review_pack",
        rebind_outer_pack,
        raising=False,
    )
    _assert_error("unsafe_seed_pack_path", lambda: check_seed_review_pack(pack))
    assert pack.stat().st_ino != original_inode
    assert pack.read_bytes() == original_bytes


def test_destination_inside_store_is_rejected_before_writes(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    dest = root / "seed.zip"
    _assert_error("destination_inside_store", lambda: make_seed_review_pack(root, dest))
    assert not dest.exists()
    _assert_no_seed_temps(tmp_path)


def test_destination_through_symlinked_parent_into_store_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    alias = tmp_path / "store-alias"
    alias.symlink_to(root, target_is_directory=True)
    dest = alias / "seed.zip"
    _assert_error("destination_inside_store", lambda: make_seed_review_pack(root, dest))
    assert not (root / "seed.zip").exists()
    _assert_no_seed_temps(tmp_path)


@pytest.mark.parametrize(
    "destination_kind",
    ["filesystem_root", "current_directory", "parent_directory", "named_directory"],
)
def test_destination_shape_is_rejected_before_store_audit(tmp_path, monkeypatch, destination_kind):
    root = tmp_path / "store"
    build_store(root)
    before = audit_market_store(root)
    named_directory = tmp_path / "destination-directory"
    named_directory.mkdir()
    destinations = {
        "filesystem_root": Path("/"),
        "current_directory": Path("."),
        "parent_directory": Path(".."),
        "named_directory": named_directory,
    }
    monkeypatch.chdir(tmp_path)

    def forbidden_audit(_root):
        raise AssertionError("destination shape must be validated before store audit")

    monkeypatch.setattr(seed_evidence, "audit_market_store", forbidden_audit)
    _assert_error(
        "unsafe_seed_destination",
        lambda: make_seed_review_pack(root, destinations[destination_kind]),
    )
    assert audit_market_store(root) == before
    assert not (root / "seed.zip").exists()
    _assert_no_seed_temps(tmp_path)


def test_destination_parent_must_already_exist(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    destination = tmp_path / "missing-parent" / "seed.zip"

    def forbidden_audit(_root):
        raise AssertionError("destination parent must be validated before store audit")

    monkeypatch.setattr(seed_evidence, "audit_market_store", forbidden_audit)
    _assert_error(
        "unsafe_seed_destination",
        lambda: make_seed_review_pack(root, destination),
    )
    assert not destination.parent.exists()
    assert not destination.exists()
    _assert_no_seed_temps(tmp_path)


@pytest.mark.parametrize("entry_kind", ["symlink", "fifo"])
def test_existing_nonregular_destination_is_rejected_before_store_audit(
    tmp_path, monkeypatch, entry_kind
):
    root = tmp_path / "store"
    build_store(root)
    outside = tmp_path / "outside-target"
    outside.write_bytes(b"unchanged")
    destination = tmp_path / "seed.zip"
    if entry_kind == "symlink":
        destination.symlink_to(outside)
    else:
        os.mkfifo(destination)

    def forbidden_audit(_root):
        raise AssertionError("destination entry type must be checked before store audit")

    monkeypatch.setattr(seed_evidence, "audit_market_store", forbidden_audit)
    _assert_error(
        "unsafe_seed_destination",
        lambda: make_seed_review_pack(root, destination),
    )
    assert outside.read_bytes() == b"unchanged"
    if entry_kind == "symlink":
        assert destination.is_symlink()
    else:
        assert stat.S_ISFIFO(destination.lstat().st_mode)
    _assert_no_seed_temps(tmp_path)


def test_builder_failure_preserves_destination_and_removes_temp(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    dest = tmp_path / "seed.zip"
    dest.write_bytes(b"previous")
    _accept_nested(monkeypatch)

    def reject(_path):
        raise MarketStoreError("injected_seed_check_failure")

    monkeypatch.setattr(seed_evidence, "check_seed_review_pack", reject)
    _assert_error("injected_seed_check_failure", lambda: make_seed_review_pack(root, dest))
    assert dest.read_bytes() == b"previous"
    _assert_no_seed_temps(tmp_path)


@pytest.mark.parametrize("metadata_kind", ["archive_comment", "member_extra", "member_comment"])
def test_unmanifested_zip_metadata_is_rejected(tmp_path, metadata_kind):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    if metadata_kind == "archive_comment":
        with zipfile.ZipFile(pack, "a") as archive:
            archive.comment = b"hidden"
    else:
        with zipfile.ZipFile(pack, "w") as archive:
            for name in sorted(payloads):
                info = _regular_info(name)
                if name == "store_version.json":
                    if metadata_kind == "member_extra":
                        info.extra = b"\xca\xfe\x02\x00hi"
                    else:
                        info.comment = b"hidden"
                archive.writestr(info, payloads[name])
    _assert_error("seed_zip_metadata_invalid", lambda: check_seed_review_pack(pack))


@pytest.mark.parametrize(
    "metadata_kind",
    [
        "member_timestamp",
        "member_order",
        "member_mode",
        "member_compression",
        "member_create_system",
        "member_zip64_version",
        "archive_prefix",
        "archive_trailer",
    ],
)
def test_noncanonical_zip_envelope_is_rejected(tmp_path, metadata_kind):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    if metadata_kind in {"archive_prefix", "archive_trailer"}:
        canonical = pack.read_bytes()
        if metadata_kind == "archive_prefix":
            pack.write_bytes(b"unmanifested-prefix" + canonical)
        else:
            pack.write_bytes(canonical + b"unmanifested-trailer")
    else:
        names = sorted(payloads)
        if metadata_kind == "member_order":
            names.reverse()
        with zipfile.ZipFile(pack, "w") as archive:
            for index, name in enumerate(names):
                info = _regular_info(name)
                if index == 0:
                    if metadata_kind == "member_timestamp":
                        info.date_time = (1980, 1, 2, 0, 0, 0)
                    elif metadata_kind == "member_mode":
                        info.external_attr = (stat.S_IFREG | 0o777) << 16
                    elif metadata_kind == "member_compression":
                        info.compress_type = zipfile.ZIP_DEFLATED
                    elif metadata_kind == "member_create_system":
                        info.create_system = 0
                    elif metadata_kind == "member_zip64_version":
                        info.create_version = 45
                        info.extract_version = 45
                archive.writestr(info, payloads[name])
    _assert_error("seed_zip_metadata_invalid", lambda: check_seed_review_pack(pack))


def test_orphan_gap_between_local_zip_records_is_rejected(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    gap = b"unmanifested-local-record-gap"
    first_record_end = None
    with zipfile.ZipFile(pack, "w") as archive:
        for index, name in enumerate(sorted(payloads)):
            archive.writestr(_regular_info(name), payloads[name])
            if index == 0:
                first_record_end = archive.start_dir
                archive.fp.write(gap)
                archive.start_dir = archive.fp.tell()
    raw = pack.read_bytes()
    with zipfile.ZipFile(pack) as archive:
        infos = archive.infolist()
    assert raw[first_record_end : first_record_end + len(gap)] == gap
    assert infos[1].header_offset == first_record_end + len(gap)
    _assert_error("seed_zip_metadata_invalid", lambda: check_seed_review_pack(pack))


def test_zip_resource_envelope_constants_are_exact():
    production_globals = make_seed_review_pack.__globals__
    names = (
        "_MAX_ARCHIVE_BYTES",
        "_MAX_MEMBER_COUNT",
        "_MAX_MEMBER_BYTES",
        "_MAX_TOTAL_UNCOMPRESSED_BYTES",
        "_MAX_CONTROL_MEMBER_BYTES",
        "_MAX_MEMBER_NAME_BYTES",
        "_MAX_CENTRAL_DIRECTORY_BYTES",
    )
    assert tuple(production_globals[name] for name in names) == (
        512 * 1024 * 1024,
        4096,
        128 * 1024 * 1024,
        512 * 1024 * 1024,
        4 * 1024 * 1024,
        1024,
        8 * 1024 * 1024,
    )


@pytest.mark.parametrize(
    "limit_name",
    [
        "_MAX_ARCHIVE_BYTES",
        "_MAX_MEMBER_COUNT",
        "_MAX_MEMBER_BYTES",
        "_MAX_TOTAL_UNCOMPRESSED_BYTES",
        "_MAX_CONTROL_MEMBER_BYTES",
        "_MAX_MEMBER_NAME_BYTES",
        "_MAX_CENTRAL_DIRECTORY_BYTES",
    ],
)
def test_zip_resource_limit_is_rejected_before_payload_reads(tmp_path, monkeypatch, limit_name):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    raw_pack = pack.read_bytes()
    eocd_offset = raw_pack.rfind(b"PK\x05\x06")
    central_directory_size = int.from_bytes(
        raw_pack[eocd_offset + 12 : eocd_offset + 16],
        "little",
    )
    controls = {
        name: data
        for name, data in payloads.items()
        if name in {"review_pack_manifest.json", "store_audit.json"}
    }
    below_canonical = {
        "_MAX_ARCHIVE_BYTES": pack.stat().st_size - 1,
        "_MAX_MEMBER_COUNT": len(payloads) - 1,
        "_MAX_MEMBER_BYTES": max(map(len, payloads.values())) - 1,
        "_MAX_TOTAL_UNCOMPRESSED_BYTES": sum(map(len, payloads.values())) - 1,
        "_MAX_CONTROL_MEMBER_BYTES": max(map(len, controls.values())) - 1,
        "_MAX_MEMBER_NAME_BYTES": max(len(name.encode()) for name in payloads) - 1,
        "_MAX_CENTRAL_DIRECTORY_BYTES": central_directory_size - 1,
    }
    monkeypatch.setattr(
        seed_evidence,
        limit_name,
        below_canonical[limit_name],
        raising=False,
    )
    payload_opens = []

    def forbidden_payload_open(_archive, member, *_args, **_kwargs):
        payload_opens.append(member)
        raise AssertionError("resource envelope must be checked before payload reads")

    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden_payload_open)
    zipfile_constructions = []
    raw_preflight_limits = {
        "_MAX_ARCHIVE_BYTES",
        "_MAX_CENTRAL_DIRECTORY_BYTES",
        "_MAX_MEMBER_COUNT",
        "_MAX_MEMBER_NAME_BYTES",
    }
    if limit_name in raw_preflight_limits:

        def forbidden_zipfile_construction(*args, **kwargs):
            zipfile_constructions.append((args, kwargs))
            raise AssertionError("raw resource bounds must precede ZipFile construction")

        monkeypatch.setattr(zipfile, "ZipFile", forbidden_zipfile_construction)
    _assert_error("seed_zip_limits_invalid", lambda: check_seed_review_pack(pack))
    assert payload_opens == []
    assert zipfile_constructions == []


def test_builder_resource_preflight_preserves_destination(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    destination = tmp_path / "seed.zip"
    destination.write_bytes(b"previous")
    monkeypatch.setattr(
        seed_evidence,
        "_MAX_TOTAL_UNCOMPRESSED_BYTES",
        1,
        raising=False,
    )

    def forbidden_temp_creation(_directory_fd):
        raise AssertionError("resource limits must be checked before temp creation")

    monkeypatch.setattr(
        seed_evidence,
        "_create_temp_entry",
        forbidden_temp_creation,
    )
    _assert_error(
        "seed_zip_limits_invalid",
        lambda: make_seed_review_pack(root, destination),
    )
    assert destination.read_bytes() == b"previous"
    _assert_no_seed_temps(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema", "wrong", "seed_schema_invalid"),
        ("storage_schema_version", "wrong", "seed_storage_schema_invalid"),
        ("run_id", "../unsafe", "seed_run_id_invalid"),
        ("run_id", True, "seed_run_id_invalid"),
        ("source_review_pack_sha256", "A" * 64, "seed_source_sha256_invalid"),
        ("source_review_pack_sha256", True, "seed_source_sha256_invalid"),
    ],
)
def test_manifest_identity_values_are_strict(tmp_path, field, value, code):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest[field] = value
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error(code, lambda: check_seed_review_pack(pack))


def test_manifest_is_required_and_self_excluded(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    manifest_bytes = payloads.pop("review_pack_manifest.json")
    _write_zip(pack, payloads)
    _assert_error("seed_manifest_missing", lambda: check_seed_review_pack(pack))

    manifest = json.loads(manifest_bytes)
    manifest["members"]["review_pack_manifest.json"] = "0" * 64
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("seed_manifest_member_set_invalid", lambda: check_seed_review_pack(pack))


def test_casefold_and_parent_child_member_collisions_are_rejected(tmp_path):
    _root, _source_sha, pack, original = _canonical_pack(tmp_path)
    for name, data in [("STORE_VERSION.JSON", b"alias"), ("datasets", b"parent-file")]:
        payloads = dict(original)
        payloads[name] = data
        manifest = json.loads(payloads["review_pack_manifest.json"])
        manifest["members"][name] = hashlib.sha256(data).hexdigest()
        payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
        _write_zip(pack, payloads)
        _assert_error("zip_path_collision", lambda: check_seed_review_pack(pack))


def test_exactly_one_receipt_identity_is_required(tmp_path):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    receipt = next(name for name in payloads if name.endswith("/import_receipt.json"))
    duplicate = receipt.replace(f"run_id={RUN_ID}", "run_id=other")
    payloads[duplicate] = payloads[receipt]
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"][duplicate] = hashlib.sha256(payloads[duplicate]).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _assert_error("seed_receipt_count_invalid", lambda: check_seed_review_pack(pack))


def test_rehashed_nested_archive_tamper_is_rejected_even_with_mock_validator(tmp_path, monkeypatch):
    _root, _source_sha, pack, payloads = _canonical_pack(tmp_path)
    nested = next(name for name in payloads if name.endswith("/review_pack.zip"))
    payloads[nested] = b"rehashed-semantic-fake"
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"][nested] = hashlib.sha256(payloads[nested]).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(pack, payloads)
    _accept_nested(monkeypatch)
    _assert_error("seed_store_audit_failed", lambda: check_seed_review_pack(pack))


@pytest.mark.parametrize("entry_kind", ["symlink", "fifo"])
def test_builder_rejects_nonregular_source_without_reading_target(
    tmp_path, monkeypatch, entry_kind
):
    root = tmp_path / "store"
    build_store(root)
    accepted_audit = audit_market_store(root)
    outside = tmp_path / "outside-secret"
    outside.write_bytes(b"must-not-enter-pack")
    unsafe = root / "unsafe-entry"
    if entry_kind == "symlink":
        unsafe.symlink_to(outside)
    else:
        os.mkfifo(unsafe)
    monkeypatch.setattr(seed_evidence, "audit_market_store", lambda _root: accepted_audit)
    _accept_nested(monkeypatch)
    _assert_error(
        "seed_store_inventory_invalid",
        lambda: make_seed_review_pack(root, tmp_path / "seed.zip"),
    )
    assert not (tmp_path / "seed.zip").exists()
    assert outside.read_bytes() == b"must-not-enter-pack"


def test_builder_streams_source_files_after_audit(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    accepted_audit = audit_market_store(root)
    monkeypatch.setattr(seed_evidence, "audit_market_store", lambda _root: accepted_audit)
    _accept_nested(monkeypatch)

    def forbidden_read_bytes(_path):
        raise AssertionError("Path.read_bytes is forbidden after store audit")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    destination = tmp_path / "seed.zip"
    result = make_seed_review_pack(root, destination)
    assert result == destination
    assert destination.is_file()


def test_builder_rejects_temp_replacement_after_self_check(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    destination = tmp_path / "seed.zip"
    destination.write_bytes(b"previous")
    original_check = seed_evidence.check_seed_review_pack

    def replace_checked_path(path):
        result = original_check(path)
        replacement = tmp_path / "unchecked.zip"
        replacement.write_bytes(b"unchecked-bytes")
        os.replace(replacement, path)
        return result

    monkeypatch.setattr(seed_evidence, "check_seed_review_pack", replace_checked_path)
    _assert_error(
        "seed_temp_path_unsafe",
        lambda: make_seed_review_pack(root, destination),
    )
    assert destination.read_bytes() == b"previous"
    _assert_no_seed_temps(tmp_path)


def test_builder_rechecks_destination_parent_before_publish(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    publish_parent = tmp_path / "publish"
    publish_parent.mkdir()
    destination = publish_parent / "seed.zip"
    destination.write_bytes(b"previous")
    moved_parent = tmp_path / "publish-before-swap"
    original_check = seed_evidence.check_seed_review_pack

    def swap_parent_after_check(path):
        result = original_check(path)
        publish_parent.rename(moved_parent)
        publish_parent.symlink_to(root, target_is_directory=True)
        return result

    monkeypatch.setattr(seed_evidence, "check_seed_review_pack", swap_parent_after_check)
    _assert_error(
        "destination_inside_store",
        lambda: make_seed_review_pack(root, destination),
    )
    assert not (root / "seed.zip").exists()
    _assert_no_seed_temps(tmp_path)
    assert (moved_parent / "seed.zip").read_bytes() == b"previous"


def test_builder_normalizes_source_descriptor_close_error(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    destination = tmp_path / "seed.zip"
    destination.write_bytes(b"previous")
    original_fdopen = seed_evidence.os.fdopen
    close_failures = []

    class CloseFailingStream:
        def __init__(self, stream):
            self._stream = stream

        def __getattr__(self, name):
            return getattr(self._stream, name)

        def close(self):
            self._stream.close()
            close_failures.append("source-close")
            raise OSError("injected source descriptor close failure")

    def fail_first_source_close(fd, mode="r", *args, **kwargs):
        stream = original_fdopen(fd, mode, *args, **kwargs)
        if mode == "rb" and not close_failures:
            return CloseFailingStream(stream)
        return stream

    monkeypatch.setattr(seed_evidence.os, "fdopen", fail_first_source_close)
    _assert_error(
        "seed_store_inventory_invalid",
        lambda: make_seed_review_pack(root, destination),
    )
    assert close_failures == ["source-close"]
    assert destination.read_bytes() == b"previous"
    _assert_no_seed_temps(tmp_path)


def test_builder_attributes_zip_output_write_failure(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    destination = tmp_path / "seed.zip"
    destination.write_bytes(b"previous")
    write_attempts = []

    def fail_zip_output_write(_self, data):
        write_attempts.append(len(data))
        raise OSError("injected ZIP output write failure")

    monkeypatch.setattr(zipfile._ZipWriteFile, "write", fail_zip_output_write)
    _assert_error(
        "seed_pack_build_invalid",
        lambda: make_seed_review_pack(root, destination),
    )
    assert len(write_attempts) == 1
    assert destination.read_bytes() == b"previous"
    _assert_no_seed_temps(tmp_path)


def test_builder_preserves_relative_destination_return_value(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    monkeypatch.chdir(tmp_path)
    destination = Path("seed.zip")
    result = make_seed_review_pack(root, destination)
    assert result == destination
    assert destination.is_file()


def test_checker_streams_store_members_instead_of_zipfile_read(tmp_path, monkeypatch):
    _root, _source_sha, pack, _payloads = _canonical_pack(tmp_path)
    _accept_nested(monkeypatch)

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("ZipFile.read is forbidden for seed payloads")

    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden_read)
    assert check_seed_review_pack(pack)["ok"] is True


def test_builder_is_byte_deterministic_across_wall_clock(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    clock = [1_700_000_000]
    monkeypatch.setattr(zipfile.time, "time", lambda: clock[0])
    first = make_seed_review_pack(root, tmp_path / "first.zip")
    clock[0] += 10
    second = make_seed_review_pack(root, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
