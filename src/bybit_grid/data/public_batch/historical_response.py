from dataclasses import dataclass as _dataclass, fields as _fields
from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation
from enum import Enum as _Enum
import hashlib as _hashlib
import json as _json
import re as _re

from .historical_plan import (
    HistoricalCapturePlan as _HistoricalCapturePlan,
    HistoricalPlanError as _HistoricalPlanError,
    HistoricalRequestSpec as _HistoricalRequestSpec,
)
from .models import (
    BybitFundingRate as _BybitFundingRate,
    BybitMarkKline1m as _BybitMarkKline1m,
    BybitTradeKline1m as _BybitTradeKline1m,
    InclusiveMinuteWindow as _InclusiveMinuteWindow,
    PublicBatchError as _PublicBatchError,
)
from .parsers import (
    parse_funding_page as _parse_funding_page,
    parse_mark_kline_page as _parse_mark_kline_page,
    parse_trade_kline_page as _parse_trade_kline_page,
)


MAX_HISTORICAL_RESPONSE_BODY_BYTES = 1_048_576


class HistoricalResponseError(ValueError):
    pass


def _fail(code: str) -> None:
    raise HistoricalResponseError(code)


def _is_exact_int64(value: object, *, nonnegative: bool = False) -> bool:
    if type(value) is not int or value < -(1 << 63) or value > (1 << 63) - 1:
        return False
    return not nonnegative or value >= 0


def _exact_nonnegative_int(value: object, code: str, *, minimum: int = 0) -> int:
    if not _is_exact_int64(value, nonnegative=True) or value < minimum:
        _fail(code)
    return value


def _exact_hash(value: object, code: str) -> str:
    if type(value) is not str or _re.fullmatch(r"[0-9a-f]{64}", value, flags=_re.ASCII) is None:
        _fail(code)
    return value


def _exact_false(value: object) -> None:
    if type(value) is not bool or value is not False:
        _fail("receipt_guardrails_invalid")


def _decimal_text(value: _Decimal) -> str:
    if type(value) is not _Decimal or not value.is_finite():
        _fail("typed_row_decimal_invalid")
    if value == 0:
        return "0"
    sign, digits, exponent = value.as_tuple()
    coefficient = "".join(str(digit) for digit in digits) or "0"
    if exponent >= 0:
        if len(coefficient) + exponent + sign > 128:
            _fail("typed_row_decimal_invalid")
        text = coefficient + "0" * exponent
    else:
        places = -exponent
        estimated_length = (
            len(coefficient) + 1 if places < len(coefficient) else places + 2
        ) + sign
        if estimated_length > 128:
            _fail("typed_row_decimal_invalid")
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
    if type(value) in (list, tuple):
        return [_plain(item) for item in value]
    if type(value) is dict:
        return {key: _plain(value[key]) for key in sorted(value)}
    if type(value) in (_BybitTradeKline1m, _BybitMarkKline1m, _BybitFundingRate):
        return {field.name: _plain(getattr(value, field.name)) for field in _fields(value)}
    _fail("canonical_value_invalid")


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


def _request_canonical_bytes(request: _HistoricalRequestSpec) -> bytes:
    return _canonical_json_bytes(
        {
            field.name: (
                [list(pair) for pair in request.params]
                if field.name == "params"
                else getattr(request, field.name)
            )
            for field in _fields(request)
        }
    )


def _plan_canonical_bytes(plan: _HistoricalCapturePlan) -> bytes:
    payload: dict[str, object] = {}
    for field in _fields(plan):
        value = getattr(plan, field.name)
        if field.name == "requests":
            requests: list[dict[str, object]] = []
            for request in plan.requests:
                request_payload: dict[str, object] = {}
                for request_field in _fields(request):
                    atom = getattr(request, request_field.name)
                    if request_field.name == "params":
                        atom = [list(pair) for pair in atom]
                    request_payload[request_field.name] = atom
                requests.append(request_payload)
            value = requests
        payload[field.name] = value
    return _canonical_json_bytes(payload)


def _row_time(row: object) -> int:
    if type(row) in (_BybitTradeKline1m, _BybitMarkKline1m):
        return row.open_time_ms
    if type(row) is _BybitFundingRate:
        return row.funding_time_ms
    _fail("typed_row_type_invalid")


def _rows_canonical_bytes(rows: tuple[object, ...]) -> bytes:
    return _canonical_json_bytes(rows)


def _scan_json_shape(raw_body_bytes: bytes) -> None:
    # This deliberately runs before decoding or json.loads.  The scalar-only
    # scanner caps adversarial nesting and lexical work without allocating a
    # token tree.  json.loads remains responsible for the full grammar.
    depth = 0
    type_stack = 0
    tokens = 0
    in_string = False
    escaped = False
    in_literal = False
    for byte in raw_body_bytes:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue

        if byte == 0x22:
            in_string = True
            in_literal = False
            tokens += 1
        elif byte in (0x7B, 0x5B):
            container_kind = 1 if byte == 0x7B else 0
            type_stack = (type_stack << 1) | container_kind
            depth += 1
            in_literal = False
            tokens += 1
            if depth > 8:
                _fail("response_json_depth_exceeded")
        elif byte in (0x7D, 0x5D):
            closing_kind = 1 if byte == 0x7D else 0
            if depth == 0 or (type_stack & 1) != closing_kind:
                _fail("response_json_invalid")
            type_stack >>= 1
            depth -= 1
            in_literal = False
            tokens += 1
        elif byte in (0x2C, 0x3A):
            in_literal = False
            tokens += 1
        elif byte in (0x20, 0x09, 0x0A, 0x0D):
            in_literal = False
        elif not in_literal:
            in_literal = True
            tokens += 1
        if tokens > 20_000:
            _fail("response_json_token_limit_exceeded")
    if in_string or escaped or depth != 0:
        _fail("response_json_invalid")


def _reject_float(_: str) -> object:
    _fail("response_json_float_forbidden")


def _reject_constant(_: str) -> object:
    _fail("response_json_nonfinite_forbidden")


def _parse_int(token: str) -> int:
    if token == "0":
        return 0
    negative = token.startswith("-")
    digits = token[1:] if negative else token
    if not digits or digits[0] == "0" or _re.fullmatch(r"[0-9]+", digits, flags=_re.ASCII) is None:
        _fail("response_json_integer_noncanonical")
    bound = "9223372036854775808" if negative else "9223372036854775807"
    if len(digits) > len(bound) or (len(digits) == len(bound) and digits > bound):
        _fail("response_json_integer_out_of_int64")
    return -int(digits) if negative else int(digits)


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("response_json_duplicate_key")
        result[key] = value
    return result


def _unicode_scalar_text(value: str) -> bool:
    index = 0
    while index < len(value):
        point = ord(value[index])
        if 0xD800 <= point <= 0xDBFF:
            if index + 1 >= len(value) or not 0xDC00 <= ord(value[index + 1]) <= 0xDFFF:
                return False
            index += 2
            continue
        if 0xDC00 <= point <= 0xDFFF:
            return False
        index += 1
    return True


def _validate_json_unicode(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is str:
            if not _unicode_scalar_text(current):
                _fail("response_json_unicode_scalar_invalid")
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is dict:
            for key, item in current.items():
                if not _unicode_scalar_text(key):
                    _fail("response_json_unicode_scalar_invalid")
                pending.append(item)


def _strict_json_loads(raw_body_bytes: bytes) -> dict[str, object]:
    try:
        text = raw_body_bytes.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise HistoricalResponseError("response_utf8_invalid") from exc
    try:
        value = _json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
        )
    except HistoricalResponseError:
        raise
    except (_json.JSONDecodeError, RecursionError) as exc:
        raise HistoricalResponseError("response_json_invalid") from exc
    _validate_json_unicode(value)
    if type(value) is not dict:
        _fail("response_root_shape_invalid")
    return value


def _normalize_content_type(content_type: object) -> str:
    if type(content_type) is not str:
        _fail("content_type_not_accepted_json")
    try:
        encoded = content_type.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise HistoricalResponseError("content_type_not_accepted_json") from exc
    if (
        not encoded
        or b"," in encoded
        or any(byte < 32 and byte != 9 or byte == 127 for byte in encoded)
    ):
        _fail("content_type_not_accepted_json")
    parts = content_type.strip(" \t").split(";")
    if not parts or not parts[0] or parts[0].strip(" \t").lower() != "application/json":
        _fail("content_type_not_accepted_json")
    if len(parts) == 2:
        parameter = parts[1].strip(" \t")
        if parameter.count("=") != 1:
            _fail("content_type_not_accepted_json")
        name, atom = (part.strip(" \t") for part in parameter.split("=", 1))
        if name.lower() != "charset" or atom.lower() not in ("utf-8", '"utf-8"'):
            _fail("content_type_not_accepted_json")
    elif len(parts) != 1:
        _fail("content_type_not_accepted_json")
    return "application/json"


def _timestamp_atom(value: object, code: str) -> int:
    if (
        type(value) is not str
        or len(value) > 19
        or _re.fullmatch(r"0|[1-9][0-9]*", value, flags=_re.ASCII) is None
    ):
        _fail(code)
    timestamp = int(value)
    if not _is_exact_int64(timestamp, nonnegative=True):
        _fail(code)
    return timestamp


def _decimal_atom(value: object, code: str) -> str:
    if (
        type(value) is not str
        or len(value) > 128
        or _re.fullmatch(
            r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?",
            value,
            flags=_re.ASCII,
        )
        is None
    ):
        _fail(code)
    return value


def _validate_payload_identity(
    payload: dict[str, object],
    *,
    plan: _HistoricalCapturePlan,
    request: _HistoricalRequestSpec,
) -> tuple[dict[str, object], list[object], int]:
    if set(payload) != {"retCode", "retMsg", "result", "retExtInfo", "time"}:
        _fail("response_root_shape_invalid")
    ret_code = payload.get("retCode")
    if type(ret_code) is not int or ret_code != 0:
        _fail("response_top_level_invalid")
    if type(payload["retMsg"]) is not str or payload["retMsg"] != "OK":
        _fail("response_top_level_invalid")
    if type(payload["retExtInfo"]) is not dict or payload["retExtInfo"]:
        _fail("response_top_level_invalid")
    response_time = payload.get("time")
    if not _is_exact_int64(response_time, nonnegative=True):
        _fail("response_time_invalid")
    result = payload.get("result")
    if type(result) is not dict:
        _fail("response_result_shape_invalid")
    expected_result_keys = (
        {"category", "symbol", "list"}
        if request.dataset in ("trade_kline_1m", "mark_kline_1m")
        else {"category", "list"}
    )
    if set(result) != expected_result_keys:
        _fail("response_result_shape_invalid")
    category = result.get("category")
    rows = result.get("list")
    if type(category) is not str or type(rows) is not list:
        _fail("response_result_shape_invalid")
    if request.dataset in ("trade_kline_1m", "mark_kline_1m"):
        if type(result.get("symbol")) is not str:
            _fail("response_result_shape_invalid")
    if category != plan.category or (
        request.dataset in ("trade_kline_1m", "mark_kline_1m")
        and result.get("symbol") != plan.symbol
    ):
        _fail("response_identity_mismatch")
    return result, rows, response_time


def _validate_kline_endpoint_rows(
    raw_rows: list[object],
    *,
    request: _HistoricalRequestSpec,
) -> None:
    if len(raw_rows) != request.target_row_count:
        _fail("kline_coverage_invalid")
    timestamps: list[int] = []
    expected_length = 7 if request.dataset == "trade_kline_1m" else 5
    for row in raw_rows:
        if (
            type(row) is not list
            or len(row) != expected_length
            or any(type(atom) is not str for atom in row)
        ):
            _fail("kline_row_shape_invalid")
    for row in raw_rows:
        timestamps.append(_timestamp_atom(row[0], "kline_timestamp_invalid"))
    if any(timestamp % 60_000 for timestamp in timestamps):
        _fail("kline_timestamp_invalid")
    ascending = tuple(range(request.start_ms, request.end_ms + 1, 60_000))
    if tuple(sorted(timestamps)) != ascending or len(timestamps) != len(set(timestamps)):
        _fail("kline_coverage_invalid")
    if tuple(timestamps) != tuple(reversed(ascending)):
        _fail("kline_order_invalid")
    for row in raw_rows:
        for atom in row[1:]:
            _decimal_atom(atom, "kline_value_invalid")


def _validate_funding_endpoint_rows(
    raw_rows: list[object],
    *,
    plan: _HistoricalCapturePlan,
    request: _HistoricalRequestSpec,
) -> None:
    if len(raw_rows) >= 200:
        _fail("funding_page_saturated")
    if len(raw_rows) > request.target_row_count:
        _fail("funding_row_limit_exceeded")
    for row in raw_rows:
        if (
            type(row) is not dict
            or set(row) != {"symbol", "fundingRate", "fundingRateTimestamp"}
            or any(type(value) is not str for value in row.values())
        ):
            _fail("funding_row_shape_invalid")
    if any(row["symbol"] != plan.symbol for row in raw_rows):
        _fail("response_identity_mismatch")
    timestamps: list[int] = []
    for row in raw_rows:
        timestamp = _timestamp_atom(
            row["fundingRateTimestamp"],
            "funding_timestamp_invalid",
        )
        if timestamp % 60_000:
            _fail("funding_timestamp_invalid")
        timestamps.append(timestamp)
    if len(timestamps) != len(set(timestamps)):
        _fail("funding_duplicate_timestamp")
    if any(timestamp < request.start_ms or timestamp > request.end_ms for timestamp in timestamps):
        _fail("funding_timestamp_out_of_range")
    for row in raw_rows:
        _decimal_atom(row["fundingRate"], "funding_value_invalid")


def _parse_typed_rows(
    payload: dict[str, object],
    *,
    plan: _HistoricalCapturePlan,
    request: _HistoricalRequestSpec,
) -> tuple[object, ...]:
    try:
        if request.dataset == "trade_kline_1m":
            rows = _parse_trade_kline_page(
                payload,
                plan.category,
                plan.symbol,
                _InclusiveMinuteWindow(request.start_ms, request.end_ms),
                plan.server_cutoff_open_time_ms,
            )
            row_type = _BybitTradeKline1m
        elif request.dataset == "mark_kline_1m":
            rows = _parse_mark_kline_page(
                payload,
                plan.category,
                plan.symbol,
                _InclusiveMinuteWindow(request.start_ms, request.end_ms),
                plan.server_cutoff_open_time_ms,
            )
            row_type = _BybitMarkKline1m
        else:
            rows = _parse_funding_page(
                payload,
                plan.category,
                plan.symbol,
                request.start_ms,
                request.end_ms,
            )
            row_type = _BybitFundingRate
    except (_PublicBatchError, _InvalidOperation, KeyError) as exc:
        code = (
            "funding_value_invalid" if request.dataset == "funding_rate" else "kline_value_invalid"
        )
        raise HistoricalResponseError(code) from exc
    if type(rows) is not tuple or any(type(row) is not row_type for row in rows):
        _fail("typed_rows_invalid")
    times = tuple(_row_time(row) for row in rows)
    if times != tuple(sorted(times)) or len(times) != len(set(times)):
        _fail("typed_row_order_invalid")
    if request.dataset in ("trade_kline_1m", "mark_kline_1m"):
        expected = tuple(range(request.start_ms, request.end_ms + 1, 60_000))
        if times != expected:
            _fail("typed_kline_coverage_invalid")
    return rows


@_dataclass(frozen=True, slots=True, init=False)
class HistoricalResponseReceipt:
    schema: str
    plan_sha256: str
    request_sha256: str
    sequence_id: int
    dataset: str
    endpoint: str
    category: str
    symbol: str
    request_start_ms: int
    request_end_ms: int
    request_limit: int
    request_target_row_count: int
    http_status: int
    content_type: str
    response_time_ms: int
    raw_body_byte_count: int
    raw_body_sha256: str
    max_response_body_bytes: int
    max_json_depth: int
    max_json_tokens: int
    row_count: int
    first_timestamp_ms: int | None
    last_timestamp_ms: int | None
    timestamps_sha256: str
    rows_sha256: str
    source_row_order: str
    canonical_row_order: str
    exact_kline_coverage_bool: bool
    funding_page_unsaturated_bool: bool
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
    rows: tuple[object, ...]

    def __init__(self, *args, **kwargs) -> None:
        _fail("receipt_factory_only")

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not str
            or self.schema != "bybit_public_historical_response_receipt_v1"
        ):
            _fail("receipt_schema_invalid")
        _exact_hash(self.plan_sha256, "receipt_plan_sha256_invalid")
        _exact_hash(self.request_sha256, "receipt_request_sha256_invalid")
        _exact_hash(self.raw_body_sha256, "receipt_body_sha256_invalid")
        _exact_hash(self.timestamps_sha256, "receipt_timestamps_sha256_invalid")
        _exact_hash(self.rows_sha256, "receipt_rows_sha256_invalid")
        _exact_nonnegative_int(self.sequence_id, "receipt_request_invalid", minimum=1)
        if type(self.dataset) is not str or self.dataset not in (
            "trade_kline_1m",
            "mark_kline_1m",
            "funding_rate",
        ):
            _fail("receipt_request_invalid")
        endpoint_for_dataset = {
            "trade_kline_1m": "/v5/market/kline",
            "mark_kline_1m": "/v5/market/mark-price-kline",
            "funding_rate": "/v5/market/funding/history",
        }
        if type(self.endpoint) is not str or self.endpoint != endpoint_for_dataset[self.dataset]:
            _fail("receipt_request_invalid")
        if type(self.category) is not str or self.category != "linear":
            _fail("receipt_request_invalid")
        if (
            type(self.symbol) is not str
            or _re.fullmatch(r"[A-Z0-9]{2,32}", self.symbol, flags=_re.ASCII) is None
        ):
            _fail("receipt_request_invalid")
        start = _exact_nonnegative_int(self.request_start_ms, "receipt_request_invalid")
        end = _exact_nonnegative_int(self.request_end_ms, "receipt_request_invalid")
        if start > end:
            _fail("receipt_request_invalid")
        limit = _exact_nonnegative_int(self.request_limit, "receipt_request_invalid", minimum=1)
        target = _exact_nonnegative_int(
            self.request_target_row_count,
            "receipt_request_invalid",
            minimum=1,
        )
        if self.dataset in ("trade_kline_1m", "mark_kline_1m"):
            exact_target = (end - start) // 60_000 + 1
            if start % 60_000 or end % 60_000 or limit != target or target != exact_target:
                _fail("receipt_request_invalid")
        else:
            first_possible = ((start + 59_999) // 60_000) * 60_000
            last_possible = (end // 60_000) * 60_000
            if first_possible > last_possible:
                _fail("receipt_request_invalid")
            exact_target = (last_possible - first_possible) // 60_000 + 1
            if (
                start % 60_000 not in (0, 1)
                or end % 60_000
                or limit != 200
                or target != exact_target
                or target > 199
            ):
                _fail("receipt_request_invalid")
        _exact_nonnegative_int(self.response_time_ms, "receipt_response_time_invalid")
        if type(self.http_status) is not int or self.http_status != 200:
            _fail("receipt_http_invalid")
        if type(self.content_type) is not str or self.content_type != "application/json":
            _fail("receipt_content_type_invalid")
        body_count = _exact_nonnegative_int(
            self.raw_body_byte_count,
            "receipt_body_size_invalid",
            minimum=1,
        )
        if body_count > 1_048_576:
            _fail("receipt_body_size_invalid")
        if (
            type(self.max_response_body_bytes) is not int
            or self.max_response_body_bytes != 1_048_576
            or type(self.max_json_depth) is not int
            or self.max_json_depth != 8
            or type(self.max_json_tokens) is not int
            or self.max_json_tokens != 20_000
        ):
            _fail("receipt_fixed_limits_invalid")
        if type(self.rows) is not tuple:
            _fail("receipt_rows_invalid")
        row_count = _exact_nonnegative_int(self.row_count, "receipt_rows_invalid")
        if row_count != len(self.rows):
            _fail("receipt_rows_invalid")
        expected_type = {
            "trade_kline_1m": _BybitTradeKline1m,
            "mark_kline_1m": _BybitMarkKline1m,
            "funding_rate": _BybitFundingRate,
        }[self.dataset]
        if any(type(row) is not expected_type for row in self.rows):
            _fail("receipt_rows_invalid")
        for row in self.rows:
            try:
                expected_type.__post_init__(row)
            except (AttributeError, TypeError, _PublicBatchError) as exc:
                raise HistoricalResponseError("receipt_rows_invalid") from exc
        times = tuple(_row_time(row) for row in self.rows)
        if times != tuple(sorted(times)) or len(times) != len(set(times)):
            _fail("receipt_rows_invalid")
        if self.dataset in ("trade_kline_1m", "mark_kline_1m"):
            if row_count != target or times != tuple(range(start, end + 1, 60_000)):
                _fail("receipt_rows_invalid")
        elif (
            row_count >= 200
            or row_count > target
            or any(timestamp < start or timestamp > end for timestamp in times)
        ):
            _fail("receipt_rows_invalid")
        for row in self.rows:
            if row.category != "linear" or row.symbol != self.symbol:
                _fail("receipt_rows_invalid")
        expected_first = times[0] if times else None
        expected_last = times[-1] if times else None
        first_matches = (
            self.first_timestamp_ms is None
            if expected_first is None
            else type(self.first_timestamp_ms) is int and self.first_timestamp_ms == expected_first
        )
        last_matches = (
            self.last_timestamp_ms is None
            if expected_last is None
            else type(self.last_timestamp_ms) is int and self.last_timestamp_ms == expected_last
        )
        if not first_matches or not last_matches:
            _fail("receipt_rows_invalid")
        if (
            self.timestamps_sha256
            != _hashlib.sha256(_canonical_json_bytes(list(times))).hexdigest()
        ):
            _fail("receipt_timestamps_sha256_invalid")
        try:
            canonical_rows = _rows_canonical_bytes(self.rows)
        except HistoricalResponseError as exc:
            raise HistoricalResponseError("receipt_rows_invalid") from exc
        if self.rows_sha256 != _hashlib.sha256(canonical_rows).hexdigest():
            _fail("receipt_rows_sha256_invalid")
        is_funding = self.dataset == "funding_rate"
        if (
            type(self.source_row_order) is not str
            or self.source_row_order != ("unspecified" if is_funding else "reverse_start_time")
            or type(self.canonical_row_order) is not str
            or self.canonical_row_order != "timestamp_ascending"
            or type(self.exact_kline_coverage_bool) is not bool
            or self.exact_kline_coverage_bool is is_funding
            or type(self.funding_page_unsaturated_bool) is not bool
            or self.funding_page_unsaturated_bool is not is_funding
        ):
            _fail("receipt_rows_invalid")
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
            _exact_false(value)

    def canonical_json_bytes(self) -> bytes:
        HistoricalResponseReceipt.__post_init__(self)
        return _canonical_json_bytes(
            {field.name: getattr(self, field.name) for field in _fields(self)}
        )

    def sha256(self) -> str:
        return _hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def _build_receipt(**values: object) -> HistoricalResponseReceipt:
    field_names = tuple(field.name for field in _fields(HistoricalResponseReceipt))
    if set(values) != set(field_names):
        _fail("receipt_builder_fields_invalid")
    receipt = object.__new__(HistoricalResponseReceipt)
    for name in field_names:
        object.__setattr__(receipt, name, values[name])
    HistoricalResponseReceipt.__post_init__(receipt)
    return receipt


def accept_historical_response_page(
    *,
    plan,
    request,
    http_status,
    content_type,
    raw_body_bytes,
):
    if type(plan) is not _HistoricalCapturePlan:
        _fail("plan_not_exact_model")
    if type(request) is not _HistoricalRequestSpec:
        _fail("request_not_exact_model")
    try:
        _HistoricalRequestSpec.__post_init__(request)
    except (AttributeError, TypeError, _HistoricalPlanError) as exc:
        raise HistoricalResponseError("request_invariants_invalid") from exc
    try:
        plan_requests = plan.requests
    except AttributeError as exc:
        raise HistoricalResponseError("plan_invariants_invalid") from exc
    if type(plan_requests) is not tuple or any(
        type(candidate) is not _HistoricalRequestSpec for candidate in plan_requests
    ):
        _fail("plan_invariants_invalid")
    try:
        for candidate in plan_requests:
            _HistoricalRequestSpec.__post_init__(candidate)
        _HistoricalCapturePlan.__post_init__(plan)
    except (AttributeError, TypeError, _HistoricalPlanError) as exc:
        raise HistoricalResponseError("plan_invariants_invalid") from exc
    if not any(candidate is request for candidate in plan_requests):
        _fail("request_not_member_of_plan")
    if type(http_status) is not int or http_status != 200:
        _fail("http_status_not_exact_200")
    normalized_content_type = _normalize_content_type(content_type)
    if type(raw_body_bytes) is not bytes:
        _fail("raw_body_not_exact_bytes")
    if not raw_body_bytes:
        _fail("response_body_empty")
    if len(raw_body_bytes) > 1_048_576:
        _fail("response_body_too_large")
    _scan_json_shape(raw_body_bytes)
    payload = _strict_json_loads(raw_body_bytes)
    _, raw_rows, response_time = _validate_payload_identity(
        payload,
        plan=plan,
        request=request,
    )
    if request.dataset in ("trade_kline_1m", "mark_kline_1m"):
        _validate_kline_endpoint_rows(raw_rows, request=request)
    else:
        _validate_funding_endpoint_rows(raw_rows, plan=plan, request=request)
    rows = _parse_typed_rows(payload, plan=plan, request=request)
    row_times = tuple(_row_time(row) for row in rows)
    request_sha256 = _hashlib.sha256(_request_canonical_bytes(request)).hexdigest()
    body_sha256 = _hashlib.sha256(raw_body_bytes).hexdigest()
    rows_sha256 = _hashlib.sha256(_rows_canonical_bytes(rows)).hexdigest()
    return _build_receipt(
        schema="bybit_public_historical_response_receipt_v1",
        plan_sha256=_hashlib.sha256(_plan_canonical_bytes(plan)).hexdigest(),
        request_sha256=request_sha256,
        sequence_id=request.sequence_id,
        dataset=request.dataset,
        endpoint=request.endpoint,
        category=plan.category,
        symbol=plan.symbol,
        request_start_ms=request.start_ms,
        request_end_ms=request.end_ms,
        request_limit=request.limit,
        request_target_row_count=request.target_row_count,
        http_status=200,
        content_type=normalized_content_type,
        response_time_ms=response_time,
        raw_body_byte_count=len(raw_body_bytes),
        raw_body_sha256=body_sha256,
        max_response_body_bytes=1_048_576,
        max_json_depth=8,
        max_json_tokens=20_000,
        row_count=len(rows),
        first_timestamp_ms=row_times[0] if row_times else None,
        last_timestamp_ms=row_times[-1] if row_times else None,
        timestamps_sha256=_hashlib.sha256(_canonical_json_bytes(list(row_times))).hexdigest(),
        rows_sha256=rows_sha256,
        source_row_order=(
            "unspecified" if request.dataset == "funding_rate" else "reverse_start_time"
        ),
        canonical_row_order="timestamp_ascending",
        exact_kline_coverage_bool=request.dataset != "funding_rate",
        funding_page_unsaturated_bool=request.dataset == "funding_rate",
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
        rows=rows,
    )


__all__ = (
    "MAX_HISTORICAL_RESPONSE_BODY_BYTES",
    "HistoricalResponseError",
    "HistoricalResponseReceipt",
    "accept_historical_response_page",
)
