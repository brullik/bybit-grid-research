from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from bybit_grid.logging import REDACTED, redact, redacted_json_dump

SINK_SAFE_REPORTING_CONTRACT = "sink-safe-v1"

_ALLOWED_COMMANDS = {
    "invalid_report_artifact",
    "python scripts/download_sample_data.py",
    "smoke_private_account",
    "smoke_public_api",
    "unknown",
    "validate_sample_grid",
}
_ALLOWED_STATUSES = {
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_key(key: Any) -> str:
    return next(iter(redact({key: None})))


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _safe_key(key).casefold())


def _numeric_counts_only(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _safe_key(key): _numeric_counts_only(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_numeric_counts_only(nested) for nested in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return REDACTED


def _sanitize_counts(value: Any) -> Any:
    return _numeric_counts_only(redact(value))


def _sanitize_error_summary(value: Any) -> str:
    if value is None or (isinstance(value, str) and value == ""):
        return ""
    return REDACTED


def _allowlisted_text(value: Any, allowed: set[str], *, fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    if value is None or (isinstance(value, str) and value == ""):
        return fallback
    return REDACTED


def _sanitize_timestamp(value: Any, *, fallback: str) -> str:
    if value is None or (isinstance(value, str) and value == ""):
        return fallback
    if not isinstance(value, str) or len(value) > 64:
        return REDACTED
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return REDACTED
    if parsed.tzinfo is None:
        return REDACTED
    return value


def _sanitize_output_paths(value: Any) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        empty = value is None or (isinstance(value, str) and value == "")
        return [] if empty else [REDACTED]
    return [REDACTED for _item in value]


def _sanitize_section_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_sanitize_section_value(nested) for nested in value]
    if not isinstance(value, Mapping):
        return value
    safe: dict[str, Any] = {}
    for key, nested in value.items():
        safe_key = _safe_key(key)
        normalized = _normalized_key(key)
        if normalized == "command":
            safe[safe_key] = _allowlisted_text(
                nested, _ALLOWED_COMMANDS, fallback="unknown"
            )
        elif normalized in {"startedat", "endedat"}:
            safe[safe_key] = _sanitize_timestamp(nested, fallback="unknown")
        elif normalized == "status":
            safe[safe_key] = _allowlisted_text(
                nested, _ALLOWED_STATUSES, fallback="unknown"
            )
        elif normalized == "counts":
            safe[safe_key] = _sanitize_counts(nested)
        elif normalized == "outputpaths":
            safe[safe_key] = _sanitize_output_paths(nested)
        elif normalized == "errorsummary":
            safe[safe_key] = _sanitize_error_summary(nested)
        else:
            safe[safe_key] = _sanitize_section_value(nested)
    return safe


def _sanitize_sections(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"invalid_sections": REDACTED}
    safe = _sanitize_section_value(redact(value))
    return safe if isinstance(safe, dict) else {"invalid_sections": REDACTED}


def _sanitize_run(value: Any, *, now: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "command": "invalid_report_artifact",
            "started_at": now,
            "ended_at": now,
            "status": "invalid",
            "counts": {},
            "output_paths": [],
            "error_summary": REDACTED,
            "sections": {"invalid_artifact": REDACTED},
        }
    return {
        "command": _allowlisted_text(
            value.get("command", "unknown"),
            _ALLOWED_COMMANDS,
            fallback="unknown",
        ),
        "started_at": _sanitize_timestamp(value.get("started_at", now), fallback=now),
        "ended_at": _sanitize_timestamp(value.get("ended_at", now), fallback=now),
        "status": _allowlisted_text(
            value.get("status", "unknown"),
            _ALLOWED_STATUSES,
            fallback="unknown",
        ),
        "counts": _sanitize_counts(value.get("counts", {})),
        "output_paths": _sanitize_output_paths(value.get("output_paths", [])),
        "error_summary": _sanitize_error_summary(value.get("error_summary", "")),
        "sections": _sanitize_sections(value.get("sections", {})),
    }


def _scrub_existing_run(path: Path, *, now: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_bytes().decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raw = None
    safe = _sanitize_run(raw, now=now)
    _write_text_atomic(path, redacted_json_dump(safe))
    return safe


def _inline_json(value: Any) -> str:
    return json.dumps(redact(value), ensure_ascii=False, sort_keys=True)


def write_sprint_report(data_dir: Path, sections: dict[str, object]) -> Path:
    del data_dir  # Historical reports location is intentionally repository-relative.
    reports_dir = Path("reports")
    runs_dir = reports_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    run = _sanitize_run(
        {
            "command": sections.get("command", "unknown"),
            "started_at": sections.get("started_at", now),
            "ended_at": sections.get("ended_at", now),
            "status": sections.get("status", "ok"),
            "counts": sections.get("counts", {}),
            "output_paths": sections.get("output_paths", []),
            "error_summary": sections.get("error_summary", ""),
            "sections": sections,
        },
        now=now,
    )
    run_path = (
        runs_dir / f"{now.replace(':', '').replace('+', 'Z')}_{uuid4().hex[:8]}.json"
    )
    _write_text_atomic(run_path, redacted_json_dump(run))

    runs = [
        _scrub_existing_run(path, now=now) for path in sorted(runs_dir.glob("*.json"))
    ]
    lines = ["# Sprint 01 API Report", "", f"Updated UTC: {now}", "", "## Runs", ""]
    for item in runs:
        lines += [
            f"### {_inline_json(item.get('command', 'unknown'))} — "
            f"{_inline_json(item.get('status', 'unknown'))}",
            "",
            f"- started_at: {_inline_json(item.get('started_at', ''))}",
            f"- ended_at: {_inline_json(item.get('ended_at', ''))}",
            f"- counts: `{_inline_json(item.get('counts', {}))}`",
            f"- output_paths: `{_inline_json(item.get('output_paths', []))}`",
            f"- error_summary: {_inline_json(item.get('error_summary') or 'none')}",
            "",
        ]
        report_sections = item.get("sections", {})
        if isinstance(report_sections, Mapping):
            for key, value in report_sections.items():
                lines += [f"#### {_inline_json(key)}", "", _inline_json(value), ""]
    report_path = reports_dir / "sprint_01_api_report.md"
    _write_text_atomic(report_path, str(redact("\n".join(lines))))
    return report_path
