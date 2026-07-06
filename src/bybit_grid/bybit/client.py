import json
import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.bybit.rate_limit import SimpleRateLimiter
from bybit_grid.bybit.signing import build_v5_sign_payload, canonical_query, sign_v5
from bybit_grid.config import Settings

log = logging.getLogger(__name__)
RETRYABLE_RETCODES = {10006, "10006"}
NON_RETRYABLE_RETCODES = {10001, "10001", 10003, "10003", 10004, "10004", 10005, "10005"}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return isinstance(exc, BybitAPIError) and (
        exc.status_code in {429, 500, 502, 503, 504} or exc.ret_code in RETRYABLE_RETCODES
    )


class BybitClient:
    def __init__(self, settings: Settings, timeout: float = 20.0):
        self.settings = settings
        self.rate_limiter = SimpleRateLimiter()
        self.http = httpx.Client(base_url=settings.bybit_api_base_url, timeout=timeout)

    def close(self):
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    def public_get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._get(endpoint, params or {}, private=False)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    def private_get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.settings.require_private_credentials()
        return self._get(endpoint, params or {}, private=True)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    def private_post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        self.settings.require_private_credentials()
        json_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        headers = self._private_headers(json_body)
        headers["Content-Type"] = "application/json"
        self.rate_limiter.wait()
        response = self.http.post(endpoint, content=json_body, headers=headers)
        return self._handle_response(endpoint, response, "bybit_post")

    def _private_headers(self, signed_payload: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        recv_window = str(self.settings.bybit_recv_window)
        payload = build_v5_sign_payload(
            ts, self.settings.bybit_api_key, recv_window, signed_payload
        )
        return {
            "X-BAPI-API-KEY": self.settings.bybit_api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": sign_v5(self.settings.bybit_api_secret, payload),
        }

    def _get(self, endpoint: str, params: dict[str, Any], private: bool) -> dict[str, Any]:
        self.rate_limiter.wait()
        headers = {}
        request_endpoint = endpoint
        request_params = params
        if private:
            query_string = canonical_query(params)
            headers = self._private_headers(query_string)
            request_endpoint = f"{endpoint}?{query_string}" if query_string else endpoint
            request_params = None
        response = self.http.get(request_endpoint, params=request_params, headers=headers)
        return self._handle_response(endpoint, response, "bybit_get")

    def _handle_response(
        self, endpoint: str, response: httpx.Response, log_name: str
    ) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {"retCode": None, "retMsg": response.text[:200]}
        log.info(
            "%s endpoint=%s status=%s retCode=%s retMsg=%s",
            log_name,
            endpoint,
            response.status_code,
            data.get("retCode"),
            data.get("retMsg"),
        )
        ret_code = data.get("retCode")
        if response.status_code in {429, 500, 502, 503, 504} or ret_code in RETRYABLE_RETCODES:
            raise BybitAPIError(
                endpoint, response.status_code, ret_code, data.get("retMsg"), "retryable"
            )
        if response.status_code >= 400 or ret_code not in (0, "0", None):
            raise BybitAPIError(
                endpoint,
                response.status_code,
                ret_code,
                data.get("retMsg"),
                "non-retryable" if ret_code in NON_RETRYABLE_RETCODES else None,
            )
        return data

    def validate_grid_bot(
        self, payload: dict[str, Any], runtime_live: bool = False
    ) -> dict[str, Any]:
        if not self.settings.grid_validate_enabled:
            return {"skipped": True, "reason": "GRID_VALIDATE_ENABLED is false"}
        return self.private_post(self.settings.bybit_fgrid_validate_path, payload)

    def create_grid_bot(self, *a, **k):
        self.settings.assert_live_trading_allowed(k.get("runtime_live", False))
        raise NotImplementedError("Live grid bot create is forbidden in Sprint 01.5")

    def close_grid_bot(self, *a, **k):
        self.settings.assert_live_trading_allowed(k.get("runtime_live", False))
        raise NotImplementedError("Live grid bot close is forbidden in Sprint 01.5")
