from dataclasses import dataclass as _dataclass, fields as _fields
import hashlib as _hashlib
import json as _json
import re as _re

from .historical_transcript import (
    HistoricalResponseTranscript as _HistoricalResponseTranscript,
    HistoricalTranscriptError as _HistoricalTranscriptError,
    reconcile_historical_response_transcript as _reconcile_historical_response_transcript,
)


_TRANSCRIPT_POST_INIT = _HistoricalResponseTranscript.__post_init__
_TRANSCRIPT_CANONICAL_JSON_BYTES = _HistoricalResponseTranscript.canonical_json_bytes


class HistoricalEvidenceError(ValueError):
    pass


def _fail(code: str) -> None:
    raise HistoricalEvidenceError(code)


def _is_exact_nonnegative_int(value: object) -> bool:
    return type(value) is int and 0 <= value <= (1 << 63) - 1


def _hash_is_valid(value: object) -> bool:
    return type(value) is str and _re.fullmatch(r"[0-9a-f]{64}", value, flags=_re.ASCII) is not None


def _plain(value: object) -> object:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _fail("layout_canonical_value_invalid")
        return {key: _plain(value[key]) for key in sorted(value)}
    _fail("layout_canonical_value_invalid")


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            _json.dumps(
                _plain(value),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except HistoricalEvidenceError:
        raise
    except (OverflowError, TypeError, ValueError) as exc:
        raise HistoricalEvidenceError("layout_canonical_json_invalid") from exc


def _sha256(value: bytes) -> str:
    return _hashlib.sha256(value).hexdigest()


def _raw_name(index: int) -> str:
    return f"raw/{index:06d}.json"


def _name_is_safe(name: object) -> bool:
    return (
        type(name) is str
        and name.isascii()
        and ".." not in name
        and "\\" not in name
        and not name.startswith("/")
        and (
            name in ("manifest.json", "transcript.json")
            or _re.fullmatch(r"raw/[0-9]{6}\.json", name, flags=_re.ASCII) is not None
        )
    )


def _descriptor(name: str, payload: bytes) -> dict[str, object]:
    return {
        "byte_count": len(payload),
        "name": name,
        "sha256": _sha256(payload),
    }


def _transcript_material(
    transcript: object,
) -> tuple[_HistoricalResponseTranscript, bytes, str]:
    if type(transcript) is not _HistoricalResponseTranscript:
        _fail("transcript_not_exact_model")
    try:
        _TRANSCRIPT_POST_INIT(transcript)
        recomputed = _reconcile_historical_response_transcript(
            plan=transcript.plan,
            receipts=transcript.receipts,
            raw_body_bytes=transcript.raw_body_bytes,
        )
        transcript_bytes = _TRANSCRIPT_CANONICAL_JSON_BYTES(transcript)
        recomputed_bytes = _TRANSCRIPT_CANONICAL_JSON_BYTES(recomputed)
    except (_HistoricalTranscriptError, AttributeError, TypeError) as exc:
        raise HistoricalEvidenceError("transcript_revalidation_failed") from exc
    if type(recomputed) is not _HistoricalResponseTranscript:
        _fail("transcript_recomputation_invalid")
    if type(transcript_bytes) is not bytes or type(recomputed_bytes) is not bytes:
        _fail("transcript_canonical_bytes_invalid")
    if transcript_bytes != recomputed_bytes:
        _fail("transcript_canonical_mismatch")
    return transcript, transcript_bytes, _sha256(transcript_bytes)


def _expected_layout_material(
    transcript: _HistoricalResponseTranscript,
    transcript_bytes: bytes,
    transcript_sha256: str,
) -> tuple[tuple[str, ...], tuple[bytes, ...]]:
    raw_names = tuple(_raw_name(index) for index in range(len(transcript.raw_body_bytes)))
    payload_names = ("transcript.json",) + raw_names
    payload_bytes = (transcript_bytes,) + transcript.raw_body_bytes
    payload_descriptors = tuple(
        _descriptor(name, payload)
        for name, payload in zip(payload_names, payload_bytes, strict=True)
    )
    manifest_bytes = _canonical_json_bytes(
        {
            "payload_member_count": len(payload_names),
            "payload_members": payload_descriptors,
            "schema": "bybit_public_historical_evidence_manifest_v1",
            "transcript_sha256": transcript_sha256,
        }
    )
    return ("manifest.json",) + payload_names, (manifest_bytes,) + payload_bytes


def _member_sequence_sha256(
    names: tuple[str, ...],
    payloads: tuple[bytes, ...],
) -> str:
    descriptors = tuple(
        _descriptor(name, payload) for name, payload in zip(names, payloads, strict=True)
    )
    return _sha256(_canonical_json_bytes(descriptors))


def _exact_true(value: object) -> None:
    if type(value) is not bool or value is not True:
        _fail("layout_evidence_flags_invalid")


def _exact_false(value: object) -> None:
    if type(value) is not bool or value is not False:
        _fail("layout_guardrails_invalid")


@_dataclass(frozen=True, slots=True, init=False)
class HistoricalEvidenceLayout:
    schema: str
    plan_sha256: str
    transcript_sha256: str
    manifest_sha256: str
    member_count: int
    raw_member_count: int
    total_member_byte_count: int
    max_layout_members: int
    member_names: tuple[str, ...]
    member_byte_counts: tuple[int, ...]
    member_sha256s: tuple[str, ...]
    member_sequence_sha256: str
    transcript_revalidated_bool: bool
    manifest_payload_committed_bool: bool
    manifest_self_excluded_bool: bool
    member_commitments_verified_bool: bool
    member_sequence_exact_bool: bool
    member_names_safe_bool: bool
    raw_body_identity_retained_bool: bool
    network_authorized_bool: bool
    transport_authorized_bool: bool
    filesystem_authorized_bool: bool
    archive_authorized_bool: bool
    persistence_authorized_bool: bool
    store_projection_authorized_bool: bool
    store_install_authorized_bool: bool
    credentials_allowed_bool: bool
    private_api_allowed_bool: bool
    telegram_authorized_bool: bool
    ordinary_order_authorized_bool: bool
    native_grid_mutation_authorized_bool: bool
    wallet_authorized_bool: bool
    position_mutation_authorized_bool: bool
    live_execution_authorized_bool: bool
    source_authenticity_proven_bool: bool
    account_eligibility_proven_bool: bool
    account_region_eligibility_proven_bool: bool
    bybit_product_availability_proven_bool: bool
    funding_coverage_proven_bool: bool
    historical_market_data_coverage_proven_bool: bool
    parameter_selection_authorized_bool: bool
    sufficient_for_parameter_selection_bool: bool
    native_equivalence_proven_bool: bool
    transcript: _HistoricalResponseTranscript
    member_bytes: tuple[bytes, ...]

    def __init__(self, *args, **kwargs) -> None:
        _fail("layout_factory_only")

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not str
            or self.schema != "bybit_public_historical_evidence_layout_v1"
        ):
            _fail("layout_schema_invalid")
        transcript, transcript_bytes, transcript_sha256 = _transcript_material(self.transcript)
        expected_names, expected_bytes = _expected_layout_material(
            transcript,
            transcript_bytes,
            transcript_sha256,
        )
        if type(self.member_names) is not tuple or len(self.member_names) != len(expected_names):
            _fail("layout_member_names_invalid")
        if any(type(name) is not str for name in self.member_names):
            _fail("layout_member_names_invalid")
        if self.member_names != expected_names:
            _fail("layout_member_names_invalid")
        if len(set(self.member_names)) != len(self.member_names) or any(
            not _name_is_safe(name) for name in self.member_names
        ):
            _fail("layout_member_names_invalid")
        if type(self.member_bytes) is not tuple or len(self.member_bytes) != len(expected_bytes):
            _fail("layout_member_bytes_invalid")
        if any(type(payload) is not bytes for payload in self.member_bytes):
            _fail("layout_member_bytes_invalid")
        if self.member_bytes[:2] != expected_bytes[:2]:
            _fail("layout_member_bytes_invalid")
        if len(self.member_bytes[2:]) != len(transcript.raw_body_bytes) or any(
            actual is not source
            for actual, source in zip(self.member_bytes[2:], transcript.raw_body_bytes, strict=True)
        ):
            _fail("layout_raw_body_identity_invalid")
        expected_counts = tuple(len(payload) for payload in expected_bytes)
        expected_sha256s = tuple(_sha256(payload) for payload in expected_bytes)
        if (
            type(self.member_byte_counts) is not tuple
            or len(self.member_byte_counts) != len(expected_counts)
            or any(not _is_exact_nonnegative_int(value) for value in self.member_byte_counts)
            or self.member_byte_counts != expected_counts
        ):
            _fail("layout_member_commitments_invalid")
        if (
            type(self.member_sha256s) is not tuple
            or len(self.member_sha256s) != len(expected_sha256s)
            or any(not _hash_is_valid(value) for value in self.member_sha256s)
            or self.member_sha256s != expected_sha256s
        ):
            _fail("layout_member_commitments_invalid")
        expected_sequence_sha256 = _member_sequence_sha256(expected_names, expected_bytes)
        if (
            not _hash_is_valid(self.member_sequence_sha256)
            or self.member_sequence_sha256 != expected_sequence_sha256
        ):
            _fail("layout_member_commitments_invalid")
        count_values = (
            self.member_count,
            self.raw_member_count,
            self.total_member_byte_count,
            self.max_layout_members,
        )
        if any(not _is_exact_nonnegative_int(value) for value in count_values):
            _fail("layout_counts_invalid")
        if (
            self.member_count != len(expected_names)
            or self.raw_member_count != len(transcript.raw_body_bytes)
            or self.total_member_byte_count != sum(expected_counts)
            or self.max_layout_members != 258
            or self.member_count > 258
        ):
            _fail("layout_counts_invalid")
        if (
            not _hash_is_valid(self.plan_sha256)
            or self.plan_sha256 != transcript.plan_sha256
            or not _hash_is_valid(self.transcript_sha256)
            or self.transcript_sha256 != transcript_sha256
            or not _hash_is_valid(self.manifest_sha256)
            or self.manifest_sha256 != expected_sha256s[0]
        ):
            _fail("layout_root_commitments_invalid")
        for value in (
            self.transcript_revalidated_bool,
            self.manifest_payload_committed_bool,
            self.manifest_self_excluded_bool,
            self.member_commitments_verified_bool,
            self.member_sequence_exact_bool,
            self.member_names_safe_bool,
            self.raw_body_identity_retained_bool,
        ):
            _exact_true(value)
        for value in (
            self.network_authorized_bool,
            self.transport_authorized_bool,
            self.filesystem_authorized_bool,
            self.archive_authorized_bool,
            self.persistence_authorized_bool,
            self.store_projection_authorized_bool,
            self.store_install_authorized_bool,
            self.credentials_allowed_bool,
            self.private_api_allowed_bool,
            self.telegram_authorized_bool,
            self.ordinary_order_authorized_bool,
            self.native_grid_mutation_authorized_bool,
            self.wallet_authorized_bool,
            self.position_mutation_authorized_bool,
            self.live_execution_authorized_bool,
            self.source_authenticity_proven_bool,
            self.account_eligibility_proven_bool,
            self.account_region_eligibility_proven_bool,
            self.bybit_product_availability_proven_bool,
            self.funding_coverage_proven_bool,
            self.historical_market_data_coverage_proven_bool,
            self.parameter_selection_authorized_bool,
            self.sufficient_for_parameter_selection_bool,
            self.native_equivalence_proven_bool,
        ):
            _exact_false(value)

    def canonical_json_bytes(self) -> bytes:
        _validate_layout(self)
        return _canonical_json_bytes(
            {
                field.name: getattr(self, field.name)
                for field in _fields(self)
                if field.name not in ("transcript", "member_bytes")
            }
        )

    def sha256(self) -> str:
        return _sha256(self.canonical_json_bytes())


_LAYOUT_POST_INIT = HistoricalEvidenceLayout.__post_init__


def _validate_layout(layout: HistoricalEvidenceLayout) -> None:
    _LAYOUT_POST_INIT(layout)


def _build_layout(**values: object) -> HistoricalEvidenceLayout:
    names = tuple(field.name for field in _fields(HistoricalEvidenceLayout))
    if set(values) != set(names):
        _fail("layout_builder_fields_invalid")
    layout = object.__new__(HistoricalEvidenceLayout)
    for name in names:
        object.__setattr__(layout, name, values[name])
    _validate_layout(layout)
    return layout


def build_historical_evidence_layout(*, transcript):
    transcript, transcript_bytes, transcript_sha256 = _transcript_material(transcript)
    member_names, member_bytes = _expected_layout_material(
        transcript,
        transcript_bytes,
        transcript_sha256,
    )
    member_byte_counts = tuple(len(payload) for payload in member_bytes)
    member_sha256s = tuple(_sha256(payload) for payload in member_bytes)
    return _build_layout(
        schema="bybit_public_historical_evidence_layout_v1",
        plan_sha256=transcript.plan_sha256,
        transcript_sha256=transcript_sha256,
        manifest_sha256=member_sha256s[0],
        member_count=len(member_names),
        raw_member_count=len(transcript.raw_body_bytes),
        total_member_byte_count=sum(member_byte_counts),
        max_layout_members=258,
        member_names=member_names,
        member_byte_counts=member_byte_counts,
        member_sha256s=member_sha256s,
        member_sequence_sha256=_member_sequence_sha256(member_names, member_bytes),
        transcript_revalidated_bool=True,
        manifest_payload_committed_bool=True,
        manifest_self_excluded_bool=True,
        member_commitments_verified_bool=True,
        member_sequence_exact_bool=True,
        member_names_safe_bool=True,
        raw_body_identity_retained_bool=True,
        network_authorized_bool=False,
        transport_authorized_bool=False,
        filesystem_authorized_bool=False,
        archive_authorized_bool=False,
        persistence_authorized_bool=False,
        store_projection_authorized_bool=False,
        store_install_authorized_bool=False,
        credentials_allowed_bool=False,
        private_api_allowed_bool=False,
        telegram_authorized_bool=False,
        ordinary_order_authorized_bool=False,
        native_grid_mutation_authorized_bool=False,
        wallet_authorized_bool=False,
        position_mutation_authorized_bool=False,
        live_execution_authorized_bool=False,
        source_authenticity_proven_bool=False,
        account_eligibility_proven_bool=False,
        account_region_eligibility_proven_bool=False,
        bybit_product_availability_proven_bool=False,
        funding_coverage_proven_bool=False,
        historical_market_data_coverage_proven_bool=False,
        parameter_selection_authorized_bool=False,
        sufficient_for_parameter_selection_bool=False,
        native_equivalence_proven_bool=False,
        transcript=transcript,
        member_bytes=member_bytes,
    )


__all__ = (
    "HistoricalEvidenceError",
    "HistoricalEvidenceLayout",
    "build_historical_evidence_layout",
)
