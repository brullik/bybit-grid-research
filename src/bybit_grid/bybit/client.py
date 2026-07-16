from __future__ import annotations

from contextvars import ContextVar
import json
import logging
import secrets
import time
import weakref
from dataclasses import dataclass, field, fields
from hashlib import blake2b
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.bybit.rate_limit import SimpleRateLimiter
from bybit_grid.bybit.signing import build_v5_sign_payload, canonical_query, sign_v5
from bybit_grid.bybit.validate_only import (
    CANONICAL_BYBIT_API_BASE_URL,
    CANONICAL_BYBIT_ENV,
    CANONICAL_FGRID_VALIDATE_ENDPOINT,
    CANONICAL_PRIVATE_GET_ENDPOINTS,
    ValidateOnlyBoundaryError,
    enforce_private_get_request as _enforce_private_get_request,
    enforce_validate_only_payload as _enforce_validate_only_payload,
    enforce_validate_only_settings as _enforce_validate_only_settings,
)
from bybit_grid.config import Settings


log = logging.getLogger(__name__)
RETRYABLE_RETCODES = {10006, "10006"}
NON_RETRYABLE_RETCODES = {
    10001,
    "10001",
    10003,
    "10003",
    10004,
    "10004",
    10005,
    "10005",
}
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
RATE_LIMIT_HEADER_NAMES = (
    "X-Bapi-Limit",
    "X-Bapi-Limit-Status",
    "X-Bapi-Limit-Reset-Timestamp",
)


@dataclass
class BybitClientStats:
    api_calls_attempted: int = 0
    api_calls_succeeded: int = 0
    api_calls_failed: int = 0
    max_observed_endpoint_limit: int | None = None
    min_observed_limit_status: int | None = None
    rate_limit_10006_count: int = 0


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _PreparedPrivateGet:
    environment: str
    origin: str
    endpoint: str
    request_target: str
    query_string: str
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    recv_window: int


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _PreparedPrivateValidate:
    environment: str
    origin: str
    endpoint: str
    json_body: str
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    recv_window: int


@dataclass(frozen=True, slots=True)
class _PreparedAuthorization:
    prepared_ref: weakref.ReferenceType[Any]
    fingerprint: bytes
    private_http: object
    private_transport: object
    has_private_transport: bool
    lifecycle: _PreparedLifecycle


@dataclass(slots=True)
class _PreparedLifecycle:
    invocation_token: object | None = None
    pending_attempt_token: object | None = None
    pending_reset_token: object | None = None
    active_attempt_token: object | None = None


_NO_PRIVATE_TRANSPORT = object()
_PRIVATE_ATTEMPT_MARKER: ContextVar[tuple[object, ...] | None] = ContextVar(
    "bybit_private_attempt_marker",
    default=None,
)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return isinstance(exc, BybitAPIError) and (
        exc.status_code in RETRYABLE_HTTP_STATUS_CODES
        or exc.ret_code in RETRYABLE_RETCODES
    )


def _credentials_are_exact(api_key: object, api_secret: object) -> bool:
    return (
        type(api_key) is str
        and bool(api_key)
        and type(api_secret) is str
        and bool(api_secret)
    )


def _prepared_fingerprint(prepared: object, key: bytes) -> bytes | None:
    if type(key) is not bytes or len(key) != 32:
        return None
    try:
        prepared_fields = fields(prepared)
    except TypeError:
        return None
    digest = blake2b(key=key, digest_size=32)
    for prepared_field in prepared_fields:
        value = getattr(prepared, prepared_field.name, None)
        if type(value) is str:
            atom_type = b"str"
            atom_value = value.encode("utf-8")
        elif type(value) is int:
            atom_type = b"int"
            atom_value = str(value).encode("ascii")
        else:
            return None
        for atom in (prepared_field.name.encode("utf-8"), atom_type, atom_value):
            digest.update(len(atom).to_bytes(8, "big"))
            digest.update(atom)
    return digest.digest()


def _retry_prepared_arguments(retry_state, error_code: str) -> tuple[object, object]:
    if len(retry_state.args) != 2 or retry_state.kwargs:
        raise ValidateOnlyBoundaryError(error_code)
    return retry_state.args


def _before_prepared_attempt(
    retry_state,
    expected_type: type[object],
    error_code: str,
) -> None:
    client, prepared = _retry_prepared_arguments(retry_state, error_code)
    try:
        authorization = client._authorize_prepared(
            prepared,
            expected_type,
            error_code,
        )
    except (AttributeError, TypeError) as exc:
        raise ValidateOnlyBoundaryError(error_code) from exc
    lifecycle = authorization.lifecycle
    if type(lifecycle) is not _PreparedLifecycle:
        raise ValidateOnlyBoundaryError(error_code)

    invocation_token = getattr(
        retry_state,
        "_bybit_private_invocation_token",
        None,
    )
    if invocation_token is None:
        if lifecycle.invocation_token is not None:
            raise ValidateOnlyBoundaryError(error_code)
        invocation_token = object()
        setattr(
            retry_state,
            "_bybit_private_invocation_token",
            invocation_token,
        )
        lifecycle.invocation_token = invocation_token
    elif lifecycle.invocation_token is not invocation_token:
        raise ValidateOnlyBoundaryError(error_code)

    if (
        lifecycle.pending_attempt_token is not None
        or lifecycle.pending_reset_token is not None
        or lifecycle.active_attempt_token is not None
        or _PRIVATE_ATTEMPT_MARKER.get() is not None
    ):
        raise ValidateOnlyBoundaryError(error_code)

    attempt_token = object()
    marker = (client, prepared, lifecycle, invocation_token, attempt_token)
    reset_token = _PRIVATE_ATTEMPT_MARKER.set(marker)
    lifecycle.pending_attempt_token = attempt_token
    lifecycle.pending_reset_token = reset_token


def _before_private_get_attempt(retry_state) -> None:
    _before_prepared_attempt(
        retry_state,
        _PreparedPrivateGet,
        "private_get_prepared_request_invalid",
    )


def _before_private_validate_attempt(retry_state) -> None:
    _before_prepared_attempt(
        retry_state,
        _PreparedPrivateValidate,
        "validate_prepared_request_invalid",
    )


def _begin_prepared_attempt(
    client: object,
    prepared: object,
    expected_type: type[object],
    error_code: str,
) -> tuple[_PreparedAuthorization, object]:
    marker = _PRIVATE_ATTEMPT_MARKER.get()
    if type(marker) is not tuple or len(marker) != 5:
        raise ValidateOnlyBoundaryError(error_code)
    marker_client, marker_prepared, lifecycle, invocation_token, attempt_token = marker
    if type(lifecycle) is not _PreparedLifecycle:
        raise ValidateOnlyBoundaryError(error_code)
    reset_token = lifecycle.pending_reset_token
    marker_is_exact = (
        marker_client is client
        and marker_prepared is prepared
        and lifecycle.invocation_token is invocation_token
        and lifecycle.pending_attempt_token is attempt_token
        and reset_token is not None
        and lifecycle.active_attempt_token is None
    )
    try:
        if not marker_is_exact:
            raise ValidateOnlyBoundaryError(error_code)
    finally:
        if reset_token is not None:
            try:
                _PRIVATE_ATTEMPT_MARKER.reset(reset_token)
            except (RuntimeError, ValueError) as exc:
                lifecycle.pending_attempt_token = None
                lifecycle.pending_reset_token = None
                raise ValidateOnlyBoundaryError(error_code) from exc
        lifecycle.pending_attempt_token = None
        lifecycle.pending_reset_token = None

    try:
        authorization = client._authorize_prepared(
            prepared,
            expected_type,
            error_code,
        )
    except (AttributeError, TypeError) as exc:
        raise ValidateOnlyBoundaryError(error_code) from exc
    if (
        authorization.lifecycle is not lifecycle
        or lifecycle.invocation_token is not invocation_token
        or lifecycle.active_attempt_token is not None
    ):
        raise ValidateOnlyBoundaryError(error_code)
    lifecycle.active_attempt_token = attempt_token
    return authorization, attempt_token


def _authorize_active_attempt(
    client: object,
    prepared: object,
    expected_type: type[object],
    error_code: str,
    authorization: _PreparedAuthorization,
    attempt_token: object,
) -> _PreparedAuthorization:
    current = client._authorize_prepared(prepared, expected_type, error_code)
    if (
        current is not authorization
        or current.lifecycle.active_attempt_token is not attempt_token
    ):
        raise ValidateOnlyBoundaryError(error_code)
    return current


def _end_prepared_attempt(
    authorization: _PreparedAuthorization,
    attempt_token: object,
) -> None:
    lifecycle = authorization.lifecycle
    if (
        type(lifecycle) is _PreparedLifecycle
        and lifecycle.active_attempt_token is attempt_token
    ):
        lifecycle.active_attempt_token = None


def _private_get_atoms_are_valid(prepared: _PreparedPrivateGet) -> bool:
    if (
        type(prepared.environment) is not str
        or prepared.environment != CANONICAL_BYBIT_ENV
        or type(prepared.origin) is not str
        or prepared.origin != CANONICAL_BYBIT_API_BASE_URL
        or type(prepared.endpoint) is not str
        or prepared.endpoint not in CANONICAL_PRIVATE_GET_ENDPOINTS
        or type(prepared.request_target) is not str
        or type(prepared.query_string) is not str
        or not _credentials_are_exact(prepared.api_key, prepared.api_secret)
        or type(prepared.recv_window) is not int
        or prepared.recv_window != 5000
    ):
        return False
    expected_target = (
        f"{prepared.endpoint}?{prepared.query_string}"
        if prepared.query_string
        else prepared.endpoint
    )
    if prepared.request_target != expected_target:
        return False
    if prepared.endpoint == "/v5/account/info":
        return prepared.query_string == ""
    if prepared.endpoint == "/v5/account/wallet-balance":
        return prepared.query_string == "accountType=UNIFIED"
    if prepared.query_string == "category=linear":
        return True
    prefix = "category=linear&symbol="
    if not prepared.query_string.startswith(prefix):
        return False
    symbol = prepared.query_string[len(prefix) :]
    return (
        2 <= len(symbol) <= 32
        and symbol.isascii()
        and symbol.isalnum()
        and symbol.isupper()
        and symbol.endswith("USDT")
    )


def _private_validate_atoms_are_valid(prepared: _PreparedPrivateValidate) -> bool:
    return (
        type(prepared.environment) is str
        and prepared.environment == CANONICAL_BYBIT_ENV
        and type(prepared.origin) is str
        and prepared.origin == CANONICAL_BYBIT_API_BASE_URL
        and type(prepared.endpoint) is str
        and prepared.endpoint == CANONICAL_FGRID_VALIDATE_ENDPOINT
        and type(prepared.json_body) is str
        and _credentials_are_exact(prepared.api_key, prepared.api_secret)
        and type(prepared.recv_window) is int
        and prepared.recv_window == 5000
    )


class BybitClient:
    def __init__(
        self,
        settings: Settings,
        timeout: float = 20.0,
        rate_limiter: SimpleRateLimiter | None = None,
    ):
        self.settings = settings
        self.rate_limiter = rate_limiter or SimpleRateLimiter()
        self.stats = BybitClientStats()
        self.http = httpx.Client(
            base_url=settings.bybit_api_base_url,
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )
        self.private_http = httpx.Client(
            base_url="https://api.bybit.com",
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )

    def _prepared_authorization_state(
        self,
        *,
        create: bool,
    ) -> tuple[dict[int, _PreparedAuthorization], bytes] | None:
        instance_state = vars(self)
        registry = instance_state.get("_private_prepared_registry")
        fingerprint_key = instance_state.get("_private_prepared_fingerprint_key")
        if registry is None and fingerprint_key is None and create:
            registry = {}
            fingerprint_key = secrets.token_bytes(32)
            object.__setattr__(self, "_private_prepared_registry", registry)
            object.__setattr__(
                self,
                "_private_prepared_fingerprint_key",
                fingerprint_key,
            )
        if type(registry) is not dict or type(fingerprint_key) is not bytes:
            return None
        if len(fingerprint_key) != 32:
            return None
        return registry, fingerprint_key

    def _issue_prepared(self, prepared: object, error_code: str) -> object:
        state = self._prepared_authorization_state(create=True)
        if state is None:
            raise ValidateOnlyBoundaryError(error_code)
        registry, fingerprint_key = state
        fingerprint = _prepared_fingerprint(prepared, fingerprint_key)
        if fingerprint is None:
            raise ValidateOnlyBoundaryError(error_code)
        private_http = self.private_http
        has_private_transport = hasattr(private_http, "_transport")
        private_transport = (
            getattr(private_http, "_transport")
            if has_private_transport
            else _NO_PRIVATE_TRANSPORT
        )

        identity = id(prepared)
        existing = registry.get(identity)
        if existing is not None:
            if (
                type(existing) is not _PreparedAuthorization
                or existing.prepared_ref() is not None
            ):
                raise ValidateOnlyBoundaryError(error_code)
            registry.pop(identity, None)

        def discard(reference: weakref.ReferenceType[Any]) -> None:
            current = registry.get(identity)
            if (
                type(current) is _PreparedAuthorization
                and current.prepared_ref is reference
            ):
                registry.pop(identity, None)

        prepared_ref = weakref.ref(prepared, discard)
        registry[id(prepared)] = _PreparedAuthorization(
            prepared_ref=prepared_ref,
            fingerprint=fingerprint,
            private_http=private_http,
            private_transport=private_transport,
            has_private_transport=has_private_transport,
            lifecycle=_PreparedLifecycle(),
        )
        return prepared

    def _authorize_prepared(
        self,
        prepared: object,
        expected_type: type[object],
        error_code: str,
    ) -> _PreparedAuthorization:
        if type(prepared) is not expected_type:
            raise ValidateOnlyBoundaryError(error_code)
        state = self._prepared_authorization_state(create=False)
        if state is None:
            raise ValidateOnlyBoundaryError(error_code)
        registry, fingerprint_key = state
        authorization = registry.get(id(prepared))
        if (
            type(authorization) is not _PreparedAuthorization
            or authorization.prepared_ref() is not prepared
            or type(authorization.lifecycle) is not _PreparedLifecycle
        ):
            raise ValidateOnlyBoundaryError(error_code)
        current_fingerprint = _prepared_fingerprint(prepared, fingerprint_key)
        if current_fingerprint is None or not secrets.compare_digest(
            current_fingerprint,
            authorization.fingerprint,
        ):
            registry.pop(id(prepared), None)
            raise ValidateOnlyBoundaryError(error_code)
        return authorization

    def _revoke_prepared(self, prepared: object) -> None:
        state = self._prepared_authorization_state(create=False)
        if state is None:
            return
        registry, _ = state
        authorization = registry.get(id(prepared))
        if (
            type(authorization) is _PreparedAuthorization
            and authorization.prepared_ref() is prepared
        ):
            registry.pop(id(prepared), None)

    def close(self):
        try:
            self.http.close()
        finally:
            try:
                self.private_http.close()
            finally:
                state = self._prepared_authorization_state(create=False)
                if state is not None:
                    state[0].clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    def public_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.rate_limiter.wait()
        response = self.http.get(endpoint, params=params or {}, headers={})
        return self._handle_response(endpoint, response, "bybit_get")

    def private_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params is None:
            owned_params = {}
        elif type(params) is dict:
            owned_params = dict(params)
        else:
            owned_params = params
        _enforce_private_get_request(endpoint=endpoint, params=owned_params)
        _enforce_validate_only_settings(settings=self.settings)
        self._enforce_private_http_policy()
        self.settings.require_private_credentials()
        query_string = canonical_query(owned_params)
        api_key = self.settings.bybit_api_key
        api_secret = self.settings.bybit_api_secret
        if not _credentials_are_exact(api_key, api_secret):
            raise ValidateOnlyBoundaryError("private_get_prepared_request_invalid")
        request_target = f"{endpoint}?{query_string}" if query_string else endpoint
        prepared = _PreparedPrivateGet(
            environment=CANONICAL_BYBIT_ENV,
            origin=CANONICAL_BYBIT_API_BASE_URL,
            endpoint=endpoint,
            request_target=request_target,
            query_string=query_string,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=self.settings.bybit_recv_window,
        )
        self._issue_prepared(prepared, "private_get_prepared_request_invalid")
        try:
            return self._private_get(prepared)
        finally:
            self._revoke_prepared(prepared)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
        before=_before_private_get_attempt,
    )
    def _private_get(self, prepared) -> dict[str, Any]:
        authorization, attempt_token = _begin_prepared_attempt(
            self,
            prepared,
            _PreparedPrivateGet,
            "private_get_prepared_request_invalid",
        )
        try:
            if not _private_get_atoms_are_valid(prepared):
                raise ValidateOnlyBoundaryError("private_get_prepared_request_invalid")
            self._enforce_private_http_policy(authorization)
            headers = self._private_headers(
                api_key=prepared.api_key,
                api_secret=prepared.api_secret,
                recv_window=prepared.recv_window,
                signed_payload=prepared.query_string,
            )
            self.rate_limiter.wait()
            authorization = _authorize_active_attempt(
                self,
                prepared,
                _PreparedPrivateGet,
                "private_get_prepared_request_invalid",
                authorization,
                attempt_token,
            )
            self._enforce_private_http_policy(authorization)
            response = self.private_http.get(
                prepared.request_target,
                params=None,
                headers=headers,
            )
            return self._handle_response(
                prepared.endpoint,
                response,
                "bybit_get_private",
            )
        finally:
            _end_prepared_attempt(authorization, attempt_token)

    def private_post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        raise ValidateOnlyBoundaryError("generic_private_post_forbidden")

    def validate_grid_bot(self, payload) -> dict[str, Any]:
        _enforce_validate_only_settings(settings=self.settings)
        _enforce_validate_only_payload(payload=payload)
        if self.settings.grid_validate_enabled is False:
            return {"skipped": True, "reason": "GRID_VALIDATE_ENABLED is false"}
        self._enforce_private_http_policy()
        self.settings.require_private_credentials()
        json_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        api_key = self.settings.bybit_api_key
        api_secret = self.settings.bybit_api_secret
        if not _credentials_are_exact(api_key, api_secret):
            raise ValidateOnlyBoundaryError("validate_prepared_request_invalid")
        prepared = _PreparedPrivateValidate(
            environment=CANONICAL_BYBIT_ENV,
            origin=CANONICAL_BYBIT_API_BASE_URL,
            endpoint=CANONICAL_FGRID_VALIDATE_ENDPOINT,
            json_body=json_body,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=self.settings.bybit_recv_window,
        )
        self._issue_prepared(prepared, "validate_prepared_request_invalid")
        try:
            return self._private_validate_post(prepared)
        finally:
            self._revoke_prepared(prepared)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
        before=_before_private_validate_attempt,
    )
    def _private_validate_post(self, prepared) -> dict[str, Any]:
        authorization, attempt_token = _begin_prepared_attempt(
            self,
            prepared,
            _PreparedPrivateValidate,
            "validate_prepared_request_invalid",
        )
        try:
            if not _private_validate_atoms_are_valid(prepared):
                raise ValidateOnlyBoundaryError("validate_prepared_request_invalid")
            try:
                payload = json.loads(prepared.json_body)
            except (TypeError, ValueError) as exc:
                raise ValidateOnlyBoundaryError(
                    "validate_prepared_request_invalid"
                ) from exc
            try:
                _enforce_validate_only_payload(payload=payload)
            except ValidateOnlyBoundaryError as exc:
                raise ValidateOnlyBoundaryError(
                    "validate_prepared_request_invalid"
                ) from exc
            if (
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                != prepared.json_body
            ):
                raise ValidateOnlyBoundaryError("validate_prepared_request_invalid")
            self._enforce_private_http_policy(authorization)
            headers = self._private_headers(
                api_key=prepared.api_key,
                api_secret=prepared.api_secret,
                recv_window=prepared.recv_window,
                signed_payload=prepared.json_body,
            )
            headers["Content-Type"] = "application/json"
            self.rate_limiter.wait()
            authorization = _authorize_active_attempt(
                self,
                prepared,
                _PreparedPrivateValidate,
                "validate_prepared_request_invalid",
                authorization,
                attempt_token,
            )
            self._enforce_private_http_policy(authorization)
            self.stats.api_calls_attempted += 1
            try:
                response = self.private_http.post(
                    CANONICAL_FGRID_VALIDATE_ENDPOINT,
                    content=prepared.json_body,
                    headers=headers,
                )
                data = self._handle_response(
                    CANONICAL_FGRID_VALIDATE_ENDPOINT,
                    response,
                    "bybit_post_validate",
                )
            except Exception:
                self.stats.api_calls_failed += 1
                raise
            self.stats.api_calls_succeeded += 1
            return data
        finally:
            _end_prepared_attempt(authorization, attempt_token)

    @staticmethod
    def _private_headers(
        *,
        api_key: str,
        api_secret: str,
        recv_window: int,
        signed_payload: str,
    ) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        recv_window_text = str(recv_window)
        signing_target = build_v5_sign_payload(
            timestamp,
            api_key,
            recv_window_text,
            signed_payload,
        )
        return {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window_text,
            "X-BAPI-SIGN": sign_v5(api_secret, signing_target),
        }

    def _enforce_private_http_origin(self) -> None:
        try:
            base_url = self.private_http.base_url
        except (AttributeError, TypeError) as exc:
            raise ValidateOnlyBoundaryError("private_http_origin_forbidden") from exc
        if type(base_url) is not httpx.URL or str(base_url) != CANONICAL_BYBIT_API_BASE_URL:
            raise ValidateOnlyBoundaryError("private_http_origin_forbidden")

    def _enforce_private_http_policy(
        self,
        authorization: _PreparedAuthorization | None = None,
    ) -> None:
        private_http = self.private_http
        if authorization is not None:
            if private_http is not authorization.private_http:
                raise ValidateOnlyBoundaryError("private_http_policy_forbidden")
            has_private_transport = hasattr(private_http, "_transport")
            if has_private_transport is not authorization.has_private_transport:
                raise ValidateOnlyBoundaryError("private_http_policy_forbidden")
            if has_private_transport:
                if private_http._transport is not authorization.private_transport:
                    raise ValidateOnlyBoundaryError("private_http_policy_forbidden")
            elif authorization.private_transport is not _NO_PRIVATE_TRANSPORT:
                raise ValidateOnlyBoundaryError("private_http_policy_forbidden")
        self._enforce_private_http_origin()
        try:
            follow_redirects = private_http.follow_redirects
            trust_env = private_http._trust_env
        except (AttributeError, TypeError) as exc:
            raise ValidateOnlyBoundaryError("private_http_policy_forbidden") from exc
        if (
            type(follow_redirects) is not bool
            or follow_redirects is not False
            or type(trust_env) is not bool
            or trust_env is not False
        ):
            raise ValidateOnlyBoundaryError("private_http_policy_forbidden")
        if hasattr(private_http, "_mounts"):
            mounts = private_http._mounts
            if type(mounts) is not dict or mounts:
                raise ValidateOnlyBoundaryError("private_http_policy_forbidden")

    def _handle_response(
        self,
        endpoint: str,
        response: httpx.Response,
        log_name: str,
    ) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {"retCode": None, "retMsg": response.text[:200]}

        self._capture_rate_limit_headers(data, response)
        ret_code = data.get("retCode")
        status_code = data.get("status_code")
        message = data.get("retMsg") or data.get("debug_msg")
        has_ret_code = "retCode" in data
        has_bot_status = "status_code" in data

        if has_ret_code:
            api_success = ret_code in (0, "0")
            api_code = ret_code
        elif has_bot_status:
            api_success = status_code in (200, "200")
            api_code = status_code
        else:
            api_success = 200 <= response.status_code < 300
            api_code = None
            if api_success:
                data.setdefault(
                    "parser_warning",
                    "response missing retCode and status_code; HTTP 2xx treated as success",
                )

        log.info(
            "%s endpoint=%s http_status=%s retCode=%s status_code=%s "
            "message=%s parser_warning=%s",
            log_name,
            endpoint,
            response.status_code,
            ret_code,
            status_code,
            message,
            data.get("parser_warning"),
        )

        if response.status_code in RETRYABLE_HTTP_STATUS_CODES or ret_code in RETRYABLE_RETCODES:
            raise BybitAPIError(
                endpoint,
                response.status_code,
                api_code,
                message,
                "retryable",
                data,
            )
        if response.status_code >= 400 or not api_success:
            debug_message = (
                "non-retryable"
                if ret_code in NON_RETRYABLE_RETCODES
                else data.get("debug_msg")
            )
            raise BybitAPIError(
                endpoint,
                response.status_code,
                api_code,
                message,
                debug_message,
                data,
            )
        return data

    def _capture_rate_limit_headers(
        self,
        data: dict[str, Any],
        response: httpx.Response,
    ) -> None:
        rate_meta: dict[str, str] = {}
        for name in RATE_LIMIT_HEADER_NAMES:
            value = response.headers.get(name)
            if value is not None:
                rate_meta[name] = value
        if rate_meta:
            data["rate_limit_headers"] = rate_meta
        endpoint_limit = rate_meta.get("X-Bapi-Limit")
        limit_status = rate_meta.get("X-Bapi-Limit-Status")
        if endpoint_limit is not None:
            try:
                value = int(endpoint_limit)
                self.stats.max_observed_endpoint_limit = (
                    value
                    if self.stats.max_observed_endpoint_limit is None
                    else max(self.stats.max_observed_endpoint_limit, value)
                )
            except ValueError:
                pass
        if limit_status is not None:
            try:
                value = int(limit_status)
                self.stats.min_observed_limit_status = (
                    value
                    if self.stats.min_observed_limit_status is None
                    else min(self.stats.min_observed_limit_status, value)
                )
            except ValueError:
                pass
        if data.get("retCode") in RETRYABLE_RETCODES:
            self.stats.rate_limit_10006_count += 1

    def create_grid_bot(self, *args, **kwargs):
        raise NotImplementedError("Live grid bot create is forbidden")

    def close_grid_bot(self, *args, **kwargs):
        raise NotImplementedError("Live grid bot close is forbidden")
