from __future__ import annotations

import json

import pytest

from scripts.check_protected_paths import protected_path_errors
from scripts.check_task_scope import ActiveTask, parse_active_task_bytes, task_scope_errors

CANONICAL = json.dumps({
    "schema": "pm_active_task_v1",
    "task_id": "NO_ACTIVE_IMPLEMENTATION",
    "allowed_paths": [],
    "required_paths": [],
    "forbidden_paths": [
        "AGENTS.md",
        ".github/CODEOWNERS",
        ".github/workflows/pm-acceptance.yml",
        "pm_acceptance/**",
        "docs/frozen_contracts/**",
        "scripts/check_protected_paths.py",
        "scripts/check_task_scope.py",
    ],
    "required_commands": [],
}, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_safe_unprotected_source_file_accepted():
    assert protected_path_errors(("src/example.py",)) == ()


def test_exact_protected_file_rejected():
    assert protected_path_errors(("AGENTS.md",)) == ("protected_path_changed:AGENTS.md",)


def test_nested_pm_acceptance_rejected():
    assert protected_path_errors(("pm_acceptance/test_x.py",)) == ("protected_path_changed:pm_acceptance/test_x.py",)


def test_nested_docs_frozen_contracts_rejected():
    assert protected_path_errors(("docs/frozen_contracts/x.md",)) == ("protected_path_changed:docs/frozen_contracts/x.md",)


def test_backslash_path_rejected():
    assert protected_path_errors((r"src\x.py",)) == (r"unsafe_path:src\x.py",)


def test_absolute_path_rejected():
    assert protected_path_errors(("/src/x.py",)) == ("unsafe_path:/src/x.py",)


def test_dotdot_component_rejected():
    assert protected_path_errors(("src/../x.py",)) == ("unsafe_path:src/../x.py",)


def test_duplicate_changed_path_rejected():
    assert protected_path_errors(("src/x.py", "src/x.py")) == ("duplicate_path:src/x.py",)


def test_valid_canonical_inactive_task_parses():
    task = parse_active_task_bytes(CANONICAL)
    assert task.task_id == "NO_ACTIVE_IMPLEMENTATION"


def test_duplicate_json_key_rejected():
    with pytest.raises(ValueError, match="^duplicate_json_key:schema$"):
        parse_active_task_bytes(b'{"schema":"x","schema":"x"}\n')


def test_float_token_rejected():
    with pytest.raises(ValueError, match="^float_token:1.0$"):
        parse_active_task_bytes(b'{"allowed_paths":1.0}\n')


def test_unknown_task_key_rejected():
    data = dict(json.loads(CANONICAL))
    data["extra"] = "x"
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_task_keys:missing=:unknown=extra$"):
        parse_active_task_bytes(raw)


def test_noncanonical_task_bytes_rejected():
    with pytest.raises(ValueError, match="^noncanonical_task_bytes$"):
        parse_active_task_bytes(json.dumps(json.loads(CANONICAL), indent=2).encode() + b"\n")


def test_inactive_task_rejects_implementation_source_change():
    task = parse_active_task_bytes(CANONICAL)
    assert task_scope_errors(task, ("src/x.py",)) == ("no_active_implementation_task:src/x.py",)


def test_active_task_accepts_allowed_exact_file():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/x.py",), (), (), ())
    assert task_scope_errors(task, ("src/x.py",)) == ()


def test_active_task_accepts_allowed_prefix():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), (), ())
    assert task_scope_errors(task, ("src/pkg/x.py",)) == ()


def test_active_task_rejects_out_of_scope_file():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), (), ())
    assert task_scope_errors(task, ("docs/x.md",)) == ("out_of_scope_path:docs/x.md",)


def test_forbidden_rule_wins_over_allowed_rule():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ("src/secret.py",), ())
    assert task_scope_errors(task, ("src/secret.py",)) == ("forbidden_path_changed:src/secret.py",)


def test_missing_required_path_rejected():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), ("src/required.py",), (), ())
    assert task_scope_errors(task, ("src/other.py",)) == ("required_path_missing:src/required.py",)


def test_json_lists_are_converted_to_immutable_tuples():
    task = parse_active_task_bytes(CANONICAL)
    assert isinstance(task.allowed_paths, tuple)
    assert isinstance(task.required_paths, tuple)
    assert isinstance(task.forbidden_paths, tuple)
    assert isinstance(task.required_commands, tuple)
