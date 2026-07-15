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
2. The PM merges the valid `pm-task-definition` PR.
3. The PM opens a deliberately empty or no-production-change implementation probe PR.
4. The PM confirms the new base-controlled acceptance tests fail on that red probe.
5. The PM closes the probe without merge.
6. Only after recorded red-probe evidence exists may Codex start the implementation task and open a separate implementation PR from `main`.
7. The PM Acceptance workflow evaluates PR production code against base-controlled acceptance tests and base-controlled checker scripts.
8. The PM reviews the draft PR. The implementation PR remains draft until PM approval.
9. After the implementation is merged, the PM closes the task in a separate `pm-task-definition` PR. A close transition changes only `pm_acceptance/active_task.json`, sets `task_id` to `NO_ACTIVE_IMPLEMENTATION`, and leaves `allowed_paths` and `required_paths` empty. Frozen task tests and contract documents remain in history and are not edited by the close PR.

No implementation PR may merge while `NO_ACTIVE_IMPLEMENTATION` is active, because production path changes fail task-scope validation.

The active-task schema intentionally has no `required_commands` field. Control-plane v1 uses fixed base-controlled workflow commands and never executes arbitrary shell strings from JSON.

For an opening transition, the base-owned checker reads the head task bytes with `git show`, requires canonical JSON, a new safe lowercase task slug that has not appeared in the base task tree, nonempty allowed and required path lists, coverage of every required rule by an allowed rule, no required rule blocked by the task's own forbidden rules, the mandatory protected-path deny rules, matching task IDs in task-test and contract paths, at least one changed `test_*.py`, and strict UTF-8 head bytes for every changed task test or contract. The workflow then compiles and collects only `pm_acceptance/tasks/<task_id>` from the head; it never executes the intentionally red tests in the task-definition PR.

## Required branch-protection checks

The repository owner must manually enable these required checks on `main`:

- `PM Acceptance / protected-paths`
- `PM Acceptance / acceptance (3.12)`
- `PM Acceptance / acceptance (3.14)`

## Required branch-protection settings

The owner must manually require:

- pull request before merge
- CODEOWNER approval only after review identity is operationally satisfiable
- conversation resolution
- no force pushes
- no bypass

GitHub does not permit a PR author to approve their own PR. Before enabling required CODEOWNER approval, the repository must choose one of these review-identity models: Codex or another bot creates implementation PRs and `brullik` reviews them, or a second trusted reviewer/team is added as an owner.

These settings are not created automatically by this repository change and must be configured in the repository hosting settings.
