from __future__ import annotations

import io
import json
import logging
from collections import UserDict
from pathlib import Path

import pytest

from bybit_grid.logging import (
    REDACTED,
    RedactionFilter,
    redact,
    redacted_json_dump,
    setup_logging,
)
from bybit_grid.reporting import write_sprint_report

SINK_SAFE_REDACTION_TEST_CONTRACT = "sink-safe-v1"


class _UnsafeObject:
    def __str__(self) -> str:
        return "OBJECT_SECRET_CANARY"


@pytest.fixture
def restore_logging_state():
    original_factory = logging.getLogRecordFactory()
    original_handle = logging.Handler.handle
    original_make_record = logging.Logger.makeRecord
    root = logging.getLogger()
    root_handlers = list(root.handlers)
    root_filters = list(root.filters)
    root_level = root.level
    handler_filters = {
        handler: list(handler.filters)
        for logger in [root, *logging.root.manager.loggerDict.values()]
        if isinstance(logger, logging.Logger)
        for handler in logger.handlers
    }
    yield
    logging.setLogRecordFactory(original_factory)
    logging.Handler.handle = original_handle
    logging.Logger.makeRecord = original_make_record
    root.handlers[:] = root_handlers
    root.filters[:] = root_filters
    root.setLevel(root_level)
    for handler, filters in handler_filters.items():
        handler.filters[:] = filters


def _assert_absent(blob: str | bytes, *canaries: str) -> None:
    payload = blob.encode("utf-8") if isinstance(blob, str) else blob
    for canary in canaries:
        assert canary.encode("utf-8") not in payload


def test_redacts_secret_signature_and_key():
    data = redact(
        {
            "api_key": "abc",
            "api_secret": "def",
            "nested": {"signature": "sig"},
            "msg": "X-BAPI-SIGN: hello secret=world",
        }
    )
    assert data["api_key"] == REDACTED
    assert data["api_secret"] == REDACTED
    assert data["nested"]["signature"] == REDACTED
    assert "hello" not in data["msg"] and "world" not in data["msg"]


def test_nested_mappings_bytes_exceptions_cycles_and_unknown_objects_are_safe():
    recursive: list[object] = []
    recursive.append(recursive)
    canaries = (
        "MAP_SECRET_CANARY",
        "RAW_BYTES_SECRET_CANARY",
        "EXCEPTION_SECRET_CANARY",
        "OBJECT_SECRET_CANARY",
        "SERVER_ERROR_CANARY",
    )
    value = UserDict(
        {
            "api_key": canaries[0],
            "nested": (
                bytearray(b'{"api_secret":"RAW_BYTES_SECRET_CANARY"}'),
                RuntimeError(canaries[2]),
                _UnsafeObject(),
                recursive,
            ),
            "error": canaries[4],
        }
    )
    rendered = redacted_json_dump(value)
    _assert_absent(rendered, *canaries)
    assert "<recursive-value>" in rendered
    assert "_UnsafeObject" in rendered


def test_raw_json_headers_queries_bearer_and_tainted_fields_are_redacted():
    canaries = (
        "DOUBLE QUOTED CANARY",
        "SERVER MESSAGE CANARY",
        "HEADER CANARY",
        "QUERY_CANARY",
        "BEARER_CANARY",
    )
    raw = (
        '{"api_key":"DOUBLE QUOTED CANARY", "retMsg":"SERVER MESSAGE CANARY"} '
        "X-BAPI-SIGN: HEADER CANARY endpoint=/v5/time "
        "?signature=QUERY_CANARY&symbol=BTCUSDT Authorization: Bearer BEARER_CANARY"
    )
    safe = redact(raw)
    _assert_absent(safe, *canaries)
    assert "endpoint=/v5/time" in safe and "symbol=BTCUSDT" in safe


def test_future_child_handler_covers_late_formatting_and_extra(restore_logging_state):
    setup_logging("INFO")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(api_key)s %(context)s"))
    logger = logging.getLogger("test_redaction.future")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    old_level = logger.level
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            "endpoint=%s api_secret=%s",
            "/v5/time",
            "POSITIONAL_KEY_CANARY",
            extra={
                "api_key": "EXTRA_KEY_CANARY",
                "context": {"message": "EXTRA_MESSAGE_CANARY"},
            },
        )
    finally:
        logger.handlers[:] = old_handlers
        logger.propagate = old_propagate
        logger.setLevel(old_level)
        handler.close()
    output = stream.getvalue()
    _assert_absent(
        output,
        "POSITIONAL_KEY_CANARY",
        "EXTRA_KEY_CANARY",
        "EXTRA_MESSAGE_CANARY",
    )
    assert "/v5/time" in output


def test_exception_message_is_removed_but_type_and_location_remain(
    restore_logging_state,
):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test_redaction.exception")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    old_level = logger.level
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    try:
        setup_logging("INFO")
        try:
            raise RuntimeError("UNLABELLED_EXCEPTION_CANARY")
        except RuntimeError:
            logger.exception("request failed endpoint=%s", "/v5/fgridbot/validate")
    finally:
        logger.handlers[:] = old_handlers
        logger.propagate = old_propagate
        logger.setLevel(old_level)
        handler.close()
    output = stream.getvalue()
    _assert_absent(output, "UNLABELLED_EXCEPTION_CANARY")
    assert "RuntimeError" in output and "test_redaction.py" in output


def test_preformatted_exception_text_is_removed_by_filter():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(message)s %(levelname)s %(threadName)s %(taskName)s")
    )
    handler.addFilter(RedactionFilter())
    record = logging.LogRecord(
        "test_redaction.cached",
        logging.ERROR,
        __file__,
        1,
        "status=500",
        (),
        None,
    )
    record.exc_text = "RuntimeError: PRECACHED_EXCEPTION_CANARY"
    record.levelname = "api_key=LEVEL_NAME_CANARY"
    record.threadName = "api_key=THREAD_NAME_CANARY"
    record.taskName = "message=TASK_NAME_CANARY"
    handler.handle(record)
    handler.close()
    _assert_absent(
        stream.getvalue(),
        "PRECACHED_EXCEPTION_CANARY",
        "LEVEL_NAME_CANARY",
        "THREAD_NAME_CANARY",
        "TASK_NAME_CANARY",
    )


def test_report_scrubs_new_existing_and_invalid_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)
    valid = runs_dir / "legacy.json"
    valid.write_text(
        json.dumps(
            {
                "command": "smoke_public_api",
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:01+00:00",
                "status": "error",
                "counts": {"rows": 7, "bad": "LEGACY_COUNT_CANARY"},
                "output_paths": ["LEGACY_PATH_CANARY"],
                "error_summary": "LEGACY_ERROR_CANARY",
                "sections": {"message": "LEGACY_MESSAGE_CANARY"},
            }
        ),
        encoding="utf-8",
    )
    invalid = runs_dir / "invalid.json"
    invalid.write_bytes(b"\xffINVALID_FILE_CANARY")
    report = write_sprint_report(
        tmp_path / "data",
        {
            "command": "UNKNOWN_COMMAND_CANARY",
            "status": "UNKNOWN_STATUS_CANARY",
            "counts": {"rows": 11, "bad": "NEW_COUNT_CANARY"},
            "output_paths": ["NEW_PATH_CANARY"],
            "error_summary": "NEW_ERROR_CANARY",
            "retMsg": "NEW_SERVER_CANARY",
            "deep": [
                {
                    "command": "DEEP_COMMAND_CANARY",
                    "status": "DEEP_STATUS_CANARY",
                    "started_at": "DEEP_STARTED_CANARY",
                    "ended_at": "DEEP_ENDED_CANARY",
                    "counts": {"bad": "DEEP_COUNT_CANARY"},
                    "output_paths": ["DEEP_PATH_CANARY"],
                }
            ],
        },
    )
    payload = b"".join(
        path.read_bytes()
        for path in (tmp_path / "reports").rglob("*")
        if path.is_file()
    )
    _assert_absent(
        payload,
        "LEGACY_COUNT_CANARY",
        "LEGACY_PATH_CANARY",
        "LEGACY_ERROR_CANARY",
        "LEGACY_MESSAGE_CANARY",
        "INVALID_FILE_CANARY",
        "UNKNOWN_COMMAND_CANARY",
        "UNKNOWN_STATUS_CANARY",
        "NEW_COUNT_CANARY",
        "NEW_PATH_CANARY",
        "NEW_ERROR_CANARY",
        "NEW_SERVER_CANARY",
        "DEEP_COMMAND_CANARY",
        "DEEP_STATUS_CANARY",
        "DEEP_STARTED_CANARY",
        "DEEP_ENDED_CANARY",
        "DEEP_COUNT_CANARY",
        "DEEP_PATH_CANARY",
    )
    assert report == Path("reports/sprint_01_api_report.md")
    assert not [
        path for path in (tmp_path / "reports").rglob("*") if ".tmp" in path.name
    ]


def test_report_preserves_allowlisted_and_numeric_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_sprint_report(
        tmp_path / "data",
        {
            "command": "validate_sample_grid",
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:00:01+00:00",
            "status": "failed",
            "counts": {"rows": 13, "nested": [True, None, 2.5]},
            "output_paths": ["data/result.json"],
            "error_summary": "",
            "endpoint": "/v5/fgridbot/validate",
            "http_status": 503,
            "api_code": 10001,
            "exception_type": "RuntimeError",
        },
    )
    path = next((tmp_path / "reports" / "runs").glob("*.json"))
    run = json.loads(path.read_text(encoding="utf-8"))
    assert run["command"] == "validate_sample_grid"
    assert run["status"] == "failed"
    assert run["counts"] == {"nested": [True, None, 2.5], "rows": 13}
    assert run["output_paths"] == [REDACTED]
    assert run["error_summary"] == ""
    assert run["sections"]["endpoint"] == "/v5/fgridbot/validate"
    assert run["sections"]["http_status"] == 503
    assert run["sections"]["api_code"] == 10001


def test_setup_is_idempotent_for_global_boundaries_and_handler_filters(
    restore_logging_state,
):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test_redaction.idempotent")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    logger.handlers[:] = [handler]
    logger.propagate = False
    try:
        setup_logging()
        factory = logging.getLogRecordFactory()
        make_record = logging.Logger.makeRecord
        handle = logging.Handler.handle
        setup_logging()
        assert logging.getLogRecordFactory() is factory
        assert logging.Logger.makeRecord is make_record
        assert logging.Handler.handle is handle
        assert sum(isinstance(item, RedactionFilter) for item in handler.filters) == 1
    finally:
        logger.handlers[:] = old_handlers
        logger.propagate = old_propagate
        handler.close()
