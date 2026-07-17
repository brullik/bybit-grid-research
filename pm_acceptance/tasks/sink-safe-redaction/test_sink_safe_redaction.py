from __future__ import annotations

import ast
import hashlib
import io
import json
import logging
from collections import UserDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import bybit_grid.logging as sink_logging
import bybit_grid.reporting as sink_reporting


TASK_ID = "sink-safe-redaction"
SENTINEL = "sink_safe_redaction_unavailable"
CONTRACT_VERSION = "sink-safe-v1"
REDACTED = "***REDACTED***"
ROOT = Path(sink_logging.__file__).resolve().parents[2]
ORDINARY_TEST_SHA256 = (
    "a2e10f02e720063798ab034c1d7125cfb26f396dbdba669435f66149acb2a309"
)


def _ordinary_test_contract() -> tuple[str, str] | None:
    try:
        raw = (ROOT / "tests/test_redaction.py").read_bytes()
        source = raw.decode("utf-8", "strict")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    values = []
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "SINK_SAFE_REDACTION_TEST_CONTRACT"
        ):
            if isinstance(statement.value, ast.Constant) and isinstance(
                statement.value.value, str
            ):
                values.append(statement.value.value)
    if len(values) != 1:
        return None
    return values[0], hashlib.sha256(raw).hexdigest()


def _available() -> None:
    if (
        getattr(sink_logging, "SINK_SAFE_REDACTION_CONTRACT", None) != CONTRACT_VERSION
        or getattr(sink_reporting, "SINK_SAFE_REPORTING_CONTRACT", None)
        != CONTRACT_VERSION
        or _ordinary_test_contract() != (CONTRACT_VERSION, ORDINARY_TEST_SHA256)
    ):
        raise RuntimeError(SENTINEL)


def _assert_absent(blob: str | bytes, *canaries: str) -> None:
    payload = blob.encode("utf-8") if isinstance(blob, str) else blob
    for canary in canaries:
        assert canary.encode("utf-8") not in payload


def _report_bytes(root: Path) -> bytes:
    return b"\n".join(
        path.read_bytes()
        for path in sorted((root / "reports").rglob("*"))
        if path.is_file()
    )


def _run_jsons(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "reports" / "runs").glob("*.json"))
    ]


class _UnsafeObject:
    def __str__(self) -> str:
        return "UNKNOWN_OBJECT_CANARY"


@contextmanager
def _logging_state() -> Iterator[None]:
    original_factory = logging.getLogRecordFactory()
    original_handle = logging.Handler.handle
    original_make_record = logging.Logger.makeRecord
    root = logging.getLogger()
    root_handlers = list(root.handlers)
    root_filters = list(root.filters)
    root_level = root.level
    existing_handlers = {
        handler: list(handler.filters)
        for logger in [root, *logging.root.manager.loggerDict.values()]
        if isinstance(logger, logging.Logger)
        for handler in logger.handlers
    }
    try:
        yield
    finally:
        logging.setLogRecordFactory(original_factory)
        logging.Handler.handle = original_handle
        logging.Logger.makeRecord = original_make_record
        root.handlers[:] = root_handlers
        root.filters[:] = root_filters
        root.setLevel(root_level)
        for handler, filters in existing_handlers.items():
            handler.filters[:] = filters


@contextmanager
def _child_logger(
    name: str,
    handler: logging.Handler,
    *,
    propagate: bool = False,
) -> Iterator[logging.Logger]:
    logger = logging.getLogger(name)
    old_handlers = list(logger.handlers)
    old_filters = list(logger.filters)
    old_level = logger.level
    old_propagate = logger.propagate
    old_disabled = logger.disabled
    logger.handlers[:] = [handler]
    logger.filters[:] = []
    logger.setLevel(logging.INFO)
    logger.propagate = propagate
    logger.disabled = False
    try:
        yield logger
    finally:
        logger.handlers[:] = old_handlers
        logger.filters[:] = old_filters
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        logger.disabled = old_disabled


def test_contract_identity_and_marker_are_exact() -> None:
    _available()
    assert TASK_ID == "sink-safe-redaction"
    assert sink_logging.SINK_SAFE_REDACTION_CONTRACT == CONTRACT_VERSION
    assert sink_reporting.SINK_SAFE_REPORTING_CONTRACT == CONTRACT_VERSION
    assert sink_logging.REDACTED == REDACTED
    assert sink_reporting._ALLOWED_COMMANDS == {
        "invalid_report_artifact",
        "python scripts/download_sample_data.py",
        "smoke_private_account",
        "smoke_public_api",
        "unknown",
        "validate_sample_grid",
    }
    assert sink_reporting._ALLOWED_STATUSES == {
        "blocked",
        "dry-run",
        "error",
        "failed",
        "invalid",
        "network-blocked",
        "ok",
        "skipped",
        "success",
        "unknown",
    }
    assert sink_logging.redact({"api_key": "IDENTITY_CANARY"}) == {"api_key": REDACTED}


def test_nested_mapping_sensitive_key_spellings_are_redacted() -> None:
    _available()
    keys = (
        "API-KEY",
        "api_key",
        "apiKey",
        "BYBIT-API-SECRET",
        "X-BAPI-API-KEY",
        "x_bapi_sign",
        "Authorization",
        "proxy-authorization",
        "access_token",
        "password",
        "retMsg",
        "debug_msg",
        "message",
        "error_summary",
        "response_body",
    )
    canaries = tuple(f"MAPPING_CANARY_{index}" for index in range(len(keys)))
    data = UserDict({key: value for key, value in zip(keys, canaries, strict=True)})
    rendered = sink_logging.redacted_json_dump({"nested": data})
    _assert_absent(rendered, *canaries)
    assert rendered.count(REDACTED) == len(canaries)


def test_raw_double_quoted_json_secret_and_tainted_values_are_redacted() -> None:
    _available()
    canaries = (
        "DOUBLE SECRET WITH SPACES",
        "SERVER RETMSG WITH SPACES",
        "MESSAGE WITH ESCAPED QUOTE",
        "DEBUG BODY CANARY",
        "RESPONSE BODY CANARY",
    )
    raw = (
        '{"api_key":"DOUBLE SECRET WITH SPACES",'
        '"retMsg":"SERVER RETMSG WITH SPACES",'
        '"message":"MESSAGE WITH ESCAPED \\"QUOTE\\"",'
        '"debug_msg":"DEBUG BODY CANARY",'
        '"response_body":"RESPONSE BODY CANARY"}'
    )
    safe = sink_logging.redact(raw)
    _assert_absent(safe, *canaries)
    assert safe.count(REDACTED) == len(canaries)


def test_single_quotes_headers_queries_and_bearer_values_are_redacted() -> None:
    _available()
    canaries = (
        "SINGLE QUOTED CANARY",
        "HEADER VALUE CANARY",
        "QUERY_CANARY",
        "AUTHORIZATION_CANARY",
        "STANDALONE_BEARER_CANARY",
    )
    raw = (
        "{'api_secret': 'SINGLE QUOTED CANARY'} "
        "X-BAPI-SIGN: HEADER VALUE CANARY endpoint=/v5/market/time "
        "url=?signature=QUERY_CANARY&symbol=BTCUSDT "
        "Authorization: Bearer AUTHORIZATION_CANARY "
        "Bearer STANDALONE_BEARER_CANARY"
    )
    safe = sink_logging.redact(raw)
    _assert_absent(safe, *canaries)
    assert "endpoint=/v5/market/time" in safe
    assert "symbol=BTCUSDT" in safe


def test_sensitive_material_embedded_in_mapping_key_text_is_redacted() -> None:
    _available()
    data = {
        "label api_secret=KEY_TEXT_CANARY": "safe-value",
        b"header X-BAPI-SIGN=BYTE_KEY_CANARY": 7,
        "ordinary-key": "ordinary-value",
    }
    safe = sink_logging.redact(data)
    rendered = sink_logging.redacted_json_dump(safe)
    _assert_absent(rendered, "KEY_TEXT_CANARY", "BYTE_KEY_CANARY")
    assert "safe-value" in rendered
    assert safe["ordinary-key"] == "ordinary-value"


def test_bytes_unknown_objects_unordered_values_and_cycles_are_safe() -> None:
    _available()
    recursive: list[object] = []
    recursive.append(recursive)
    value = {
        "bytes": b'{"api_key":"BYTES_CANARY"}',
        "bytearray": bytearray(b"retMsg=BYTEARRAY_CANARY"),
        "memoryview": memoryview(b"?signature=MEMORYVIEW_CANARY&symbol=ETHUSDT"),
        "tuple": ("message=TUPLE_CANARY", 3),
        "set": {"api_secret=SET_CANARY", "safe"},
        "frozenset": frozenset({"error=FROZENSET_CANARY"}),
        "unknown": _UnsafeObject(),
        "recursive": recursive,
    }
    rendered = sink_logging.redacted_json_dump(value)
    _assert_absent(
        rendered,
        "BYTES_CANARY",
        "BYTEARRAY_CANARY",
        "MEMORYVIEW_CANARY",
        "TUPLE_CANARY",
        "SET_CANARY",
        "FROZENSET_CANARY",
        "UNKNOWN_OBJECT_CANARY",
    )
    assert "<recursive-value>" in rendered
    assert "_UnsafeObject" in rendered


def test_exception_json_value_drops_message_but_retains_type_and_metadata() -> None:
    _available()
    rendered = sink_logging.redacted_json_dump(
        {
            "exception": RuntimeError("EXCEPTION_VALUE_CANARY"),
            "exception_type": "RuntimeError",
            "endpoint": "/v5/fgridbot/validate",
            "http_status": 503,
            "api_code": 10001,
        }
    )
    _assert_absent(rendered, "EXCEPTION_VALUE_CANARY")
    assert "RuntimeError" in rendered
    assert "/v5/fgridbot/validate" in rendered
    assert "503" in rendered and "10001" in rendered


def test_child_handler_present_before_setup_redacts_late_formatting() -> None:
    _available()
    with _logging_state():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        with _child_logger("sink_safe.preexisting", handler) as logger:
            sink_logging.setup_logging("INFO")
            logger.info(
                "endpoint=%s api_key=%s message=%s",
                "/v5/market/time",
                "PREEXISTING_KEY_CANARY",
                "PREEXISTING_MESSAGE_CANARY",
            )
        output = stream.getvalue()
        handler.close()
    _assert_absent(output, "PREEXISTING_KEY_CANARY", "PREEXISTING_MESSAGE_CANARY")
    assert "endpoint=/v5/market/time" in output


def test_child_handler_added_after_setup_redacts_extra_after_make_record() -> None:
    _available()
    with _logging_state():
        sink_logging.setup_logging("INFO")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s %(api_key)s %(server)s"))
        with _child_logger("sink_safe.future", handler) as logger:
            logger.info(
                "status=200",
                extra={
                    "api_key": "FUTURE_EXTRA_KEY_CANARY",
                    "server": {"retMsg": "FUTURE_SERVER_CANARY"},
                },
            )
        output = stream.getvalue()
        assert getattr(logging.getLogRecordFactory(), "_bybit_grid_sink_safe", False)
        assert getattr(logging.Logger.makeRecord, "_bybit_grid_sink_safe", False)
        handler.close()
    _assert_absent(output, "FUTURE_EXTRA_KEY_CANARY", "FUTURE_SERVER_CANARY")
    assert "status=200" in output


def test_secret_split_between_percent_template_and_positional_arg_is_redacted() -> None:
    _available()
    with _logging_state():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        with _child_logger("sink_safe.positional", handler) as logger:
            sink_logging.setup_logging("INFO")
            logger.info("api_key=%s endpoint=%s", "POSITIONAL_SPLIT_CANARY", "/v5/time")
        output = stream.getvalue()
        handler.close()
    _assert_absent(output, "POSITIONAL_SPLIT_CANARY")
    assert "/v5/time" in output and REDACTED in output


def test_mapping_format_args_and_structured_extra_are_redacted() -> None:
    _available()
    with _logging_state():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s %(context)s"))
        with _child_logger("sink_safe.structured", handler) as logger:
            sink_logging.setup_logging("INFO")
            logger.info(
                "status=%(status)s api_secret=%(api_secret)s",
                {"status": 200, "api_secret": "MAPPING_FORMAT_CANARY"},
                extra={
                    "context": {
                        "authorization": "STRUCTURED_AUTH_CANARY",
                        "error": "STRUCTURED_ERROR_CANARY",
                        "endpoint": "/v5/account/info",
                    }
                },
            )
        output = stream.getvalue()
        handler.close()
    _assert_absent(
        output,
        "MAPPING_FORMAT_CANARY",
        "STRUCTURED_AUTH_CANARY",
        "STRUCTURED_ERROR_CANARY",
    )
    assert "status=200" in output and "/v5/account/info" in output


def test_logger_exception_drops_unlabelled_message_but_retains_type_and_location() -> (
    None
):
    _available()
    with _logging_state():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        with _child_logger("sink_safe.exception", handler) as logger:
            sink_logging.setup_logging("INFO")
            try:
                raise RuntimeError("UNLABELLED_EXCEPTION_MESSAGE_CANARY")
            except RuntimeError:
                logger.exception("request failed endpoint=%s", "/v5/fgridbot/validate")
        output = stream.getvalue()
        handler.close()
    _assert_absent(output, "UNLABELLED_EXCEPTION_MESSAGE_CANARY")
    assert "RuntimeError" in output
    assert "test_sink_safe_redaction.py" in output
    assert "/v5/fgridbot/validate" in output


def test_cached_exception_text_is_removed_before_handler_emit() -> None:
    _available()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(message)s %(levelname)s %(threadName)s %(taskName)s")
    )
    handler.addFilter(sink_logging.RedactionFilter())
    record = logging.LogRecord(
        "sink_safe.cached",
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
    output = stream.getvalue()
    handler.close()
    _assert_absent(
        output,
        "PRECACHED_EXCEPTION_CANARY",
        "LEVEL_NAME_CANARY",
        "THREAD_NAME_CANARY",
        "TASK_NAME_CANARY",
    )
    assert "status=500" in output and REDACTED in output


def test_setup_and_root_propagation_are_idempotent_without_duplicate_records() -> None:
    _available()
    with _logging_state():
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root.handlers[:] = [handler]
        root.setLevel(logging.INFO)
        logger = logging.getLogger("sink_safe.propagated")
        old_handlers = list(logger.handlers)
        old_propagate = logger.propagate
        old_level = logger.level
        logger.handlers[:] = []
        logger.propagate = True
        logger.setLevel(logging.INFO)
        try:
            sink_logging.setup_logging("INFO")
            factory = logging.getLogRecordFactory()
            make_record = logging.Logger.makeRecord
            handle = logging.Handler.handle
            sink_logging.setup_logging("INFO")
            assert logging.getLogRecordFactory() is factory
            assert logging.Logger.makeRecord is make_record
            assert logging.Handler.handle is handle
            assert (
                sum(
                    isinstance(item, sink_logging.RedactionFilter)
                    for item in handler.filters
                )
                == 1
            )
            logger.info("api_key=%s", "PROPAGATED_CANARY")
        finally:
            logger.handlers[:] = old_handlers
            logger.propagate = old_propagate
            logger.setLevel(old_level)
        output = stream.getvalue()
        handler.close()
    _assert_absent(output, "PROPAGATED_CANARY")
    assert len(output.splitlines()) == 1


def test_new_report_sanitizes_every_json_and_markdown_sink(
    tmp_path, monkeypatch
) -> None:
    _available()
    monkeypatch.chdir(tmp_path)
    canaries = (
        "NEW_TEXT_COUNT_CANARY",
        "NEW_UNLABELLED_PATH_CANARY",
        "NEW_ERROR_SUMMARY_CANARY",
        "NEW_NESTED_SECRET_CANARY",
        "NEW_SERVER_MESSAGE_CANARY",
        "NEW_UNKNOWN_COMMAND_CANARY",
        "NEW_UNKNOWN_STATUS_CANARY",
        "NEW_INVALID_STARTED_CANARY",
        "NEW_INVALID_ENDED_CANARY",
        "DEEP_COMMAND_CANARY",
        "DEEP_STATUS_CANARY",
        "DEEP_STARTED_CANARY",
        "DEEP_ENDED_CANARY",
        "DEEP_COUNT_CANARY",
        "DEEP_OUTPUT_PATH_CANARY",
    )
    report_path = sink_reporting.write_sprint_report(
        tmp_path / "data",
        {
            "command": canaries[5],
            "started_at": canaries[7],
            "ended_at": canaries[8],
            "status": canaries[6],
            "counts": {"rows": 11, "unexpected": canaries[0]},
            "output_paths": [canaries[1]],
            "error_summary": canaries[2],
            "nested": {"api_secret": canaries[3], "retMsg": canaries[4]},
            "deep": [
                {
                    "command": canaries[9],
                    "status": canaries[10],
                    "started_at": canaries[11],
                    "ended_at": canaries[12],
                    "counts": {"bad": canaries[13]},
                    "output_paths": [canaries[14]],
                }
            ],
        },
    )
    payload = _report_bytes(tmp_path)
    _assert_absent(payload, *canaries)
    assert report_path == Path("reports/sprint_01_api_report.md")
    assert b"11" in payload and REDACTED.encode() in payload


def test_existing_valid_run_is_rewritten_safe_before_markdown(
    tmp_path, monkeypatch
) -> None:
    _available()
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)
    legacy_path = runs_dir / "legacy.json"
    canaries = (
        "LEGACY_TEXT_COUNT_CANARY",
        "LEGACY_UNLABELLED_PATH_CANARY",
        "LEGACY_ERROR_CANARY",
        "LEGACY_NESTED_SECRET_CANARY",
        "LEGACY_SERVER_CANARY",
    )
    legacy_path.write_text(
        json.dumps(
            {
                "command": "smoke_public_api",
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:01+00:00",
                "status": "error",
                "counts": {"ok": 7, "bad": canaries[0]},
                "output_paths": [canaries[1]],
                "error_summary": canaries[2],
                "sections": {
                    "api_secret": canaries[3],
                    "message": canaries[4],
                    "endpoint": "/v5/market/time",
                },
            }
        ),
        encoding="utf-8",
    )
    sink_reporting.write_sprint_report(
        tmp_path / "data",
        {"command": "smoke_public_api", "status": "ok"},
    )
    _assert_absent(legacy_path.read_bytes(), *canaries)
    _assert_absent(_report_bytes(tmp_path), *canaries)
    assert json.loads(legacy_path.read_text(encoding="utf-8"))["counts"]["ok"] == 7


def test_malformed_and_non_utf8_existing_runs_fail_closed_in_place(
    tmp_path, monkeypatch
) -> None:
    _available()
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "reports" / "runs"
    runs_dir.mkdir(parents=True)
    malformed = runs_dir / "malformed.json"
    non_utf8 = runs_dir / "non_utf8.json"
    non_object = runs_dir / "non_object.json"
    malformed.write_text("not json MALFORMED_ARTIFACT_CANARY", encoding="utf-8")
    non_utf8.write_bytes(b"\xff\xfeNON_UTF8_ARTIFACT_CANARY")
    non_object.write_text(
        json.dumps(["VALID_NON_OBJECT_ARTIFACT_CANARY"]),
        encoding="utf-8",
    )
    sink_reporting.write_sprint_report(
        tmp_path / "data",
        {"command": "smoke_private_account", "status": "blocked"},
    )
    for path in (malformed, non_utf8, non_object):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["command"] == "invalid_report_artifact"
        assert value["status"] == "invalid"
    _assert_absent(
        _report_bytes(tmp_path),
        "MALFORMED_ARTIFACT_CANARY",
        "NON_UTF8_ARTIFACT_CANARY",
        "VALID_NON_OBJECT_ARTIFACT_CANARY",
    )


def test_useful_allowlisted_and_numeric_diagnostics_survive_exactly(
    tmp_path, monkeypatch
) -> None:
    _available()
    monkeypatch.chdir(tmp_path)
    started = "2026-01-01T00:00:00+00:00"
    ended = "2026-01-01T00:00:01+00:00"
    sink_reporting.write_sprint_report(
        tmp_path / "data",
        {
            "command": "validate_sample_grid",
            "started_at": started,
            "ended_at": ended,
            "status": "failed",
            "counts": {"rows": 13, "nested": [True, None, 2.5]},
            "output_paths": ["data/private-looking.json"],
            "error_summary": "",
            "endpoint": "/v5/fgridbot/validate",
            "http_status": 503,
            "api_code": 10001,
            "exception_type": "RuntimeError",
        },
    )
    run = _run_jsons(tmp_path)[0]
    assert run["command"] == "validate_sample_grid"
    assert run["started_at"] == started and run["ended_at"] == ended
    assert run["status"] == "failed"
    assert run["counts"] == {"nested": [True, None, 2.5], "rows": 13}
    assert run["output_paths"] == [REDACTED]
    assert run["error_summary"] == ""
    assert run["sections"]["endpoint"] == "/v5/fgridbot/validate"
    assert run["sections"]["http_status"] == 503
    assert run["sections"]["api_code"] == 10001
    assert run["sections"]["exception_type"] == "RuntimeError"


def test_redaction_and_report_rewrites_are_idempotent_and_leave_no_temp_debris(
    tmp_path,
    monkeypatch,
) -> None:
    _available()
    sample = {
        "api_key": "IDEMPOTENT_KEY_CANARY",
        "nested": ["retMsg=IDEMPOTENT_SERVER_CANARY", {"rows": 4}],
    }
    once = sink_logging.redact(sample)
    assert sink_logging.redact(once) == once
    monkeypatch.chdir(tmp_path)
    sections = {
        "command": "smoke_public_api",
        "status": "error",
        "counts": {"rows": 4, "text": "IDEMPOTENT_COUNT_CANARY"},
        "output_paths": ["IDEMPOTENT_PATH_CANARY"],
        "error_summary": "IDEMPOTENT_ERROR_CANARY",
        "message": "IDEMPOTENT_MESSAGE_CANARY",
    }
    sink_reporting.write_sprint_report(tmp_path / "data", sections)
    sink_reporting.write_sprint_report(tmp_path / "data", sections)
    _assert_absent(
        _report_bytes(tmp_path),
        "IDEMPOTENT_KEY_CANARY",
        "IDEMPOTENT_SERVER_CANARY",
        "IDEMPOTENT_COUNT_CANARY",
        "IDEMPOTENT_PATH_CANARY",
        "IDEMPOTENT_ERROR_CANARY",
        "IDEMPOTENT_MESSAGE_CANARY",
    )
    assert not [
        path for path in (tmp_path / "reports").rglob("*") if ".tmp" in path.name
    ]


def test_existing_public_api_and_sprint_015_expectations_remain_compatible(
    tmp_path,
    monkeypatch,
) -> None:
    _available()
    data = sink_logging.redact(
        {
            "api_key": "abc",
            "api_secret": "def",
            "nested": {"signature": "sig"},
            "msg": "X-BAPI-SIGN: hello secret=world",
            "headers": {
                "X-BAPI-API-KEY": "header-key",
                "X-BAPI-TIMESTAMP": "123",
            },
        }
    )
    assert data["api_key"] == REDACTED
    assert data["api_secret"] == REDACTED
    assert data["nested"]["signature"] == REDACTED
    assert "hello" not in data["msg"] and "world" not in data["msg"]
    assert data["headers"]["X-BAPI-API-KEY"] == REDACTED
    assert data["headers"]["X-BAPI-TIMESTAMP"] == "123"
    assert json.loads(sink_logging.redacted_json_dump(data))["api_key"] == REDACTED
    monkeypatch.chdir(tmp_path)
    report = sink_reporting.write_sprint_report(
        tmp_path / "data",
        {"command": "python scripts/download_sample_data.py"},
    )
    assert report == Path("reports/sprint_01_api_report.md")
    assert report.exists() and "# Sprint 01 API Report" in report.read_text(
        encoding="utf-8"
    )
    assert _run_jsons(tmp_path)[0]["status"] == "ok"
