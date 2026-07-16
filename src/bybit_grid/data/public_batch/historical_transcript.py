from dataclasses import dataclass as _dataclass, fields as _fields
from decimal import Decimal as _Decimal
from enum import Enum as _Enum
import hashlib as _hashlib
import json as _json
import re as _re

from .historical_plan import (
    HistoricalCapturePlan as _HistoricalCapturePlan,
    HistoricalPlanError as _HistoricalPlanError,
    HistoricalRequestSpec as _HistoricalRequestSpec,
)
from .historical_response import (
    HistoricalResponseError as _HistoricalResponseError,
    HistoricalResponseReceipt as _HistoricalResponseReceipt,
    accept_historical_response_page as _accept_historical_response_page,
)
from .models import (
    BybitFundingRate as _BybitFundingRate,
    BybitMarkKline1m as _BybitMarkKline1m,
    BybitTradeKline1m as _BybitTradeKline1m,
)


MAX_HISTORICAL_TRANSCRIPT_PAGES = 256
MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES = 268_435_456


class HistoricalTranscriptError(ValueError):
    pass


def _fail(code: str) -> None:
    raise HistoricalTranscriptError(code)


def _is_exact_nonnegative_int(value: object) -> bool:
    return type(value) is int and 0 <= value <= (1 << 63) - 1


def _hash_is_valid(value: object) -> bool:
    return type(value) is str and _re.fullmatch(r"[0-9a-f]{64}", value, flags=_re.ASCII) is not None


def _hash_matches(value: object, expected: str) -> bool:
    return _hash_is_valid(value) and value == expected


def _hash_tuple_matches(value: object, expected: tuple[str, ...]) -> bool:
    return (
        type(value) is tuple
        and len(value) == len(expected)
        and all(
            _hash_matches(actual, wanted) for actual, wanted in zip(value, expected, strict=True)
        )
    )


def _decimal_text(value: _Decimal) -> str:
    if type(value) is not _Decimal or not value.is_finite():
        _fail("transcript_rows_invalid")
    if value == 0:
        return "0"
    sign, digits, exponent = value.as_tuple()
    coefficient = "".join(str(digit) for digit in digits) or "0"
    if exponent >= 0:
        if len(coefficient) + exponent + sign > 128:
            _fail("transcript_rows_invalid")
        text = coefficient + "0" * exponent
    else:
        places = -exponent
        estimated = (len(coefficient) + 1 if places < len(coefficient) else places + 2) + sign
        if estimated > 128:
            _fail("transcript_rows_invalid")
        if places < len(coefficient):
            text = coefficient[:-places] + "." + coefficient[-places:]
        else:
            text = "0." + "0" * (places - len(coefficient)) + coefficient
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if sign:
        text = "-" + text
    return "0" if text in ("", "-0") else text


def _plain(value: object) -> object:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is _Decimal:
        return _decimal_text(value)
    if isinstance(value, _Enum):
        return value.value
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    if type(value) is dict:
        return {key: _plain(value[key]) for key in sorted(value)}
    if type(value) in (
        _HistoricalRequestSpec,
        _HistoricalCapturePlan,
        _HistoricalResponseReceipt,
        _BybitTradeKline1m,
        _BybitMarkKline1m,
        _BybitFundingRate,
    ):
        return {field.name: _plain(getattr(value, field.name)) for field in _fields(value)}
    _fail("transcript_canonical_value_invalid")


def _canonical_json_bytes(value: object) -> bytes:
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


def _digest(value: object) -> str:
    return _hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _request_sha256(request: _HistoricalRequestSpec) -> str:
    return _digest(request)


def _plan_sha256(plan: _HistoricalCapturePlan) -> str:
    return _digest(plan)


def _receipt_bytes(receipt: _HistoricalResponseReceipt) -> bytes:
    return _canonical_json_bytes(receipt)


def _receipt_sha256(receipt: _HistoricalResponseReceipt) -> str:
    return _hashlib.sha256(_receipt_bytes(receipt)).hexdigest()


def _timestamp(row: object) -> int:
    if type(row) in (_BybitTradeKline1m, _BybitMarkKline1m):
        return row.open_time_ms
    if type(row) is _BybitFundingRate:
        return row.funding_time_ms
    _fail("transcript_rows_invalid")


def _validate_plan(plan: object) -> tuple[_HistoricalCapturePlan, str]:
    if type(plan) is not _HistoricalCapturePlan:
        _fail("plan_not_exact_model")
    try:
        requests = plan.requests
        if type(requests) is not tuple or any(
            type(request) is not _HistoricalRequestSpec for request in requests
        ):
            raise TypeError
        for request in requests:
            _HistoricalRequestSpec.__post_init__(request)
        _HistoricalCapturePlan.__post_init__(plan)
        plan_sha256 = _plan_sha256(plan)
    except (AttributeError, TypeError, _HistoricalPlanError) as exc:
        raise HistoricalTranscriptError("plan_invariants_invalid") from exc
    return plan, plan_sha256


def _receipt_matches_request(
    receipt: _HistoricalResponseReceipt,
    plan: _HistoricalCapturePlan,
    request: _HistoricalRequestSpec,
    plan_sha256: str,
) -> bool:
    return (
        receipt.plan_sha256 == plan_sha256
        and receipt.request_sha256 == _request_sha256(request)
        and receipt.sequence_id == request.sequence_id
        and receipt.dataset == request.dataset
        and receipt.endpoint == request.endpoint
        and receipt.category == plan.category
        and receipt.symbol == plan.symbol
        and receipt.request_start_ms == request.start_ms
        and receipt.request_end_ms == request.end_ms
        and receipt.request_limit == request.limit
        and receipt.request_target_row_count == request.target_row_count
    )


def _verify_inputs(
    plan: _HistoricalCapturePlan,
    plan_sha256: str,
    receipts: object,
    raw_body_bytes: object,
) -> tuple[tuple[_HistoricalResponseReceipt, ...], tuple[bytes, ...]]:
    if type(receipts) is not tuple:
        _fail("receipts_not_exact_tuple")
    if type(raw_body_bytes) is not tuple:
        _fail("raw_body_bytes_not_exact_tuple")
    if len(receipts) != len(plan.requests) or len(raw_body_bytes) != len(plan.requests):
        _fail("transcript_length_mismatch")
    if len(receipts) > 256:
        _fail("transcript_page_limit_exceeded")
    if any(type(receipt) is not _HistoricalResponseReceipt for receipt in receipts):
        _fail("receipt_not_exact_model")
    if any(type(raw_body) is not bytes for raw_body in raw_body_bytes):
        _fail("raw_body_not_exact_bytes")
    if sum(len(raw_body) for raw_body in raw_body_bytes) > 268_435_456:
        _fail("transcript_raw_body_limit_exceeded")

    for receipt in receipts:
        try:
            _HistoricalResponseReceipt.__post_init__(receipt)
        except (AttributeError, TypeError, _HistoricalResponseError) as exc:
            raise HistoricalTranscriptError("receipt_invariants_invalid") from exc
    for receipt, request in zip(receipts, plan.requests, strict=True):
        if not _receipt_matches_request(receipt, plan, request, plan_sha256):
            _fail("receipt_request_binding_invalid")

    recomputed: list[_HistoricalResponseReceipt] = []
    for receipt, request, raw_body in zip(
        receipts,
        plan.requests,
        raw_body_bytes,
        strict=True,
    ):
        try:
            admitted = _accept_historical_response_page(
                plan=plan,
                request=request,
                http_status=receipt.http_status,
                content_type=receipt.content_type,
                raw_body_bytes=raw_body,
            )
        except _HistoricalResponseError as exc:
            raise HistoricalTranscriptError("raw_body_reverification_failed") from exc
        if type(admitted) is not _HistoricalResponseReceipt:
            _fail("recomputed_receipt_invalid")
        recomputed.append(admitted)
    if any(
        _receipt_bytes(supplied) != _receipt_bytes(admitted)
        for supplied, admitted in zip(receipts, recomputed, strict=True)
    ):
        _fail("receipt_canonical_mismatch")
    return receipts, raw_body_bytes


def _aggregate(
    receipts: tuple[_HistoricalResponseReceipt, ...],
) -> tuple[tuple[object, ...], tuple[object, ...], tuple[object, ...]]:
    groups: dict[str, list[object]] = {
        "trade_kline_1m": [],
        "mark_kline_1m": [],
        "funding_rate": [],
    }
    for receipt in receipts:
        groups[receipt.dataset].extend(receipt.rows)
    outputs: list[tuple[object, ...]] = []
    for dataset in ("trade_kline_1m", "mark_kline_1m", "funding_rate"):
        rows = groups[dataset]
        timestamps = tuple(_timestamp(row) for row in rows)
        if len(timestamps) != len(set(timestamps)):
            _fail("cross_page_timestamp_duplicate")
        canonical = tuple(sorted(rows, key=_timestamp))
        canonical_timestamps = tuple(_timestamp(row) for row in canonical)
        if canonical_timestamps != tuple(sorted(canonical_timestamps)):
            _fail("canonical_dataset_row_order_invalid")
        outputs.append(canonical)
    return outputs[0], outputs[1], outputs[2]


def _endpoints(rows: tuple[object, ...]) -> tuple[int | None, int | None]:
    if not rows:
        return None, None
    return _timestamp(rows[0]), _timestamp(rows[-1])


def _endpoint_matches(value: object, expected: int | None) -> bool:
    if expected is None:
        return value is None
    return type(value) is int and value == expected


def _rows_are_exact_retained_objects(
    retained: object,
    expected: tuple[object, ...],
) -> bool:
    return (
        type(retained) is tuple
        and len(retained) == len(expected)
        and all(actual is source for actual, source in zip(retained, expected, strict=True))
    )


@_dataclass(frozen=True, slots=True, init=False)
class HistoricalResponseTranscript:
    schema: str
    plan_sha256: str
    request_count: int
    receipt_count: int
    raw_body_page_count: int
    total_raw_body_byte_count: int
    max_transcript_pages: int
    max_transcript_raw_body_bytes: int
    request_sha256s: tuple[str, ...]
    raw_body_sha256s: tuple[str, ...]
    receipt_sha256s: tuple[str, ...]
    request_sequence_sha256: str
    raw_body_sequence_sha256: str
    receipt_sequence_sha256: str
    trade_row_count: int
    mark_row_count: int
    funding_row_count: int
    trade_first_timestamp_ms: int | None
    trade_last_timestamp_ms: int | None
    mark_first_timestamp_ms: int | None
    mark_last_timestamp_ms: int | None
    funding_first_timestamp_ms: int | None
    funding_last_timestamp_ms: int | None
    trade_timestamps_sha256: str
    mark_timestamps_sha256: str
    funding_timestamps_sha256: str
    trade_rows_sha256: str
    mark_rows_sha256: str
    funding_rows_sha256: str
    request_graph_reconciled_bool: bool
    raw_bodies_reverified_bool: bool
    receipts_canonical_match_bool: bool
    sequence_exact_bool: bool
    cross_page_timestamps_unique_bool: bool
    canonical_dataset_row_order_bool: bool
    network_authorized_bool: bool
    filesystem_authorized_bool: bool
    persistence_authorized_bool: bool
    credentials_allowed_bool: bool
    private_api_allowed_bool: bool
    telegram_authorized_bool: bool
    ordinary_order_authorized_bool: bool
    native_grid_mutation_authorized_bool: bool
    wallet_authorized_bool: bool
    position_mutation_authorized_bool: bool
    live_execution_authorized_bool: bool
    funding_coverage_proven_bool: bool
    historical_market_data_coverage_proven_bool: bool
    parameter_selection_authorized_bool: bool
    sufficient_for_parameter_selection_bool: bool
    native_equivalence_proven_bool: bool
    plan: _HistoricalCapturePlan
    receipts: tuple[_HistoricalResponseReceipt, ...]
    raw_body_bytes: tuple[bytes, ...]
    trade_rows: tuple[_BybitTradeKline1m, ...]
    mark_rows: tuple[_BybitMarkKline1m, ...]
    funding_rows: tuple[_BybitFundingRate, ...]

    def __init__(self, *args, **kwargs) -> None:
        _fail("transcript_factory_only")

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not str
            or self.schema != "bybit_public_historical_response_transcript_v1"
        ):
            _fail("transcript_schema_invalid")
        plan, plan_sha256 = _validate_plan(self.plan)
        if self.plan_sha256 != plan_sha256 or not _hash_is_valid(self.plan_sha256):
            _fail("transcript_plan_sha256_invalid")
        receipts, raw_bodies = _verify_inputs(
            plan,
            plan_sha256,
            self.receipts,
            self.raw_body_bytes,
        )
        trade_rows, mark_rows, funding_rows = _aggregate(receipts)
        expected_request_sha256s = tuple(_request_sha256(request) for request in plan.requests)
        expected_raw_body_sha256s = tuple(
            _hashlib.sha256(raw_body).hexdigest() for raw_body in raw_bodies
        )
        expected_receipt_sha256s = tuple(_receipt_sha256(receipt) for receipt in receipts)
        count_fields = (
            self.request_count,
            self.receipt_count,
            self.raw_body_page_count,
            self.total_raw_body_byte_count,
            self.trade_row_count,
            self.mark_row_count,
            self.funding_row_count,
        )
        if any(not _is_exact_nonnegative_int(value) for value in count_fields):
            _fail("transcript_counts_invalid")
        if (
            self.request_count != len(plan.requests)
            or self.receipt_count != len(receipts)
            or self.raw_body_page_count != len(raw_bodies)
            or self.total_raw_body_byte_count != sum(map(len, raw_bodies))
            or self.trade_row_count != len(trade_rows)
            or self.mark_row_count != len(mark_rows)
            or self.funding_row_count != len(funding_rows)
        ):
            _fail("transcript_counts_invalid")
        if (
            type(self.max_transcript_pages) is not int
            or self.max_transcript_pages != 256
            or type(self.max_transcript_raw_body_bytes) is not int
            or self.max_transcript_raw_body_bytes != 268_435_456
        ):
            _fail("transcript_fixed_limits_invalid")
        if (
            not _hash_tuple_matches(self.request_sha256s, expected_request_sha256s)
            or not _hash_tuple_matches(self.raw_body_sha256s, expected_raw_body_sha256s)
            or not _hash_tuple_matches(self.receipt_sha256s, expected_receipt_sha256s)
            or not _hash_matches(
                self.request_sequence_sha256,
                _digest(expected_request_sha256s),
            )
            or not _hash_matches(
                self.raw_body_sequence_sha256,
                _digest(expected_raw_body_sha256s),
            )
            or not _hash_matches(
                self.receipt_sequence_sha256,
                _digest(expected_receipt_sha256s),
            )
        ):
            _fail("transcript_sequence_digests_invalid")
        expected_rows = (trade_rows, mark_rows, funding_rows)
        retained_rows = (self.trade_rows, self.mark_rows, self.funding_rows)
        if any(
            not _rows_are_exact_retained_objects(retained, expected)
            for retained, expected in zip(retained_rows, expected_rows, strict=True)
        ):
            _fail("transcript_rows_invalid")
        endpoints = tuple(_endpoints(rows) for rows in expected_rows)
        if (
            not _endpoint_matches(self.trade_first_timestamp_ms, endpoints[0][0])
            or not _endpoint_matches(self.trade_last_timestamp_ms, endpoints[0][1])
            or not _endpoint_matches(self.mark_first_timestamp_ms, endpoints[1][0])
            or not _endpoint_matches(self.mark_last_timestamp_ms, endpoints[1][1])
            or not _endpoint_matches(self.funding_first_timestamp_ms, endpoints[2][0])
            or not _endpoint_matches(self.funding_last_timestamp_ms, endpoints[2][1])
        ):
            _fail("transcript_timestamp_endpoints_invalid")
        timestamps = tuple(tuple(_timestamp(row) for row in rows) for rows in expected_rows)
        if (
            not _hash_matches(self.trade_timestamps_sha256, _digest(timestamps[0]))
            or not _hash_matches(self.mark_timestamps_sha256, _digest(timestamps[1]))
            or not _hash_matches(self.funding_timestamps_sha256, _digest(timestamps[2]))
            or not _hash_matches(self.trade_rows_sha256, _digest(trade_rows))
            or not _hash_matches(self.mark_rows_sha256, _digest(mark_rows))
            or not _hash_matches(self.funding_rows_sha256, _digest(funding_rows))
        ):
            _fail("transcript_dataset_digests_invalid")
        for value in (
            self.request_graph_reconciled_bool,
            self.raw_bodies_reverified_bool,
            self.receipts_canonical_match_bool,
            self.sequence_exact_bool,
            self.cross_page_timestamps_unique_bool,
            self.canonical_dataset_row_order_bool,
        ):
            if type(value) is not bool or value is not True:
                _fail("transcript_reconciliation_flags_invalid")
        for value in (
            self.network_authorized_bool,
            self.filesystem_authorized_bool,
            self.persistence_authorized_bool,
            self.credentials_allowed_bool,
            self.private_api_allowed_bool,
            self.telegram_authorized_bool,
            self.ordinary_order_authorized_bool,
            self.native_grid_mutation_authorized_bool,
            self.wallet_authorized_bool,
            self.position_mutation_authorized_bool,
            self.live_execution_authorized_bool,
            self.funding_coverage_proven_bool,
            self.historical_market_data_coverage_proven_bool,
            self.parameter_selection_authorized_bool,
            self.sufficient_for_parameter_selection_bool,
            self.native_equivalence_proven_bool,
        ):
            if type(value) is not bool or value is not False:
                _fail("transcript_guardrails_invalid")

    def canonical_json_bytes(self) -> bytes:
        HistoricalResponseTranscript.__post_init__(self)
        payload = {
            field.name: getattr(self, field.name)
            for field in _fields(self)
            if field.name != "raw_body_bytes"
        }
        return _canonical_json_bytes(payload)

    def sha256(self) -> str:
        return _hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def _build_transcript(**values: object) -> HistoricalResponseTranscript:
    names = tuple(field.name for field in _fields(HistoricalResponseTranscript))
    if set(values) != set(names):
        _fail("transcript_builder_fields_invalid")
    transcript = object.__new__(HistoricalResponseTranscript)
    for name in names:
        object.__setattr__(transcript, name, values[name])
    HistoricalResponseTranscript.__post_init__(transcript)
    return transcript


def reconcile_historical_response_transcript(*, plan, receipts, raw_body_bytes):
    plan, plan_sha256 = _validate_plan(plan)
    receipts, raw_bodies = _verify_inputs(plan, plan_sha256, receipts, raw_body_bytes)
    trade_rows, mark_rows, funding_rows = _aggregate(receipts)
    request_sha256s = tuple(_request_sha256(request) for request in plan.requests)
    raw_body_sha256s = tuple(_hashlib.sha256(body).hexdigest() for body in raw_bodies)
    receipt_sha256s = tuple(_receipt_sha256(receipt) for receipt in receipts)
    trade_endpoints = _endpoints(trade_rows)
    mark_endpoints = _endpoints(mark_rows)
    funding_endpoints = _endpoints(funding_rows)
    return _build_transcript(
        schema="bybit_public_historical_response_transcript_v1",
        plan_sha256=plan_sha256,
        request_count=len(plan.requests),
        receipt_count=len(receipts),
        raw_body_page_count=len(raw_bodies),
        total_raw_body_byte_count=sum(map(len, raw_bodies)),
        max_transcript_pages=256,
        max_transcript_raw_body_bytes=268_435_456,
        request_sha256s=request_sha256s,
        raw_body_sha256s=raw_body_sha256s,
        receipt_sha256s=receipt_sha256s,
        request_sequence_sha256=_digest(request_sha256s),
        raw_body_sequence_sha256=_digest(raw_body_sha256s),
        receipt_sequence_sha256=_digest(receipt_sha256s),
        trade_row_count=len(trade_rows),
        mark_row_count=len(mark_rows),
        funding_row_count=len(funding_rows),
        trade_first_timestamp_ms=trade_endpoints[0],
        trade_last_timestamp_ms=trade_endpoints[1],
        mark_first_timestamp_ms=mark_endpoints[0],
        mark_last_timestamp_ms=mark_endpoints[1],
        funding_first_timestamp_ms=funding_endpoints[0],
        funding_last_timestamp_ms=funding_endpoints[1],
        trade_timestamps_sha256=_digest(tuple(_timestamp(row) for row in trade_rows)),
        mark_timestamps_sha256=_digest(tuple(_timestamp(row) for row in mark_rows)),
        funding_timestamps_sha256=_digest(tuple(_timestamp(row) for row in funding_rows)),
        trade_rows_sha256=_digest(trade_rows),
        mark_rows_sha256=_digest(mark_rows),
        funding_rows_sha256=_digest(funding_rows),
        request_graph_reconciled_bool=True,
        raw_bodies_reverified_bool=True,
        receipts_canonical_match_bool=True,
        sequence_exact_bool=True,
        cross_page_timestamps_unique_bool=True,
        canonical_dataset_row_order_bool=True,
        network_authorized_bool=False,
        filesystem_authorized_bool=False,
        persistence_authorized_bool=False,
        credentials_allowed_bool=False,
        private_api_allowed_bool=False,
        telegram_authorized_bool=False,
        ordinary_order_authorized_bool=False,
        native_grid_mutation_authorized_bool=False,
        wallet_authorized_bool=False,
        position_mutation_authorized_bool=False,
        live_execution_authorized_bool=False,
        funding_coverage_proven_bool=False,
        historical_market_data_coverage_proven_bool=False,
        parameter_selection_authorized_bool=False,
        sufficient_for_parameter_selection_bool=False,
        native_equivalence_proven_bool=False,
        plan=plan,
        receipts=receipts,
        raw_body_bytes=raw_bodies,
        trade_rows=trade_rows,
        mark_rows=mark_rows,
        funding_rows=funding_rows,
    )


__all__ = (
    "HistoricalResponseTranscript",
    "HistoricalTranscriptError",
    "MAX_HISTORICAL_TRANSCRIPT_PAGES",
    "MAX_HISTORICAL_TRANSCRIPT_RAW_BODY_BYTES",
    "reconcile_historical_response_transcript",
)
