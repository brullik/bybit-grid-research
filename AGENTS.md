Never edit pm_acceptance/** in an implementation PR.
Never edit .github/workflows/pm-acceptance.yml in an implementation PR.
Never edit docs/frozen_contracts/**, AGENTS.md, .github/CODEOWNERS, scripts/check_protected_paths.py, or scripts/check_task_scope.py in an implementation PR.
Never delete, weaken, skip, xfail, parameter-pad, rename, or replace a frozen acceptance test.
Never use pytest.raises(Exception) or pytest.raises(BaseException).
Never catch Exception or BaseException in tests unless a frozen PM contract explicitly requires it.
Never use a passing test whose only assertion checks a label, test ID, type name, nonempty list, generic object existence, or missing-path failure unrelated to the behavior name.
Implementation PRs may change only paths allowed by pm_acceptance/active_task.json.
Implementation authority is offline-only by default: no network, private API, credentials, live execution, Telegram, order, position, wallet, or native-grid mutation. Path scope alone never authorizes these actions. They remain forbidden unless a base-controlled staged-execution contract explicitly authorizes the current stage and freezes fail-closed risk, credential, approval, kill-switch, and rollback gates.
Never place credentials in repository files, issues, pull requests, comments, logs, tests, fixtures, reports, or agent context; approved runtime secret stores are the only credential boundary.
Withdrawal and ordinary-order mutation are never authorized in V1; execution scope is limited to the native Bybit grid lifecycle after its future staged gates exist.
Run the exact commands from the active task and keep the PR draft until all required acceptance checks and lifecycle evidence pass.
Under standing owner authorization, the autonomous maintainer may mark its own non-probe PR ready and merge it only when the expected head SHA is unchanged, every required check is successful, the exact scope is verified, and no review thread is unresolved. Mandatory RED probes must always be closed unmerged. Never bypass a required check, force a merge, or merge an unknown, pending, stale, or failing status.
If a frozen acceptance test appears wrong, report it; do not change it.
Never edit dependency/config files pyproject.toml, requirements.txt, requirements-dev.txt, requirements/*.txt, uv.lock, poetry.lock, Pipfile, or Pipfile.lock in any PR for control-plane v1.
