import hashlib
import hmac
from urllib.parse import urlencode


def canonical_query(params: dict[str, object] | None) -> str:
    if not params:
        return ""
    return urlencode(sorted((k, str(v)) for k, v in params.items() if v is not None))


def build_v5_sign_payload(
    timestamp_ms: int | str, api_key: str, recv_window: int | str, query_string_or_body: str = ""
) -> str:
    return f"{timestamp_ms}{api_key}{recv_window}{query_string_or_body}"


def sign_v5(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
