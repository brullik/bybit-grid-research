Never edit pm_acceptance/** in an implementation PR.
Never edit .github/workflows/pm-acceptance.yml in an implementation PR.
Never edit docs/frozen_contracts/**, AGENTS.md, .github/CODEOWNERS, scripts/check_protected_paths.py, or scripts/check_task_scope.py in an implementation PR.
Never delete, weaken, skip, xfail, parameter-pad, rename, or replace a frozen acceptance test.
Never use pytest.raises(Exception) or pytest.raises(BaseException).
Never catch Exception or BaseException in tests unless a frozen PM contract explicitly requires it.
Never use a passing test whose only assertion checks a label, test ID, type name, nonempty list, generic object existence, or missing-path failure unrelated to the behavior name.
Implementation PRs may change only paths allowed by pm_acceptance/active_task.json.
No network, private API, credentials, live execution, Telegram, order, position, wallet, or native-grid mutation.
Run the exact commands from the active task and keep the PR draft until PM approval.
Do not merge your own PR.
If a frozen acceptance test appears wrong, report it; do not change it.
Never edit dependency/config files pyproject.toml, requirements.txt, requirements-dev.txt, requirements/*.txt, uv.lock, poetry.lock, Pipfile, or Pipfile.lock in any PR for control-plane v1.
BOOTSTRAP ATTACK PROBE V2 — this protected-file change must be rejected.
