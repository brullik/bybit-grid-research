from __future__ import annotations

import hashlib
from decimal import Decimal
import json
import os
from pathlib import Path
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
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _typed_info(name, mode):
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
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


def test_destination_inside_store_is_rejected_before_writes(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    dest = root / "seed.zip"
    _assert_error("destination_inside_store", lambda: make_seed_review_pack(root, dest))
    assert not dest.exists()
    assert not (root / "seed.zip.tmp").exists()


def test_destination_through_symlinked_parent_into_store_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "store"
    build_store(root)
    _accept_nested(monkeypatch)
    alias = tmp_path / "store-alias"
    alias.symlink_to(root, target_is_directory=True)
    dest = alias / "seed.zip"
    _assert_error("destination_inside_store", lambda: make_seed_review_pack(root, dest))
    assert not (root / "seed.zip").exists()
    assert not (root / "seed.zip.tmp").exists()


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
    assert not (tmp_path / "seed.zip.tmp").exists()


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
