# Control Plane v1: Immutable PM Acceptance

## Why acceptance tests are base-controlled

PM acceptance tests define the behavior that an implementation PR must satisfy. The workflow checks out base and head separately, copies base `pm_acceptance/` to runner temp, disables pytest plugin autoloading, uses a base-owned pytest config, and runs acceptance from outside the PR checkout. This prevents a PR's tests, root `conftest.py`, pytest configuration, or auto-loaded plugins from weakening, deleting, skipping, xfail-padding, renaming, or replacing the acceptance criteria it must satisfy.

## PR modes

Every PR is classified as exactly one mode:

- `implementation`: no PM mode label. Protected paths are forbidden and the exact production scope comes from base `pm_acceptance/active_task.json`.
- `pm-task-definition`: requires author `brullik` and exact label `pm-task-definition`. It may change only `pm_acceptance/active_task.json`, Python files below `pm_acceptance/tasks/<task_id>/`, and `docs/frozen_contracts/tasks/<task_id>.md`. The task ID in every changed path must equal the canonical task ID in the head task file. Task-local `conftest.py` files are forbidden. No `src/**`, ordinary `tests/**`, workflow, checker, dependency, or control-plane change is allowed.
- `pm-control-plane`: requires author `brullik` and exact label `pm-control-plane`. Changes are restricted to the frozen control-plane allowlist; no `src/**`, ordinary `tests/**`, or production code is allowed.
- `pm-frozen-erratum`: requires author `brullik`, explicit owner authorization recorded in the manifest-linked issue, and exact label `pm-frozen-erratum`. It is a one-time repair transition from `NO_ACTIVE_IMPLEMENTATION` that reactivates the same invalidated task. Its changed paths are exactly `pm_acceptance/active_task.json` and a two-file erratum payload: one already-existing `pm_acceptance/tasks/<task_id>/test_*.py` plus one new canonical `pm_acceptance/errata/<task_id>.json`. The matching frozen contract and every production, ordinary-test, dependency, checker, workflow, and other acceptance path remain unchanged.

The workflow fails closed on multiple PM mode labels, unknown `pm-*` mode labels, missing required labels for protected paths, wrong author, and mixed PM/production changes.

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

## Frozen-test erratum lifecycle

An apparent acceptance-test defect never grants permission to edit the frozen suite in place or to continue an implementation around it. The only supported recovery is this ordered, fail-closed sequence:

1. Record the defect and the owner's explicit authorization. Stop and close any implementation attempt without merge.
2. While the old control plane is still authoritative, merge a separate `pm-task-definition` cancellation PR that changes only `pm_acceptance/active_task.json` to `NO_ACTIVE_IMPLEMENTATION`. This prevents the invalid task from authorizing production work.
3. Merge a separate `pm-control-plane` PR that introduces the generic erratum gate. That bootstrap PR does not edit the faulty frozen test.
4. From fresh `main`, open one owner-authored `pm-frozen-erratum` PR. It must reactivate the invalidated task and change exactly three paths: `pm_acceptance/active_task.json`, the single faulty existing `test_*.py`, and the new `pm_acceptance/errata/<task_id>.json`. Thus the corrective payload itself has an exact two-file scope: the test and its manifest. The frozen behavior contract is unchanged because an erratum repairs only the defective fixture or harness expression, not the required behavior.
5. Merge the erratum only at its unchanged expected head SHA after all required checks succeed, exact scope is reverified, and no review thread is unresolved.
6. Treat every earlier RED probe and implementation result as stale. Create a fresh `probe/` branch from the corrected `main`, obtain the exact expected behavioral RED result, record it, and close the probe without merge.
7. Only then create a new implementation PR from fresh `main`. After that implementation merges, close the task through the normal separate `pm-task-definition` close PR.

The erratum manifest uses canonical compact sorted UTF-8 JSON with one trailing LF and schema `pm_frozen_erratum_v1`. It contains exactly `schema`, `task_id`, `issue_number`, `test_path`, `base_sha256`, `head_sha256`, `head_active_task_sha256`, `historical_active_task_commit_sha`, `reason_code`, `expected_red_failed_node_ids`, and `expected_red_passed_node_ids`. `base_sha256` and `head_sha256` are lowercase SHA-256 digests of the complete frozen-test bytes before and after the repair; `head_active_task_sha256` pins the complete canonical reactivated task bytes. `historical_active_task_commit_sha` is a lowercase 40-hex commit ID that must be an ancestor of the erratum base and whose exact `active_task.json` bytes must equal the reactivated head bytes. The issue number is positive, the manifest path and test path must match the reactivated task ID, the base test must already exist, and the manifest must be new. A merged manifest makes the exception one-time; the same task cannot use this transition again.

The base-owned checker validates the inactive-to-reactivated task transition, exact historical active-task byte identity, exact three-path diff, canonical manifest, both pinned file digests, and the corrective test's structure. Every sync and async function whose name starts with `test_` must have exactly the same AST as in base. The workflow independently collects the base test in an isolated subprocess and requires the expected manifest union, head collection, and actual head outcome union all to equal that baseline node-ID set. Tests cannot be deleted, added, renamed, reordered through parameter padding, weakened, skipped, xfailed, or replaced. The checker also continues to reject production, dependency, workflow, checker, contract, task-local `conftest.py`, and unrelated acceptance changes.

For `pm-frozen-erratum`, the workflow deliberately does not execute the ordinary base frozen harness containing the known-bad fixture. It does run the base control-plane self-tests. It then stages only the SHA-pinned base and head versions of the one test plus the canonical manifest outside the checkout. An isolated subprocess collects the base node IDs without executing the defective fixture; a separate isolated subprocess executes the corrected head suite against the installed head package. Acceptance-fixture and script dependencies resolve from the trusted base checkout, never from head ordinary tests or scripts; the only staged head test content is the manifest-pinned corrected frozen test. The installed production package remains the unchanged head package, and exact scope proves the head and base production trees are unchanged. The job succeeds only when the manifest union, head collection, and actual passed-and-failed union all exactly equal the baseline collection, the actual passed and failed sets separately equal the manifest, at least one RED failure is present, and there are no skipped, xfailed, xpassed, deselected, collection-error, setup-error, or teardown-error outcomes. Both supported Python matrix jobs must independently match this profile. Supplemental numeric, dependency, no-live, compilation, lint, and diff checks remain mandatory; supplemental pytest uses the same ordinary `tests/`-only selection as a task-definition PR so the known-bad frozen tree is not accidentally treated as implementation evidence.

An erratum success authorizes only the corrected acceptance definition and task reactivation. It is not implementation acceptance, does not substitute for the fresh mandatory RED probe, and grants no network, credential, private API, Telegram, order, position, wallet, or live-execution authority.

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
