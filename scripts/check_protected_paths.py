#!/usr/bin/env python3
"""Reject implementation PR changes to PM-controlled paths."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_PROTECTED_EXACT = frozenset({
    "AGENTS.md",
    ".github/CODEOWNERS",
    "scripts/check_protected_paths.py",
    "scripts/check_task_scope.py",
    "scripts/check_numeric_environment.py",
    "scripts/check_no_live_execution.py",
    "conftest.py",
    "pytest.ini",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "noxfile.py",
    "sitecustomize.py",
    "usercustomize.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
})
_PROTECTED_PREFIXES = (".github/workflows/", ".github/actions/", "pm_acceptance/", "docs/frozen_contracts/", "requirements/")
_UNSUPPORTED_MODES = {"120000", "160000"}
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _path_error(path: object) -> str | None:
    if not isinstance(path, str):
        return f"unsafe_path:{path!r}"
    if not path:
        return "unsafe_path:"
    if path.startswith("/") or path.startswith("//") or _DRIVE_RE.match(path):
        return f"unsafe_path:{path}"
    if "\\" in path or any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return f"unsafe_path:{path}"
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return f"unsafe_path:{path}"
    return None


def _validate_changed_paths(changed_paths: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    if type(changed_paths) is not tuple:
        return ["changed_paths_not_tuple"]
    seen: set[str] = set()
    for path in changed_paths:
        err = _path_error(path)
        if err is not None:
            errors.append(err)
            continue
        if path in seen:
            errors.append(f"duplicate_path:{path}")
        seen.add(path)
    return errors


def protected_path_errors(changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    errors = _validate_changed_paths(changed_paths)
    for path in changed_paths if type(changed_paths) is tuple else ():
        if isinstance(path, str) and _path_error(path) is None:
            if path in _PROTECTED_EXACT or any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
                errors.append(f"protected_path_changed:{path}")
    return tuple(sorted(errors))


def parse_git_diff_raw_z(data: bytes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fields = data.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    paths: list[str] = []
    errors: list[str] = []
    i = 0
    while i < len(fields):
        header = fields[i].decode("ascii", "strict")
        i += 1
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(":"):
            errors.append("unsupported_git_diff_entry")
            break
        old_mode = parts[0][1:]
        new_mode = parts[1]
        status = parts[4]
        if status.startswith("R") or status.startswith("C"):
            errors.append(f"unsupported_git_diff_status:{status}")
        if old_mode in _UNSUPPORTED_MODES:
            errors.append(f"unsupported_git_diff_mode:{old_mode}")
        if new_mode in _UNSUPPORTED_MODES:
            errors.append(f"unsupported_git_diff_mode:{new_mode}")
        if i >= len(fields):
            errors.append("unsupported_git_diff_entry")
            break
        try:
            path = fields[i].decode("utf-8", "strict")
        except UnicodeDecodeError:
            errors.append("invalid_utf8_path")
            i += 1
            continue
        i += 1
        paths.append(path)
    return tuple(paths), tuple(sorted(errors))


def changed_paths_from_git(base_sha: str, head_sha: str) -> tuple[str, ...]:
    proc = subprocess.run(
        ["git", "diff", "--raw", "-z", "--no-renames", "--diff-filter=ACDMRTUXB", f"{base_sha}...{head_sha}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git_diff_failed")
    if proc.stderr:
        proc.stderr.decode("utf-8", "strict")
    paths, errors = parse_git_diff_raw_z(proc.stdout)
    if errors:
        raise RuntimeError(errors[0])
    return paths


def _emit(changed_count: int, errors: tuple[str, ...]) -> int:
    print(json.dumps({"changed_count": changed_count, "errors": list(errors), "ok": not errors}, sort_keys=True, separators=(",", ":")))
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args(argv)
    errors: list[str] = []
    if not _SHA_RE.fullmatch(args.base_sha):
        errors.append("invalid_base_sha")
    if not _SHA_RE.fullmatch(args.head_sha):
        errors.append("invalid_head_sha")
    if errors:
        return _emit(0, tuple(sorted(errors)))
    try:
        changed = changed_paths_from_git(args.base_sha, args.head_sha)
        return _emit(len(changed), protected_path_errors(changed))
    except (RuntimeError, UnicodeDecodeError) as exc:
        return _emit(0, (str(exc),))


if __name__ == "__main__":
    sys.exit(main())
