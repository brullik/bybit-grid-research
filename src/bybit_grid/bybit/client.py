import logging, time
from typing import Any
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.bybit.rate_limit import SimpleRateLimiter
from bybit_grid.bybit.signing import canonical_query, build_v5_sign_payload, sign_v5
from bybit_grid.config import Settings
log=logging.getLogger(__name__)

class BybitClient:
    def __init__(self, settings: Settings, timeout: float=20.0):
        self.settings=settings; self.rate_limiter=SimpleRateLimiter(); self.http=httpx.Client(base_url=settings.bybit_api_base_url, timeout=timeout)
    def close(self): self.http.close()
    def __enter__(self): return self
    def __exit__(self,*a): self.close()
    @retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=0.5, min=0.5, max=8), retry=retry_if_exception_type((httpx.TimeoutException,httpx.TransportError,BybitAPIError)))
    def public_get(self, endpoint: str, params: dict[str, Any] | None=None) -> dict[str, Any]:
        return self._get(endpoint, params or {}, private=False)
    @retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=0.5, min=0.5, max=8), retry=retry_if_exception_type((httpx.TimeoutException,httpx.TransportError,BybitAPIError)))
    def private_get(self, endpoint: str, params: dict[str, Any] | None=None) -> dict[str, Any]:
        self.settings.require_private_credentials(); return self._get(endpoint, params or {}, private=True)
    def _get(self, endpoint: str, params: dict[str, Any], private: bool) -> dict[str, Any]:
        self.rate_limiter.wait(); headers={}
        if private:
            ts=str(int(time.time()*1000)); qs=canonical_query(params); payload=build_v5_sign_payload(ts,self.settings.bybit_api_key,self.settings.bybit_recv_window,qs)
            headers={'X-BAPI-API-KEY':self.settings.bybit_api_key,'X-BAPI-TIMESTAMP':ts,'X-BAPI-RECV-WINDOW':str(self.settings.bybit_recv_window),'X-BAPI-SIGN':sign_v5(self.settings.bybit_api_secret,payload)}
        r=self.http.get(endpoint, params=params, headers=headers)
        try: data=r.json()
        except ValueError: data={'retCode':None,'retMsg':r.text[:200]}
        log.info('bybit_get endpoint=%s status=%s retCode=%s retMsg=%s', endpoint, r.status_code, data.get('retCode'), data.get('retMsg'))
        if r.status_code in {429,500,502,503,504}: raise BybitAPIError(endpoint,r.status_code,data.get('retCode'),data.get('retMsg'),'temporary/rate-limit')
        if r.status_code>=400 or data.get('retCode') not in (0,'0',None): raise BybitAPIError(endpoint,r.status_code,data.get('retCode'),data.get('retMsg'))
        return data
    def validate_grid_bot(self, payload: dict[str, Any], runtime_live: bool=False) -> dict[str, Any]:
        if not self.settings.grid_validate_enabled: return {'skipped': True, 'reason': 'GRID_VALIDATE_ENABLED is false'}
        # Validate-only endpoint is allowed when explicitly configured; no create/close call is implemented.
        return self.private_get(self.settings.bybit_grid_validate_path, payload)
    def create_grid_bot(self,*a,**k):
        self.settings.assert_live_trading_allowed(k.get('runtime_live', False)); raise NotImplementedError('Live grid bot create is forbidden in Sprint 01')
    def close_grid_bot(self,*a,**k):
        self.settings.assert_live_trading_allowed(k.get('runtime_live', False)); raise NotImplementedError('Live grid bot close is forbidden in Sprint 01')
