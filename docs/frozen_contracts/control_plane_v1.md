# Control Plane v1: Immutable PM Acceptance

## Why acceptance tests are base-controlled

PM acceptance tests define the behavior that an implementation PR must satisfy. The workflow therefore restores `pm_acceptance/` from the exact base SHA before running tests against PR production code. This prevents an implementation branch from weakening, deleting, renaming, skipping, or replacing the acceptance criteria it is supposed to satisfy.

## Why implementation PRs cannot edit protected paths

The control plane itself is protected: `AGENTS.md`, CODEOWNERS, the PM acceptance workflow, frozen contracts, acceptance tests, and scope-checking scripts are PM-owned. Implementation PRs cannot edit these files because changing them would let an implementation agent alter governance, workflow execution, or its own acceptance criteria.

## Active-task lifecycle

1. The PM first lands a control-plane or task-definition PR directly on `main`.
2. For implementation work, the PM adds frozen acceptance tests and updates `pm_acceptance/active_task.json` on `main` with the task ID, allowed paths, required paths, forbidden paths, and required commands.
3. Codex then opens a separate implementation PR from `main`.
4. The PM Acceptance workflow evaluates the implementation PR by running PR production code against base-controlled acceptance tests and base-controlled checker scripts.
5. The PM reviews the draft PR. The implementation PR remains draft until PM approval.
6. After the implementation is merged, the PM can return `pm_acceptance/active_task.json` to `NO_ACTIVE_IMPLEMENTATION` or prepare the next task on `main`.

No implementation PR may merge while `NO_ACTIVE_IMPLEMENTATION` is active, because production path changes fail task-scope validation unless they are part of this control-plane PR's exact allowed file list.

## Required branch-protection checks

The repository owner must manually enable these required checks on `main`:

- `PM Acceptance / protected-paths`
- `PM Acceptance / acceptance (3.12)`
- `PM Acceptance / acceptance (3.14)`

## Required branch-protection settings

The owner must manually require:

- pull request before merge
- one owner approval
- conversation resolution
- no force pushes
- no bypass

These settings are not created automatically by this repository change and must be configured in the repository hosting settings.
