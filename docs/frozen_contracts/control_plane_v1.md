# Control Plane v1: Immutable PM Acceptance

## Why acceptance tests are base-controlled

PM acceptance tests define the behavior that an implementation PR must satisfy. The workflow checks out base and head separately, copies base `pm_acceptance/` to runner temp, disables pytest plugin autoloading, uses a base-owned pytest config, and runs acceptance from outside the PR checkout. This prevents a PR's tests, root `conftest.py`, pytest configuration, or auto-loaded plugins from weakening, deleting, skipping, xfail-padding, renaming, or replacing the acceptance criteria it must satisfy.

## PR modes

Every PR is classified as exactly one mode:

- `implementation`: no PM mode label. Protected paths are forbidden and the exact production scope comes from base `pm_acceptance/active_task.json`.
- `pm-task-definition`: requires author `brullik` and exact label `pm-task-definition`. Changes are restricted to `pm_acceptance/**` and `docs/frozen_contracts/**`; no `src/**`, `tests/**`, `pyproject.toml`, workflow, checker, or ordinary production change is allowed.
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
- `sitecustomize.py`, `usercustomize.py`

Dependency and configuration files such as `pyproject.toml` and lockfiles may change only through an explicit PM task-definition or PM control-plane scope, never as an incidental implementation change.

## Active-task lifecycle

1. The PM first opens and merges a `pm-task-definition` PR on `main` that adds frozen acceptance tests and updates `pm_acceptance/active_task.json` with the task ID, allowed paths, required paths, and forbidden paths.
2. Codex then opens a separate implementation PR from `main`.
3. The PM Acceptance workflow evaluates PR production code against base-controlled acceptance tests and base-controlled checker scripts.
4. The PM reviews the draft PR. The implementation PR remains draft until PM approval.
5. After the implementation is merged, the PM can return `pm_acceptance/active_task.json` to `NO_ACTIVE_IMPLEMENTATION` or prepare the next task via another `pm-task-definition` PR.

No implementation PR may merge while `NO_ACTIVE_IMPLEMENTATION` is active, because production path changes fail task-scope validation.

The active-task schema intentionally has no `required_commands` field. Control-plane v1 uses fixed base-controlled workflow commands and never executes arbitrary shell strings from JSON.

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
