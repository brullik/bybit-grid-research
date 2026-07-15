# PM Acceptance

This directory contains frozen PM-owned acceptance tests and the active task scope file. Implementation PRs must not edit this directory; the PM Acceptance workflow restores it from the base branch before running acceptance checks.

Each task owns only `tasks/<task_id>/**/*.py`. A PM task-definition PR must use the same safe task ID in `active_task.json`, its task directory, and its optional frozen contract document. Task-local `conftest.py` files are forbidden.
