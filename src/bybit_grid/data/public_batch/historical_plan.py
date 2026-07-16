from dataclasses import dataclass as _dataclass, fields as _fields
import hashlib as _hashlib
import json as _json
import re as _re

from .models import (
    MINUTE_MS as _MINUTE_MS,
    BybitInstrumentMeta as _BybitInstrumentMeta,
    BybitServerTime as _BybitServerTime,
    InclusiveMinuteWindow as _InclusiveMinuteWindow,
)


MAX_PLAN_SPAN_MINUTES = 44_640
KLINE_LIMIT = 1000
FUNDING_LIMIT = 200
FUNDING_TARGET_RECORDS = 199
MAX_TOTAL_REQUESTS = 256
MAX_TOTAL_RESPONSE_ROWS = 100_000

_SCHEMA = "bybit_public_historical_capture_plan_v1"
_CATEGORY = "linear"
_MAX_INT64 = (1 << 63) - 1
_MIN_INT64 = -(1 << 63)


class HistoricalPlanError(ValueError):
    pass


def _is_exact_int64(value: object, *, nonnegative: bool = False) -> bool:
    if type(value) is not int or value < _MIN_INT64 or value > _MAX_INT64:
        return False
    return not nonnegative or value >= 0


def _exact_nonnegative_int(value: object, code: str, *, minimum: int = 0) -> int:
    if not _is_exact_int64(value, nonnegative=True) or value < minimum:
        raise HistoricalPlanError(code)
    return value


def _exact_false(value: object, code: str) -> None:
    if type(value) is not bool or value is not False:
        raise HistoricalPlanError(code)


def _symbol_is_valid(value: object) -> bool:
    return (
        type(value) is str
        and 2 <= len(value) <= 32
        and _re.fullmatch(r"[A-Z0-9]+", value, flags=_re.ASCII) is not None
    )


def _ceil_minute(value: int) -> int:
    quotient, remainder = divmod(value, _MINUTE_MS)
    return quotient * _MINUTE_MS + (_MINUTE_MS if remainder else 0)


def _inclusive_minute_count(start_ms: int, end_ms: int) -> int:
    return (end_ms - start_ms) // _MINUTE_MS + 1


def _request_identity(dataset: str) -> tuple[str, str]:
    if dataset == "trade_kline_1m":
        return "/v5/market/kline", "missing_windows_ascending"
    if dataset == "mark_kline_1m":
        return "/v5/market/mark-price-kline", "missing_windows_ascending"
    if dataset == "funding_rate":
        return "/v5/market/funding/history", "backward_full_range"
    raise HistoricalPlanError("request_spec_invalid")


def _dataset_rank(dataset: str) -> int:
    if dataset == "trade_kline_1m":
        return 0
    if dataset == "mark_kline_1m":
        return 1
    if dataset == "funding_rate":
        return 2
    raise HistoricalPlanError("plan_requests_invalid")


def _validate_params(value: object) -> tuple[tuple[str, str | int], ...]:
    if type(value) is not tuple:
        raise HistoricalPlanError("request_spec_invalid")
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            raise HistoricalPlanError("request_spec_invalid")
        key, atom = pair
        if type(key) is not str or not key or type(atom) not in (str, int):
            raise HistoricalPlanError("request_spec_invalid")
    return value


def _request_symbol(params: tuple[tuple[str, str | int], ...]) -> str:
    if len(params) < 2 or params[0] != ("category", _CATEGORY):
        raise HistoricalPlanError("request_spec_invalid")
    pair = params[1]
    if type(pair) is not tuple or len(pair) != 2 or pair[0] != "symbol":
        raise HistoricalPlanError("request_spec_invalid")
    symbol = pair[1]
    if not _symbol_is_valid(symbol):
        raise HistoricalPlanError("request_spec_invalid")
    return symbol


def _funding_target(start_ms: int, end_ms: int) -> int:
    first_possible = _ceil_minute(start_ms)
    last_possible = (end_ms // _MINUTE_MS) * _MINUTE_MS
    if first_possible > last_possible:
        raise HistoricalPlanError("request_spec_invalid")
    return (last_possible - first_possible) // _MINUTE_MS + 1


@_dataclass(frozen=True, slots=True)
class HistoricalRequestSpec:
    sequence_id: int
    dataset: str
    endpoint: str
    pagination: str
    start_ms: int
    end_ms: int
    limit: int
    target_row_count: int
    requested_minute_count: int
    params: tuple[tuple[str, str | int], ...]

    def __post_init__(self) -> None:
        _exact_nonnegative_int(self.sequence_id, "request_spec_invalid", minimum=1)
        if type(self.dataset) is not str:
            raise HistoricalPlanError("request_spec_invalid")
        endpoint, pagination = _request_identity(self.dataset)
        if self.endpoint != endpoint or type(self.endpoint) is not str:
            raise HistoricalPlanError("request_spec_invalid")
        if self.pagination != pagination or type(self.pagination) is not str:
            raise HistoricalPlanError("request_spec_invalid")
        start = _exact_nonnegative_int(self.start_ms, "request_spec_invalid")
        end = _exact_nonnegative_int(self.end_ms, "request_spec_invalid")
        if start > end:
            raise HistoricalPlanError("request_spec_invalid")
        limit = _exact_nonnegative_int(self.limit, "request_spec_invalid", minimum=1)
        target = _exact_nonnegative_int(
            self.target_row_count,
            "request_spec_invalid",
            minimum=1,
        )
        minutes = _exact_nonnegative_int(
            self.requested_minute_count,
            "request_spec_invalid",
            minimum=1,
        )
        params = _validate_params(self.params)
        symbol = _request_symbol(params)

        if self.dataset in ("trade_kline_1m", "mark_kline_1m"):
            if start % _MINUTE_MS or end % _MINUTE_MS:
                raise HistoricalPlanError("request_spec_invalid")
            exact_rows = _inclusive_minute_count(start, end)
            if (
                exact_rows > 1000
                or target != exact_rows
                or limit != exact_rows
                or minutes != exact_rows
            ):
                raise HistoricalPlanError("request_spec_invalid")
            expected_params = (
                ("category", _CATEGORY),
                ("symbol", symbol),
                ("interval", "1"),
                ("start", start),
                ("end", end),
                ("limit", target),
            )
        else:
            if start % _MINUTE_MS not in (0, 1) or end % _MINUTE_MS:
                raise HistoricalPlanError("request_spec_invalid")
            exact_target = _funding_target(start, end)
            exact_minutes = _inclusive_minute_count(start, end)
            if (
                limit != 200
                or exact_target > 199
                or target != exact_target
                or minutes != exact_minutes
            ):
                raise HistoricalPlanError("request_spec_invalid")
            expected_params = (
                ("category", _CATEGORY),
                ("symbol", symbol),
                ("startTime", start),
                ("endTime", end),
                ("limit", 200),
            )
        if params != expected_params:
            raise HistoricalPlanError("request_spec_invalid")


@_dataclass(frozen=True, slots=True)
class HistoricalCapturePlan:
    schema: str
    category: str
    symbol: str
    launch_cutoff_open_time_ms: int
    delivery_cutoff_open_time_ms: int | None
    request_start_open_time_ms: int
    request_cutoff_open_time_ms: int
    server_cutoff_open_time_ms: int
    funding_interval_minutes: int
    observed_trade_row_count: int
    observed_mark_row_count: int
    observed_funding_row_count: int
    observed_funding_times_sha256: str
    trade_missing_row_count: int
    mark_missing_row_count: int
    funding_recapture_observation_upper_bound: int
    plan_span_minutes: int
    request_count: int
    planned_max_response_rows: int
    max_plan_span_minutes: int
    max_total_requests: int
    max_total_response_rows: int
    network_authorized_bool: bool
    credentials_allowed_bool: bool
    private_api_allowed_bool: bool
    live_execution_authorized_bool: bool
    funding_coverage_proven_bool: bool
    historical_market_data_coverage_proven_bool: bool
    parameter_selection_authorized_bool: bool
    sufficient_for_parameter_selection_bool: bool
    native_equivalence_proven_bool: bool
    requests: tuple[HistoricalRequestSpec, ...]

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != _SCHEMA:
            raise HistoricalPlanError("plan_identity_invalid")
        if type(self.category) is not str or self.category != _CATEGORY:
            raise HistoricalPlanError("plan_identity_invalid")
        if not _symbol_is_valid(self.symbol):
            raise HistoricalPlanError("plan_identity_invalid")
        if (
            type(self.observed_funding_times_sha256) is not str
            or _re.fullmatch(
                r"[0-9a-f]{64}",
                self.observed_funding_times_sha256,
                flags=_re.ASCII,
            )
            is None
        ):
            raise HistoricalPlanError("plan_identity_invalid")

        launch = _exact_nonnegative_int(
            self.launch_cutoff_open_time_ms,
            "plan_identity_invalid",
        )
        if launch % _MINUTE_MS:
            raise HistoricalPlanError("plan_identity_invalid")
        delivery = self.delivery_cutoff_open_time_ms
        if delivery is not None:
            delivery = _exact_nonnegative_int(delivery, "plan_identity_invalid")
            if delivery % _MINUTE_MS:
                raise HistoricalPlanError("plan_identity_invalid")
        request_start = _exact_nonnegative_int(
            self.request_start_open_time_ms,
            "plan_identity_invalid",
        )
        request_end = _exact_nonnegative_int(
            self.request_cutoff_open_time_ms,
            "plan_identity_invalid",
        )
        server_end = _exact_nonnegative_int(
            self.server_cutoff_open_time_ms,
            "plan_identity_invalid",
        )
        if (
            request_start % _MINUTE_MS
            or request_end % _MINUTE_MS
            or server_end % _MINUTE_MS
            or request_start > request_end
            or request_start < launch
            or request_end > server_end
            or (delivery is not None and request_end > delivery)
        ):
            raise HistoricalPlanError("plan_identity_invalid")
        _exact_nonnegative_int(
            self.funding_interval_minutes,
            "plan_identity_invalid",
            minimum=1,
        )

        count_fields = (
            "observed_trade_row_count",
            "observed_mark_row_count",
            "observed_funding_row_count",
            "trade_missing_row_count",
            "mark_missing_row_count",
            "funding_recapture_observation_upper_bound",
            "plan_span_minutes",
            "request_count",
            "planned_max_response_rows",
        )
        for name in count_fields:
            _exact_nonnegative_int(getattr(self, name), "plan_totals_invalid")
        span = _inclusive_minute_count(request_start, request_end)
        if self.plan_span_minutes != span or span > 44_640:
            raise HistoricalPlanError("plan_totals_invalid")

        if (
            type(self.max_plan_span_minutes) is not int
            or self.max_plan_span_minutes != 44_640
            or type(self.max_total_requests) is not int
            or self.max_total_requests != 256
            or type(self.max_total_response_rows) is not int
            or self.max_total_response_rows != 100_000
        ):
            raise HistoricalPlanError("plan_fixed_limits_invalid")

        guardrail_names = (
            "network_authorized_bool",
            "credentials_allowed_bool",
            "private_api_allowed_bool",
            "live_execution_authorized_bool",
            "funding_coverage_proven_bool",
            "historical_market_data_coverage_proven_bool",
            "parameter_selection_authorized_bool",
            "sufficient_for_parameter_selection_bool",
            "native_equivalence_proven_bool",
        )
        for name in guardrail_names:
            _exact_false(getattr(self, name), "plan_guardrails_invalid")

        if type(self.requests) is not tuple or any(
            type(request) is not HistoricalRequestSpec for request in self.requests
        ):
            raise HistoricalPlanError("plan_requests_invalid")
        if self.request_count != len(self.requests):
            raise HistoricalPlanError("plan_totals_invalid")
        if len(self.requests) > 256:
            raise HistoricalPlanError("plan_totals_invalid")
        if tuple(request.sequence_id for request in self.requests) != tuple(
            range(1, len(self.requests) + 1)
        ):
            raise HistoricalPlanError("plan_requests_invalid")

        identities = tuple(
            (request.dataset, request.start_ms, request.end_ms) for request in self.requests
        )
        if len(identities) != len(set(identities)):
            raise HistoricalPlanError("plan_requests_invalid")
        if any(_request_symbol(request.params) != self.symbol for request in self.requests):
            raise HistoricalPlanError("plan_requests_invalid")
        ranks = tuple(_dataset_rank(request.dataset) for request in self.requests)
        if ranks != tuple(sorted(ranks)):
            raise HistoricalPlanError("plan_requests_invalid")
        if any(
            request.start_ms < request_start or request.end_ms > request_end
            for request in self.requests
        ):
            raise HistoricalPlanError("plan_requests_invalid")

        trade = tuple(request for request in self.requests if request.dataset == "trade_kline_1m")
        mark = tuple(request for request in self.requests if request.dataset == "mark_kline_1m")
        funding = tuple(request for request in self.requests if request.dataset == "funding_rate")
        for group in (trade, mark):
            if any(
                current.start_ms <= previous.end_ms for previous, current in zip(group, group[1:])
            ):
                raise HistoricalPlanError("plan_requests_invalid")
            if any(
                current.start_ms == previous.end_ms + _MINUTE_MS
                and previous.target_row_count != 1000
                for previous, current in zip(group, group[1:])
            ):
                raise HistoricalPlanError("plan_requests_invalid")
        if self.trade_missing_row_count != sum(request.target_row_count for request in trade):
            raise HistoricalPlanError("plan_totals_invalid")
        if self.mark_missing_row_count != sum(request.target_row_count for request in mark):
            raise HistoricalPlanError("plan_totals_invalid")
        if (
            self.observed_trade_row_count + self.trade_missing_row_count != span
            or self.observed_mark_row_count + self.mark_missing_row_count != span
            or self.observed_funding_row_count > span
        ):
            raise HistoricalPlanError("plan_totals_invalid")
        if self.funding_recapture_observation_upper_bound != sum(
            request.target_row_count for request in funding
        ):
            raise HistoricalPlanError("plan_totals_invalid")

        expected_funding = _funding_windows(request_start, request_end)
        actual_funding = tuple(
            (request.start_ms, request.end_ms, request.target_row_count) for request in funding
        )
        if actual_funding != expected_funding:
            raise HistoricalPlanError("plan_requests_invalid")

        max_rows = sum(request.limit for request in self.requests)
        if self.planned_max_response_rows != max_rows:
            raise HistoricalPlanError("plan_totals_invalid")
        if max_rows > 100_000:
            raise HistoricalPlanError("plan_totals_invalid")

    def canonical_json_bytes(self) -> bytes:
        payload: dict[str, object] = {}
        for field in _fields(self):
            value = getattr(self, field.name)
            if field.name == "requests":
                value = [
                    {
                        request_field.name: (
                            [list(pair) for pair in request.params]
                            if request_field.name == "params"
                            else getattr(request, request_field.name)
                        )
                        for request_field in _fields(request)
                    }
                    for request in self.requests
                ]
            payload[field.name] = value
        return (
            _json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )

    def sha256(self) -> str:
        return _hashlib.sha256(self.canonical_json_bytes()).hexdigest()


def _validate_observed(
    values: object,
    *,
    name: str,
    requested_window: _InclusiveMinuteWindow,
) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise HistoricalPlanError(f"{name}_not_exact_tuple")
    previous: int | None = None
    for value in values:
        if not _is_exact_int64(value):
            raise HistoricalPlanError(f"{name}_timestamp_not_exact_int")
        if previous is not None and value <= previous:
            raise HistoricalPlanError(f"{name}_timestamps_not_strictly_increasing")
        if value % _MINUTE_MS:
            raise HistoricalPlanError(f"{name}_timestamp_not_minute_aligned")
        if value < requested_window.start_open_time_ms or value > requested_window.end_open_time_ms:
            raise HistoricalPlanError(f"{name}_timestamp_outside_requested_window")
        previous = value
    return values


def _observed_funding_digest(values: tuple[int, ...]) -> str:
    data = (
        _json.dumps(
            list(values),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return _hashlib.sha256(data).hexdigest()


def _missing_kline_windows(
    requested_window: _InclusiveMinuteWindow,
    observed: tuple[int, ...],
) -> tuple[tuple[int, int, int], ...]:
    windows: list[tuple[int, int, int]] = []
    cursor = requested_window.start_open_time_ms
    for timestamp in observed:
        if cursor < timestamp:
            _append_kline_run(windows, cursor, timestamp - _MINUTE_MS)
        cursor = timestamp + _MINUTE_MS
    if cursor <= requested_window.end_open_time_ms:
        _append_kline_run(windows, cursor, requested_window.end_open_time_ms)
    return tuple(windows)


def _append_kline_run(
    out: list[tuple[int, int, int]],
    start_ms: int,
    end_ms: int,
) -> None:
    cursor = start_ms
    while cursor <= end_ms:
        window_end = min(end_ms, cursor + 999 * _MINUTE_MS)
        count = _inclusive_minute_count(cursor, window_end)
        out.append((cursor, window_end, count))
        cursor = window_end + _MINUTE_MS


def _funding_windows(
    request_start_ms: int,
    request_end_ms: int,
) -> tuple[tuple[int, int, int], ...]:
    windows: list[tuple[int, int, int]] = []
    cursor = request_start_ms
    while cursor <= request_end_ms:
        first_possible = _ceil_minute(cursor)
        window_end = min(
            request_end_ms,
            first_possible + 198 * _MINUTE_MS,
        )
        target = ((window_end // _MINUTE_MS) * _MINUTE_MS - first_possible) // _MINUTE_MS + 1
        windows.append((cursor, window_end, target))
        cursor = window_end + 1
    return tuple(reversed(windows))


def _kline_spec(
    *,
    sequence_id: int,
    dataset: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    count: int,
) -> HistoricalRequestSpec:
    endpoint, pagination = _request_identity(dataset)
    return HistoricalRequestSpec(
        sequence_id=sequence_id,
        dataset=dataset,
        endpoint=endpoint,
        pagination=pagination,
        start_ms=start_ms,
        end_ms=end_ms,
        limit=count,
        target_row_count=count,
        requested_minute_count=count,
        params=(
            ("category", _CATEGORY),
            ("symbol", symbol),
            ("interval", "1"),
            ("start", start_ms),
            ("end", end_ms),
            ("limit", count),
        ),
    )


def _funding_spec(
    *,
    sequence_id: int,
    symbol: str,
    start_ms: int,
    end_ms: int,
    target: int,
) -> HistoricalRequestSpec:
    endpoint, pagination = _request_identity("funding_rate")
    return HistoricalRequestSpec(
        sequence_id=sequence_id,
        dataset="funding_rate",
        endpoint=endpoint,
        pagination=pagination,
        start_ms=start_ms,
        end_ms=end_ms,
        limit=200,
        target_row_count=target,
        requested_minute_count=_inclusive_minute_count(start_ms, end_ms),
        params=(
            ("category", _CATEGORY),
            ("symbol", symbol),
            ("startTime", start_ms),
            ("endTime", end_ms),
            ("limit", 200),
        ),
    )


def _instrument_is_replay_eligible(instrument: _BybitInstrumentMeta) -> bool:
    return (
        instrument.category == _CATEGORY
        and instrument.contract_type == "LinearPerpetual"
        and instrument.status == "Trading"
        and instrument.quote_coin == "USDT"
        and instrument.settle_coin == "USDT"
        and instrument.is_pre_listing is False
        and type(instrument.funding_interval_minutes) is int
        and instrument.funding_interval_minutes > 0
    )


def _validate_instrument_lifecycle(instrument: _BybitInstrumentMeta) -> int:
    launch = instrument.launch_time_ms
    delivery = instrument.delivery_time_ms
    if not _is_exact_int64(launch, nonnegative=True):
        raise HistoricalPlanError("instrument_lifecycle_invalid")
    if not _is_exact_int64(delivery, nonnegative=True):
        raise HistoricalPlanError("instrument_lifecycle_invalid")
    launch_cutoff = _ceil_minute(launch)
    if launch_cutoff > _MAX_INT64:
        raise HistoricalPlanError("instrument_lifecycle_invalid")
    if delivery != 0 and delivery <= launch:
        raise HistoricalPlanError("instrument_lifecycle_invalid")
    return launch_cutoff


def _validate_server_identity(server_time: _BybitServerTime) -> None:
    values = (
        server_time.server_time_ms,
        server_time.time_second,
        server_time.time_nano,
        server_time.top_level_time_ms,
        server_time.last_closed_open_time_ms,
    )
    if any(not _is_exact_int64(value, nonnegative=True) for value in values):
        raise HistoricalPlanError("server_time_identity_invalid")
    server_ms = server_time.server_time_ms
    if (
        server_time.time_nano // 1_000_000 != server_ms
        or abs(server_ms - server_time.time_second * 1000) > 999
        or abs(server_ms - server_time.top_level_time_ms) > 999
        or server_time.last_closed_open_time_ms
        != (server_ms // _MINUTE_MS) * _MINUTE_MS - _MINUTE_MS
    ):
        raise HistoricalPlanError("server_time_identity_invalid")


def build_historical_capture_plan(
    *,
    instrument,
    server_time,
    requested_window,
    observed_trade_open_times_ms,
    observed_mark_open_times_ms,
    observed_funding_times_ms,
):
    if type(instrument) is not _BybitInstrumentMeta:
        raise HistoricalPlanError("instrument_not_exact_model")
    if type(server_time) is not _BybitServerTime:
        raise HistoricalPlanError("server_time_not_exact_model")
    if type(requested_window) is not _InclusiveMinuteWindow:
        raise HistoricalPlanError("requested_window_not_exact_model")
    if not _instrument_is_replay_eligible(instrument):
        raise HistoricalPlanError("instrument_not_replay_eligible")
    if not _symbol_is_valid(instrument.symbol):
        raise HistoricalPlanError("instrument_symbol_invalid")

    launch_cutoff = _validate_instrument_lifecycle(instrument)
    _validate_server_identity(server_time)
    if not _is_exact_int64(
        requested_window.start_open_time_ms,
        nonnegative=True,
    ) or not _is_exact_int64(
        requested_window.end_open_time_ms,
        nonnegative=True,
    ):
        raise HistoricalPlanError("window_time_out_of_int64")
    if instrument.snapshot_server_time_ms != server_time.server_time_ms:
        raise HistoricalPlanError("instrument_server_time_mismatch")

    delivery_cutoff = None
    if instrument.delivery_time_ms:
        delivery_cutoff = (instrument.delivery_time_ms // _MINUTE_MS) * _MINUTE_MS - _MINUTE_MS
    if requested_window.start_open_time_ms < launch_cutoff:
        raise HistoricalPlanError("window_before_launch")
    if requested_window.end_open_time_ms > server_time.last_closed_open_time_ms:
        raise HistoricalPlanError("window_after_last_closed")
    if delivery_cutoff is not None and requested_window.end_open_time_ms > delivery_cutoff:
        raise HistoricalPlanError("window_at_or_after_delivery")
    span_minutes = requested_window.row_count
    if span_minutes > 44_640:
        raise HistoricalPlanError("plan_span_limit_exceeded")

    trade_observed = _validate_observed(
        observed_trade_open_times_ms,
        name="observed_trade_open_times_ms",
        requested_window=requested_window,
    )
    mark_observed = _validate_observed(
        observed_mark_open_times_ms,
        name="observed_mark_open_times_ms",
        requested_window=requested_window,
    )
    funding_observed = _validate_observed(
        observed_funding_times_ms,
        name="observed_funding_times_ms",
        requested_window=requested_window,
    )

    trade_windows = _missing_kline_windows(requested_window, trade_observed)
    mark_windows = _missing_kline_windows(requested_window, mark_observed)
    funding_windows = _funding_windows(
        requested_window.start_open_time_ms,
        requested_window.end_open_time_ms,
    )
    requests: list[HistoricalRequestSpec] = []
    for dataset, windows in (
        ("trade_kline_1m", trade_windows),
        ("mark_kline_1m", mark_windows),
    ):
        for start_ms, end_ms, count in windows:
            requests.append(
                _kline_spec(
                    sequence_id=len(requests) + 1,
                    dataset=dataset,
                    symbol=instrument.symbol,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    count=count,
                )
            )
    for start_ms, end_ms, target in funding_windows:
        requests.append(
            _funding_spec(
                sequence_id=len(requests) + 1,
                symbol=instrument.symbol,
                start_ms=start_ms,
                end_ms=end_ms,
                target=target,
            )
        )

    identities = tuple((request.dataset, request.start_ms, request.end_ms) for request in requests)
    if len(identities) != len(set(identities)):
        raise HistoricalPlanError("request_spec_duplicate")
    if len(requests) > 256:
        raise HistoricalPlanError("request_limit_exceeded")
    planned_rows = sum(request.limit for request in requests)
    if planned_rows > 100_000:
        raise HistoricalPlanError("response_row_limit_exceeded")

    return HistoricalCapturePlan(
        schema=_SCHEMA,
        category=_CATEGORY,
        symbol=instrument.symbol,
        launch_cutoff_open_time_ms=launch_cutoff,
        delivery_cutoff_open_time_ms=delivery_cutoff,
        request_start_open_time_ms=requested_window.start_open_time_ms,
        request_cutoff_open_time_ms=requested_window.end_open_time_ms,
        server_cutoff_open_time_ms=server_time.last_closed_open_time_ms,
        funding_interval_minutes=instrument.funding_interval_minutes,
        observed_trade_row_count=len(trade_observed),
        observed_mark_row_count=len(mark_observed),
        observed_funding_row_count=len(funding_observed),
        observed_funding_times_sha256=_observed_funding_digest(funding_observed),
        trade_missing_row_count=sum(count for _, _, count in trade_windows),
        mark_missing_row_count=sum(count for _, _, count in mark_windows),
        funding_recapture_observation_upper_bound=sum(target for _, _, target in funding_windows),
        plan_span_minutes=span_minutes,
        request_count=len(requests),
        planned_max_response_rows=planned_rows,
        max_plan_span_minutes=44_640,
        max_total_requests=256,
        max_total_response_rows=100_000,
        network_authorized_bool=False,
        credentials_allowed_bool=False,
        private_api_allowed_bool=False,
        live_execution_authorized_bool=False,
        funding_coverage_proven_bool=False,
        historical_market_data_coverage_proven_bool=False,
        parameter_selection_authorized_bool=False,
        sufficient_for_parameter_selection_bool=False,
        native_equivalence_proven_bool=False,
        requests=tuple(requests),
    )


__all__ = (
    "FUNDING_LIMIT",
    "FUNDING_TARGET_RECORDS",
    "HistoricalCapturePlan",
    "HistoricalPlanError",
    "HistoricalRequestSpec",
    "KLINE_LIMIT",
    "MAX_PLAN_SPAN_MINUTES",
    "MAX_TOTAL_REQUESTS",
    "MAX_TOTAL_RESPONSE_ROWS",
    "build_historical_capture_plan",
)
