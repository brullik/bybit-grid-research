from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import zipfile

import pytest

from bybit_grid.data.market_store import evidence as seed_evidence
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.evidence import make_seed_review_pack
from bybit_grid.data.market_store.models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    MarketStoreError,
    StoreEvidenceReference,
    StoreImportReceipt,
    StoreVersion,
)
from bybit_grid.data.market_store.parsing import parse_import_receipt_bytes
from bybit_grid.data.market_store.paths import evidence_rel, receipt_rel
from bybit_grid.data.market_store.writer import write_chunk_atomic
from bybit_grid.data.public_batch.models import PublicBatchError


RUN_ID = "bybit_public_batch_063b_btcusdt_v1"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_INSTALL_TEMP_GLOB = ".bybit-grid-seed-install-*.tmp"


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


def _build_store(root: Path, source_bytes: bytes):
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    root.mkdir()
    (root / "store_version.json").write_bytes(
        canonical_json_bytes(StoreVersion(STORE_SCHEMA_VERSION))
    )
    manifest = write_chunk_atomic(
        root,
        MarketDatasetKind.trade_kline_1m,
        (_row(source_sha),),
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


def _build_seed(tmp_path: Path):
    source_bytes = b"synthetic-public-review-pack-for-owner-install"
    source_root = tmp_path / "source-store"
    source_sha = _build_store(source_root, source_bytes)
    pack = make_seed_review_pack(source_root, tmp_path / "owner-seed.zip")
    return source_root, source_sha, source_bytes, pack


def _expected_receipt(source_root: Path, source_sha: str):
    path = source_root / receipt_rel(RUN_ID, source_sha)
    return parse_import_receipt_bytes(path.read_bytes())


def _install(pack, destination):
    installer = getattr(seed_evidence, "install_seed_review_pack", None)
    if installer is None:
        raise MarketStoreError("seed_install_unavailable")
    return installer(pack, destination)


def _assert_error(code, callable_):
    with pytest.raises(MarketStoreError) as caught:
        callable_()
    assert str(caught.value) == code


def _file_graph(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _assert_no_install_temps(root: Path):
    assert list(root.rglob(_INSTALL_TEMP_GLOB)) == []


def _stat_identity(path: Path):
    value = path.stat()
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _regular_info(name: str):
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _load_pack(path: Path):
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _write_pack(path: Path, payloads):
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(payloads):
            archive.writestr(_regular_info(name), payloads[name])


def _rehashed_semantic_tamper(pack: Path):
    payloads = _load_pack(pack)
    payloads["store_version.json"] = canonical_json_bytes({"storage_schema_version": "wrong"})
    manifest = json.loads(payloads["review_pack_manifest.json"])
    manifest["members"]["store_version.json"] = hashlib.sha256(
        payloads["store_version.json"]
    ).hexdigest()
    payloads["review_pack_manifest.json"] = canonical_json_bytes(manifest)
    _write_pack(pack, payloads)


def test_install_roundtrip_is_exact_and_audited(tmp_path):
    source_root, source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    expected_receipt = _expected_receipt(source_root, source_sha)

    result = _install(pack, destination)

    assert type(result) is StoreImportReceipt
    assert result == expected_receipt
    assert result.run_id == RUN_ID
    assert result.source_review_pack_sha256 == source_sha
    assert result.storage_schema_version == STORE_SCHEMA_VERSION
    assert result.chunks == expected_receipt.chunks
    assert _file_graph(destination) == _file_graph(source_root)
    audit = audit_market_store(destination)
    assert audit.ok, audit.failures


def test_relative_destination_installs_requested_target_and_returns_receipt(tmp_path, monkeypatch):
    source_root, source_sha, _source_bytes, pack = _build_seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    requested = Path("runtime-store")
    expected_receipt = _expected_receipt(source_root, source_sha)

    installer = getattr(seed_evidence, "install_seed_review_pack", None)
    if installer is None:
        raise MarketStoreError("seed_install_unavailable")
    result = installer(pack, destination_store_root=requested)

    assert result == expected_receipt
    assert audit_market_store(tmp_path / requested).ok is True


def test_install_excludes_control_members_and_special_entries(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"

    _install(pack, destination)

    installed_names = set(_file_graph(destination))
    assert "review_pack_manifest.json" not in installed_names
    assert "store_audit.json" not in installed_names
    for path in (destination, *destination.rglob("*")):
        mode = path.lstat().st_mode
        assert not path.is_symlink()
        if stat.S_ISDIR(mode):
            assert stat.S_IMODE(mode) == 0o700
        else:
            assert stat.S_ISREG(mode)
            assert stat.S_IMODE(mode) == 0o600


def test_install_binds_nested_validator_to_receipt_identity(tmp_path, monkeypatch):
    _source_root, _source_sha, source_bytes, pack = _build_seed(tmp_path)
    calls = []

    def accept_nested(path, run_id):
        calls.append((path.read_bytes(), run_id))
        return {"ok": True}

    monkeypatch.setattr(seed_evidence, "validate_review_pack", accept_nested)

    _install(pack, tmp_path / "runtime-store")

    assert calls == [(source_bytes, RUN_ID)]


def test_same_pack_installs_identical_fresh_stores(tmp_path):
    source_root, source_sha, _source_bytes, pack = _build_seed(tmp_path)
    first = tmp_path / "first-store"
    second = tmp_path / "second-store"
    expected_receipt = _expected_receipt(source_root, source_sha)

    first_receipt = _install(pack, first)
    second_receipt = _install(pack, second)

    assert first_receipt == second_receipt == expected_receipt
    assert _file_graph(first) == _file_graph(second)
    assert audit_market_store(first) == audit_market_store(second)


def test_install_does_not_mutate_source_archive(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    before_bytes = pack.read_bytes()
    before_identity = _stat_identity(pack)

    _install(pack, tmp_path / "runtime-store")

    assert pack.read_bytes() == before_bytes
    assert _stat_identity(pack) == before_identity


@pytest.mark.parametrize(
    "destination_shape",
    ("current_directory", "parent_directory", "filesystem_root", "bytes_path"),
)
def test_invalid_destination_shape_is_rejected(tmp_path, monkeypatch, destination_shape):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    destinations = {
        "current_directory": Path("."),
        "parent_directory": Path(".."),
        "filesystem_root": Path(tmp_path.anchor),
        "bytes_path": b"runtime-store",
    }

    _assert_error(
        "unsafe_seed_install_destination",
        lambda: _install(pack, destinations[destination_shape]),
    )
    _assert_no_install_temps(tmp_path)


def test_destination_parent_must_already_exist(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "missing-parent" / "runtime-store"

    _assert_error(
        "unsafe_seed_install_destination",
        lambda: _install(pack, destination),
    )

    assert not destination.parent.exists()
    _assert_no_install_temps(tmp_path)


@pytest.mark.parametrize(
    "entry_kind",
    ("regular_file", "directory", "symlink", "fifo"),
)
def test_existing_destination_is_never_replaced(tmp_path, entry_kind):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside-unchanged")
    if entry_kind == "regular_file":
        destination.write_bytes(b"owner-unchanged")
    elif entry_kind == "directory":
        destination.mkdir()
        (destination / "owner.txt").write_bytes(b"owner-unchanged")
    elif entry_kind == "symlink":
        destination.symlink_to(outside)
    else:
        os.mkfifo(destination)
    before_mode = destination.lstat().st_mode

    _assert_error(
        "seed_install_destination_exists",
        lambda: _install(pack, destination),
    )

    assert destination.lstat().st_mode == before_mode
    assert outside.read_bytes() == b"outside-unchanged"
    if entry_kind == "regular_file":
        assert destination.read_bytes() == b"owner-unchanged"
    elif entry_kind == "directory":
        assert (destination / "owner.txt").read_bytes() == b"owner-unchanged"
    _assert_no_install_temps(tmp_path)


def test_symlinked_destination_parent_is_rejected(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias = tmp_path / "parent-alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    destination = alias / "runtime-store"

    _assert_error(
        "unsafe_seed_install_destination",
        lambda: _install(pack, destination),
    )

    assert not (real_parent / destination.name).exists()
    _assert_no_install_temps(tmp_path)


def test_destination_parent_swap_before_publish_is_rejected(tmp_path, monkeypatch):
    source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    publish_parent = tmp_path / "publish-parent"
    publish_parent.mkdir()
    moved_parent = tmp_path / "moved-parent"
    destination = publish_parent / "runtime-store"
    original_validate = seed_evidence._validate_extracted_store

    def swap_parent_after_validation(root, audit_bytes, manifest):
        result = original_validate(root, audit_bytes, manifest)
        publish_parent.rename(moved_parent)
        publish_parent.symlink_to(source_root, target_is_directory=True)
        return result

    monkeypatch.setattr(
        seed_evidence,
        "_validate_extracted_store",
        swap_parent_after_validation,
    )

    _assert_error(
        "unsafe_seed_install_destination",
        lambda: _install(pack, destination),
    )

    assert not (source_root / destination.name).exists()
    assert not (moved_parent / destination.name).exists()
    _assert_no_install_temps(tmp_path)


def test_symlinked_source_pack_is_rejected_without_destination(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    alias = tmp_path / "owner-seed-alias.zip"
    alias.symlink_to(pack)
    destination = tmp_path / "runtime-store"

    _assert_error(
        "unsafe_seed_pack_path",
        lambda: _install(alias, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_fifo_source_rebind_before_open_is_rejected_without_blocking(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    replacement = tmp_path / "replacement.fifo"
    os.mkfifo(replacement)
    original_lstat = Path.lstat
    pack_lstat_calls = 0

    def replace_after_outer_preflight(path):
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

    monkeypatch.setattr(Path, "lstat", replace_after_outer_preflight)
    previous_handler = signal.signal(signal.SIGALRM, reject_blocked_open)
    signal.setitimer(signal.ITIMER_REAL, 0.5)
    try:
        try:
            _assert_error(
                "unsafe_seed_pack_path",
                lambda: _install(pack, tmp_path / "runtime-store"),
            )
        except BlockedOpen:
            pytest.fail("FIFO source rebind blocked the installer input open")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)

    assert pack_lstat_calls == 2
    assert stat.S_ISFIFO(original_lstat(pack).st_mode)
    _assert_no_install_temps(tmp_path)


def test_source_in_place_mutation_with_restored_mtime_is_rejected(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    before = pack.stat()

    def mutate_source(_nested_path, _run_id):
        with pack.open("r+b") as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(b"X" if first != b"X" else b"Y")
        os.utime(pack, ns=(before.st_atime_ns, before.st_mtime_ns))
        return {"ok": True}

    monkeypatch.setattr(seed_evidence, "validate_review_pack", mutate_source)

    _assert_error(
        "unsafe_seed_pack_path",
        lambda: _install(pack, tmp_path / "runtime-store"),
    )

    assert not (tmp_path / "runtime-store").exists()
    _assert_no_install_temps(tmp_path)


def test_source_pathname_rebind_during_validation_is_rejected(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    original_bytes = pack.read_bytes()
    original_inode = pack.stat().st_ino
    replacement = tmp_path / "replacement.zip"
    replacement.write_bytes(original_bytes)

    def rebind_source(_nested_path, _run_id):
        os.replace(replacement, pack)
        return {"ok": True}

    monkeypatch.setattr(seed_evidence, "validate_review_pack", rebind_source)

    _assert_error(
        "unsafe_seed_pack_path",
        lambda: _install(pack, tmp_path / "runtime-store"),
    )

    assert pack.stat().st_ino != original_inode
    assert pack.read_bytes() == original_bytes
    assert not (tmp_path / "runtime-store").exists()
    _assert_no_install_temps(tmp_path)


def test_corrupt_pack_failure_leaves_no_store_or_staging(tmp_path):
    pack = tmp_path / "corrupt.zip"
    pack.write_bytes(b"not-a-zip")
    destination = tmp_path / "runtime-store"

    _assert_error("seed_zip_invalid", lambda: _install(pack, destination))

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_raw_member_limit_fails_before_staging_creation(tmp_path, monkeypatch):
    pack = tmp_path / "too-many-members.zip"
    end_record = struct.pack(
        "<4s4H2LH",
        b"PK\x05\x06",
        0,
        0,
        4097,
        4097,
        0,
        0,
        0,
    )
    pack.write_bytes(end_record)
    destination = tmp_path / "runtime-store"

    def forbidden_staging(*_args, **_kwargs):
        raise AssertionError("raw preflight must complete before staging creation")

    monkeypatch.setattr(
        seed_evidence,
        "_create_seed_install_temp",
        forbidden_staging,
        raising=False,
    )

    _assert_error(
        "seed_zip_limits_invalid",
        lambda: _install(pack, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_metadata_limit_fails_before_staging_or_payload_reads(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"

    def reject_metadata_limits(_infos):
        raise MarketStoreError("seed_zip_limits_invalid")

    def forbidden_staging(*_args, **_kwargs):
        raise AssertionError("metadata preflight must complete before staging creation")

    def forbidden_payload(*_args, **_kwargs):
        raise AssertionError("metadata preflight must complete before payload reads")

    monkeypatch.setattr(seed_evidence, "_validate_zip_limits", reject_metadata_limits)
    monkeypatch.setattr(
        seed_evidence,
        "_create_seed_install_temp",
        forbidden_staging,
        raising=False,
    )
    monkeypatch.setattr(seed_evidence.zipfile.ZipFile, "open", forbidden_payload)

    _assert_error(
        "seed_zip_limits_invalid",
        lambda: _install(pack, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_existing_checker_raw_failure_precedes_temporary_store(tmp_path, monkeypatch):
    pack = tmp_path / "corrupt.zip"
    pack.write_bytes(b"not-a-zip")

    def forbidden_temporary_store(*_args, **_kwargs):
        raise AssertionError("checker temporary store created before raw preflight")

    monkeypatch.setattr(
        seed_evidence.tempfile,
        "TemporaryDirectory",
        forbidden_temporary_store,
    )

    _assert_error(
        "seed_zip_invalid",
        lambda: seed_evidence.check_seed_review_pack(pack),
    )


def test_rehashed_semantic_tamper_leaves_no_store_or_staging(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    _rehashed_semantic_tamper(pack)
    destination = tmp_path / "runtime-store"

    _assert_error("seed_store_audit_failed", lambda: _install(pack, destination))

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_extraction_failure_leaves_no_store_or_staging(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"

    def reject_extract(*_args, **_kwargs):
        raise MarketStoreError("injected_seed_extract_failure")

    monkeypatch.setattr(
        seed_evidence,
        "_write_seed_install_member",
        reject_extract,
        raising=False,
    )

    _assert_error(
        "injected_seed_extract_failure",
        lambda: _install(pack, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_cleanup_failure_overrides_and_chains_primary_failure(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    owner_file = tmp_path / "owner-file.txt"
    owner_file.write_bytes(b"owner-unchanged")
    owner_directory = tmp_path / "owner-directory"
    owner_directory.mkdir()
    (owner_directory / "sentinel.txt").write_bytes(b"sentinel-unchanged")

    def reject_extract(*_args, **_kwargs):
        raise MarketStoreError("injected_primary_failure")

    def reject_cleanup(*_args, **_kwargs):
        raise MarketStoreError("seed_install_cleanup_invalid")

    monkeypatch.setattr(
        seed_evidence,
        "_write_seed_install_member",
        reject_extract,
        raising=False,
    )
    monkeypatch.setattr(
        seed_evidence,
        "_cleanup_seed_install_temp",
        reject_cleanup,
        raising=False,
    )

    with pytest.raises(MarketStoreError) as caught:
        _install(pack, destination)

    assert str(caught.value) == "seed_install_cleanup_invalid"
    assert type(caught.value.__cause__) is MarketStoreError
    assert str(caught.value.__cause__) == "injected_primary_failure"
    assert not destination.exists()
    assert owner_file.read_bytes() == b"owner-unchanged"
    assert (owner_directory / "sentinel.txt").read_bytes() == b"sentinel-unchanged"


def test_staging_creation_cleanup_failure_is_not_suppressed(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    original_chmod = seed_evidence.os.chmod
    original_rmdir = seed_evidence.os.rmdir

    def reject_temp_chmod(path, *args, **kwargs):
        if str(path).startswith(".bybit-grid-seed-install-"):
            raise OSError("injected staging normalization failure")
        return original_chmod(path, *args, **kwargs)

    def reject_temp_rmdir(path, *args, **kwargs):
        if str(path).startswith(".bybit-grid-seed-install-"):
            raise OSError("injected staging cleanup failure")
        return original_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(seed_evidence.os, "chmod", reject_temp_chmod)
    monkeypatch.setattr(seed_evidence.os, "rmdir", reject_temp_rmdir)

    with pytest.raises(MarketStoreError) as caught:
        _install(pack, destination)

    assert str(caught.value) == "seed_install_cleanup_invalid"
    assert type(caught.value.__cause__) is MarketStoreError
    assert str(caught.value.__cause__) == "seed_install_temp_unsafe"
    assert not destination.exists()
    leftovers = list(tmp_path.glob(_INSTALL_TEMP_GLOB))
    assert len(leftovers) == 1
    original_rmdir(leftovers[0])


def test_publication_failure_leaves_no_store_or_staging(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"

    def reject_publish(_parent_fd, _source_name, _destination_name):
        raise OSError("injected publication failure")

    monkeypatch.setattr(
        seed_evidence,
        "_rename_seed_install_noreplace",
        reject_publish,
        raising=False,
    )

    _assert_error(
        "seed_install_publish_invalid",
        lambda: _install(pack, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_install_has_no_overwrite_capable_rename_fallback(tmp_path, monkeypatch):
    source_root, source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    expected_receipt = _expected_receipt(source_root, source_sha)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("overwrite-capable rename fallback is forbidden")

    monkeypatch.setattr(seed_evidence.os, "rename", forbidden_fallback)
    monkeypatch.setattr(seed_evidence.os, "replace", forbidden_fallback)

    result = _install(pack, destination)

    assert result == expected_receipt
    assert audit_market_store(destination).ok is True


def test_destination_wins_publication_race_without_overwrite(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    original_publish = getattr(seed_evidence, "_rename_seed_install_noreplace", None)

    def destination_wins(parent_fd, source_name, destination_name):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(destination_name, flags, 0o600, dir_fd=parent_fd)
        try:
            os.write(fd, b"owner-won-race")
        finally:
            os.close(fd)
        if original_publish is None:
            raise MarketStoreError("seed_install_unavailable")
        return original_publish(parent_fd, source_name, destination_name)

    monkeypatch.setattr(
        seed_evidence,
        "_rename_seed_install_noreplace",
        destination_wins,
        raising=False,
    )

    _assert_error(
        "seed_install_destination_exists",
        lambda: _install(pack, destination),
    )

    assert destination.read_bytes() == b"owner-won-race"
    _assert_no_install_temps(tmp_path)


def test_replaced_staging_root_is_rejected_before_publication(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    original_validate = seed_evidence._validate_extracted_store
    replaced = []

    def replace_staging_root(root, audit_bytes, manifest):
        result = original_validate(root, audit_bytes, manifest)
        root = Path(root)
        stable_parent = Path(os.path.realpath(root.parent))
        stable_root = stable_parent / root.name
        moved = stable_parent / "validated-stage-moved-aside"
        stable_root.rename(moved)
        stable_root.mkdir(mode=0o700)
        (stable_root / "attacker.txt").write_bytes(b"must-not-publish")
        replacement_identity = _stat_identity(stable_root)
        replaced.append((stable_root, moved, replacement_identity))
        return result

    monkeypatch.setattr(
        seed_evidence,
        "_validate_extracted_store",
        replace_staging_root,
    )

    _assert_error(
        "seed_install_temp_unsafe",
        lambda: _install(pack, destination),
    )

    assert len(replaced) == 1
    replacement, moved_owned_stage, replacement_identity = replaced[0]
    assert _stat_identity(replacement) == replacement_identity
    assert (replacement / "attacker.txt").read_bytes() == b"must-not-publish"
    assert not moved_owned_stage.exists()
    assert not destination.exists()


def test_nested_validator_rejection_leaves_no_store_or_staging(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"

    def reject_nested(_path, _run_id):
        raise PublicBatchError("rejected")

    monkeypatch.setattr(seed_evidence, "validate_review_pack", reject_nested)

    _assert_error(
        "nested_public_review_pack_invalid",
        lambda: _install(pack, destination),
    )

    assert not destination.exists()
    _assert_no_install_temps(tmp_path)


def test_second_install_preserves_first_committed_store(tmp_path):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    _install(pack, destination)
    before = _file_graph(destination)

    _assert_error(
        "seed_install_destination_exists",
        lambda: _install(pack, destination),
    )

    assert _file_graph(destination) == before
    assert audit_market_store(destination).ok is True
    _assert_no_install_temps(tmp_path)


def test_install_uses_one_source_descriptor_without_path_reopen(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    original_open = seed_evidence._open_regular_no_follow
    source_opens = []

    @contextmanager
    def counted_open(path, error_code):
        if Path(path) == pack:
            source_opens.append(Path(path))
        with original_open(path, error_code) as stream:
            yield stream

    monkeypatch.setattr(seed_evidence, "_open_regular_no_follow", counted_open)

    _install(pack, tmp_path / "runtime-store")

    assert source_opens == [pack]


def test_install_streams_archive_without_bulk_source_reads(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path):
        if path == pack:
            raise AssertionError("bulk Path.read_bytes of the source pack is forbidden")
        return original_read_bytes(path)

    def forbidden_zip_read(*_args, **_kwargs):
        raise AssertionError("ZipFile.read is forbidden for seed payloads")

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(seed_evidence.zipfile.ZipFile, "read", forbidden_zip_read)

    _install(pack, tmp_path / "runtime-store")

    assert audit_market_store(tmp_path / "runtime-store").ok is True


def test_store_audit_completes_before_atomic_publication(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    original_audit = seed_evidence.audit_market_store
    original_publish = getattr(seed_evidence, "_rename_seed_install_noreplace", None)
    events = []

    def observed_audit(root):
        result = original_audit(root)
        events.append(("audit", result.ok))
        return result

    def observed_publish(parent_fd, source_name, destination_name):
        events.append(("publish", not destination.exists()))
        assert ("audit", True) in events
        if original_publish is None:
            raise MarketStoreError("seed_install_unavailable")
        return original_publish(parent_fd, source_name, destination_name)

    monkeypatch.setattr(seed_evidence, "audit_market_store", observed_audit)
    monkeypatch.setattr(
        seed_evidence,
        "_rename_seed_install_noreplace",
        observed_publish,
        raising=False,
    )

    _install(pack, destination)

    publish_index = next(index for index, event in enumerate(events) if event[0] == "publish")
    audit_index = next(index for index, event in enumerate(events) if event == ("audit", True))
    assert audit_index < publish_index


def test_nested_validation_completes_before_atomic_publication(tmp_path, monkeypatch):
    _source_root, _source_sha, _source_bytes, pack = _build_seed(tmp_path)
    destination = tmp_path / "runtime-store"
    original_publish = getattr(seed_evidence, "_rename_seed_install_noreplace", None)
    events = []

    def observed_nested(_path, run_id):
        events.append(("nested", run_id))
        return {"ok": True}

    def observed_publish(parent_fd, source_name, destination_name):
        events.append(("publish", not destination.exists()))
        assert ("nested", RUN_ID) in events
        if original_publish is None:
            raise MarketStoreError("seed_install_unavailable")
        return original_publish(parent_fd, source_name, destination_name)

    monkeypatch.setattr(seed_evidence, "validate_review_pack", observed_nested)
    monkeypatch.setattr(
        seed_evidence,
        "_rename_seed_install_noreplace",
        observed_publish,
        raising=False,
    )

    _install(pack, destination)

    nested_index = events.index(("nested", RUN_ID))
    publish_index = next(index for index, event in enumerate(events) if event[0] == "publish")
    assert nested_index < publish_index
