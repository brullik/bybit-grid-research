from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_protected_paths import parse_git_diff_raw_z, protected_path_errors, changed_paths_from_git
from scripts.check_task_scope import ActiveTask, acceptance_plan_for_mode, classify_pr_mode, parse_active_task_bytes, task_scope_errors

CANONICAL = json.dumps({
    "schema": "pm_active_task_v1",
    "task_id": "NO_ACTIVE_IMPLEMENTATION",
    "allowed_paths": [],
    "required_paths": [],
    "forbidden_paths": [
        "AGENTS.md", ".github/CODEOWNERS", ".github/workflows/**", ".github/actions/**",
        "pm_acceptance/**", "docs/frozen_contracts/**", "scripts/check_protected_paths.py",
        "scripts/check_task_scope.py", "scripts/check_numeric_environment.py", "scripts/check_no_live_execution.py",
        "conftest.py", "pytest.ini", "setup.py", "setup.cfg", "tox.ini", "noxfile.py",
        "sitecustomize.py", "usercustomize.py", "src/sitecustomize.py", "src/usercustomize.py",
        "pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements/*.txt",
        "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock",
    ],
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


def test_control_character_path_rejected():
    assert protected_path_errors(("src/bad\nname.py",)) == ("unsafe_path:src/bad\nname.py",)


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
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/x.py",), (), ())
    assert task_scope_errors(task, ("src/x.py",)) == ()


def test_active_task_accepts_allowed_prefix():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ())
    assert task_scope_errors(task, ("src/pkg/x.py",)) == ()


def test_active_task_rejects_out_of_scope_file():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ())
    assert task_scope_errors(task, ("docs/x.md",)) == ("out_of_scope_path:docs/x.md",)


def test_forbidden_rule_wins_over_allowed_rule():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ("src/secret.py",))
    assert task_scope_errors(task, ("src/secret.py",)) == ("forbidden_path_changed:src/secret.py",)


def test_missing_required_path_rejected():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), ("src/required.py",), ())
    assert task_scope_errors(task, ("src/other.py",)) == ("required_path_missing:src/required.py",)


def test_json_lists_are_converted_to_immutable_tuples():
    task = parse_active_task_bytes(CANONICAL)
    assert isinstance(task.allowed_paths, tuple)
    assert isinstance(task.required_paths, tuple)
    assert isinstance(task.forbidden_paths, tuple)


def test_dependency_paths_are_protected_with_exact_errors():
    assert protected_path_errors(("pyproject.toml",)) == ("protected_path_changed:pyproject.toml",)
    assert protected_path_errors(("uv.lock",)) == ("protected_path_changed:uv.lock",)
    assert protected_path_errors(("requirements/base.txt",)) == ("protected_path_changed:requirements/base.txt",)


def test_src_customization_paths_are_protected_with_exact_errors():
    assert protected_path_errors(("src/sitecustomize.py",)) == ("protected_path_changed:src/sitecustomize.py",)
    assert protected_path_errors(("src/usercustomize.py",)) == ("protected_path_changed:src/usercustomize.py",)


def test_no_required_commands_or_shell_command_field_exists():
    task = parse_active_task_bytes(CANONICAL)
    assert not hasattr(task, "required_commands")
    data = dict(json.loads(CANONICAL))
    data["required_commands"] = []
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_task_keys:missing=:unknown=required_commands$"):
        parse_active_task_bytes(raw)


def test_output_mode_for_three_valid_modes():
    assert classify_pr_mode("codex", (), ("src/x.py",))[0] == "implementation"
    assert classify_pr_mode("brullik", ("pm-task-definition",), ("pm_acceptance/test_x.py",))[0] == "pm-task-definition"
    assert classify_pr_mode("brullik", ("pm-control-plane",), ("AGENTS.md",))[0] == "pm-control-plane"


def test_mode_acceptance_plan_selection():
    assert acceptance_plan_for_mode("implementation") == ("base-isolated-acceptance",)
    assert acceptance_plan_for_mode("pm-control-plane") == ("base-isolated-acceptance", "head-control-plane-self-tests")
    assert acceptance_plan_for_mode("pm-task-definition") == ("base-control-plane-self-tests", "head-task-definition-collect-only")


def test_pr_mode_labels_and_scope_fail_closed():
    assert classify_pr_mode("alice", ("pm-task-definition",), ("pm_acceptance/x.py",))[1] == ("wrong_author:alice",)
    assert classify_pr_mode("brullik", ("pm-task-definition", "pm-control-plane"), ("pm_acceptance/x.py",))[1] == ("multiple_mode_labels",)
    assert classify_pr_mode("brullik", ("pm-unknown",), ("src/x.py",))[1] == ("unknown_mode_label:pm-unknown",)
    assert classify_pr_mode("brullik", (), ("pm_acceptance/x.py",))[1] == ("missing_required_mode_label:pm_acceptance/x.py",)
    assert classify_pr_mode("brullik", ("pm-task-definition",), ("src/x.py",))[1] == (
        "pm_task_definition_out_of_scope:src/x.py",
        "production_path_forbidden_in_pm_mode:src/x.py",
    )
    assert classify_pr_mode("brullik", ("pm-control-plane",), ("AGENTS.md",))[1] == ()


def test_parse_raw_diff_rejects_symlink_and_submodule_modes():
    symlink = b":000000 120000 0000000 1111111 A\0link\0"
    submodule = b":000000 160000 0000000 1111111 A\0module\0"
    assert parse_git_diff_raw_z(symlink)[1] == ("unsupported_git_diff_mode:120000",)
    assert parse_git_diff_raw_z(submodule)[1] == ("unsupported_git_diff_mode:160000",)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


def test_multi_commit_diff_and_rename_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "AGENTS.md").write_text("rules\n")
    (repo / "plain.txt").write_text("plain\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "head")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "one")
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "two")
    head = _git(repo, "rev-parse", "HEAD")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert changed_paths_from_git(base, head) == ("a.txt", "b.txt")
        _git(repo, "mv", "AGENTS.md", "moved.txt")
        _git(repo, "mv", "plain.txt", "pm_acceptance_file.txt")
        _git(repo, "commit", "-q", "-m", "renames")
        renamed = changed_paths_from_git(head, _git(repo, "rev-parse", "HEAD"))
    finally:
        os.chdir(old_cwd)
    assert renamed == ("AGENTS.md", "moved.txt", "plain.txt", "pm_acceptance_file.txt")
    assert "protected_path_changed:AGENTS.md" in protected_path_errors(renamed)


def test_protected_deletion_is_reported_by_raw_diff(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "AGENTS.md").write_text("rules\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "AGENTS.md").unlink()
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-q", "-m", "delete")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        changed = changed_paths_from_git(base, _git(repo, "rev-parse", "HEAD"))
    finally:
        os.chdir(old_cwd)
    assert changed == ("AGENTS.md",)
    assert protected_path_errors(changed) == ("protected_path_changed:AGENTS.md",)


def test_isolated_acceptance_ignores_malicious_root_conftest(tmp_path: Path):
    head = tmp_path / "head"
    acc = tmp_path / "pm_acceptance"
    head.mkdir()
    acc.mkdir()
    (head / "conftest.py").write_text("import pytest\ndef pytest_collection_modifyitems(items):\n    pytest.skip('malicious skip')\n")
    (acc / "test_acceptance.py").write_text("def test_acceptance_runs():\n    assert True\n")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(acc), "-q", f"--confcutdir={acc}", "-c", os.devnull],
        cwd=head,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0
    assert "1 passed" in result.stdout
    assert "malicious skip" not in result.stdout + result.stderr


def _stage_isolated_tree(temp: Path) -> None:
    scripts = temp / "scripts"
    pm = temp / "pm_acceptance"
    scripts.mkdir(parents=True)
    pm.mkdir()
    (scripts / "__init__.py").write_text("")
    repo_root = Path(__file__).resolve().parents[1]
    (scripts / "check_protected_paths.py").write_text((repo_root / "scripts/check_protected_paths.py").read_text())
    (scripts / "check_task_scope.py").write_text((repo_root / "scripts/check_task_scope.py").read_text())
    (temp / "pytest.ini").write_text("[pytest]\n")


def test_exact_base_harness_temp_import_shape_runs_one_test(tmp_path: Path):
    temp = tmp_path / "temp"
    temp.mkdir()
    _stage_isolated_tree(temp)
    (temp / "pm_acceptance/test_acceptance.py").write_text(
        "from scripts.check_protected_paths import protected_path_errors\n"
        "from scripts.check_task_scope import parse_active_task_bytes\n"
        "def test_acceptance_imports():\n"
        "    assert protected_path_errors(('src/x.py',)) == ()\n"
        "    assert parse_active_task_bytes.__name__ == 'parse_active_task_bytes'\n"
    )
    env = dict(os.environ, PYTHONPATH=str(temp), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "pm_acceptance", "-q", "-c", str(temp / "pytest.ini"), f"--confcutdir={temp / 'pm_acceptance'}"],
        cwd=temp, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert result.returncode == 0
    assert "1 passed" in result.stdout


def test_head_task_definition_collection_valid_and_syntax_error(tmp_path: Path):
    good = tmp_path / "good"
    good.mkdir()
    _stage_isolated_tree(good)
    (good / "pm_acceptance/test_acceptance.py").write_text("def test_collectable():\n    assert False\n")
    env = dict(os.environ, PYTHONPATH=str(good), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    compile_good = subprocess.run([sys.executable, "-m", "compileall", "-q", str(good)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    collect_good = subprocess.run(
        [sys.executable, "-m", "pytest", str(good), "--collect-only", "-q", "-c", str(good / "pytest.ini"), f"--confcutdir={good / 'pm_acceptance'}"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert compile_good.returncode == 0
    assert collect_good.returncode == 0
    assert "test_acceptance.py::test_collectable" in collect_good.stdout
    assert "failed" not in collect_good.stdout.lower()

    bad = tmp_path / "bad"
    bad.mkdir()
    _stage_isolated_tree(bad)
    (bad / "pm_acceptance/test_acceptance.py").write_text("def broken(:\n")
    env_bad = dict(os.environ, PYTHONPATH=str(bad), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    compile_bad = subprocess.run([sys.executable, "-m", "compileall", "-q", str(bad)], env=env_bad, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert compile_bad.returncode != 0
