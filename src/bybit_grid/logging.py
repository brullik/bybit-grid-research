from __future__ import annotations

import json
import logging
import os
import re
import threading
import traceback
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

REDACTED = "***REDACTED***"
SINK_SAFE_REDACTION_CONTRACT = "sink-safe-v1"

_SECRET_LABEL = (
    r"(?:x-bapi-(?:api-key|sign)|bybit[_-]?api[_-]?(?:key|secret)|"
    r"api[_-]?(?:key|secret)|apikey|apisecret|client[_-]?secret|"
    r"private[_-]?key|signature|secret|sign|authorization|"
    r"proxy[_-]?authorization|access[_-]?token|refresh[_-]?token|token|"
    r"password|passwd|cookie|set-cookie)"
)
_TAINTED_TEXT_LABEL = (
    r"(?:body|body_first_500|debug[_-]?msg|error|error_summary|message|"
    r"response_body|response_text|retmsg|server_error)"
)
_SENSITIVE_LABEL = rf"(?:{_SECRET_LABEL}|{_TAINTED_TEXT_LABEL})"
_LABEL_PREFIX = rf"(?<![\w-])[\"']?{_SENSITIVE_LABEL}[\"']?\s*[:=]\s*"
_DOUBLE_QUOTED_SENSITIVE = re.compile(
    rf'(?P<prefix>{_LABEL_PREFIX})"(?:\\.|[^"\\])*"',
    re.IGNORECASE,
)
_SINGLE_QUOTED_SENSITIVE = re.compile(
    rf"(?P<prefix>{_LABEL_PREFIX})'(?:\\.|[^'\\])*'",
    re.IGNORECASE,
)
_UNQUOTED_SENSITIVE = re.compile(
    rf"(?P<prefix>{_LABEL_PREFIX})"
    r"(?P<value>.*?)(?=(?:[&,;}\]])|(?:\s+[A-Za-z_][\w-]*\s*[:=])|$)",
    re.IGNORECASE,
)
_STANDALONE_BEARER = re.compile(
    r"(?P<prefix>(?<![\w-])bearer\s+)(?P<value>[^\s,;}\]]+)",
    re.IGNORECASE,
)

_SENSITIVE_KEY_TOKENS = {
    "access_token",
    "api_key",
    "api_secret",
    "apikey",
    "apisecret",
    "authorization",
    "body",
    "body_first_500",
    "bybit_api_key",
    "bybit_api_secret",
    "client_secret",
    "cookie",
    "debug_msg",
    "error",
    "error_summary",
    "message",
    "password",
    "passwd",
    "private_key",
    "proxy_authorization",
    "refresh_token",
    "response_body",
    "response_text",
    "retmsg",
    "secret",
    "server_error",
    "set_cookie",
    "sign",
    "signature",
    "token",
    "x_bapi_api_key",
    "x_bapi_sign",
}
_SENSITIVE_NORMALIZED_KEYS = {
    re.sub(r"[^a-z0-9]", "", key.casefold()) for key in _SENSITIVE_KEY_TOKENS
}
_FACTORY_LOCK = threading.Lock()
_HANDLER_LOCK = threading.Lock()
_LOGGER_LOCK = threading.Lock()

_STANDARD_RECORD_FIELDS = {
    "_bybit_grid_exc_sanitized",
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


def _redact_text(value: str) -> str:
    text = _DOUBLE_QUOTED_SENSITIVE.sub(
        lambda match: f'{match.group("prefix")}"{REDACTED}"',
        value,
    )
    text = _SINGLE_QUOTED_SENSITIVE.sub(
        lambda match: f"{match.group('prefix')}'{REDACTED}'",
        text,
    )
    text = _STANDALONE_BEARER.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        text,
    )
    return _UNQUOTED_SENSITIVE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        text,
    )


def _type_name(value: Any) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _key_text(key: Any) -> str:
    if isinstance(key, str):
        return _redact_text(key)
    if isinstance(key, (bytes, bytearray, memoryview)):
        raw = key.tobytes() if isinstance(key, memoryview) else bytes(key)
        return _redact_text(raw.decode("utf-8", errors="replace"))
    if key is None or isinstance(key, (bool, int, float, Decimal, UUID)):
        return _redact_text(str(key))
    return f"<{_type_name(key)}>"


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, (str, bytes, bytearray, memoryview)):
        return False
    key_string = _key_text(key)
    normalized = re.sub(r"[^a-z0-9]", "", key_string.casefold())
    return normalized in _SENSITIVE_NORMALIZED_KEYS


def _stable_sort_key(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=lambda _: "<object>"
    )


def _redact(value: Any, active: set[int]) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = value.tobytes() if isinstance(value, memoryview) else bytes(value)
        return _redact_text(raw.decode("utf-8", errors="replace"))
    if isinstance(value, BaseException):
        return f"{_type_name(value)}: {REDACTED}"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return _redact(value.value, active)
    if isinstance(value, (Decimal, UUID, datetime, date, time)):
        return _redact_text(str(value))
    if isinstance(value, os.PathLike):
        try:
            return _redact(os.fspath(value), active)
        except Exception:
            return f"<{_type_name(value)}>"

    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        identity = id(value)
        if identity in active:
            return "<recursive-value>"
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                result: dict[str, Any] = {}
                for key, nested_value in value.items():
                    safe_key = _key_text(key)
                    if _is_sensitive_key(key):
                        result[safe_key] = (
                            nested_value
                            if nested_value is None
                            or (isinstance(nested_value, str) and nested_value == "")
                            else REDACTED
                        )
                    else:
                        result[safe_key] = _redact(nested_value, active)
                return result
            if isinstance(value, list):
                return [_redact(item, active) for item in value]
            if isinstance(value, tuple):
                return tuple(_redact(item, active) for item in value)
            items = [_redact(item, active) for item in value]
            return sorted(items, key=_stable_sort_key)
        finally:
            active.remove(identity)

    return f"<{_type_name(value)}>"


def redact(obj: Any) -> Any:
    """Return a deterministic, JSON-safe copy with identifiable secrets removed."""

    return _redact(obj, set())


def _redacted_exception_text(
    exc_info: tuple[type[BaseException], BaseException, Any],
) -> str:
    exc_type, _exc_value, tb = exc_info
    type_name = f"{exc_type.__module__}.{exc_type.__qualname__}"
    locations = []
    if tb is not None:
        for frame in traceback.extract_tb(tb):
            filename = _redact_text(os.path.basename(frame.filename))
            function = _redact_text(frame.name)
            locations.append(f"  {filename}:{frame.lineno} in {function}")
    lines = [f"Sanitized exception {type_name}: {REDACTED}"]
    if locations:
        lines.extend(["Traceback locations (source text redacted):", *locations])
    return "\n".join(lines)


def _sanitize_record(record: logging.LogRecord) -> logging.LogRecord:
    if not isinstance(record.msg, str):
        record.msg = redact(record.msg)
    if record.args:
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        else:
            record.args = redact(record.args)

    try:
        rendered = record.getMessage()
    except (KeyError, TypeError, ValueError) as exc:
        rendered = f"<unformattable-log-message:{type(exc).__name__}>"
    record.msg = _redact_text(rendered)
    record.args = ()

    if record.exc_info:
        record.exc_text = _redacted_exception_text(record.exc_info)
        record.exc_info = None
        record.__dict__["_bybit_grid_exc_sanitized"] = True
    elif record.exc_text:
        already_safe = (
            record.__dict__.get("_bybit_grid_exc_sanitized") is True
            and isinstance(record.exc_text, str)
            and record.exc_text.startswith("Sanitized exception ")
        )
        if not already_safe:
            record.exc_text = REDACTED
            record.__dict__["_bybit_grid_exc_sanitized"] = True
    if record.stack_info:
        record.stack_info = "Stack information redacted"

    for field in (
        "filename",
        "funcName",
        "levelname",
        "module",
        "name",
        "pathname",
        "processName",
        "taskName",
        "threadName",
    ):
        current = getattr(record, field, None)
        if isinstance(current, str):
            setattr(record, field, _redact_text(current))
    for key, value in tuple(record.__dict__.items()):
        if key in _STANDARD_RECORD_FIELDS:
            continue
        record.__dict__[key] = REDACTED if _is_sensitive_key(key) else redact(value)
    return record


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        _sanitize_record(record)
        return True


def _install_record_factory() -> None:
    with _FACTORY_LOCK:
        current_factory = logging.getLogRecordFactory()
        if getattr(current_factory, "_bybit_grid_sink_safe", False):
            return

        def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            return _sanitize_record(current_factory(*args, **kwargs))

        setattr(redacting_factory, "_bybit_grid_sink_safe", True)
        logging.setLogRecordFactory(redacting_factory)


def _install_handler_boundary() -> None:
    with _HANDLER_LOCK:
        current_handle = logging.Handler.handle
        if getattr(current_handle, "_bybit_grid_sink_safe", False):
            return

        def redacting_handle(
            handler: logging.Handler,
            record: logging.LogRecord,
        ) -> bool:
            return current_handle(handler, _sanitize_record(record))

        setattr(redacting_handle, "_bybit_grid_sink_safe", True)
        logging.Handler.handle = redacting_handle


def _install_logger_boundary() -> None:
    with _LOGGER_LOCK:
        current_make_record = logging.Logger.makeRecord
        if getattr(current_make_record, "_bybit_grid_sink_safe", False):
            return

        def redacting_make_record(
            logger: logging.Logger,
            *args: Any,
            **kwargs: Any,
        ) -> logging.LogRecord:
            return _sanitize_record(current_make_record(logger, *args, **kwargs))

        setattr(redacting_make_record, "_bybit_grid_sink_safe", True)
        logging.Logger.makeRecord = redacting_make_record


def _install_handler_filters() -> None:
    handlers: dict[int, logging.Handler] = {}
    for handler in logging.getLogger().handlers:
        handlers[id(handler)] = handler
    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers:
                handlers[id(handler)] = handler
    for handler in handlers.values():
        if not any(isinstance(item, RedactionFilter) for item in handler.filters):
            handler.addFilter(RedactionFilter())


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _install_record_factory()
    _install_logger_boundary()
    _install_handler_boundary()
    _install_handler_filters()


def redacted_json_dump(data: Any) -> str:
    return json.dumps(
        redact(data),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=lambda value: f"<{_type_name(value)}>",
    )
