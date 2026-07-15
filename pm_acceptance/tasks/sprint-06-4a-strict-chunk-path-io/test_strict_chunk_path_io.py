from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib

import pytest

from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.models import MarketDatasetKind, MarketStoreError
from bybit_grid.data.market_store.paths import (
    ensure_safe_store_path,
    rel_chunk_path,
    safe_posix_relative_text,
    safe_symbol,
)
from bybit_grid.data.market_store.reader import read_and_validate_chunk, read_dataset
from bybit_grid.data.market_store.writer import build_planned_chunk, write_chunk_atomic


KIND = MarketDatasetKind.trade_kline_1m
SHA_A = "a" * 64
INT64_OVERFLOW = 1 << 63
CALENDAR_OVERFLOW_MS = ((1 << 63) - 1) // 60_000 * 60_000


class _StringSubclass(str):
    pass


class _HostileHash:
    def __hash__(self):
        raise RuntimeError("must-not-run")


def _row(open_time_ms: int = 0) -> dict[str, object]:
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "open_time_ms": open_time_ms,
        "open": Decimal("1"),
        "high": Decimal("1"),
        "low": Decimal("1"),
        "close": Decimal("1"),
        "volume": Decimal("2"),
        "turnover": Decimal("2"),
        "closed_bool": True,
        "source_run_id": "capture-001",
        "source_review_pack_sha256": SHA_A,
        "source_plan_id": "plan-001",
        "source_name": "trade_kline_1m.jsonl",
        "storage_schema_version": "bybit_public_parquet_store_v1",
    }


def _write_valid_chunk(root):
    manifest = write_chunk_atomic(root, KIND, [_row(0), _row(60_000)])
    return manifest, root / manifest.relative_path


def test_safe_symbol_requires_exact_plain_ascii_fullmatch():
    assert safe_symbol("BTCUSDT") == "BTCUSDT"
    for invalid in (
        _StringSubclass("BTCUSDT"),
        "BTCUSDT\n",
        "B",
        "BTC-USDT",
        "ＢＴＣＵＳＤＴ",
    ):
        with pytest.raises(MarketStoreError, match="^unsafe_symbol$"):
            safe_symbol(invalid)


def test_safe_posix_relative_text_rejects_controls_surrogates_and_non_strings():
    valid = "datasets/trade_kline_1m/symbol=BTCUSDT/chunk=x"
    assert safe_posix_relative_text(valid) == valid
    for invalid in (
        "datasets/trade_kline_1m/chunk=x\n",
        "datasets/trade_kline_1m/chunk=x\x7f",
        "datasets/trade_kline_1m/chunk=x\x85",
        "datasets/trade_kline_1m/chunk=\ud800",
        _StringSubclass(valid),
    ):
        with pytest.raises(MarketStoreError, match="^relative_path_invalid$"):
            safe_posix_relative_text(invalid)


@pytest.mark.parametrize(
    "invalid_dataset",
    (
        "unknown_dataset",
        object(),
        _StringSubclass(KIND.value),
        _HostileHash(),
    ),
    ids=("unknown-string", "wrong-type", "string-subclass", "hostile-hash"),
)
def test_rel_chunk_path_invalid_dataset_never_leaks_enum_value_error(invalid_dataset):
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        rel_chunk_path(
            invalid_dataset,
            symbol="BTCUSDT",
            min_ms=0,
            max_ms=0,
            logical_hash=SHA_A,
        )


def test_rel_chunk_path_unrepresentable_time_never_leaks_native_overflow():
    with pytest.raises(MarketStoreError, match="^min_ms_invalid$"):
        rel_chunk_path(
            KIND,
            symbol="BTCUSDT",
            min_ms=CALENDAR_OVERFLOW_MS,
            max_ms=CALENDAR_OVERFLOW_MS,
            logical_hash=SHA_A,
        )


def test_rel_snapshot_path_rejects_timestamp_outside_portable_utc_range():
    with pytest.raises(MarketStoreError, match="^snapshot_server_time_ms_invalid$"):
        rel_chunk_path(
            MarketDatasetKind.instrument_snapshot,
            snapshot_server_time_ms=INT64_OVERFLOW,
            logical_hash=SHA_A,
        )


@pytest.mark.parametrize(
    "invalid_dataset",
    (
        "unknown_dataset",
        object(),
        _StringSubclass(KIND.value),
        _HostileHash(),
    ),
    ids=("unknown-string", "wrong-type", "string-subclass", "hostile-hash"),
)
def test_build_planned_chunk_invalid_dataset_never_leaks_enum_value_error(invalid_dataset):
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        build_planned_chunk(invalid_dataset, ())


@pytest.mark.parametrize(
    "invalid_dataset",
    (
        "unknown_dataset",
        object(),
        _StringSubclass(KIND.value),
        _HostileHash(),
    ),
    ids=("unknown-string", "wrong-type", "string-subclass", "hostile-hash"),
)
def test_write_chunk_invalid_dataset_never_leaks_enum_value_error(tmp_path, invalid_dataset):
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        write_chunk_atomic(tmp_path, invalid_dataset, ())


@pytest.mark.parametrize(
    "invalid_dataset",
    (
        "unknown_dataset",
        object(),
        _StringSubclass(KIND.value),
        _HostileHash(),
    ),
    ids=("unknown-string", "wrong-type", "string-subclass", "hostile-hash"),
)
def test_read_dataset_invalid_dataset_never_leaks_enum_value_error(tmp_path, invalid_dataset):
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        read_dataset(tmp_path, invalid_dataset)


def test_rel_chunk_path_has_exact_portable_utc_partition_layout():
    path = rel_chunk_path(
        KIND,
        symbol="BTCUSDT",
        min_ms=1_704_067_200_000,
        max_ms=1_704_067_260_000,
        logical_hash=SHA_A,
    )
    assert path.as_posix() == (
        "datasets/trade_kline_1m/symbol=BTCUSDT/year=2024/month=01/"
        "chunk=1704067200000-1704067260000-aaaaaaaaaaaaaaaa"
    )


def test_store_path_helper_rejects_lexical_escape(tmp_path):
    store = tmp_path / "store"
    store.mkdir()

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        ensure_safe_store_path(store, store / ".." / "outside")


def test_store_path_helper_normalizes_embedded_nul_native_error(tmp_path):
    store = tmp_path / "store"
    store.mkdir()

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        ensure_safe_store_path(store, store / "bad\x00entry")


def test_writer_rejects_symlink_store_root_before_any_write(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    store = tmp_path / "store"
    store.symlink_to(outside, target_is_directory=True)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        write_chunk_atomic(store, KIND, [_row()])

    assert list(outside.iterdir()) == []


def test_writer_rejects_symlinked_dataset_ancestor_before_any_write(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (store / "datasets").symlink_to(outside, target_is_directory=True)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        write_chunk_atomic(store, KIND, [_row()])

    assert list(outside.iterdir()) == []
    building = store / ".building"
    assert not building.exists() or list(building.iterdir()) == []


def test_writer_rejects_symlinked_staging_ancestor_before_any_write(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (store / ".building").symlink_to(outside, target_is_directory=True)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        write_chunk_atomic(store, KIND, [_row()])

    assert list(outside.iterdir()) == []
    assert not (store / "datasets").exists()


@pytest.mark.parametrize("member_name", ("chunk_manifest.json", "data.parquet"))
def test_writer_reuse_rejects_symlinked_chunk_members(tmp_path, member_name):
    store = tmp_path / "store"
    _, chunk_dir = _write_valid_chunk(store)
    member = chunk_dir / member_name
    outside = tmp_path / f"outside-{member_name}"
    member.replace(outside)
    if member_name == "chunk_manifest.json":
        outside.write_bytes(b"not-json\n")
    member.symlink_to(outside)

    with pytest.raises(MarketStoreError, match="^chunk_dir_contract_invalid$"):
        write_chunk_atomic(store, KIND, [_row(0), _row(60_000)])


def test_reader_rejects_symlink_store_root(tmp_path):
    real_store = tmp_path / "real-store"
    manifest, _ = _write_valid_chunk(real_store)
    linked_store = tmp_path / "linked-store"
    linked_store.symlink_to(real_store, target_is_directory=True)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        read_and_validate_chunk(linked_store, linked_store / manifest.relative_path)


def test_reader_rejects_symlinked_ancestor_below_store_root(tmp_path):
    real_store = tmp_path / "real-store"
    manifest, _ = _write_valid_chunk(real_store)
    linked_store = tmp_path / "linked-store"
    linked_store.mkdir()
    (linked_store / "datasets").symlink_to(
        real_store / "datasets",
        target_is_directory=True,
    )

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        read_and_validate_chunk(linked_store, linked_store / manifest.relative_path)


@pytest.mark.parametrize("member_name", ("chunk_manifest.json", "data.parquet"))
def test_reader_rejects_symlinked_chunk_members_with_stable_error(tmp_path, member_name):
    store = tmp_path / "store"
    _, chunk_dir = _write_valid_chunk(store)
    member = chunk_dir / member_name
    outside = tmp_path / f"outside-{member_name}"
    member.replace(outside)
    member.symlink_to(outside)

    with pytest.raises(MarketStoreError, match="^chunk_dir_contract_invalid$"):
        read_and_validate_chunk(store, chunk_dir)


def test_planned_chunk_reuse_rejects_symlinked_existing_store_root(tmp_path):
    real_store = tmp_path / "real-store"
    _write_valid_chunk(real_store)
    linked_store = tmp_path / "linked-store"
    linked_store.symlink_to(real_store, target_is_directory=True)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        build_planned_chunk(
            KIND,
            [_row(0), _row(60_000)],
            existing_store_root=linked_store,
        )


def _replace_parquet_with_hash_consistent_corruption(chunk_dir, manifest):
    corrupt = b"not-a-parquet-file"
    (chunk_dir / "data.parquet").write_bytes(corrupt)
    changed = replace(
        manifest,
        parquet_sha256=hashlib.sha256(corrupt).hexdigest(),
    )
    (chunk_dir / "chunk_manifest.json").write_bytes(canonical_json_bytes(changed))


def test_reader_normalizes_native_parquet_decode_error(tmp_path):
    store = tmp_path / "store"
    manifest, chunk_dir = _write_valid_chunk(store)
    _replace_parquet_with_hash_consistent_corruption(chunk_dir, manifest)

    with pytest.raises(MarketStoreError, match="^parquet_read_invalid$"):
        read_and_validate_chunk(store, chunk_dir)


def test_writer_reuse_normalizes_native_parquet_decode_error(tmp_path):
    store = tmp_path / "store"
    manifest, chunk_dir = _write_valid_chunk(store)
    _replace_parquet_with_hash_consistent_corruption(chunk_dir, manifest)

    with pytest.raises(MarketStoreError, match="^parquet_read_invalid$"):
        write_chunk_atomic(store, KIND, [_row(0), _row(60_000)])


def test_writer_normalizes_native_filesystem_error(tmp_path):
    overlong_store_component = tmp_path / ("x" * 256)

    with pytest.raises(MarketStoreError, match="^unsafe_store_entry$"):
        write_chunk_atomic(overlong_store_component, KIND, [_row()])


@pytest.mark.parametrize("fail_at", ("early", "mid", "late"))
def test_injected_chunk_failures_publish_nothing_and_clean_staging(tmp_path, fail_at):
    store = tmp_path / "store"

    with pytest.raises(MarketStoreError, match=f"^injected_chunk_failure_{fail_at}$"):
        write_chunk_atomic(store, KIND, [_row()], fail_at=fail_at)

    assert not (store / "datasets").exists()
    building = store / ".building"
    assert not building.exists() or list(building.iterdir()) == []


def test_write_read_round_trip_and_identical_reuse_are_deterministic(tmp_path):
    store = tmp_path / "store"
    first = write_chunk_atomic(store, KIND, [_row(60_000), _row(0)])
    second = write_chunk_atomic(store, KIND, [_row(0), _row(60_000)])

    assert first == second
    loaded_manifest, rows = read_and_validate_chunk(
        store,
        store / first.relative_path,
        expected_manifest=first,
    )
    assert loaded_manifest == first
    assert tuple(row["open_time_ms"] for row in rows) == (0, 60_000)
