# PM Acceptance

This directory contains frozen PM-owned acceptance tests and the active task scope file. Implementation PRs must not edit this directory; the PM Acceptance workflow restores it from the base branch before running acceptance checks.

Each task owns only `tasks/<task_id>/**/*.py`. A PM task-definition PR must use the same safe task ID in `active_task.json`, its task directory, and its optional frozen contract document. Task-local `conftest.py` files are forbidden.

## One-time frozen-test errata

A reported frozen-test defect must first be cancelled by closing the active task. After the generic erratum control plane is present on `main`, an explicitly owner-authorized `pm-frozen-erratum` PR may reactivate that same task and change exactly three paths: `active_task.json`, one existing `tasks/<task_id>/test_*.py`, and one new `errata/<task_id>.json`. The latter two files are the exact erratum payload; no contract or production file changes.

The canonical `pm_frozen_erratum_v1` manifest names an ancestor commit whose exact active-task bytes must equal the reactivated head bytes, SHA-256-pins the complete reactivated active-task bytes and the complete base and head test bytes, and records the linked issue, reason code, test path, and exact expected RED passed and failed node IDs. All `test_*` ASTs remain unchanged. The base-controlled workflow separately collects the base test and accepts the transition only when the corrected suite executes exactly that unchanged node-ID set and produces exactly the declared RED profile without skip, xfail, xpass, deselection, or collection/setup/teardown errors on every Python version. A successful erratum must still be followed by a fresh mandatory RED probe closed without merge, a fresh-main implementation PR, and a separate close PR.
