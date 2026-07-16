# P0 — fail-closed signed private transport and validate-only POST boundary

## Scope and authority

This release-blocking task closes issue #130 before any owner credential or private-API run.
It implements a fail-closed boundary for three existing read-only signed GET operations and the
sole authorized private POST, Bybit Futures Grid validation. It does not authorize executing
any private operation during development, CI, acceptance, or autonomous maintenance.

The complete implementation scope is exactly these eight required paths:

- `src/bybit_grid/bybit/validate_only.py` (new);
- `src/bybit_grid/bybit/client.py`;
- `src/bybit_grid/bybit/fgrid_payloads.py`;
- `src/bybit_grid/common/source_safety_audit.py`;
- `src/bybit_grid/config.py`;
- `scripts/validate_sample_grid.py`;
- `scripts/validate_universe_fgrid_constraints.py`;
- `tests/test_sprint_01_5_hotfix.py`.

The ordinary-test path is a mandatory non-weakened migration of its obsolete generic private
transport success tests. No package export, configuration, environment example, dependency,
other ordinary test, workflow, checker, frozen contract, or other source/script path may change.

The task grants no network, DNS, HTTP, credential, secret, account, wallet, position, Telegram,
ordinary-order, withdrawal, transfer, native-grid create/close, or live-execution authority.
Frozen tests use only in-memory fakes. Green code is a prerequisite, not permission to supply
credentials or run a private request.

## Exact destinations and operations

The sole admitted environment and origin are exact built-in strings:

```text
mainnet
https://api.bybit.com
```

The complete signed private GET allowlist, in exact tuple order, is:

```text
/v5/account/info
/v5/account/wallet-balance
/v5/account/fee-rate
```

The sole private POST target is the exact built-in string:

```text
/v5/fgridbot/validate
```

A canonical relative path on any other origin is forbidden. A hostile `BYBIT_API_BASE_URL`
must never receive signed headers. No normalization, parsing, trimming, joining, prefix/suffix
matching, case folding, environment fallback, redirect-derived authority, or alias is accepted.

## Exact policy module

`bybit_grid.bybit.validate_only` has exact `__all__`:

```python
(
    "CANONICAL_BYBIT_ENV",
    "CANONICAL_BYBIT_API_BASE_URL",
    "CANONICAL_PRIVATE_GET_ENDPOINTS",
    "CANONICAL_FGRID_VALIDATE_ENDPOINT",
    "CANONICAL_FGRID_GRID_MODE_NEUTRAL",
    "CANONICAL_FGRID_GRID_TYPE_GEOMETRIC",
    "ValidateOnlyBoundaryError",
    "enforce_validate_only_settings",
    "enforce_private_get_request",
    "enforce_validate_only_payload",
)
```

`ValidateOnlyBoundaryError` is a `PermissionError`. Constants have the exact built-in types and
values above; neutral mode is exact integer `1`, geometric type exact integer `2`. Guards have
exact keyword-only signatures:

```python
enforce_validate_only_settings(*, settings)
enforce_private_get_request(*, endpoint, params)
enforce_validate_only_payload(*, payload)
```

They return `None` on success and otherwise raise a stable group. The module imports no
environment, filesystem, network, HTTP, signing, retry, rate-limit, subprocess, clock,
randomness, or concurrency module and performs no import-time calls. Client and payload modules
capture the original guards and constants at import; later rebinding of the public policy names
does not weaken them.

## Exact settings and host guard

`settings` has exact type `bybit_grid.config.Settings`; subclasses and duck types are
`validate_settings_not_exact`. Accepted policy state is exactly:

- `bybit_env`: exact `str` `mainnet`;
- `bybit_api_base_url`: exact `str` `https://api.bybit.com`;
- `bybit_fgrid_validate_path`: exact `str` `/v5/fgridbot/validate`;
- `bybit_fgrid_grid_mode_neutral`: exact non-boolean `int` `1`;
- `bybit_fgrid_grid_type_geometric`: exact non-boolean `int` `2`;
- `bybit_recv_window`: exact non-boolean `int` `5000`;
- `grid_validate_enabled`: exact `bool`, either `False` or `True`;
- `live_trading_enabled`: exact `bool` `False`;
- `allow_live_trading`: exact `str` `NO`.

Failure precedence is:

```text
validate_settings_not_exact
validate_environment_forbidden
validate_api_base_url_forbidden
validate_endpoint_forbidden
validate_grid_mode_forbidden
validate_grid_type_forbidden
validate_recv_window_forbidden
validate_enabled_flag_invalid
validate_live_authority_forbidden
```

Origin rejection includes testnet/demo aliases, HTTP, alternate/lookalike/userinfo hosts, ports,
trailing slash, path/query/fragment, scheme-relative origin, localhost/IP/custom origins,
`None`, bytes, and `str` subclasses. Endpoint rejection includes empty/whitespace text, missing
leading slash, doubled slash, dot segments, trailing slash, case variants, absolute/scheme-
relative URLs, query/fragment variants, create/close/detail/order/wallet/position/withdraw paths,
`None`, bytes, dynamic alternatives, and `str` subclasses.

Noncanonical `BYBIT_ENV`, `BYBIT_API_BASE_URL`, `BYBIT_FGRID_VALIDATE_PATH`,
`BYBIT_FGRID_GRID_MODE_NEUTRAL`, `BYBIT_FGRID_GRID_TYPE_GEOMETRIC`,
`BYBIT_RECV_WINDOW`, `GRID_VALIDATE_ENABLED`, `LIVE_TRADING_ENABLED`, or
`ALLOW_LIVE_TRADING` therefore fails before credentials, signing, rate limiting, retry, or
HTTP. Values are not ignored, repaired, or forwarded.

`config.py` removes the unused create/close/detail endpoint fields; ignored legacy environment
variables cannot become runtime attributes. It retains the validate path so a noncanonical
override is detected and refused rather than silently ignored. The neutral/geometric/receive-
window settings are exact `int` fields (not unions). Before Pydantic coercion, each accepts only
an exact non-boolean built-in `int` or canonical unsigned decimal text (`0` or a nonzero digit
followed by digits); leading zeroes, sign, decimal point, exponent, whitespace, bytes,
subclasses, booleans, and all other aliases are configuration validation errors. Canonical
environment text `1`/`2`/`5000` parses to exact integers; other canonical integers reach the
policy guard and fail its corresponding stable group.

Before Pydantic coercion, `grid_validate_enabled` and `live_trading_enabled` accept only exact
built-in booleans or exact lowercase environment text `true`/`false`. Numeric, case, whitespace,
`yes`/`no`, and `on`/`off` aliases are configuration validation errors. The policy then permits
either exact grid-validation boolean but only exact false live-trading authority.

`BybitClient.__init__` constructs a public client and a separate `private_http` client. The
private client has the literal canonical base origin and cannot inherit a caller-selected
origin. Both are constructed with exact
`httpx.Client(..., trust_env=False, follow_redirects=False)`. `HTTP_PROXY`,
`HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, and `SSL_CERT_DIR` cannot configure its
proxy or TLS trust, and redirects cannot move a signed request. Both explicit exact-false
keywords are mandatory; relying on defaults fails. Before preparation and again before each
signed attempt, `private_http.base_url` must be the canonical HTTPS origin; drift is
`private_http_origin_forbidden` before credentials on the outer boundary and before signing on
a retry. The rate limiter is an untrusted call boundary: after every `rate_limiter.wait()` and
immediately before the matching relative-path HTTP dispatch, the actual private-client origin is
checked again. If the limiter or any concurrent callback changes the origin, that attempt raises
`private_http_origin_forbidden` and performs no HTTP call; signed headers are never delivered to
the changed origin for either GET or POST. At the same outer, per-attempt, and post-limiter
checkpoints, the private client's effective redirect policy must remain exact false and its owned
trust-environment policy must remain exact false. Replacement or mutation to a redirect-following
or environment-trusting transport is `private_http_policy_forbidden` before dispatch. In
particular a 307 response can never carry `X-BAPI-*` headers to another origin.

## Exact signed private GET boundary

`private_get(endpoint, params=None)` is an undecorated preparation boundary. `endpoint` must be
an exact built-in `str` member of `CANONICAL_PRIVATE_GET_ENDPOINTS`; every absolute, query,
fragment, alias, dynamic other path, subclass, or malformed value is
`private_get_endpoint_forbidden` before settings/credentials/retry.

`params` is normalized from `None` to a newly owned exact empty `dict`; otherwise it must already
be an exact built-in `dict` with exact built-in `str` keys and values. Endpoint schemas are:

- `/v5/account/info`: exact empty mapping;
- `/v5/account/wallet-balance`: exact `{"accountType":"UNIFIED"}`;
- `/v5/account/fee-rate`: exact `{"category":"linear"}` or that mapping plus `symbol`.

Fee `symbol`, when present, is exact built-in `str`, 2–32 ASCII uppercase letters/digits, and
ends in `USDT`. Missing, extra, subclassed, boolean, nested, list, alternate category/account,
or otherwise malformed parameters are `private_get_params_forbidden`.

After endpoint/params and settings guards, credentials are required exactly once. The canonical
query string and approved environment/origin/API key/API secret/receive-window values are
snapshotted into one factory-only immutable private prepared request before tenacity. Caller
params and mutable settings are never read by a retry. `_private_get(self, prepared)` is the only
retry-decorated signed GET helper and has no endpoint, params, settings, environment, origin, or
credential argument. It rejects a foreign/subclassed/malformed prepared value as
`private_get_prepared_request_invalid` before signing/rate limiting/HTTP and always sends the
same exact path-plus-query with `params=None` and the same credential snapshot.

Factory issuance is an instance-bound, single-public-call capability rather than module-global
authorization. Only the exact `BybitClient` instance that issued a prepared GET may use it. The
capability remains valid across all internal attempts of that one decorated retry call, then the
outer `private_get` boundary consumes it in a `finally` path on either success or failure. A
cross-client use or any second helper invocation with the captured object is
`private_get_prepared_request_invalid` before signing, rate limiting, or HTTP.

Python's `object.__setattr__` can bypass a frozen dataclass, so issuance also retains an external,
client-owned immutable reference snapshot of every prepared atom. Before every retry attempt, the
helper compares the exact current object and all fields with that external snapshot. A different
still-schema-valid query and matching request target is therefore
`private_get_prepared_request_invalid` before signing, rate limiting, or HTTP. The external record
is removed in the same outer `finally` that consumes the capability.

## Exact validate payload and SL-only schema

`payload` must be an exact built-in `dict`. Subclasses/other mappings are
`validate_payload_not_exact_dict`. Its exact built-in-string key set is:

```text
symbol
leverage
grid_mode
grid_type
min_price
max_price
cell_number
init_margin
stop_loss_price
```

Missing, extra, subclassed, or malformed keys are `validate_payload_keys_invalid`. In
particular every take-profit, side/direction, create/close/order, callback, URL, and retry key is
forbidden; V1 is stop-loss-only.

- `symbol`: exact `str`, 2–32 ASCII uppercase letters/digits ending `USDT`, otherwise
  `validate_payload_symbol_forbidden`;
- `leverage`, `min_price`, `max_price`, `init_margin`, `stop_loss_price`: exact built-in strings
  in canonical positive decimal grammar (no sign, exponent, whitespace, leading zero alias, or
  redundant trailing fractional zero), otherwise `validate_payload_decimal_forbidden`;
- `grid_mode`: exact `int` `1`, otherwise `validate_payload_grid_mode_forbidden`;
- `grid_type`: exact `int` `2`, otherwise `validate_payload_grid_type_forbidden`;
- `cell_number`: exact non-boolean `int` in `[2,100]`, otherwise
  `validate_payload_cell_number_forbidden`;
- exact decimals satisfy `0 < stop_loss_price < min_price < max_price`, otherwise
  `validate_payload_geometry_forbidden`.

`build_fgrid_validate_payload` removes caller `grid_mode`/`grid_type`, guards current settings,
and emits exact fixed integers `1`/`2` and the exact schema. Caller alternatives fail by
signature; malicious environment alternatives fail by the settings groups instead of changing
output.

## Exact validate POST call graph and retry snapshot

`validate_grid_bot(self, payload)` has no endpoint/path/URL, environment, mode/type,
runtime-live, retry, or transport argument. It performs: exact settings guard; exact payload
guard; existing disabled result for exact `grid_validate_enabled is False`; one credential
check; one deterministic serialization; one immutable prepared-request snapshot; then
`_private_validate_post(prepared)`.

`_private_validate_post(self, prepared)` has no endpoint/path/URL, mutable payload, settings,
environment, origin, or credential parameter. It is the only function allowed to call
`self.private_http.post`. Before signing it verifies exact private prepared type, factory-issued
identity, and all snapshot atoms,
parses the immutable JSON body, and reruns the payload guard. Foreign/subclassed/malformed values
are `validate_prepared_request_invalid` before signing/rate limiting/HTTP. It signs only the
snapshotted key/secret/receive window and POSTs only
`CANONICAL_FGRID_VALIDATE_ENDPOINT`.

One retryable call performs one credential check and up to four signing/rate-limit/HTTP attempts
over identical endpoint, origin policy, body bytes, API key/secret, and receive window. Mutating
the caller payload or `Settings` after the first failure cannot change later attempts.

Validate prepared issuance has the same instance-bound, single-public-call lifetime. It remains
valid for every internal attempt of exactly one `_private_validate_post` retry call and is
consumed by `validate_grid_bot` in a `finally` path after that retry call finishes. Another client
or any later helper invocation receives `validate_prepared_request_invalid` before signing, rate
limiting, or HTTP. No module-global issuance registry may authorize either prepared type.

The immutable snapshot still contains the exact API key and secret required for internal retries,
but both dataclass fields have `repr=False`; neither credential value may appear in `repr` of a
prepared GET or validate object. The capability is not retained beyond its one public call by an
issuance registry.

Validate issuance likewise retains and checks an external exact reference snapshot on every
attempt. Mutating the frozen object's JSON body to a different but otherwise valid payload between
retry attempts is `validate_prepared_request_invalid` before signing, rate limiting, or HTTP. The
reference snapshot and capability record are removed after both successful and failed outer calls;
they remain available only long enough to authorize internal retries.

`private_post(self, endpoint, body)` remains only as an undecorated compatibility refusal. After
an optional docstring its exact sole statement is:

```python
raise ValidateOnlyBoundaryError("generic_private_post_forbidden")
```

It rejects even the canonical endpoint without inspecting values or calling credentials,
signing, rate limiting, retry, HTTP, or a helper. External callers use `validate_grid_bot`.

## Script, mutation-stub, and audit boundaries

No `scripts/` file calls or dynamically looks up `private_post`. `validate_sample_grid.py` calls
`client.validate_grid_bot(payload)`, never reads/forwards `bybit_fgrid_validate_path`, and uses
the captured canonical constant only as report metadata. Immediately after `load_settings`, and
before `_refusal_reason`, timestamps, output-path/filesystem work, payload-file reads, payload
construction, `BybitClient`, or dynamic public requests, `main` calls the captured exact settings
guard. Its first handler for a `try` containing `validate_grid_bot` is an explicit
`except ValidateOnlyBoundaryError: raise`; a broad handler may report other failures but must not
convert or swallow a boundary refusal.

For non-dry-run operation, `validate_universe_fgrid_constraints.py` loads one authority settings
object and executes the captured exact settings/origin-value policy preflight before its explicit
credential check, filesystem planning, or `ThreadPoolExecutor` construction. Synchronous planning
may call `build_min_sweep_candidates`, whose payload builder reloads and guards current settings;
all such planning and guarded reloads finish before the thread pool is constructed. The resulting
immutable-by-ownership candidate lists and the already-preflighted authority settings object are
passed explicitly to every `_validate_symbol` worker, then that exact settings parameter is passed
to `BybitClient`.

A worker must not directly or indirectly call `load_settings`, `Settings`,
`build_min_sweep_candidates`, or `build_fgrid_validate_payload`, read `os.environ`, or otherwise
reload configuration. Its first handler around `validate_grid_bot` is
`except ValidateOnlyBoundaryError: raise` before any broad handler. Every worker still enters the
same guarded client boundary; unchecked environment values and swallowed policy refusals cannot
reach or remain inside a thread.

`--purge-skipped-constraints` is a local maintenance operation and does not require private
credentials, but it is not a dry run: `main` must load the authority settings object and execute
the same captured exact settings/origin policy preflight before calling
`purge_skipped_constraints` or performing any purge filesystem work.

`create_grid_bot` and `close_grid_bot`, after an optional docstring, each have exactly one direct
`raise NotImplementedError(...)`, no decorator, call, branch, nested decoy, credential/signing/
retry/HTTP access, or following statement. Ordinary-order create/amend/cancel, withdrawal,
transfer, wallet mutation, position mutation, and live-execution methods remain absent.

`audit_source_tree` accepts the completed real tree and rejects without literal recovery:

- direct `.private_post(...)`: `generic private_post call is forbidden`;
- `getattr(..., "private_post")`: `dynamic lookup of private_post is forbidden`;
- HTTP `.post(...)` outside canonical client helper:
  `HTTP POST outside canonical client transport is forbidden`;
- endpoint/path/URL input or noncanonical target in the retry POST helper:
  `canonical validate transport shape is required`;
- non-immediate create/close stub:
  `<method> must be immediate unconditional NotImplementedError stub`.
- universe validation credential/thread setup before exact policy preflight:
  `validate universe policy preflight must precede credentials and threads`.
- universe worker configuration reload or environment access:
  `validate universe workers must use preflighted settings`.
- sample preflight after refusal/filesystem/client/public work:
  `validate sample policy preflight must precede side effects`.
- broad handler that can swallow a validate-only boundary refusal:
  `validate-only boundary error must be re-raised before broad handler`.

Adversarial AST covers dynamic endpoint variables, direct/raw transport, absolute/query targets,
and nested/unreachable/misordered `NotImplementedError`. Script preflight recognition is likewise
control-flow structural rather than line-number-only: a guard beneath `if False`, a conditional or
nested decoy that does not dominate every protected path, or a guard after a purge is rejected.

## Mandatory ordinary-test migration

Pre-task `tests/test_sprint_01_5_hotfix.py` expects arbitrary `/v5/private` GET and successful
generic `private_post` through `https://example.test` with an incomplete payload. These are the
vulnerable expectations. The same implementation PR must preserve and strengthen their intent:

- private GET signing test uses canonical mainnet origin, one exact allowlisted endpoint/schema,
  and still proves the canonical query signed is exactly the query sent;
- generic POST becomes an exact refusal/no-side-effect test;
- a validate success test uses canonical mainnet, complete exact neutral/geometric SL-only
  payload, in-memory fake HTTP, and proves the exact serialized bytes signed are the bytes sent,
  plus endpoint and content type;
- the three unrelated data-quality/redaction tests remain behaviorally unchanged.

No test is deleted, skipped, xfailed, broadly caught, or replaced by label/type-only padding.
The migrated file contains at least the original five behaviors plus generic refusal.

## Frozen lifecycle and exact RED

The frozen file has no skip, xfail, importorskip, broad `pytest.raises`, broad exception handler,
or parameterization. Every fixed node first resolves the new module. Both a missing module and a
comment-only probe make every node fail in the call phase with exactly:

```text
validate_only_boundary_unavailable
```

No collection/import/setup/fixture failure is allowed. Record that exact all-node RED on a fresh
`probe/` PR. Because all eight implementation paths are required by scope, the probe changes
exactly all eight without behavior: the new module contains only
`# RED probe only: validate_only_boundary_unavailable`, and each existing required file receives
only `# RED probe only: no behavior`. This makes scope green while all 28 frozen nodes fail only
at `_api()` with the sentinel; ordinary and supplemental checks remain otherwise green. Close
that probe unmerged. Implement from fresh `main`, change all and only the eight
required paths, make frozen/ordinary/supplemental checks green, and close the task in a separate
PM transition.

## Required verification

```bash
python -m compileall -q pm_acceptance/tasks/p0-fail-closed-private-transport
python -m pytest pm_acceptance/tasks/p0-fail-closed-private-transport -q
python scripts/check_no_live_execution.py
python -m pytest -q
python -m compileall -q src tests scripts
ruff check src tests scripts
```

No command authorizes a credential, private-API, or network run.
