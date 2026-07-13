from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import PublicBatchError

PLAN_IDS = (
    "server_time_snapshot",
    "instrument_primary_1000",
    "instrument_alternate_200",
    "trade_primary_1000",
    "trade_alternate_251",
    "mark_primary_1000",
    "mark_alternate_251",
    "funding_primary_backward_200",
    "funding_alternate_chunked_100",
)

_FORBIDDEN_HEADERS = ("authorization", "api", "key", "secret", "cookie", "x-bapi")


def _reject_constant(x):
    raise PublicBatchError(f"json_non_finite_token:{x}")


def _reject_float(x):
    raise PublicBatchError("json_float_token")


def _object_pairs_no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise PublicBatchError("json_duplicate_key")
        out[k] = v
    return out


def strict_json_loads(text: str):
    if type(text) is not str:
        raise PublicBatchError("json_text_not_str")
    value = json.loads(
        text,
        object_pairs_hook=_object_pairs_no_dupes,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    if type(value) is not dict:
        raise PublicBatchError("json_root_not_object")
    return value


def json_exact_identity(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(json_exact_identity(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(json_exact_identity(x, y) for x, y in zip(a, b))
    return a == b


def _validate_plan_id(plan_id):
    if type(plan_id) is not str or plan_id.strip() != plan_id or plan_id not in PLAN_IDS:
        raise PublicBatchError("plan_id_invalid")


def _freeze(v):
    if isinstance(v, MappingProxyType):
        return v
    if type(v) is dict:
        return MappingProxyType({str(k): _freeze(vv) for k, vv in sorted(v.items())})
    if type(v) is list or type(v) is tuple:
        return tuple(_freeze(x) for x in v)
    return v


def _validate_public(endpoint, params):
    if (
        type(endpoint) is not str
        or endpoint.strip() != endpoint
        or not endpoint.startswith("/v5/market/")
    ):
        raise PublicBatchError("endpoint_not_public_market")
    if type(params) is not dict and not isinstance(params, MappingProxyType):
        raise PublicBatchError("params_not_mapping")
    for k, v in params.items():
        if type(k) is not str or not k:
            raise PublicBatchError("param_key_invalid")
        lk = k.lower()
        if any(s in lk for s in ("key", "secret", "sign", "token")):
            raise PublicBatchError("credential_param_forbidden")
        if type(v) not in (str, int):
            raise PublicBatchError("param_value_type_invalid")


@dataclass(frozen=True)
class RecordedPublicResponse:
    request_sequence_id: int
    endpoint: str
    params: MappingProxyType
    http_status: int
    content_type: str
    raw_body_text: str
    raw_body_sha256: str
    parsed_payload: dict
    plan_id: str = "server_time_snapshot"

    def __post_init__(self):
        if type(self.request_sequence_id) is not int or self.request_sequence_id < 1:
            raise PublicBatchError("request_sequence_id_invalid")
        _validate_plan_id(self.plan_id)
        _validate_public(self.endpoint, self.params)
        if type(self.http_status) is not int:
            raise PublicBatchError("http_status_not_int")
        if type(self.content_type) is not str:
            raise PublicBatchError("content_type_not_str")
        expected = hashlib.sha256(self.raw_body_text.encode("utf-8")).hexdigest()
        if (
            self.raw_body_sha256 != expected
            or len(self.raw_body_sha256) != 64
            or self.raw_body_sha256.lower() != self.raw_body_sha256
        ):
            raise PublicBatchError("raw_body_sha256_mismatch")
        if not json_exact_identity(strict_json_loads(self.raw_body_text), self.parsed_payload):
            raise PublicBatchError("parsed_payload_mismatch")
        object.__setattr__(self, "params", _freeze(dict(self.params)))


class RecordingPublicClient:
    def __init__(
        self,
        base_url="https://api.bybit.com",
        *,
        max_attempts=3,
        backoff_seconds=Decimal("0.25"),
        opener=None,
    ):
        if type(base_url) is not str or base_url.rstrip("/") not in {
            "https://api.bybit.com",
            "https://api.bytick.com",
        }:
            raise PublicBatchError("base_url_not_approved")
        if type(max_attempts) is not int or not (1 <= max_attempts <= 10):
            raise PublicBatchError("max_attempts_invalid")
        if type(backoff_seconds) is int:
            backoff_seconds = Decimal(backoff_seconds)
        if (
            type(backoff_seconds) is not Decimal
            or not backoff_seconds.is_finite()
            or backoff_seconds < 0
        ):
            raise PublicBatchError("backoff_seconds_invalid")
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._opener = opener
        self.records = []
        self._seq = 0

    def for_plan(self, plan_id):
        _validate_plan_id(plan_id)
        return PlanScopedPublicClient(self, plan_id)

    def public_get(self, endpoint, params, *, plan_id):
        _validate_plan_id(plan_id)
        _validate_public(endpoint, params)
        clean = dict(sorted(params.items()))
        query = urlencode(clean)
        url = f"{self.base_url}{endpoint}" + (f"?{query}" if query else "")
        last = None
        for attempt in range(1, self.max_attempts + 1):
            req = Request(url, method="GET", headers={"Accept": "application/json"})
            for h in req.header_items():
                if any(x in h[0].lower() for x in _FORBIDDEN_HEADERS):
                    raise PublicBatchError("forbidden_header")
            res = None
            try:
                res = (self._opener or urlopen)(req, timeout=10)
                status = int(getattr(res, "status", res.getcode()))
                ctype = str(res.headers.get("content-type", ""))
                body = res.read().decode("utf-8")
            except HTTPError as e:
                status = int(e.code)
                ctype = str(e.headers.get("content-type", ""))
                body = e.read().decode("utf-8")
            except UnicodeDecodeError as e:
                raise PublicBatchError("response_utf8_invalid") from e
            except (URLError, TimeoutError, OSError) as e:
                raise PublicBatchError(f"transport_error:{type(e).__name__}") from e
            finally:
                if res is not None and hasattr(res, "close"):
                    res.close()
            last = (status, ctype, body)
            if status not in (429,) and not (500 <= status <= 599):
                break
            if attempt < self.max_attempts:
                time.sleep(float(min(self.backoff_seconds * (2 ** (attempt - 1)), Decimal("2.0"))))
        status, ctype, body = last
        payload = strict_json_loads(body)
        self._seq += 1
        rec = RecordedPublicResponse(
            self._seq,
            endpoint,
            MappingProxyType(clean),
            status,
            ctype,
            body,
            hashlib.sha256(body.encode("utf-8")).hexdigest(),
            payload,
            plan_id,
        )
        self.records.append(rec)
        return payload


class PlanScopedPublicClient:
    def __init__(self, parent, plan_id):
        self._parent = parent
        self.plan_id = plan_id

    def public_get(self, endpoint, params):
        return self._parent.public_get(endpoint, params, plan_id=self.plan_id)
