# Frozen task contract: P0 strict API response envelopes

Task ID: `p0-strict-api-response-envelopes`
Issue: `#149`
Contract version: `strict-envelope-v1`
RED sentinel: `strict_api_response_envelope_unavailable`

Design audit ref: `7c9fd8547ddd6df93221d9cf5196dcd32e7d8672`
Fresh activation baseline: `bf472eb34782a0b6097a71f56ec19ee9a1b6643f`

Issue `#148` and its PM close are the only intervening changes. The six implementation paths are
byte-identical at both refs and at the activation baseline, with these Git blob identities:

- `scripts/smoke_private_account.py`: `91702ad64a6ac92df6f53a8a0476d2a67b927b7f`
- `src/bybit_grid/bybit/client.py`: `1b3875ff12f9de933f99902d4d1f948f5fe4bd58`
- `src/bybit_grid/bybit/fgrid_constraints.py`: `2e5f93cffa4e16ddf3cf512ac6dabf8e54cc8376`
- `src/bybit_grid/bybit/models.py`: `127bd66e2675da354d4dffc438026a4595e10fdb`
- `tests/test_sprint_01_8_hotfix.py`: `e0321432a60ffdc758c68e32b7a1017d0521f468`
- `tests/test_sprint_02.py`: `e78181ab86250405d2a3fd840b3df87356410420`

This task closes ambiguous success authority at the online Bybit response boundary. It is an
offline implementation task. It grants no network, credential, private-account, Bybit, bot-create,
bot-close, live, or trading authority.

## Exact implementation scope

The implementation PR must change exactly all six paths below and no others:

1. `scripts/smoke_private_account.py`
2. `src/bybit_grid/bybit/client.py`
3. `src/bybit_grid/bybit/fgrid_constraints.py`
4. `src/bybit_grid/bybit/models.py`
5. `tests/test_sprint_01_8_hotfix.py`
6. `tests/test_sprint_02.py`

The task does not authorize changes to endpoints, request methods or payloads, signing, prepared
capabilities, retry attempts, rate limiting, HTTP transports, settings, workflows, dependencies,
PM enforcement, source-safety checks, create/close stubs, or native validate `result` semantics.
Exact native validate result/check/range meaning remains owned by issue `#150`.

## Availability gate and mandatory RED

The frozen suite contains exactly 24 plain synchronous tests. Each test's first statement is the
shared availability check. Availability requires all four production modules to expose
`STRICT_API_RESPONSE_ENVELOPE_CONTRACT = "strict-envelope-v1"` and both ordinary test files to
contain exactly one `STRICT_API_RESPONSE_ENVELOPE_TEST_CONTRACT = "strict-envelope-v1"` assignment
with their frozen raw-byte SHA-256 values.

From the task-definition merge, the inert comment-only probe must change every one of the exact six
required implementation paths above, and only those six. This is required by the repository's
task-scope checker for probe/implementation PRs. It must produce exactly 24 failures whose terminal
exception is `RuntimeError("strict_api_response_envelope_unavailable")` on every supported Python
matrix. The probe must be closed unmerged. Collection errors, unrelated failures, skips, xfails,
partial required-path scope, and any other reason do not satisfy RED.

## Strict JSON boundary

Online responses are decoded only from `httpx.Response.content` using strict UTF-8. JSON parsing
must reject duplicate object keys at every depth, non-finite constants (`NaN`, `Infinity`, and
`-Infinity`), and finite JSON number spellings such as `1e400` whose Python float conversion is
non-finite. Numeric conversion `ValueError` (including the interpreter's huge-integer digit limit)
and parser `RecursionError` are JSON-invalid without retaining raw text. The root must be an exact
built-in dictionary.
`response.json()` and synthesized pseudo-responses from raw response text are forbidden.

The stable reason-code allowlist is below; policy-specific precedence follows it:

```text
response_body_empty
response_utf8_invalid
response_json_duplicate_key
response_json_nonfinite
response_json_invalid
response_root_not_object
response_marker_missing
response_marker_type_invalid
response_marker_alias_forbidden
response_marker_conflict
response_message_type_invalid
```

Whitespace-only bodies are JSON-invalid. Marker values must be exact built-in integers, must not be
booleans, and must fit signed int64. Present top-level `retMsg` and `debug_msg` values must be exact
strings. Raw malformed bytes, text, marker values, and message evidence must not enter errors,
attributes, logs, or persisted error evidence.

## Envelope policies

V5 public and signed private GET responses require exact integer `retCode`. Only `retCode == 0` is
API success. Top-level `status_code` is forbidden as an authority alias, including when `retCode`
is also present. V5 marker precedence is forbidden `status_code` alias, missing `retCode`, then
invalid `retCode` type. HTTP status `>= 400` remains failure even with `retCode == 0`.
When the JSON marker indicates API success, every HTTP status `>= 400` uses stable reason
`http_status_error`; retryability remains determined independently by the exact retryable HTTP
status allowlist.

Only the existing `_private_validate_post` path for exact `/v5/fgridbot/validate` may use the native
validate policy. It accepts exact integer `retCode`, exact integer `status_code`, or both. With both
present, `(retCode == 0) == (status_code == 200)` must hold. Compatible dual failures are ordinary
API errors; conflicting dual markers are envelope errors. HTTP status is independent transport
evidence and never substitutes for a missing JSON marker. The native response helper must reject
every noncanonical endpoint. Native marker precedence is missing marker, invalid marker type, then
dual-marker conflict; exact-string message checks follow marker-policy checks. Current production
source must contain exactly one call from the
prepared validate-only path. Frozen acceptance parses the complete `client.py` AST: the module may
contain exactly one attribute `.post` call; it must be `self.private_http.post`, inside
`BybitClient._private_validate_post`, assigned directly to `response`, with the canonical endpoint
positional argument and only exact `content=prepared.json_body` and `headers=headers` keywords.
That same method must contain the module's sole `self._handle_validate_response` call, assigned
directly to `data`, with exact canonical endpoint, `response`, and `"bybit_post_validate"`
arguments, followed by the method's sole `return data`. Comments, strings, duplicate or aliased
calls, decoy dispatches, and extra keywords are not dispatch evidence. The runtime canonical
endpoint constant must equal the literal `/v5/fgridbot/validate`. This AST evidence and the
existing protected validate-only transport suite jointly govern caller-payload preservation,
canonical serialization, and signing; the task's frozen AST check is not standalone payload
provenance.

Only an exact JSON `retCode == 10006` retains API-code retry authority. Native `status_code ==
10006` remains exposed as API evidence when it is the sole marker but never grants API-code retry
authority. Compatible dual failure with exact `retCode == 10006` does grant that authority.
Existing retryable HTTP statuses retain independent transport retry authority. String aliases never
reach success or retry logic.

## Safe typed errors

`BybitResponseEnvelopeError` must subclass `BybitAPIError` and expose an exact stable
`reason_code`. It may carry only a sanitized endpoint and exact HTTP status; it must not retain an
invalid body or marker value.

`BybitAPIError` must expose an allowlisted stable `reason_code`; arbitrary caller text cannot become
a reason. Its string contains only sanitized endpoint,
HTTP status, validated integer API code, and stable reason. It never interpolates upstream
`retMsg`, `debug_msg`, or response body. Message attributes and exact-dict response evidence are
redacted before storage. Constructor HTTP-status and API-code atoms that are booleans or outside
signed int64 are discarded. Non-exact-dict response evidence is discarded; exact-dict response
evidence is recursively redacted without claiming that ordinary nested atoms are type-filtered.
If recursive evidence redaction exhausts interpreter recursion, stored response evidence becomes
an empty dictionary while sanitized status, API code, reason, and retry metadata remain usable.
Exact top-level `rate_limit_headers` evidence is dropped from the stored exception response after
the existing limiter/statistics capture, so arbitrary header text cannot survive in string,
attributes, logs, or persistable evidence; limiter behavior is unchanged. Logging contains stable
structural evidence only. Sink-safe redaction from issue `#148` remains defense in depth.

## Downstream fail-closed rules

`smoke_private_account._status` classifies only `None` as `not-run`, and only an exact dictionary
with exact integer `retCode == 0`, no `error` key, no forbidden `status_code` alias, and exact-string
top-level message evidence when present as `ok`. Everything else is `error`.

`parse_validate_response` preserves HTTP status as separate evidence and never uses it as payload
success authority. It exposes `envelope_valid`. Missing, null, string, boolean, floating,
out-of-int64, or conflicting markers, plus non-string top-level message evidence or nested
`result.debug_msg`, force `envelope_valid=False`, `validate_ok=False`, all Bybit and user feasibility
flags false, and blocker `response_envelope_invalid` before investment blockers. Exact non-success
markers are valid failure envelopes, not malformed envelopes. Persistable rows retain marker and
HTTP atoms only when they are exact int64 values; invalid atoms become null. Param/schema semantics
are computed from local exact-string message values before exposure. Nonempty `retMsg` and
effective `debug_msg` values are redacted through the project redactor under their sensitive keys,
empty strings may remain empty, and invalid types become null. A Parquet round trip must contain no
raw message canary.

## Acceptance cases

The exact 24 frozen tests cover:

1. exact V5 integer success;
2. exact V5 integer API failure;
3. HTTP failure cannot be overridden;
4. exact-only retry code;
5. native `retCode` success;
6. native `status_code` success;
7. native marker failure;
8. compatible dual success;
9. compatible dual failure;
10. conflicting dual markers;
11. empty body;
12. whitespace and malformed JSON;
13. invalid UTF-8 without raw evidence;
14. duplicate top-level marker;
15. duplicate nested key;
16. non-finite JSON constants and overflowing finite-number spellings;
17. non-object roots;
18. missing marker on HTTP 2xx;
19. exact int64 `retCode` typing;
20. exact int64 native `status_code` typing;
21. forbidden V5 status alias;
22. exact string message evidence;
23. safe error attributes, rate-limit header evidence, text, logs, and persistence;
24. account/fgrid classifiers, canonicalized Parquet evidence, AST-exact validate-only dispatch,
    and forbidden generic POST.

The implementation must pass the exact frozen 24/24 suite and the complete ordinary suite on all
supported Python versions, Ruff, compile checks, protected-scope checks, and the unchanged
head/base/review gates before merge.
