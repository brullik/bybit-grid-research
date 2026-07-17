# Frozen task contract: P1 native grid validate result semantics

Task ID: `p1-native-grid-validate-result-semantics`
Issue: `#150`
Contract version: `native-grid-validate-result-v1`
RED sentinel: `native_grid_validate_result_contract_unavailable`
Activation baseline: `0fd6eb4b16ce3b0a211be66da3dc6963c4e60529`

This task freezes the conservative offline meaning of the native Bybit Futures Grid validate
`result` object and makes that meaning the sole authority for sweep resume, early stop, feasible
artifacts, and reporting. It does not claim that the frozen subset is equivalent to every current
or future Bybit response shape. Broader response shapes require a separately governed contract.

The two existing implementation paths at the activation baseline have these Git blob and raw-byte
SHA-256 identities:

- `scripts/validate_universe_fgrid_constraints.py`: Git blob
  `f2bc3e893a937a2b8a57fdd196300c3da85a732a`, SHA-256
  `530638ef7e350bcf03d8de327c2acb749e968850c5f70cda63f891e233bb05d8`
- `src/bybit_grid/bybit/fgrid_constraints.py`: Git blob
  `7c0ddb548ebf663696413dd1ea4dc2e5f4d25107`, SHA-256
  `7821e96db51ee65fbd8088643be9c73057b13f94690875299309c89ac5518656`

`tests/test_native_grid_validate_result_semantics.py` is a new implementation path and therefore
has no activation-baseline blob. Its final raw-byte SHA-256 is pinned by the frozen availability
gate.

## Exact implementation scope

The implementation PR must change exactly all three paths below and no others:

1. `scripts/validate_universe_fgrid_constraints.py`
2. `src/bybit_grid/bybit/fgrid_constraints.py`
3. `tests/test_native_grid_validate_result_semantics.py`

The implementation must preserve the legacy `parse_validate_response` entry point sufficiently to
keep the already-frozen issue `#149` acceptance contract green. The real sweep must use the new
strict entry point exclusively. This task does not authorize changes to the Bybit client, error
classes, endpoints, payloads, signing, retries, rate limits, validate-only boundary, settings,
candidate generation, `fgrid_min_sweep.py`, other tests, dependencies, workflows, PM enforcement,
create/close stubs, or any live execution.

## Availability gate and mandatory RED

The frozen suite contains exactly 18 plain synchronous tests. Every test's first statement is the
shared availability check. Availability requires:

- `bybit_grid.bybit.fgrid_constraints` to expose exactly
  `NATIVE_GRID_VALIDATE_RESULT_CONTRACT = "native-grid-validate-result-v1"`;
- the sweep script to contain exactly one top-level
  `STRICT_NATIVE_GRID_VALIDATE_SWEEP_CONTRACT = "native-grid-validate-result-v1"` assignment;
- the new ordinary test to contain exactly one top-level
  `NATIVE_GRID_VALIDATE_RESULT_TEST_CONTRACT = "native-grid-validate-result-v1"` assignment and
  to match its frozen raw-byte SHA-256.

The availability check parses the sweep source without importing it. Runtime sweep checks load the
exact repository file by path, install a controlled `scripts.build_universe` stub, and restore
`sys.path` and `sys.modules` after execution. This prevents the copied frozen suite's
`RUNNER_TEMP/scripts` directory from shadowing the repository script package.

From the task-definition merge, the mandatory inert comment-only probe must change all three exact
required implementation paths and only those paths. The new ordinary test path must contain only
inert probe content. On every supported Python matrix the probe must produce exactly 18 failures,
each terminating in
`RuntimeError("native_grid_validate_result_contract_unavailable")`. The probe must be closed
unmerged. Collection errors, unrelated failures, skips, xfails, partial required-path scope, or any
other failure reason do not satisfy RED.

## Conservative strict result schema

The outer response envelope remains governed by issue `#149`. For the new strict parser, an exact
outer success envelope is required. The separately supplied HTTP status may be absent only for the
normal successful client path or be the exact built-in integer `200`; booleans, strings, floats,
and every other HTTP value fail closed.

`result` must be an exact built-in dictionary. No top-level fallback, flattened aliases, dotted
aliases, mapping subclasses, or synthesized result are accepted. A successful result contains:

- exact built-in integer `status_code == 200`;
- exact built-in string
  `check_code == "FGRID_CHECK_CODE_UNSPECIFIED"`;
- exact built-in empty string `debug_msg == ""`;
- all nine exact built-in range dictionaries listed below, each containing both and only usable
  `from` and `to` bounds:
  `investment`, `cell_number`, `leverage`, `min_price`, `max_price`, `entry_price`,
  `stop_loss_price`, `take_profit_price`, and `profit`.

A present nonempty top-level `debug_msg` also rejects strict success even when the nested debug
message is empty. Upstream message text is not a secondary success authority.

Range bounds must be exact built-in finite decimal strings. Nulls, empty strings, booleans,
integers, floats, `Decimal` instances, string subclasses, NaN, sNaN, and infinities are invalid.
Finite decimal spellings that overflow to infinity or underflow to zero in the persisted numeric
representation are also invalid. Every range is inclusive and ordered. Investment is positive and
profit is nonnegative; cell counts are positive integral values; leverage and all prices are
positive. No incomplete or invalid range may leave any feasibility flag true.

The requested cell count, leverage, initial margin, minimum price, maximum price, and stop-loss
price must be finite, non-boolean local values. Cell count is integral; requested prices are
ordered with stop loss strictly below minimum and minimum strictly below maximum. Each requested
value must be inside its matching inclusive range: initial margin maps to `investment`, and the
other five fields map to their same-named ranges. The user target of exactly 5 USDT must also be
inside the complete investment range; checking only the lower investment bound is forbidden.
If requested metadata is invalid or any requested value is outside its range, every membership and
feasibility flag, including `target_init_margin_inside_validate_range`, is false. The diagnostic
`validate_ok` may remain true in that case when the envelope and native result themselves are a
complete exact success; it is not standalone feasibility authority.

Every row emitted by the strict parser carries the exact
`native_grid_validate_result_contract` marker and exact boolean `result_schema_valid`. A row is
admitted as current feasible evidence only when schema, status/check/debug semantics, every
requested-value range check, and the 5 USDT check all pass. An admitted row has all feasibility
flags literally `True` and `blocker_reason is None`. Missing, unknown, malformed, rejected, or
out-of-range evidence cannot inherit authority from a legacy boolean.

Blocker precedence and exact codes are:

1. `response_envelope_invalid`
2. `native_result_schema_invalid`
3. `native_check_rejected`
4. `requested_values_outside_validate_ranges`
5. `min_investment_gt_5usdt`
6. `None` for admitted strict success

## Bounded structured error evidence

Sweep exceptions must use the sanitized structured `BybitAPIError.response_data` evidence when it
exists. Legacy `.payload`, `str(exc)`, raw response bodies, traceback text, and arbitrary exception
attributes are forbidden as persisted evidence.

`build_strict_validate_error_evidence` returns an exact dictionary with top-level keys
`reason_code`, `http_status_code`, `retCode`, `retMsg`, `debug_msg`, and `response_data`.
`response_data` may retain only `retCode`, `status_code`, `retMsg`, and `result`; nested `result`
may retain only `status_code`, `check_code`, and `debug_msg`. Codes and markers retain only their
strict safe types. Arbitrary message/debug text is redacted; ranges, raw payloads, secrets, and
unknown fields are dropped. Canonical compact sorted JSON must be at most 1024 UTF-8 bytes.

The parser persists this projection as canonical compact sorted JSON in `error_evidence_json`, or
null for no error. Optional flat safe error columns are not admission evidence. Raw or redacted
file paths remain paths only and never substitute for structured validation evidence.

## Sweep authority

The sweep script must:

- parse both successful and exception responses only with `parse_strict_validate_response`;
- project exceptions only with `build_strict_validate_error_evidence` and never stringify them;
- remove or quarantine rows without the exact current contract before resume or output use;
- let resume suppress only current-contract rows with a complete accepted native result, never
  legacy, envelope-invalid, result-schema-invalid, or native-check-rejected rows;
- append and deduplicate through the strict persistence entry point;
- pass only strict 5-USDT-feasible admitted rows to the existing legacy early-stop helper;
- select report and metric input through `strict_constraint_records`, rejecting legacy rows and
  selector-shaped forgeries that omit the complete strict parser schema;
- select current feasible rows only through `strict_feasible_constraints`, which requires the
  exact contract marker, all required boolean flags literally true, and null blocker;
- return an empty feasible selection, rather than raising or trusting data, when required columns
  are absent;
- generate `fgrid_feasible_configs.parquet` and the constraints report from the strict selection,
  excluding legacy, partial, spoofed, or blocked rows.

Before a real sweep, stale derived feasible/report outputs must be reset. Normal completion and
`KeyboardInterrupt` flushing must regenerate derived outputs only through the strict selectors, so
an older legacy artifact or report cannot survive as apparently current evidence.

No private credential, account, network, Bybit, or live execution is required or authorized by
this acceptance suite.

## Acceptance cases

The exact 18 frozen tests cover:

1. the complete conservative official-example-shaped success;
2. rejection of top-level fallback and flattened aliases;
3. complete required result fields and range bounds;
4. exact nested status/check success pair plus outer/HTTP failure;
5. exact empty nested debug message and rejection of nonempty top-level debug evidence;
6. exact finite decimal-string range atoms;
7. ordered and domain-valid bounds;
8. finite, non-boolean requested metadata and price ordering;
9. each requested value inside its named range;
10. inclusive edges and integral grid count;
11. exact 5 USDT membership in the complete investment range;
12. all feasibility flags false for invalid result evidence;
13. deterministic blocker precedence and exact row contract marker;
14. bounded, structured, redacted error evidence and canonical persistence;
15. strict sweep parser dispatch and structured exception handling;
16. resume and preparation exclude legacy and retry invalid evidence;
17. early stop only after strict admitted 5 USDT success;
18. strict-record, feasible artifact, report, and stale-output handling exclude legacy or partial
    rows.

The implementation must pass the exact frozen 18/18 suite and the complete ordinary suite on all
supported Python versions, Ruff, compile checks, protected-scope checks, and unchanged
head/base/review gates before merge.
