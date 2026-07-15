# Control Plane v1: Immutable PM Acceptance

## Why acceptance tests are base-controlled

PM acceptance tests define the behavior that an implementation PR must satisfy. The workflow checks out base and head separately, copies base `pm_acceptance/` to runner temp, disables pytest plugin autoloading, uses a base-owned pytest config, and runs acceptance from outside the PR checkout. This prevents a PR's tests, root `conftest.py`, pytest configuration, or auto-loaded plugins from weakening, deleting, skipping, xfail-padding, renaming, or replacing the acceptance criteria it must satisfy.

## PR modes

Every PR is classified as exactly one mode:

- `implementation`: no PM mode label. Protected paths are forbidden and the exact production scope comes from base `pm_acceptance/active_task.json`.
- `pm-task-definition`: requires author `brullik` and exact label `pm-task-definition`. It may change only `pm_acceptance/active_task.json`, Python files below `pm_acceptance/tasks/<task_id>/`, and `docs/frozen_contracts/tasks/<task_id>.md`. The task ID in every changed path must equal the canonical task ID in the head task file. Task-local `conftest.py` files are forbidden. No `src/**`, ordinary `tests/**`, workflow, checker, dependency, or control-plane change is allowed.
- `pm-control-plane`: requires author `brullik` and exact label `pm-control-plane`. Changes are restricted to the frozen control-plane allowlist; no `src/**`, ordinary `tests/**`, or production code is allowed.

The workflow fails closed on multiple PM mode labels, unknown `pm-*` mode labels, missing required labels for control-plane paths, wrong author, and mixed control-plane/production changes.

## Protected infrastructure paths

Implementation PRs cannot edit:

- `.github/workflows/**`
- `.github/actions/**`
- `AGENTS.md`
- `.github/CODEOWNERS`
- `pm_acceptance/**`
- `docs/frozen_contracts/**`
- `scripts/check_protected_paths.py`
- `scripts/check_task_scope.py`
- `scripts/check_numeric_environment.py`
- `scripts/check_no_live_execution.py`
- root `conftest.py`
- `pytest.ini`, `setup.py`, `setup.cfg`, `tox.ini`, `noxfile.py`
- `sitecustomize.py`, `usercustomize.py`, `sitecustomize/**`, `usercustomize/**`
- `src/sitecustomize.py`, `src/usercustomize.py`, `src/sitecustomize/**`, `src/usercustomize/**`
- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `requirements/*.txt`
- `uv.lock`, `poetry.lock`, `Pipfile`, `Pipfile.lock`

Control-plane v1 does not support dependency changes. Implementation PRs, PM task-definition PRs, and PM control-plane PRs must all reject changes to these dependency and configuration paths.

## Active-task lifecycle

1. The PM first opens a `pm-task-definition` PR on `main` that changes the canonical `pm_acceptance/active_task.json`, adds at least one frozen test below `pm_acceptance/tasks/<task_id>/`, and may add the matching `docs/frozen_contracts/tasks/<task_id>.md` contract.
2. After every required check succeeds, the authorized autonomous maintainer may mark the valid non-probe PR ready and merge it at its unchanged expected head SHA.
3. The PM opens a deliberately empty or no-production-change implementation probe PR from a `probe/` branch.
4. The PM confirms the new base-controlled acceptance tests fail for the exact expected behavioral reason on that red probe.
5. The PM closes the probe without merge. A mandatory RED probe is never mergeable under the standing authorization.
6. Only after recorded red-probe evidence exists may Codex start the implementation task and open a separate implementation PR from fresh `main`.
7. The PM Acceptance workflow evaluates PR production code against base-controlled acceptance tests and base-controlled checker scripts.
8. The autonomous maintainer independently reviews the draft PR, verifies exact scope and unresolved-thread state, and keeps it draft until all required checks and lifecycle evidence pass. Standing owner authorization satisfies PM approval only when those objective conditions are met.
9. After the implementation is merged, the PM closes the task in a separate `pm-task-definition` PR. A close transition changes only `pm_acceptance/active_task.json`, sets `task_id` to `NO_ACTIVE_IMPLEMENTATION`, and leaves `allowed_paths` and `required_paths` empty. Frozen task tests and contract documents remain in history and are not edited by the close PR.

No implementation PR may merge while `NO_ACTIVE_IMPLEMENTATION` is active, because production path changes fail task-scope validation.

For every non-probe PR, autonomous merge additionally requires the expected head SHA to remain unchanged, every required status to be successful, exact scope verification, and zero unresolved review threads. Unknown, pending, stale, skipped, cancelled, or failing status is not approval. Required checks may never be bypassed, and force merge is forbidden.

## Staged execution authority

Implementation authority remains offline-only by default. An active task's path allowlist never by itself authorizes network access, credentials, private Bybit API calls, Telegram, orders, positions, wallet access, or native-grid mutation. Those capabilities remain forbidden until a later base-controlled control-plane contract explicitly defines the current execution stage and freezes its risk, credential, human-approval, kill-switch, rollback, and audit gates. Production secrets may exist only in an approved runtime secret store and never in repository or agent-visible content.

Withdrawal and ordinary-order mutation are never authorized in V1. Any later execution authority is limited to the native Bybit grid lifecycle and cannot be inferred from a production path allowlist.

This governance revision does not enable private or live execution. The existing no-live source audit remains mandatory and unchanged.

## Aggregate head status

The base-owned `pull_request_target` workflow publishes a `pm-acceptance` commit status on the exact pull-request head SHA. A minimal pending job publishes the Actions run URL before acceptance. A final `always()` job reports success only when the pending publication, protected-path job, and complete acceptance matrix all succeeded and the PR is Ready, owner-authored, and not on a `probe/` branch. Every other completed result publishes failure or error. The status remains pending only if the finalizer cannot publish its result.

Only the two status publisher jobs receive `statuses: write`. They do not check out or execute pull-request head code. The protected-path and acceptance jobs retain read-only permissions. This makes the run URL and aggregate result discoverable from the head SHA without transferring a user-supplied Actions URL and without exposing a write token to untrusted head code.

The active-task schema intentionally has no `required_commands` field. Control-plane v1 uses fixed base-controlled workflow commands and never executes arbitrary shell strings from JSON.

For an opening transition, the base-owned checker reads the head task bytes with `git show`, requires canonical JSON, a new safe lowercase task slug that has not appeared in the base task tree, nonempty allowed and required path lists, coverage of every required rule by an allowed rule, no required rule blocked by the task's own forbidden rules, the mandatory protected-path deny rules, matching task IDs in task-test and contract paths, at least one changed `test_*.py`, and strict UTF-8 head bytes for every changed task test or contract. The workflow then compiles and collects only `pm_acceptance/tasks/<task_id>` from the head; it never executes the intentionally red tests in the task-definition PR.

## Required branch-protection checks

The repository owner must manually enable these required checks on `main`:

- `pm-acceptance`
- `PM Acceptance / protected-paths`
- `PM Acceptance / acceptance (3.12)`
- `PM Acceptance / acceptance (3.14)`

## Required branch-protection settings

The owner must manually require:

- pull request before merge
- repository auto-merge enabled for green non-probe pull requests
- CODEOWNER approval only after review identity is operationally satisfiable; otherwise objective required checks and conversation resolution remain the merge gate
- conversation resolution
- no force pushes
- no bypass

GitHub does not permit a PR author to approve their own PR. Required CODEOWNER approval therefore remains disabled unless a second trusted reviewer or bot identity is added. Standing owner authorization permits autonomous merge only through the objective conditions in this contract; it is not a substitute for a GitHub approval when branch protection requires one.

These settings are not created automatically by this repository change and must be configured in the repository hosting settings.
