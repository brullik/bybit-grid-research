from __future__ import annotations

import ast
import builtins
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import hashlib
import importlib
import inspect
import io
import json
import socket
import struct
import time
import zipfile
import zlib

import pytest

from bybit_grid.data.public_batch.historical_plan import build_historical_capture_plan
from bybit_grid.data.public_batch.models import (
    BybitInstrumentMeta,
    BybitServerTime,
    InclusiveMinuteWindow,
)


MINUTE_MS = 60_000
MODULE_NAME = "bybit_grid.data.public_batch.historical_evidence_archive"
EVIDENCE_MODULE_NAME = "bybit_grid.data.public_batch.historical_evidence"
TRANSCRIPT_MODULE_NAME = "bybit_grid.data.public_batch.historical_transcript"
RESPONSE_MODULE_NAME = "bybit_grid.data.public_batch.historical_response"
UNAVAILABLE = "historical_evidence_archive_unavailable"
EXPECTED_ARCHIVE_SHA256 = "02afacf8a3746e50c0ed0c29697525d3082a9ae9cbe02c02e89ed442e76456f6"
EXPECTED_CANONICAL_SHA256 = "c1071baf357468c932d71a8d9273cea3a48a8deb9dc054c4dc1e09e90c408487"
EXPECTED_FIELD_NAMES = (
    "schema",
    "plan_sha256",
    "transcript_sha256",
    "manifest_sha256",
    "layout_sha256",
    "member_sequence_sha256",
    "archive_sha256",
    "member_count",
    "payload_byte_count",
    "archive_byte_count",
    "max_archive_members",
    "max_archive_payload_bytes",
    "max_archive_bytes",
    "zip_version_made_by",
    "zip_version_needed",
    "zip_compression_method",
    "zip_general_purpose_flags",
    "zip_dos_time",
    "zip_dos_date",
    "zip_unix_mode",
    "layout_revalidated_bool",
    "archive_member_sequence_exact_bool",
    "archive_member_payloads_exact_bool",
    "zip32_envelope_verified_bool",
    "zip_stored_only_bool",
    "fixed_metadata_verified_bool",
    "archive_sha256_verified_bool",
    "in_memory_archive_authorized_bool",
    "filesystem_authorized_bool",
    "persistence_authorized_bool",
    "store_projection_authorized_bool",
    "store_install_authorized_bool",
    "network_authorized_bool",
    "transport_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "source_authenticity_proven_bool",
    "account_eligibility_proven_bool",
    "account_region_eligibility_proven_bool",
    "bybit_product_availability_proven_bool",
    "publication_authorized_bool",
    "arbitrary_archive_ingestion_authorized_bool",
    "archive_extraction_authorized_bool",
    "withdrawal_authorized_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
    "profitability_proven_bool",
    "layout",
    "archive_bytes",
)
TRUE_EVIDENCE_FLAGS = (
    "layout_revalidated_bool",
    "archive_member_sequence_exact_bool",
    "archive_member_payloads_exact_bool",
    "zip32_envelope_verified_bool",
    "zip_stored_only_bool",
    "fixed_metadata_verified_bool",
    "archive_sha256_verified_bool",
    "in_memory_archive_authorized_bool",
)
FALSE_GUARDRAILS = (
    "filesystem_authorized_bool",
    "persistence_authorized_bool",
    "store_projection_authorized_bool",
    "store_install_authorized_bool",
    "network_authorized_bool",
    "transport_authorized_bool",
    "credentials_allowed_bool",
    "private_api_allowed_bool",
    "telegram_authorized_bool",
    "ordinary_order_authorized_bool",
    "native_grid_mutation_authorized_bool",
    "wallet_authorized_bool",
    "position_mutation_authorized_bool",
    "live_execution_authorized_bool",
    "source_authenticity_proven_bool",
    "account_eligibility_proven_bool",
    "account_region_eligibility_proven_bool",
    "bybit_product_availability_proven_bool",
    "publication_authorized_bool",
    "arbitrary_archive_ingestion_authorized_bool",
    "archive_extraction_authorized_bool",
    "withdrawal_authorized_bool",
    "funding_coverage_proven_bool",
    "historical_market_data_coverage_proven_bool",
    "parameter_selection_authorized_bool",
    "sufficient_for_parameter_selection_bool",
    "native_equivalence_proven_bool",
    "profitability_proven_bool",
)


def _api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    required = (
        "HistoricalEvidenceArchiveError",
        "HistoricalEvidenceArchive",
        "build_historical_evidence_archive",
        "__all__",
    )
    if any(not hasattr(module, name) for name in required):
        raise RuntimeError(UNAVAILABLE)
    return module


def _evidence_api():
    return importlib.import_module(EVIDENCE_MODULE_NAME)


def _transcript_api():
    return importlib.import_module(TRANSCRIPT_MODULE_NAME)


def _response_api():
    return importlib.import_module(RESPONSE_MODULE_NAME)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _instrument(server_time: BybitServerTime) -> BybitInstrumentMeta:
    return BybitInstrumentMeta(
        category="linear",
        symbol="BTCUSDT",
        contract_type="LinearPerpetual",
        status="Trading",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        launch_time_ms=0,
        delivery_time_ms=0,
        is_pre_listing=False,
        funding_interval_minutes=480,
        tick_size=Decimal("0.10"),
        qty_step=Decimal("0.001"),
        min_order_qty=Decimal("0.001"),
        min_notional_value=Decimal("5"),
        min_leverage=Decimal("1"),
        max_leverage=Decimal("100"),
        leverage_step=Decimal("0.01"),
        snapshot_server_time_ms=server_time.server_time_ms,
    )


def _plan(*, end_minute=2, include_trade=True, include_mark=True):
    server_time_ms = (end_minute + 2) * MINUTE_MS + 1_234
    server_time = BybitServerTime(
        server_time_ms=server_time_ms,
        time_second=server_time_ms // 1_000,
        time_nano=server_time_ms * 1_000_000,
        top_level_time_ms=server_time_ms,
        last_closed_open_time_ms=(end_minute + 1) * MINUTE_MS,
    )
    all_times = tuple(range(0, end_minute * MINUTE_MS + 1, MINUTE_MS))
    return build_historical_capture_plan(
        instrument=_instrument(server_time),
        server_time=server_time,
        requested_window=InclusiveMinuteWindow(0, end_minute * MINUTE_MS),
        observed_trade_open_times_ms=() if include_trade else all_times,
        observed_mark_open_times_ms=() if include_mark else all_times,
        observed_funding_times_ms=(),
    )


def _trade_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105", "1.5", "150"]


def _mark_row(timestamp_ms: int):
    return [str(timestamp_ms), "100", "110", "90", "105"]


def _funding_row(timestamp_ms: int):
    return {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingRateTimestamp": str(timestamp_ms),
    }


def _body(request, *, empty_funding=False, response_time_ms=700_123) -> bytes:
    if request.dataset == "trade_kline_1m":
        rows = [
            _trade_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    elif request.dataset == "mark_kline_1m":
        rows = [
            _mark_row(value) for value in range(request.end_ms, request.start_ms - 1, -MINUTE_MS)
        ]
    else:
        candidates = [] if empty_funding else [_funding_row(2 * MINUTE_MS), _funding_row(0)]
        rows = [
            row
            for row in candidates
            if request.start_ms <= int(row["fundingRateTimestamp"]) <= request.end_ms
        ]
    result = {"category": "linear", "list": rows}
    if request.dataset != "funding_rate":
        result["symbol"] = "BTCUSDT"
    return json.dumps(
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": result,
            "retExtInfo": {},
            "time": response_time_ms,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _transcript(*, end_minute=2, include_trade=True, include_mark=True, empty_funding=False):
    plan = _plan(
        end_minute=end_minute,
        include_trade=include_trade,
        include_mark=include_mark,
    )
    bodies = tuple(_body(request, empty_funding=empty_funding) for request in plan.requests)
    receipts = tuple(
        _response_api().accept_historical_response_page(
            plan=plan,
            request=request,
            http_status=200,
            content_type="application/json",
            raw_body_bytes=body,
        )
        for request, body in zip(plan.requests, bodies, strict=True)
    )
    return _transcript_api().reconcile_historical_response_transcript(
        plan=plan,
        receipts=receipts,
        raw_body_bytes=bodies,
    )


def _layout(transcript=None):
    source = _transcript() if transcript is None else transcript
    return _evidence_api().build_historical_evidence_layout(transcript=source)


def _archive(api, layout=None):
    source = _layout() if layout is None else layout
    return api.build_historical_evidence_archive(layout=source)


def _parse_exact_zip32(value: bytes):
    local_format = "<IHHHHHIIIHH"
    central_format = "<IHHHHHHIIIHHHHHII"
    eocd_format = "<IHHHHIIH"
    eocd = struct.unpack_from(eocd_format, value, len(value) - 22)
    assert eocd[0] == 0x06054B50
    assert eocd[1:3] == (0, 0)
    assert eocd[3] == eocd[4]
    assert eocd[7] == 0
    member_count = eocd[3]
    central_size = eocd[5]
    central_offset = eocd[6]
    assert central_offset + central_size + 22 == len(value)
    locals_out = []
    cursor = 0
    for _index in range(member_count):
        offset = cursor
        header = struct.unpack_from(local_format, value, cursor)
        assert header[0] == 0x04034B50
        cursor += 30
        name = value[cursor : cursor + header[9]]
        cursor += header[9]
        assert header[10] == 0
        payload = value[cursor : cursor + header[7]]
        cursor += header[7]
        assert header[7] == header[8]
        assert zlib.crc32(payload) & 0xFFFFFFFF == header[6]
        locals_out.append((offset, header, name, payload))
    assert cursor == central_offset
    centrals_out = []
    for _index in range(member_count):
        header = struct.unpack_from(central_format, value, cursor)
        assert header[0] == 0x02014B50
        cursor += 46
        name = value[cursor : cursor + header[10]]
        cursor += header[10]
        assert header[11:14] == (0, 0, 0)
        centrals_out.append((header, name))
    assert cursor == len(value) - 22
    return tuple(locals_out), tuple(centrals_out), eocd


def _tamper(api, archive, field_name, value, code):
    object.__setattr__(archive, field_name, value)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        archive.canonical_json_bytes()
    assert str(caught.value) == code


def test_exact_public_surface_signature_and_field_order():
    api = _api()
    assert issubclass(api.HistoricalEvidenceArchiveError, ValueError)
    assert api.__all__ == (
        "HistoricalEvidenceArchiveError",
        "HistoricalEvidenceArchive",
        "build_historical_evidence_archive",
    )
    assert (
        tuple(field.name for field in fields(api.HistoricalEvidenceArchive)) == EXPECTED_FIELD_NAMES
    )
    signature = inspect.signature(api.build_historical_evidence_archive)
    assert tuple(signature.parameters) == ("layout",)
    parameter = signature.parameters["layout"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_module_ast_has_no_filesystem_network_clock_or_import_time_calls():
    api = _api()
    source = inspect.getsource(api)
    tree = ast.parse(source)
    forbidden = {
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "io",
        "locale",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "ssl",
        "subprocess",
        "tarfile",
        "tempfile",
        "threading",
        "time",
        "urllib",
        "uuid",
        "zoneinfo",
        "zipfile",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            assert not isinstance(value, ast.Call)


def test_package_exports_remain_unchanged_and_archive_has_no_public_parser():
    api = _api()
    package = importlib.import_module("bybit_grid.data.public_batch")
    assert "HistoricalEvidenceArchive" not in package.__all__
    assert "build_historical_evidence_archive" not in package.__all__
    public = {name for name in vars(api) if not name.startswith("_")}
    assert public == set(api.__all__)
    assert not any(
        fragment in name.lower()
        for name in public
        for fragment in ("parse", "read", "open", "verify")
    )


def test_exact_06_4f_layout_model_is_required():
    api = _api()
    for value in (None, object(), {}, (), b""):
        with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
            api.build_historical_evidence_archive(layout=value)
        assert str(caught.value) == "layout_not_exact_model"


def test_layout_is_independently_revalidated_before_packing():
    api = _api()
    layout = _layout()
    object.__setattr__(layout, "member_count", 999)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        api.build_historical_evidence_archive(layout=layout)
    assert str(caught.value) == "layout_revalidation_failed"
    assert isinstance(caught.value.__cause__, _evidence_api().HistoricalEvidenceError)


def test_uninitialized_exact_layout_wraps_structural_failure():
    api = _api()
    forged = object.__new__(_evidence_api().HistoricalEvidenceLayout)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        api.build_historical_evidence_archive(layout=forged)
    assert str(caught.value) == "layout_revalidation_failed"
    assert isinstance(caught.value.__cause__, (AttributeError, TypeError))


def test_success_retains_layout_and_commits_archive_outside_bytes():
    api = _api()
    layout = _layout()
    archive = _archive(api, layout)
    assert archive.layout is layout
    assert type(archive.archive_bytes) is bytes
    assert archive.archive_sha256 == _sha256(archive.archive_bytes)
    assert archive.archive_sha256.encode("ascii") not in archive.archive_bytes
    assert archive.plan_sha256 == layout.plan_sha256
    assert archive.transcript_sha256 == layout.transcript_sha256
    assert archive.manifest_sha256 == layout.manifest_sha256
    assert archive.layout_sha256 == _sha256(layout.canonical_json_bytes())
    assert archive.member_sequence_sha256 == layout.member_sequence_sha256


def test_archive_is_literal_deterministic_across_repeated_builds():
    api = _api()
    first = _archive(api)
    second = _archive(api)
    assert first.archive_bytes == second.archive_bytes
    assert first.archive_sha256 == second.archive_sha256 == EXPECTED_ARCHIVE_SHA256
    assert first.sha256() == second.sha256() == EXPECTED_CANONICAL_SHA256


def test_local_headers_are_exact_zip32_stored_records():
    api = _api()
    archive = _archive(api)
    locals_out, _centrals, _eocd = _parse_exact_zip32(archive.archive_bytes)
    for (_offset, header, name, payload), expected_name, expected_payload in zip(
        locals_out,
        archive.layout.member_names,
        archive.layout.member_bytes,
        strict=True,
    ):
        assert header[1:6] == (20, 0, 0, 0, 33)
        assert header[7] == header[8] == len(expected_payload)
        assert header[9] == len(expected_name.encode("ascii"))
        assert name == expected_name.encode("ascii")
        assert payload == expected_payload


def test_central_headers_freeze_unix_creator_mode_and_local_offsets():
    api = _api()
    archive = _archive(api)
    locals_out, centrals, _eocd = _parse_exact_zip32(archive.archive_bytes)
    for local, (header, name) in zip(locals_out, centrals, strict=True):
        assert header[1:7] == (788, 20, 0, 0, 0, 33)
        assert header[14] == 0
        assert header[15] == 2_172_649_472
        assert header[16] == local[0]
        assert name == local[2]
        assert header[8] == header[9] == len(local[3])


def test_eocd_is_single_disk_exact_and_has_no_comment_or_trailer():
    api = _api()
    archive = _archive(api)
    _locals, _centrals, eocd = _parse_exact_zip32(archive.archive_bytes)
    assert eocd == (
        0x06054B50,
        0,
        0,
        archive.member_count,
        archive.member_count,
        eocd[5],
        eocd[6],
        0,
    )
    assert archive.archive_bytes[-22:-18] == b"PK\x05\x06"


def test_zipfile_independently_reads_exact_names_order_bytes_and_metadata():
    api = _api()
    archive = _archive(api)
    with zipfile.ZipFile(io.BytesIO(archive.archive_bytes), "r") as reader:
        infos = reader.infolist()
        assert tuple(info.filename for info in infos) == archive.layout.member_names
        assert tuple(reader.read(info) for info in infos) == archive.layout.member_bytes
        for info in infos:
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.flag_bits == 0
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert info.external_attr >> 16 == 0o100600
            assert info.extra == b""
            assert info.comment == b""
            assert info.is_dir() is False
        assert reader.comment == b""
        assert reader.testzip() is None


def test_no_compression_encryption_descriptor_zip64_prefix_gap_or_directory():
    api = _api()
    archive = _archive(api)
    locals_out, centrals, _eocd = _parse_exact_zip32(archive.archive_bytes)
    assert locals_out[0][0] == 0
    assert all(header[1][2] == 0 for header in locals_out)
    assert all(header[0][3] == 0 for header in centrals)
    assert all(not name.endswith(b"/") for _offset, _header, name, _payload in locals_out)
    assert archive.archive_byte_count < (1 << 32)
    assert archive.member_count < (1 << 16)


def test_duplicate_payloads_remain_distinct_ordered_members():
    api = _api()
    transcript = _transcript(
        end_minute=400,
        include_trade=False,
        include_mark=False,
        empty_funding=True,
    )
    assert len(set(transcript.raw_body_bytes)) == 1
    layout = _layout(transcript)
    archive = _archive(api, layout)
    locals_out, _centrals, _eocd = _parse_exact_zip32(archive.archive_bytes)
    assert tuple(item[2].decode("ascii") for item in locals_out) == layout.member_names
    assert tuple(item[3] for item in locals_out) == layout.member_bytes
    assert len(locals_out) == layout.member_count


def test_exact_caps_bound_zip32_and_in_memory_amplification():
    api = _api()
    archive = _archive(api)
    assert archive.max_archive_members == 258
    assert archive.max_archive_payload_bytes == 268_435_456
    maximum_name_overhead = 230 + 256 * 106
    assert maximum_name_overhead == 27_366
    assert archive.max_archive_bytes == 268_435_456 + maximum_name_overhead
    assert archive.max_archive_bytes == 268_462_822
    assert archive.max_archive_bytes < (1 << 32)


def test_actual_counts_follow_closed_form_without_hidden_bytes():
    api = _api()
    archive = _archive(api)
    expected_overhead = 22 + sum(
        76 + 2 * len(name.encode("ascii")) for name in archive.layout.member_names
    )
    assert archive.payload_byte_count == sum(map(len, archive.layout.member_bytes))
    assert archive.archive_byte_count == archive.payload_byte_count + expected_overhead
    assert archive.archive_byte_count == len(archive.archive_bytes)


def test_fixed_metadata_fields_are_exact_nonboolean_integers():
    api = _api()
    archive = _archive(api)
    values = (
        archive.zip_version_made_by,
        archive.zip_version_needed,
        archive.zip_compression_method,
        archive.zip_general_purpose_flags,
        archive.zip_dos_time,
        archive.zip_dos_date,
        archive.zip_unix_mode,
    )
    assert all(type(value) is int for value in values)
    assert values == (788, 20, 0, 0, 0, 33, 33_152)


def test_archive_is_frozen_slotted_hashable_and_factory_only():
    api = _api()
    archive = _archive(api)
    assert not hasattr(archive, "__dict__")
    hash(archive)
    with pytest.raises(FrozenInstanceError):
        archive.schema = "forged"
    with pytest.raises(api.HistoricalEvidenceArchiveError) as direct:
        api.HistoricalEvidenceArchive()
    assert str(direct.value) == "archive_factory_only"
    with pytest.raises(api.HistoricalEvidenceArchiveError) as replaced:
        replace(archive, schema="forged")
    assert str(replaced.value) == "archive_factory_only"


def test_canonical_metadata_omits_retained_layout_and_archive_bytes():
    api = _api()
    archive = _archive(api)
    payload = json.loads(archive.canonical_json_bytes())
    assert "layout" not in payload
    assert "archive_bytes" not in payload
    assert payload["archive_sha256"] == archive.archive_sha256
    assert payload["archive_byte_count"] == len(archive.archive_bytes)
    assert archive.canonical_json_bytes().endswith(b"\n")
    assert not archive.canonical_json_bytes().endswith(b"\n\n")


def test_all_narrow_archive_evidence_flags_are_exact_true():
    api = _api()
    archive = _archive(api)
    for name in TRUE_EVIDENCE_FLAGS:
        assert type(getattr(archive, name)) is bool
        assert getattr(archive, name) is True


def test_every_external_authority_eligibility_coverage_and_selection_claim_is_false():
    api = _api()
    archive = _archive(api)
    for name in FALSE_GUARDRAILS:
        assert type(getattr(archive, name)) is bool
        assert getattr(archive, name) is False


def test_tampered_schema_fails_closed():
    api = _api()
    _tamper(api, _archive(api), "schema", "v2", "archive_schema_invalid")


def test_tampered_counts_and_fixed_limits_fail_closed():
    api = _api()
    _tamper(api, _archive(api), "member_count", True, "archive_counts_invalid")
    _tamper(
        api,
        _archive(api),
        "max_archive_payload_bytes",
        1,
        "archive_fixed_limits_invalid",
    )


def test_nonbytes_archive_atom_has_distinct_fail_closed_group():
    api = _api()
    _tamper(api, _archive(api), "archive_bytes", memoryview(b"not-bytes"), "archive_bytes_invalid")


def test_tampered_commitment_and_raw_envelope_fail_closed():
    api = _api()
    archive = _archive(api)
    _tamper(api, archive, "archive_sha256", "0" * 64, "archive_commitments_invalid")
    archive = _archive(api)
    changed = b"X" + archive.archive_bytes[1:]
    object.__setattr__(archive, "archive_bytes", changed)
    object.__setattr__(archive, "archive_sha256", _sha256(changed))
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        archive.canonical_json_bytes()
    assert str(caught.value) == "archive_envelope_invalid"


def test_tampered_zip_metadata_and_flags_fail_closed():
    api = _api()
    _tamper(api, _archive(api), "zip_unix_mode", 0o100644, "archive_zip_metadata_invalid")
    _tamper(
        api,
        _archive(api),
        "zip32_envelope_verified_bool",
        False,
        "archive_evidence_flags_invalid",
    )
    _tamper(
        api,
        _archive(api),
        "filesystem_authorized_bool",
        True,
        "archive_guardrails_invalid",
    )


def test_source_byte_change_changes_layout_and_archive_commitments():
    api = _api()
    first = _archive(api)
    transcript = _transcript()
    changed_bodies = tuple(
        _body(request, response_time_ms=700_124) for request in transcript.plan.requests
    )
    changed_receipts = tuple(
        _response_api().accept_historical_response_page(
            plan=transcript.plan,
            request=request,
            http_status=200,
            content_type="application/json",
            raw_body_bytes=body,
        )
        for request, body in zip(transcript.plan.requests, changed_bodies, strict=True)
    )
    changed_transcript = _transcript_api().reconcile_historical_response_transcript(
        plan=transcript.plan,
        receipts=changed_receipts,
        raw_body_bytes=changed_bodies,
    )
    second = _archive(api, _layout(changed_transcript))
    assert first.layout_sha256 != second.layout_sha256
    assert first.archive_sha256 != second.archive_sha256
    assert first.archive_bytes != second.archive_bytes


def test_rebound_public_layout_and_archive_methods_cannot_suppress_validation(monkeypatch):
    api = _api()
    layout = _layout()
    monkeypatch.setattr(
        _evidence_api().HistoricalEvidenceLayout, "__post_init__", lambda self: None
    )
    object.__setattr__(layout, "member_count", 999)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as layout_caught:
        api.build_historical_evidence_archive(layout=layout)
    assert str(layout_caught.value) == "layout_revalidation_failed"
    assert isinstance(layout_caught.value.__cause__, _evidence_api().HistoricalEvidenceError)

    archive = api.build_historical_evidence_archive(layout=_layout())
    object.__setattr__(archive, "network_authorized_bool", True)
    monkeypatch.setattr(api.HistoricalEvidenceArchive, "__post_init__", lambda self: None)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        archive.canonical_json_bytes()
    assert str(caught.value) == "archive_guardrails_invalid"


def test_build_performs_no_filesystem_network_clock_environment_or_zipfile_calls(monkeypatch):
    api = _api()
    layout = _layout()

    def forbidden(*args, **kwargs):
        raise AssertionError("external_authority_called")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(time, "sleep", forbidden)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    archive = api.build_historical_evidence_archive(layout=layout)
    assert archive.filesystem_authorized_bool is False
    assert archive.network_authorized_bool is False
    assert archive.in_memory_archive_authorized_bool is True


def test_builder_rejects_positional_variadic_and_extra_authority_inputs():
    api = _api()
    layout = _layout()
    with pytest.raises(TypeError):
        api.build_historical_evidence_archive(layout)
    for name in (
        "path",
        "directory",
        "stream",
        "writer",
        "callback",
        "compression",
        "clock",
        "client",
        "environment",
        "persist",
    ):
        with pytest.raises(TypeError):
            api.build_historical_evidence_archive(layout=layout, **{name: object()})


def test_result_exposes_bytes_and_metadata_but_no_write_open_extract_or_install_method():
    api = _api()
    archive = _archive(api)
    public = {name for name in dir(archive) if not name.startswith("_")}
    assert public == set(EXPECTED_FIELD_NAMES) | {"canonical_json_bytes", "sha256"}
    forbidden_methods = {"write", "open", "extract", "extractall", "install", "upload"}
    assert forbidden_methods.isdisjoint(public)
    assert not any(
        callable(getattr(archive, name))
        and any(fragment in name.lower() for fragment in forbidden_methods)
        for name in public
    )


def test_each_root_commitment_is_exact_and_tamper_evident():
    api = _api()
    for name in (
        "plan_sha256",
        "transcript_sha256",
        "manifest_sha256",
        "layout_sha256",
        "member_sequence_sha256",
    ):
        archive = _archive(api)
        assert type(getattr(archive, name)) is str
        _tamper(api, archive, name, "0" * 64, "archive_commitments_invalid")


def test_exact_atoms_reject_boolean_and_builtin_subclass_aliases():
    api = _api()

    class Text(str):
        pass

    archive = _archive(api)
    _tamper(api, archive, "schema", Text(archive.schema), "archive_schema_invalid")
    archive = _archive(api)
    _tamper(
        api, archive, "layout_sha256", Text(archive.layout_sha256), "archive_commitments_invalid"
    )
    archive = _archive(api)
    _tamper(api, archive, "archive_byte_count", True, "archive_counts_invalid")
    archive = _archive(api)
    _tamper(api, archive, "zip_version_needed", True, "archive_zip_metadata_invalid")


def test_local_and_central_metadata_disagreement_fails_after_sha_recommitment():
    api = _api()
    archive = _archive(api)
    changed = bytearray(archive.archive_bytes)
    changed[6] = 1
    changed_bytes = bytes(changed)
    object.__setattr__(archive, "archive_bytes", changed_bytes)
    object.__setattr__(archive, "archive_sha256", _sha256(changed_bytes))
    with pytest.raises(api.HistoricalEvidenceArchiveError) as local_caught:
        archive.canonical_json_bytes()
    assert str(local_caught.value) == "archive_envelope_invalid"

    archive = _archive(api)
    _locals, _centrals, eocd = _parse_exact_zip32(archive.archive_bytes)
    changed = bytearray(archive.archive_bytes)
    struct.pack_into("<I", changed, eocd[6] + 42, 1)
    changed_bytes = bytes(changed)
    object.__setattr__(archive, "archive_bytes", changed_bytes)
    object.__setattr__(archive, "archive_sha256", _sha256(changed_bytes))
    with pytest.raises(api.HistoricalEvidenceArchiveError) as central_caught:
        archive.canonical_json_bytes()
    assert str(central_caught.value) == "archive_envelope_invalid"


def test_prefix_trailer_extra_and_comment_are_rejected():
    api = _api()
    archive = _archive(api)
    for changed in (b"X" + archive.archive_bytes, archive.archive_bytes + b"X"):
        candidate = _archive(api)
        object.__setattr__(candidate, "archive_bytes", changed)
        object.__setattr__(candidate, "archive_byte_count", len(changed))
        object.__setattr__(candidate, "archive_sha256", _sha256(changed))
        with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
            candidate.canonical_json_bytes()
        assert str(caught.value) == "archive_counts_invalid"

    archive = _archive(api)
    changed = bytearray(archive.archive_bytes)
    struct.pack_into("<H", changed, 28, 1)
    changed_bytes = bytes(changed)
    object.__setattr__(archive, "archive_bytes", changed_bytes)
    object.__setattr__(archive, "archive_sha256", _sha256(changed_bytes))
    with pytest.raises(api.HistoricalEvidenceArchiveError) as extra_caught:
        archive.canonical_json_bytes()
    assert str(extra_caught.value) == "archive_envelope_invalid"

    archive = _archive(api)
    changed = bytearray(archive.archive_bytes)
    struct.pack_into("<H", changed, len(changed) - 2, 1)
    changed_bytes = bytes(changed)
    object.__setattr__(archive, "archive_bytes", changed_bytes)
    object.__setattr__(archive, "archive_sha256", _sha256(changed_bytes))
    with pytest.raises(api.HistoricalEvidenceArchiveError) as comment_caught:
        archive.canonical_json_bytes()
    assert str(comment_caught.value) == "archive_envelope_invalid"


def test_rebound_source_builder_and_canonical_methods_are_not_authority(monkeypatch):
    api = _api()
    evidence = _evidence_api()
    layout = _layout()

    def forbidden(*args, **kwargs):
        raise AssertionError("rebound_source_called")

    monkeypatch.setattr(evidence, "build_historical_evidence_layout", forbidden)
    monkeypatch.setattr(evidence.HistoricalEvidenceLayout, "canonical_json_bytes", forbidden)
    archive = api.build_historical_evidence_archive(layout=layout)
    assert archive.layout is layout
    assert archive.layout_revalidated_bool is True


def test_nested_layout_revalidation_precedes_invalid_archive_fields():
    api = _api()
    archive = _archive(api)
    object.__setattr__(archive.layout, "member_count", 999)
    object.__setattr__(archive, "schema", "forged")
    object.__setattr__(archive, "archive_sha256", "0" * 64)
    with pytest.raises(api.HistoricalEvidenceArchiveError) as caught:
        archive.canonical_json_bytes()
    assert str(caught.value) == "layout_revalidation_failed"
    assert isinstance(caught.value.__cause__, _evidence_api().HistoricalEvidenceError)
