# Frozen task contract: P0 range reference/fast configuration parity

Task ID: `p0-range-reference-fast-config-parity`
Issue: `#155`
Contract version: `range-reference-fast-config-parity-v1`
RED sentinel: `range_reference_fast_config_parity_contract_unavailable`
Audit source baseline named by issue `#155`: `f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`
Task-definition base: `0e2874d7ee309c3dc3d9f14ea7e7209c8a59576f`

This task removes a P0 research-validity defect: the existing “reference versus fast” test reaches
the fast implementation through both sides, the fast core hard-codes zone thresholds, and the
production builder drops its advertised zero-volume setting. The task freezes two independently
executed offline implementations with the same complete-window configuration semantics. It grants
no network, credential, Bybit, live, order, grid, position, wallet, Telegram, or trading authority.

## Exact implementation scope

The implementation PR must change all and only these six paths:

1. `scripts/build_range_candidates.py`
2. `src/bybit_grid/research/range_detector.py`
3. `src/bybit_grid/research/range_core/adapter.py`
4. `src/bybit_grid/research/range_core/numpy_fast.py`
5. `src/bybit_grid/research/range_core/python_reference.py`
6. `tests/test_range_reference_fast_config_parity.py`

No profile table, candidate/actionable semantics, dependency, workflow, PM checker, configuration
file, persisted artifact, report schema, private/public transport, execution, or historical branch
change is authorized.

The existing callable shapes remain available. In particular,
`numpy_fast.detect_ranges(..., lookbacks=...)` remains keyword-compatible, and the adapter accepts
legacy calls that provide only `lookbacks`. A supplied full config must have exactly the same
lookbacks as the positional value or fail closed.

## Availability gate and mandatory RED

The frozen suite contains exactly 29 collected nodes. Every complete `test_*` function has
`_available()` as its first statement. Availability requires one exact top-level literal
assignment in each of the five production paths:

```python
RANGE_REFERENCE_FAST_CONFIG_PARITY_CONTRACT = "range-reference-fast-config-parity-v1"
```

The ordinary test must contain exactly one top-level literal assignment:

```python
RANGE_REFERENCE_FAST_CONFIG_PARITY_TEST_CONTRACT = "range-reference-fast-config-parity-v1"
```

Its complete raw bytes are pinned at SHA-256
`46d5c2b47048145345eaa92d2159752281a1229e3e5323e36d0853b3ef538f7d`.

After task-definition merge, the mandatory fresh `probe/` PR changes every required path and no
other path. The five existing production paths receive inert comment-only changes; the new
ordinary-test path contains inert probe content only. On each supported Python matrix, the probe
must yield exactly 29 failures, each terminating in
`RuntimeError("range_reference_fast_config_parity_contract_unavailable")`, with zero frozen
passes and no unrelated failure, collection/setup/teardown error, skip, xfail/xpass, or
deselection. The probe remains Draft and is closed unmerged.

## Direct independent parity

Acceptance imports and calls `python_reference.detect_from_frame()` directly and separately calls
`numpy_fast.detect_ranges()` over arrays made from the same frame. Calling the production fast
wrapper on both sides, aliasing one implementation to the other, or comparing only candidate IDs
does not satisfy the contract.

For every deterministic fixture:

- emitted column order, row order, row count, nullable shape, strings, integers, booleans and
  identifiers match exactly;
- every finite floating field matches with absolute and relative tolerance `1e-12`;
- NaN is equal only to NaN and may not be introduced by accepted normalized volume/turnover data;
- every key in `FUNNEL_KEYS` is an integer and the complete funnel dictionaries match exactly;
- the direct reference result equals its instrumented reference-with-funnel result.

The frozen suite covers baseline, reversed input, aliases, missing turnover, empty/short input,
seeded adversarial randomized frames and all advertised configuration boundaries.

## Versioned DetectionConfig semantics

All numeric fields reject booleans, strings, nulls, NaN and infinities with stable `ValueError`.

- `lookbacks` is a nonempty tuple of unique positive integers and controls both cores.
- `lower_zone_pct`, `mid_zone_pct`, and `upper_zone_pct` are finite values in `[0, 1]`.
  Exact-mid `mid_zone_pct=0` remains supported. The same values control both cores.
- `min_valid_candle_pct` is explicitly versioned to exactly `1.0`; other values fail closed.
  The v1 detector does not silently reinterpret a row-count window as a partial time window.
- `max_zero_volume_window_pct` is in `[0, 1]`; the effective threshold is the stricter of config
  and profile. The CLI builder constructs the full config, passes it through the adapter, and
  records the effective requested value in dry-run/performance evidence.
- `min_range_height_pct` is finite and nonnegative; the effective minimum is the stricter of
  config and profile.
- `profile_name` is a nonempty string. With no explicit profile it must name an exact registered
  profile; there is no silent broad-profile fallback. An explicitly supplied `RangeProfile`
  remains authoritative, including a custom profile.

## Complete minute grid and funnel ownership

A window is complete only when all of the following hold after stable timestamp sorting:

1. endpoint span equals `(lookback - 1) * 60_000`;
2. all timestamps are unique;
3. every adjacent internal step equals exactly `60_000`.

No epoch-modulo alignment is required. Endpoint mismatch is owned by
`missing_window_rejection_count`; an in-window duplicate is then owned by
`duplicate_timestamp_rejection_count`; any remaining non-minute internal step is owned by
`missing_window_rejection_count`. A duplicate immediately before but outside a window must not
poison that window. Other rejection stages retain the declared funnel order, and a window is
counted by only its first rejecting stage.

## Nullable data, ATR recovery, and stable aggregates

Present null, nonfinite or nonpositive volume is normalized to zero and counted as zero-volume.
Present null, nonfinite or negative turnover is normalized to zero. Missing volume retains the
existing synthetic default of one; missing turnover retains zero.

True range has one explicit policy:

- invalid current high/low envelope yields invalid TR;
- valid current high/low with invalid previous close uses `high - low`;
- otherwise standard true range is the maximum of the three usual terms.

Rolling ATR requires a fully finite 14/60-value window and recovers once invalid TR leaves that
window. Both cores use stable slice-local summation for ATR; a large finite historical TR outside
the rolling window cannot change an ATR threshold decision through prefix-sum cancellation. A bad
historical row outside the candidate lookback must not poison all future ATR values. Accepted
window volume and turnover aggregates likewise use stable slice-local summation, not subtraction
from a catastrophically cancelled global prefix sum. Dynamic-range fixtures prove that later
windows recover exact finite sums after a `1e20` prefix.

Log returns are computed as `log(current) - log(previous)` for finite positive closes, without
forming an overflowed or underflowed price ratio first. Midline-cross classification uses direct
side comparisons and does not multiply extreme finite price differences.

## Safety boundary

All frozen and ordinary acceptance uses synthetic in-memory frames and monkeypatched builder
boundaries. It performs no filesystem publication, public/private request, credential read, Bybit
call, order/grid operation, live execution, Telegram action, or external mutation. Existing builder
I/O authority is neither expanded nor exercised.
