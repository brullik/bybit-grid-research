import json
import logging
import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(X-BAPI-(?:SIGN|API-KEY)\s*[:=]\s*)([^,\s}]+)", re.I),
    re.compile(r"((?:api[_-]?(?:secret|key)|apiKey|apiSecret)\s*[:=]\s*)([^,\s}]+)", re.I),
    re.compile(r"(signature\s*[:=]\s*)([^,\s}]+)", re.I),
    re.compile(r"(secret\s*[:=]\s*)([^,\s}]+)", re.I),
]
SENSITIVE_KEYS = {
    "bybit_api_key",
    "api_key",
    "apikey",
    "api-key",
    "apikey",
    "x-bapi-api-key",
    "bybit_api_secret",
    "api_secret",
    "apisecret",
    "api-secret",
    "secret",
    "signature",
    "sign",
    "x-bapi-sign",
}


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if str(k).lower() in SENSITIVE_KEYS else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        s = obj
        for p in SECRET_PATTERNS:
            s = p.sub(r"\1***REDACTED***", s)
        return s
    return obj


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if record.args:
            record.args = (
                tuple(redact(a) for a in record.args)
                if isinstance(record.args, tuple)
                else redact(record.args)
            )
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger().addFilter(RedactionFilter())


def redacted_json_dump(data: Any) -> str:
    return json.dumps(redact(data), indent=2, sort_keys=True, default=str)
# RED PROBE: inert sink-safe logging availability check.\n