#!/usr/bin/env python3
"""Validate changed paths against the PM active-task scope."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.check_protected_paths import _path_error, _SHA_RE

_KEYS = ("allowed_paths", "forbidden_paths", "required_commands", "required_paths", "schema", "task_id")
_SCHEMA = "pm_active_task_v1"
_CONTROL_PLANE_ALLOWED = frozenset({
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/workflows/pm-acceptance.yml",
    "scripts/check_protected_paths.py",
    "scripts/check_task_scope.py",
    "pm_acceptance/README.md",
    "pm_acceptance/active_task.json",
    "pm_acceptance/conftest.py",
    "pm_acceptance/test_control_plane_self.py",
    "docs/frozen_contracts/control_plane_v1.md",
})


@dataclass(frozen=True)
class ActiveTask:
    schema: str
    task_id: str
    allowed_paths: tuple[str, ...]
    required_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    required_commands: tuple[str, ...]


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid_json_constant:{value}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate_json_key:{key}")
        out[key] = value
    return out


def _reject_float(value: str) -> None:
    raise ValueError(f"float_token:{value}")


def _validate_rule(rule: str) -> None:
    if not isinstance(rule, str) or _path_error(rule[:-3] if rule.endswith("/**") else rule) is not None:
        raise ValueError(f"unsafe_rule:{rule}")
    body = rule[:-3] if rule.endswith("/**") else rule
    if not body or "*" in body or "?" in body or "[" in body or "]" in body:
        raise ValueError(f"invalid_rule:{rule}")


def _strings(name: str, value: Any, *, paths: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"not_list:{name}")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"non_string:{name}")
        if item in seen:
            raise ValueError(f"duplicate_entry:{name}:{item}")
        if paths:
            _validate_rule(item)
        seen.add(item)
        out.append(item)
    return tuple(out)


def parse_active_task_bytes(data: bytes) -> ActiveTask:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom")
    text = data.decode("utf-8", "strict")
    obj = json.loads(text, object_pairs_hook=_pairs_hook, parse_float=_reject_float, parse_constant=_reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("task_not_object")
    if set(obj) != set(_KEYS):
        unknown = sorted(set(obj) - set(_KEYS))
        missing = sorted(set(_KEYS) - set(obj))
        raise ValueError(f"invalid_task_keys:missing={','.join(missing)}:unknown={','.join(unknown)}")
    if obj["schema"] != _SCHEMA or not isinstance(obj["schema"], str):
        raise ValueError("invalid_schema")
    if not isinstance(obj["task_id"], str) or not obj["task_id"]:
        raise ValueError("invalid_task_id")
    task = ActiveTask(
        schema=obj["schema"], task_id=obj["task_id"],
        allowed_paths=_strings("allowed_paths", obj["allowed_paths"], paths=True),
        required_paths=_strings("required_paths", obj["required_paths"], paths=True),
        forbidden_paths=_strings("forbidden_paths", obj["forbidden_paths"], paths=True),
        required_commands=_strings("required_commands", obj["required_commands"], paths=False),
    )
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if data != canonical:
        raise ValueError("noncanonical_task_bytes")
    return task


def _matches(rule: str, path: str) -> bool:
    if rule.endswith("/**"):
        return path.startswith(rule[:-2])
    return path == rule


def task_scope_errors(task: ActiveTask, changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    if type(changed_paths) is not tuple:
        return ("changed_paths_not_tuple",)
    seen: set[str] = set()
    for path in changed_paths:
        err = _path_error(path)
        if err:
            errors.append(err)
        elif path in seen:
            errors.append(f"duplicate_path:{path}")
        seen.add(path)
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    if task.task_id == "NO_ACTIVE_IMPLEMENTATION":
        for path in valid:
            if path not in _CONTROL_PLANE_ALLOWED:
                errors.append(f"no_active_implementation_task:{path}")
    else:
        for path in valid:
            if not any(_matches(rule, path) for rule in task.allowed_paths):
                errors.append(f"out_of_scope_path:{path}")
    for path in valid:
        for rule in task.forbidden_paths:
            if _matches(rule, path):
                errors.append(f"forbidden_path_changed:{path}")
                break
    for rule in task.required_paths:
        if not any(_matches(rule, path) for path in valid):
            errors.append(f"required_path_missing:{rule}")
    return tuple(sorted(errors))


def _changed_paths(base_sha: str, head_sha: str) -> tuple[str, ...]:
    proc = subprocess.run(["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base_sha}...{head_sha}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RuntimeError("git_diff_failed")
    if proc.stderr:
        proc.stderr.decode("utf-8", "strict")
    return tuple(line for line in proc.stdout.decode("utf-8", "strict").split("\n") if line)


def _emit(changed_count: int, errors: tuple[str, ...]) -> int:
    print(json.dumps({"changed_count": changed_count, "errors": list(errors), "ok": not errors}, sort_keys=True, separators=(",", ":")))
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args(argv)
    errors: list[str] = []
    if args.task_file != "pm_acceptance/active_task.json":
        errors.append("invalid_task_file")
    if not _SHA_RE.fullmatch(args.base_sha):
        errors.append("invalid_base_sha")
    if not _SHA_RE.fullmatch(args.head_sha):
        errors.append("invalid_head_sha")
    if errors:
        return _emit(0, tuple(sorted(errors)))
    try:
        task = parse_active_task_bytes(Path(args.task_file).read_bytes())
        changed = _changed_paths(args.base_sha, args.head_sha)
        return _emit(len(changed), task_scope_errors(task, changed))
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as exc:
        return _emit(0, (str(exc),))


if __name__ == "__main__":
    sys.exit(main())
