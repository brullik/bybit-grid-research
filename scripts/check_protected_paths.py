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
    ".github/workflows/pm-acceptance.yml",
    "scripts/check_protected_paths.py",
    "scripts/check_task_scope.py",
})
_PROTECTED_PREFIXES = ("pm_acceptance/", "docs/frozen_contracts/")
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
    """Return stable errors for unsafe or protected changed paths."""
    errors = _validate_changed_paths(changed_paths)
    for path in changed_paths if type(changed_paths) is tuple else ():
        if isinstance(path, str) and _path_error(path) is None:
            if path in _PROTECTED_EXACT or any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
                errors.append(f"protected_path_changed:{path}")
    return tuple(sorted(errors))


def _changed_paths(base_sha: str, head_sha: str) -> tuple[str, ...]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base_sha}...{head_sha}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git_diff_failed")
    text = proc.stdout.decode("utf-8", "strict")
    if proc.stderr:
        proc.stderr.decode("utf-8", "strict")
    return tuple(line for line in text.split("\n") if line)


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
        changed = _changed_paths(args.base_sha, args.head_sha)
        return _emit(len(changed), protected_path_errors(changed))
    except (RuntimeError, UnicodeDecodeError) as exc:
        return _emit(0, (str(exc),))


if __name__ == "__main__":
    sys.exit(main())
