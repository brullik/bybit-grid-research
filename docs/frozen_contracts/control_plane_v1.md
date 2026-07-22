# Control Plane v1: Immutable PM Acceptance

## Why acceptance tests are base-controlled

PM acceptance tests define the behavior that an implementation PR must satisfy. The workflow checks out base and head separately, copies base `pm_acceptance/` to runner temp, disables pytest plugin autoloading, uses a base-owned pytest config, and runs acceptance from outside the PR checkout. This prevents a PR's tests, root `conftest.py`, pytest configuration, or auto-loaded plugins from weakening, deleting, skipping, xfail-padding, renaming, or replacing the acceptance criteria it must satisfy.

## PR modes

Every PR is classified as exactly one mode:

- `implementation`: no PM mode label. Protected paths are forbidden and the exact production scope comes from base `pm_acceptance/active_task.json`.
- `pm-task-definition`: requires author `brullik` and exact label `pm-task-definition`. It may change only `pm_acceptance/active_task.json`, Python files below `pm_acceptance/tasks/<task_id>/`, and `docs/frozen_contracts/tasks/<task_id>.md`. The task ID in every changed path must equal the canonical task ID in the head task file. Task-local `conftest.py` files are forbidden. No `src/**`, ordinary `tests/**`, workflow, checker, dependency, or control-plane change is allowed.
- `pm-control-plane`: requires author `brullik` and exact label `pm-control-plane`. Changes are restricted to the frozen control-plane allowlist; no active-task, acceptance `conftest.py`, `src/**`, ordinary `tests/**`, dependency, or production-code change is allowed.
- `pm-frozen-erratum`: requires author `brullik`, explicit owner authorization recorded in the manifest-linked issue, and exact label `pm-frozen-erratum`. It is a repair transition from `NO_ACTIVE_IMPLEMENTATION` that reactivates the same invalidated task. The v1 transition changes exactly `pm_acceptance/active_task.json` and a two-file erratum payload: one already-existing `pm_acceptance/tasks/<task_id>/test_*.py` plus one new canonical `pm_acceptance/errata/<task_id>.json`. If and only if that merged repair is itself invalid and the second recovery gate is already base-owned, the v2 transition has the same exact scope but adds `pm_acceptance/errata/<task_id>.v2.json` instead; the v1 manifest remains unchanged. The matching frozen contract and every production, ordinary-test, dependency, checker, workflow, and other acceptance path remain unchanged.
- `pm-recovery-bundle`: requires author and live sender `brullik`, the exact sole label `pm-recovery-bundle`, canonical head/base repositories, and base branch `main`. A metadata-only base-owned preflight enforces that identity before any checkout or head fetch, and the checked-out base checker enforces it again. It is the one-time, non-generic activation for exactly `p0-walk-forward-exclusive-outcome-end` plus `p0-committed-key-preflight`. One non-merge commit directly based on the manifest-pinned live base changes exactly `pm_acceptance/active_task.json` and `pm_acceptance/reactivations/p0-recovery-walk-forward-committed-key.json`.

The workflow fails closed on multiple PM mode labels, unknown `pm-*` mode labels, missing required labels for protected paths, wrong author, and mixed PM/production changes.

Implementation PRs execute the complete base-owned frozen acceptance suite. The workflow first materializes byte- and mode-pinned base and head Git-object snapshots. Its frozen execution tree preserves the head `src/`, `scripts/`, and ordinary `tests/` layout needed by existing frozen imports, then overlays only base-controlled `pm_acceptance`, frozen contracts, and the protected-path/task-scope checker pair; head acceptance controls never enter that tree. Every PM-owned mode instead executes the base control-plane self-tests, and `pm-control-plane` additionally stages and executes only the head self-test file, active-task fixture, checker pair, and workflow. A base-owned exact-outcome runner requires a nonempty collection and exactly one plain passing call per node; it rejects skip, xfail/xpass, deselection, duplicate or missing calls, and collection/setup/teardown anomalies. The head workflow is syntax-parsed before merge. Supplemental pytest for PM-owned modes is restricted to ordinary `tests/` with plugin autoload disabled; the protected-path gate has already prohibited production, ordinary-test, and dependency changes. This keeps both the old and proposed governance revisions under test while allowing the control plane to repair a known-invalid frozen harness without first executing that same harness. The base-owned classifier and protected-path check remain authoritative for the PR.

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

Every complete `test_*` function AST is identical before and after an erratum. Consequently, an expression already inside an immutable test function cannot be added, removed, or moved by the repair. The unsafe-pattern scanner applies to the mutable module and helper harness outside those frozen function ASTs, where new skip/xfail calls, markers, broad exception handlers, and broad `pytest.raises` remain forbidden. The exact-outcome runner independently rejects any skipped, xfailed, xpassed, setup-error, teardown-error, or collection-error test outcome, including one caused by an immutable legacy expression.

The base-owned checker validates the inactive-to-reactivated task transition, exact historical active-task byte identity, exact three-path diff, canonical manifest, both pinned file digests, and the corrective test's structure. Every sync and async function whose name starts with `test_` must have exactly the same AST as in base. The workflow independently collects the base test in an isolated subprocess and requires the expected manifest union, head collection, and actual head outcome union all to equal that baseline node-ID set. Tests cannot be deleted, added, renamed, reordered through parameter padding, weakened, skipped, xfailed, or replaced. The checker also continues to reject production, dependency, workflow, checker, contract, task-local `conftest.py`, and unrelated acceptance changes.

For `pm-frozen-erratum`, the workflow deliberately does not execute the ordinary base frozen harness containing the known-bad fixture. It does run the base control-plane self-tests. It stages the SHA-pinned base and head versions of the one test plus the canonical manifest outside the checkout. An isolated subprocess collects the base node IDs without executing the defective fixture and may resolve collection-only helpers from the trusted base checkout. A separate isolated subprocess executes the corrected head against the installed head package in a copy of the normal base-controlled harness: base `pm_acceptance`, an empty staged `scripts` package containing only the two checker modules, base pytest configuration, and no full trusted-base or head scripts/tests root on `PYTHONPATH`. This ordering applies to v1 and v2, so a first erratum cannot pass only because the special erratum runner exposed helper imports that the normal implementation harness shadows. The only head acceptance content is the manifest-pinned corrected frozen test. Exact scope proves the head and base production trees are unchanged. The job succeeds only when the manifest union, head collection, and actual passed-and-failed union all exactly equal the baseline collection, the actual passed and failed sets separately equal the manifest, at least one RED failure is present, and there are no skipped, xfailed, xpassed, deselected, collection-error, setup-error, or teardown-error outcomes. Both supported Python matrix jobs must independently match this profile. Supplemental numeric, dependency, no-live, compilation, lint, and diff checks remain mandatory; supplemental pytest uses the same ordinary `tests/`-only selection as a task-definition PR so the known-bad frozen tree is not accidentally treated as implementation evidence.

### Audit-chained second erratum

A defect in the already-merged v1 correction does not reopen or mutate that exception. The task must first be cancelled to `NO_ACTIVE_IMPLEMENTATION` again. Only explicit owner authorization and a separate base-owned control-plane revision may enable the one-and-only second repair. From fresh `main`, the owner-authored `pm-frozen-erratum` PR must reactivate the identical task and change exactly `pm_acceptance/active_task.json`, the same existing frozen test, and a new `pm_acceptance/errata/<task_id>.v2.json`. The existing `<task_id>.json` is immutable, an existing `.v2.json` rejects reuse, and `.v3.json` or any unmanifested path is unsupported.

The v2 manifest is canonical compact sorted UTF-8 JSON with one trailing LF and schema `pm_frozen_erratum_v2`. It contains every v1 field plus exactly `predecessor_commit_sha` and `predecessor_manifest_sha256`. Its task ID, test path, positive issue number, historical active-task commit, and head active-task digest must equal the corresponding immutable v1 evidence. Its `base_sha256` must equal both the current base test digest and the v1 `head_sha256`. `predecessor_manifest_sha256` pins the complete v1 manifest bytes. `predecessor_commit_sha` must be a lowercase 40-hex ancestor of the current base that contains those exact v1 manifest bytes, the v1-corrected test bytes, and active-task bytes identical to the v2 head. The historical active-task commit must precede that predecessor and contain the same canonical active-task bytes. These links bind the second correction to the exact first correction rather than merely to a reused task name.

The v2 checker independently preserves the v1 structural rules: exactly three changed paths, inactive-to-identical-reactivated task transition, a new manifest, exact byte hashes, unchanged nonempty `test_*` function ASTs, no unsafe skip/xfail or broad-exception patterns in mutable module/helper harness code, and a complete manifest node-name partition. The workflow stages the current base test separately and collects it with the trusted base checkout on `PYTHONPATH`; for sprint 06.4B this recovers the complete 39-node baseline without executing its invalid fixture. It then copies base `pm_acceptance` into a separate normal harness, overwrites only the pinned target test with the v2 head bytes, creates the same empty `scripts/__init__.py` and stages only the two base-owned checker scripts, uses the base-owned pytest configuration, sets both `RUNNER_TEMP` and the sole `PYTHONPATH` root to that harness, and executes against the installed unchanged head package. This reproduces the normal base-isolated import order instead of allowing trusted-base production helper imports to mask a collection defect.

The exact-outcome plugin rejects every non-plain result: collection failures or skips, deselection, duplicate node IDs, duplicate calls, calls without collection, collected nodes without exactly one call, setup or teardown failure/skip, call skip, and xfail/xpass. The complete current-base collection, v2-head collection, call pass/fail union, and manifest union must be identical; the failed and passed sets must separately match the manifest, at least one failure must remain RED, and pytest must return the exact expected collection and RED exit codes on every Python matrix version.

After a successful v2 merge, all earlier probe and implementation evidence is stale. The same fresh closed-unmerged `probe/` RED, fresh-main implementation PR, and separate task-close PR are mandatory. No first- or second-erratum success authorizes production behavior, network access, credentials, private APIs, Telegram, orders, positions, wallets, or live execution.

## One-time two-task recovery lifecycle

The recovery manifest has schema `pm_recovery_bundle_v1` and compact canonical sorted UTF-8 JSON with one trailing LF. Its exact keys pin the bundle ID, activation base, head active-task digest, suspension commit, identical allowed and required 12-path union, two ordered members, and the prior v1 erratum evidence. Each member pins its task and issue identity, historical first-parent activation commit, complete historical active-task/frozen-test/contract SHA-256 values, exact frozen-test and contract paths, expected sentinel, and exact node IDs. The previous member has 32 nodes; the suspended current member has 20; duplicates or any total other than 52 are invalid. Float tokens, booleans used as integers, BOM, duplicate/unknown/missing keys, unsafe IDs or paths, reordered/substituted members, mutable scope, and noncanonical bytes are rejected.

The activation base must be the exact v1-erratum reactivation of `p0-walk-forward-exclusive-outcome-end`. Canonical first-parent task history must contain the first activation, its pinned close, the second activation, its manifest-pinned suspension, and the v1 erratum reactivation in that exact order with no added task transition. The erratum must be the activation base, directly follow that suspension, change exactly the active task, one frozen test, and the new v1 manifest, and carry a canonically parsed manifest whose identity, historical digest, corrected-test digest, and exact 32-node RED partition match the recovery permit. The checker also verifies source commits, exact active-task/test/contract and erratum/corrected-test bytes, SHA-256 values, regular-file modes, and unchanged base copies. A changed-then-reverted file, task substitution, repeated activation, side-branch evidence, missing or repeated erratum, base drift, merge commit, multi-commit or stale head, non-direct base, existing recovery manifest, wrong exact two-path activation diff, or replay fails closed.

Activation collects the exact manifest node set without executing behavior and therefore is not RED evidence. A fresh combined Draft `probe/` branch must then execute exactly those 52 nodes and observe one plain call-phase failure per node with the correct member sentinel. The exact-outcome gate rejects every pass, skip, xfail/xpass, deselection, collection/setup/teardown anomaly, duplicate or missing call, node drift, sentinel drift, and unexpected exit. The probe is closed unmerged. The subsequent fresh-main implementation changes exactly the 12 declared production/ordinary-test paths and must make the complete frozen tree and ordinary suite plain green on Python 3.12 and 3.14. Ordinary tests execute only in a disposable copy of the pinned head snapshot, so their expected `data/processed/**` and `reports/**` products cannot mutate either source snapshot; post-run verification still checks the pristine source snapshots' exact file sets, bytes, and regular-file modes against Git objects. Only then may a separate task-definition PR close the bundle to canonical inactive.

An ordinary task-opening transition additionally runs the complete base frozen tree through the exact plain-pass gate; unresolved frozen behavior blocks the new task before collection of its proposed tests. Final status is computed only after live PR and live `main` readback proves unchanged head/base/main SHA and refs, labels, author, canonical repositories, open/readiness state, and a complete paginated review-thread set with zero unresolved threads. Malformed responses, pagination drift, or a missing cursor fail closed. Draft is valid for preliminary execution and evidence only: it cannot publish aggregate success. Old probes, Draft results, and implementations are never reusable. The recovery permit authorizes no network, credentials, private API, Telegram, trading, wallet, deployment, or live execution and cannot be generalized to another pair or invoked a second time.

An erratum success authorizes only the corrected acceptance definition and task reactivation. It is not implementation acceptance, does not substitute for the fresh mandatory RED probe, and grants no network, credential, private API, Telegram, order, position, wallet, or live-execution authority.

For every non-probe PR, autonomous merge additionally requires the expected head SHA to remain unchanged, every required status to be successful, exact scope verification, and zero unresolved review threads. Unknown, pending, stale, skipped, cancelled, or failing status is not approval. Required checks may never be bypassed, and force merge is forbidden.

## Staged execution authority

Implementation authority remains offline-only by default. An active task's path allowlist never by itself authorizes network access, credentials, private Bybit API calls, Telegram, orders, positions, wallet access, or native-grid mutation. Those capabilities remain forbidden until a later base-controlled control-plane contract explicitly defines the current execution stage and freezes its risk, credential, human-approval, kill-switch, rollback, and audit gates. Production secrets may exist only in an approved runtime secret store and never in repository or agent-visible content.

Withdrawal and ordinary-order mutation are never authorized in V1. Any later execution authority is limited to the native Bybit grid lifecycle and cannot be inferred from a production path allowlist.

This governance revision does not enable private or live execution. The existing no-live source audit remains mandatory and unchanged.

## Aggregate head status

The base-owned workflow publishes a `pm-acceptance` commit status on the exact pull-request head SHA. It accepts the bounded `pull_request_target` activity set and the supported authenticated `pull_request_review: submitted` event. A submitted-review run is governing only for a comment-only review whose event sender, triggering actor, and review author are all `brullik`; other review submissions remain fail-closed. A minimal pending job publishes the Actions run URL before acceptance. A final `always()` job re-reads the live PR, live `main` ref, and every paginated review thread, then reports success only when those identities match the triggering head/base/main state, every thread is resolved, the pending publication, protected-path job, and complete acceptance matrix all succeeded, and the PR is Ready, owner-authored, open, and not on a `probe/` branch. The fail-closed truth table is: Draft plus otherwise-green upstream jobs is failure; Ready plus otherwise-green upstream jobs and all live attestations is success; any explicit upstream failure is failure; cancelled, skipped, stale, unknown, malformed, or incomplete evidence is error or an unpublished failure. A Draft-to-Ready transition retriggers and cancels stale work, and only a fresh unchanged-SHA run may publish success. If a finalizer observes an unresolved thread it cannot approve that run; after resolving every thread, `brullik` must submit a comment-only review to create a distinct governing run, whose finalizer revalidates the unchanged reviewed SHA and complete live thread set before the pending status can advance. Resolution by itself is not represented as a GitHub Actions trigger. PR edits and Draft conversion also retrigger the workflow. The status remains pending only if the finalizer cannot publish its result.

Only the two status publisher jobs receive `statuses: write`. They do not check out or execute pull-request head code. The final publisher additionally has read-only contents permission solely for live `main` ref validation; the protected-path and acceptance jobs retain read-only permissions. This makes the run URL and aggregate result discoverable from the head SHA without transferring a user-supplied Actions URL and without exposing a write token to untrusted head code.

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
