# Frozen contract — sink-safe redaction

## Scope and authority

Task ID: `sink-safe-redaction`.

This P0 security task closes the bounded defect owned by issue #148. The defect was confirmed by
read-only inspection of current production source at audit ref
`f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`. No historical branch was executed, no credential was
used, no Bybit request was made, and no public, private, live, order, position, grid, transfer, or
withdrawal path was exercised.

The task-definition PR changes exactly these three protected paths:

1. `pm_acceptance/active_task.json`;
2. `pm_acceptance/tasks/sink-safe-redaction/test_sink_safe_redaction.py`;
3. `docs/frozen_contracts/tasks/sink-safe-redaction.md`.

The later implementation PR changes exactly these three required paths:

1. `src/bybit_grid/logging.py`;
2. `src/bybit_grid/reporting.py`;
3. `tests/test_redaction.py`.

No script, client, configuration, dependency, lock file, workflow, checker, PM acceptance file,
frozen contract, generated report, data artifact, documentation file, network behavior, private
dispatch behavior, credential boundary, live behavior, or trading behavior may change in the
implementation PR. Base-owned tests may not be weakened, moved, skipped, or replaced.

Passing this contract proves only sink-safe handling at the named logging and Sprint 01 report
boundaries. It grants no credential, network, private API, validate, create-grid, close-grid,
Telegram, deployment, live-execution, or trading authority.

## Availability and mandatory RED

Availability requires all three implementation paths to be material. The runtime modules expose
these exact executable assignments:

```python
SINK_SAFE_REDACTION_CONTRACT = "sink-safe-v1"
SINK_SAFE_REPORTING_CONTRACT = "sink-safe-v1"
```

`tests/test_redaction.py` contains exactly one top-level executable assignment, verified by AST
rather than text search:

```python
SINK_SAFE_REDACTION_TEST_CONTRACT = "sink-safe-v1"
```

Its exact raw UTF-8 source SHA-256 after final Ruff formatting is:

```text
a2e10f02e720063798ab034c1d7125cfb26f396dbdba669435f66149acb2a309
```

The protected suite does not import the ordinary test module. Missing files, unreadable/non-UTF-8
source, invalid Python, comments containing marker text, duplicate marker assignments, absent
runtime constants, wrong values, or an inert/changed ordinary regression suite are unavailable.
Every one of exactly 20 plain synchronous tests calls the same availability helper as its first
statement.

The unmodified baseline and the mandatory inert/comment-only RED probe therefore collect exactly
20 tests and fail exactly 20 times with:

```text
RuntimeError: sink_safe_redaction_unavailable
```

There may be no pass, skip, xfail, collection error, fixture error, or different failure in the
RED profile. The RED probe changes all three required implementation paths only with inert
comments, is never merged, and is closed unmerged after both supported Python matrices prove the
exact profile. Adding the three markers without implementing behavior is not GREEN: all material
adversarial tests still execute and fail.

## Canonical redaction behavior

The deterministic replacement value remains exactly:

```text
***REDACTED***
```

The existing public API remains available: `redact`, `RedactionFilter`, `setup_logging`, and
`redacted_json_dump`. The recursive canonicalizer supports mappings (including `UserDict`), lists,
tuples, sets/frozensets, bytes/bytearray/memoryview, path-like values, exceptions, known scalar
types, and recursive containers. Unordered values are stable-sorted, cycles become a fixed safe
token, and an arbitrary object becomes its module-qualified type name. A raw arbitrary-object
`str()` fallback is forbidden.

Sensitive mapping keys are case-insensitive and normalize `_`, `-`, spaces, and other separators.
They include API keys/secrets, Bybit signing headers, signatures, authorization, bearer/access/
refresh tokens, passwords, cookies, client/private secrets, and the explicitly tainted fields
listed below. Sensitive material embedded in key text is sanitized too. Empty strings and nulls
under a sensitive key may remain empty/null; every nonempty value is replaced.

Raw text covers double-quoted JSON, single-quoted mapping text, header syntax, query assignments,
unquoted assignments, Authorization/Proxy-Authorization, and standalone bearer syntax. Quoted
values may contain spaces and escaped characters. All occurrences are processed, while unrelated
endpoint, status, symbol, numeric, and type diagnostics remain usable.

The explicitly tainted server/error labels are:

```text
body body_first_500 debug_msg error error_summary message
response_body response_text retMsg server_error
```

These fields lose arbitrary text even when that text has no secret-like pattern. Exception values
lose their messages while retaining exception type. This is the exact truthful boundary: an
arbitrary unlabelled string in an ordinary field or log message is not claimed to be discoverable
as a secret. Such text is guaranteed absent only when it appears behind a known sensitive label,
an explicitly tainted server/error field, an exception message/traceback, or another report field
declared unconditionally tainted below.

Repeated redaction is idempotent. JSON rendering is UTF-8/Unicode-safe, sorted, and never falls
back to an arbitrary object's raw string representation.

## Logging sink boundary

`LogRecord` protection occurs after all relevant values exist:

1. structured arguments are recursively canonicalized;
2. percent/mapping formatting is completed exactly once;
3. the rendered message is redacted and `args` is cleared;
4. fields added by `Logger.makeRecord(..., extra=...)` are canonicalized;
5. exception and cached exception text are sanitized before a handler emits.

This ordering is binding. Redacting a format template before interpolation, processing `msg` and
`args` independently without checking the rendered result, or relying on a root-logger filter is
insufficient.

`setup_logging()` idempotently wraps the current `LogRecordFactory`, protects the post-`extra`
`Logger.makeRecord` boundary, protects normal handler emission, and adds one `RedactionFilter` to
all root and already-registered non-root handlers. A child handler present before setup and a child
handler added after setup are both covered. Repeated setup retains one wrapper/filter layer and
does not duplicate a record. The prior factories/boundaries remain chained.

`logger.exception()` output removes the arbitrary exception message and traceback source lines.
It retains the exception type and sanitized `filename:line:function` locations. Precomputed
`exc_text`, stack text, `levelname`, `threadName`, `taskName`, structured extras, mapping-format
arguments, and a secret split between a format template and a positional argument cannot bypass
the sink boundary.

## Report sink boundary

`write_sprint_report()` first constructs a canonical run object, then sanitizes the entire object
before writing any bytes. Every new and existing `reports/runs/*.json` artifact is sanitized and
atomically replaced before it is used to render `reports/sprint_01_api_report.md`. Markdown is
created only from sanitized objects and receives a final text-redaction pass.

The report fields have these exact policies:

- `counts` preserves mapping/list shape and only numeric, Boolean, and null atoms; any text or
  object atom becomes the marker;
- every `output_paths` entry is unconditionally tainted and becomes one marker, preserving list
  length but never a raw path;
- empty/null `error_summary` becomes an empty string and every nonempty value becomes the marker;
- `command` preserves only `smoke_private_account`, `smoke_public_api`, `validate_sample_grid`, and
  `python scripts/download_sample_data.py`, plus reserved safe constants `unknown` and
  `invalid_report_artifact`; absent command becomes `unknown`, while every other incoming value
  becomes the marker;
- `status` preserves only `ok`, `success`, `error`, `failed`, `blocked`, `network-blocked`,
  `dry-run`, `skipped`, `invalid`, and `unknown`; a new `write_sprint_report()` call with no status
  keeps the historical `ok` default, while an existing run artifact with no status becomes
  `unknown`; every other incoming value becomes the marker;
- `started_at` and `ended_at` preserve only bounded timezone-aware ISO-8601 strings; absent values
  use the current UTC timestamp and malformed, naive, non-string, or oversized values become the
  marker;
- endpoint, HTTP status, API code, exception type, and other ordinary structured diagnostics are
  passed through the canonical redactor.

The command/status/timestamp/counts/output-path/error policy applies recursively at every mapping
depth and through lists/tuples inside `sections`; retaining raw input through a nested section is
forbidden. Section keys are sanitized as well as values.

Malformed JSON, non-UTF-8 bytes, and a non-object run artifact fail closed to a canonical
`invalid_report_artifact`/`invalid` record at the original path. No raw backup is retained in the
report tree. Same-directory temporary files are removed after success or failure. A scan of every
file below the report tree must find none of the injected canary bytes.

The historical repository-relative `reports/` location and return value remain compatible. The
unused `data_dir` behavior is not changed by this task.

## Exact adversarial acceptance matrix

The frozen suite contains exactly these 20 material tests:

1. exact task/runtime/ordinary-test contract markers and deterministic replacement value;
2. nested `UserDict` values for every normalized sensitive/tainted key family;
3. double-quoted JSON secret plus `retMsg`, `message`, `debug_msg`, and response body values;
4. single-quoted mapping, Bybit header, query, Authorization, and standalone bearer syntax;
5. sensitive material embedded in string and byte mapping keys;
6. bytes, bytearray, memoryview, tuple, set/frozenset, cycles, and hostile unknown objects;
7. exception as JSON value with message absent and type/endpoint/HTTP/API diagnostics retained;
8. child logger handler present before setup and late percent formatting;
9. child handler added after setup with sensitive and tainted `extra` values;
10. secret split between percent template and positional argument;
11. mapping-format arguments plus nested structured extras;
12. `logger.exception()` with an unlabelled canary, type and location retained;
13. manually cached `exc_text` plus tainted `levelname`/`threadName`/`taskName` reaching a handler
    filter;
14. root propagation plus repeated setup, one filter and one emitted record;
15. new report with distinct canaries in top-level and deeply nested command/status/timestamps/
    counts/path/error/sections;
16. existing valid run rewritten before Markdown generation;
17. malformed, non-UTF-8, and valid non-object JSON runs replaced in place with canonical invalid
    records;
18. exact useful allowlisted, ISO timestamp, numeric, endpoint, HTTP/API, and type diagnostics;
19. recursive redaction and repeated report rewriting are idempotent with no temporary debris;
20. original public API, original `tests/test_redaction.py`, Sprint 01.5 expectations, and the
    actual download command's omitted-status `ok` default remain compatible.

Mutations that remove a post-format pass, omit a sensitive/tainted label, use raw `str()`, trust
only the root filter/factory, skip post-`extra` values, retain exception text, preserve one raw
output path, preserve an unknown command/status/time, pass text inside counts, render existing raw
JSON, skip malformed artifacts, leave a backup/temp file, weaken the ordinary regression marker,
or change the replacement value must fail.

## Required GREEN evidence

Before merge, verify on both supported Python matrices:

- the task-definition branch has the exact three protected paths;
- the mandatory RED has exact three required paths and the exact 20-sentinel failure profile;
- the implementation branch has exact three required paths and all 20 frozen tests pass;
- ordinary repository tests, compile checks, Ruff lint/format, dependency checks, protected-scope
  checks, numeric-environment checks, and no-live-execution checks remain green;
- no acceptance, workflow, checker, dependency, or frozen-contract change is present in the
  implementation diff;
- no generated report, credential, network transcript, private response, or live artifact is
  committed.

Issue #148 may close only after the GREEN implementation merge and the separate active-task close
transition. Completion does not close issue #133, issue #134, or any other assurance/E2E/live gate.
