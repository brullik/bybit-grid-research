from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.models import (
    STORE_SCHEMA_VERSION,
    MarketDatasetKind,
    MarketStoreError,
    StoreChunkManifest,
    StoreEvidenceReference,
    StoreImportReceipt,
    StoreVersion,
)
from bybit_grid.data.market_store.parsing import (
    parse_chunk_manifest_bytes,
    parse_evidence_reference_bytes,
    parse_import_receipt_bytes,
    parse_store_version_bytes,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
STORE_VERSION_BYTES = (
    b'{"storage_schema_version":"bybit_public_parquet_store_v1"}\n'
)
EVIDENCE_REFERENCE_BYTES = (
    b'{"run_id":"capture-001","source_review_pack_sha256":"'
    + SHA_A.encode("ascii")
    + b'"}\n'
)
CHUNK_MANIFEST_BYTES = (
    b'{"dataset":"trade_kline_1m","logical_rows_sha256":"'
    + SHA_B.encode("ascii")
    + b'","max_key":["BTCUSDT",0],"min_key":["BTCUSDT",0],'
    + b'"parquet_sha256":"'
    + SHA_A.encode("ascii")
    + b'","primary_key_columns":["symbol","open_time_ms"],'
    + b'"relative_path":"datasets/trade_kline_1m/symbol=BTCUSDT/'
    + b'year=2025/month=01/chunk=0-0-aaaaaaaaaaaaaaaa","row_count":1,'
    + b'"storage_schema_version":"bybit_public_parquet_store_v1"}\n'
)
IMPORT_RECEIPT_BYTES = (
    b'{"chunks":['
    + CHUNK_MANIFEST_BYTES.rstrip(b"\n")
    + b'],"run_id":"capture-001","source_review_pack_sha256":"'
    + SHA_A.encode("ascii")
    + b'","storage_schema_version":"bybit_public_parquet_store_v1"}\n'
)


class _StringSubclass(str):
    pass


def _manifest(**changes: object) -> StoreChunkManifest:
    values = {
        "dataset": "trade_kline_1m",
        "relative_path": (
            "datasets/trade_kline_1m/symbol=BTCUSDT/year=2025/"
            "month=01/chunk=0-0-aaaaaaaaaaaaaaaa"
        ),
        "row_count": 1,
        "primary_key_columns": ("symbol", "open_time_ms"),
        "min_key": ("BTCUSDT", 0),
        "max_key": ("BTCUSDT", 0),
        "parquet_sha256": SHA_A,
        "logical_rows_sha256": SHA_B,
        "storage_schema_version": STORE_SCHEMA_VERSION,
    }
    values.update(changes)
    return StoreChunkManifest(**values)


def _manifest_object() -> dict[str, object]:
    return json.loads(canonical_json_bytes(_manifest()))


def _receipt_object() -> dict[str, object]:
    receipt = StoreImportReceipt("capture-001", SHA_A, (_manifest(),))
    return json.loads(canonical_json_bytes(receipt))


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def test_store_version_canonical_round_trip_returns_exact_frozen_model():
    expected = StoreVersion(STORE_SCHEMA_VERSION)

    parsed = parse_store_version_bytes(STORE_VERSION_BYTES)

    assert type(parsed) is StoreVersion
    assert parsed == expected
    assert canonical_json_bytes(parsed) == STORE_VERSION_BYTES
    with pytest.raises(FrozenInstanceError):
        parsed.storage_schema_version = "changed"


def test_store_version_parser_rejects_non_bytes_and_non_objects():
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes("{}\n")
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes(b"[]\n")


def test_store_version_parser_rejects_invalid_utf8_and_bom():
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes(b'{"storage_schema_version":"\xff"}\n')
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes(b"\xef\xbb\xbf" + STORE_VERSION_BYTES)


def test_store_version_parser_rejects_missing_and_unknown_keys():
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes(b"{}\n")
    with pytest.raises(MarketStoreError, match="^store_version_schema_invalid$"):
        parse_store_version_bytes(
            b'{"storage_schema_version":"bybit_public_parquet_store_v1",'
            b'"unexpected":true}\n'
        )


def test_persisted_parsers_reject_duplicate_float_and_non_finite_tokens():
    duplicate = (
        b'{"storage_schema_version":"bybit_public_parquet_store_v1",'
        b'"storage_schema_version":"bybit_public_parquet_store_v1"}\n'
    )
    with pytest.raises(
        MarketStoreError,
        match="^store_version:json_duplicate_key$",
    ):
        parse_store_version_bytes(duplicate)
    with pytest.raises(MarketStoreError, match="^chunk_manifest:json_float_token$"):
        parse_chunk_manifest_bytes(
            CHUNK_MANIFEST_BYTES.replace(b'"row_count":1', b'"row_count":1.0')
        )
    with pytest.raises(MarketStoreError, match="^receipt:json_non_finite_token$"):
        parse_import_receipt_bytes(
            IMPORT_RECEIPT_BYTES.replace(b'"row_count":1', b'"row_count":NaN')
        )


def test_chunk_manifest_canonical_round_trip_returns_exact_model():
    expected = _manifest()

    parsed = parse_chunk_manifest_bytes(CHUNK_MANIFEST_BYTES)

    assert type(parsed) is StoreChunkManifest
    assert parsed == expected
    assert canonical_json_bytes(parsed) == CHUNK_MANIFEST_BYTES
    assert type(parsed.primary_key_columns) is tuple
    assert type(parsed.min_key) is tuple
    assert type(parsed.max_key) is tuple


def test_chunk_manifest_dataset_must_be_exact_known_string():
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        _manifest(dataset="unknown_dataset")
    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        _manifest(dataset=MarketDatasetKind.trade_kline_1m)


def test_chunk_manifest_schema_version_must_be_exact_string():
    value = _StringSubclass(STORE_SCHEMA_VERSION)

    with pytest.raises(MarketStoreError, match="^storage_schema_version_invalid$"):
        _manifest(storage_schema_version=value)


def test_chunk_manifest_relative_path_rejects_unsafe_posix_components():
    with pytest.raises(MarketStoreError, match="^relative_path_invalid$"):
        _manifest(relative_path="datasets/trade_kline_1m//chunk=x")
    with pytest.raises(MarketStoreError, match="^relative_path_invalid$"):
        _manifest(relative_path="datasets/trade_kline_1m/C:/chunk=x")
    with pytest.raises(MarketStoreError, match="^relative_path_invalid$"):
        _manifest(relative_path="datasets/trade_kline_1m/./chunk=x")


def test_chunk_manifest_primary_key_columns_are_nonempty_unique_strings():
    with pytest.raises(MarketStoreError, match="^primary_key_columns_invalid$"):
        _manifest(primary_key_columns=())
    with pytest.raises(MarketStoreError, match="^primary_key_columns_invalid$"):
        _manifest(primary_key_columns=("symbol", "symbol"))
    with pytest.raises(MarketStoreError, match="^primary_key_columns_invalid$"):
        _manifest(primary_key_columns=("symbol", 1))


def test_chunk_manifest_row_count_rejects_bool_as_int():
    with pytest.raises(MarketStoreError, match="^row_count_not_exact_int$"):
        _manifest(row_count=True)


def test_chunk_manifest_min_key_matches_primary_key_shape_and_types():
    with pytest.raises(MarketStoreError, match="^min_key_invalid$"):
        _manifest(min_key=("BTCUSDT",))
    with pytest.raises(MarketStoreError, match="^min_key_invalid$"):
        _manifest(min_key=("BTCUSDT", True))
    with pytest.raises(MarketStoreError, match="^min_key_invalid$"):
        _manifest(min_key=("", 0))


def test_chunk_manifest_max_key_matches_primary_key_shape_and_types():
    with pytest.raises(MarketStoreError, match="^max_key_invalid$"):
        _manifest(max_key=("BTCUSDT",))
    with pytest.raises(MarketStoreError, match="^max_key_invalid$"):
        _manifest(max_key=("BTCUSDT", -1))
    with pytest.raises(MarketStoreError, match="^max_key_invalid$"):
        _manifest(max_key=(1, 0))


def test_chunk_manifest_key_order_error_is_stable_after_type_validation():
    with pytest.raises(MarketStoreError, match="^key_order_invalid$"):
        _manifest(min_key=("BTCUSDT", 60_000), max_key=("BTCUSDT", 0))


def test_parse_chunk_manifest_invalid_dataset_never_leaks_enum_value_error():
    obj = _manifest_object()
    obj["dataset"] = "unknown_dataset"

    with pytest.raises(MarketStoreError, match="^dataset_invalid$"):
        parse_chunk_manifest_bytes(_json_bytes(obj))


def test_parse_chunk_manifest_wrong_container_is_schema_error():
    obj = _manifest_object()
    obj["primary_key_columns"] = {"symbol": "open_time_ms"}

    with pytest.raises(MarketStoreError, match="^chunk_manifest_schema_invalid$"):
        parse_chunk_manifest_bytes(_json_bytes(obj))


def test_evidence_reference_canonical_round_trip_and_safe_run_id():
    expected = StoreEvidenceReference("capture-001", SHA_A)

    parsed = parse_evidence_reference_bytes(EVIDENCE_REFERENCE_BYTES)

    assert type(parsed) is StoreEvidenceReference
    assert parsed == expected
    assert canonical_json_bytes(parsed) == EVIDENCE_REFERENCE_BYTES
    with pytest.raises(MarketStoreError, match="^run_id_unsafe$"):
        StoreEvidenceReference("capture:001", SHA_A)
    with pytest.raises(MarketStoreError, match="^run_id_unsafe$"):
        StoreEvidenceReference("capture\n001", SHA_A)


def test_evidence_reference_parser_never_leaks_unicode_encode_error():
    data = (
        b'{"run_id":"\\ud800","source_review_pack_sha256":"'
        + SHA_A.encode("ascii")
        + b'"}\n'
    )

    with pytest.raises(MarketStoreError, match="^run_id_unsafe$"):
        parse_evidence_reference_bytes(data)


def test_import_receipt_canonical_round_trip_is_deeply_immutable():
    expected = StoreImportReceipt("capture-001", SHA_A, (_manifest(),))

    parsed = parse_import_receipt_bytes(IMPORT_RECEIPT_BYTES)

    assert type(parsed) is StoreImportReceipt
    assert parsed == expected
    assert canonical_json_bytes(parsed) == IMPORT_RECEIPT_BYTES
    assert type(parsed.chunks) is tuple
    assert all(type(chunk) is StoreChunkManifest for chunk in parsed.chunks)
    with pytest.raises(FrozenInstanceError):
        parsed.run_id = "changed"


def test_import_receipt_requires_at_least_one_chunk():
    with pytest.raises(MarketStoreError, match="^chunks_invalid$"):
        StoreImportReceipt("capture-001", SHA_A, ())


def test_import_receipt_schema_version_must_be_exact_string():
    value = _StringSubclass(STORE_SCHEMA_VERSION)

    with pytest.raises(MarketStoreError, match="^storage_schema_version_invalid$"):
        StoreImportReceipt("capture-001", SHA_A, (_manifest(),), value)


def test_parse_import_receipt_non_object_chunk_is_schema_error():
    obj = _receipt_object()
    obj["chunks"] = [1]

    with pytest.raises(MarketStoreError, match="^receipt_schema_invalid$"):
        parse_import_receipt_bytes(_json_bytes(obj))


def test_parse_import_receipt_missing_nested_field_is_schema_error():
    obj = _receipt_object()
    del obj["chunks"][0]["row_count"]

    with pytest.raises(MarketStoreError, match="^receipt_schema_invalid$"):
        parse_import_receipt_bytes(_json_bytes(obj))


def test_parse_import_receipt_unknown_nested_field_is_schema_error():
    obj = _receipt_object()
    obj["chunks"][0]["unexpected"] = True

    with pytest.raises(MarketStoreError, match="^receipt_schema_invalid$"):
        parse_import_receipt_bytes(_json_bytes(obj))


def test_all_persisted_parsers_reject_noncanonical_bytes():
    fixtures = (
        (parse_store_version_bytes, STORE_VERSION_BYTES, "store_version_canonical_mismatch"),
        (
            parse_chunk_manifest_bytes,
            CHUNK_MANIFEST_BYTES,
            "chunk_manifest_canonical_mismatch",
        ),
        (
            parse_evidence_reference_bytes,
            EVIDENCE_REFERENCE_BYTES,
            "evidence_reference_canonical_mismatch",
        ),
        (parse_import_receipt_bytes, IMPORT_RECEIPT_BYTES, "receipt_canonical_mismatch"),
    )

    for parser, canonical, expected_error in fixtures:
        noncanonical = canonical[:-1] + b" \n"
        with pytest.raises(MarketStoreError, match=f"^{expected_error}$"):
            parser(noncanonical)
