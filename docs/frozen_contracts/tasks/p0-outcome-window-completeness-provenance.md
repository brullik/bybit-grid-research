# Frozen task contract: P0 exact outcome-window completeness and provenance

Task ID: `p0-outcome-window-completeness-provenance`
Issue: `#158`
Contract version: `outcome-window-completeness-provenance-v1`
RED sentinel: `outcome_window_completeness_provenance_contract_unavailable`
Audit source baseline named by issue `#158`: `f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`
Task-definition base: `79488e9d5d189360b727df756aabcc1873e1a62d`

This task removes a P0 research-validity defect: row count can currently masquerade as a complete
one-minute outcome horizon, incomplete horizons retain categorical claims, and the fast output can
overwrite event/range provenance. The task freezes one fail-closed v5 outcome-row contract shared
by both cores, semantic audit, and summaries. It grants no network, credential, Bybit, live, order,
grid, position, wallet, Telegram, or trading authority.

## Exact implementation scope

The implementation PR must change all and only these eight paths:

1. `src/bybit_grid/research/outcome_core/outcome_numpy.py`
2. `src/bybit_grid/research/outcome_core/outcome_fast.py`
3. `src/bybit_grid/research/outcome_semantics.py`
4. `src/bybit_grid/research/outcome_summary.py`
5. `scripts/audit_outcome_semantics.py`
6. `tests/test_sprint_04_candidate_outcomes.py`
7. `tests/test_sprint_04_7_input_equivalence.py`
8. `tests/test_outcome_window_completeness_provenance.py`

`outcome_semantics.py` and the last test path are new. No outcome store, scoring grain, range-event
producer, workflow, dependency, PM checker, historical artifact, transport, live-execution, or
historical branch change is authorized. Persisted scoring-grain propagation remains issue `#156`.
Physical refusal to append into an existing run is not promised here: a reviewable run must use a
new immutable `outcome_run_id`, and the shared validator rejects legacy-only, mixed v4/v5,
duplicate-composite, or duplicate-ID rows before audit or summary acceptance.

## Availability gate and mandatory RED

The frozen suite contains exactly 96 collected nodes: one harness node and 95 embedded ordinary
nodes. Every complete `test_*` function calls `_available()` as its first statement. Availability
requires one exact top-level literal assignment in each of the five production paths:

```python
OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)
```

The ordinary test requires one exact top-level literal assignment:

```python
OUTCOME_WINDOW_COMPLETENESS_PROVENANCE_TEST_CONTRACT = (
    "outcome-window-completeness-provenance-v1"
)
```

Its complete UTF-8/LF raw bytes are embedded once as `ORDINARY_TEST_SOURCE` and pinned at SHA-256
`fa24ab7fabe36199b7fd62224f1d321cb052b5036ea47f4a018301576933e29f`.
The complete frozen-suite raw bytes are SHA-256
`79bd489b9cc882fa0f3217c9c681f16db511bcd16a9b459ba74d59d5f947e7d0`.

After task-definition merge, a mandatory fresh Draft `probe/` PR changes all eight required paths
and no others. The four existing production paths receive inert comment-only edits; the new shared
semantic module contains inert probe content; the two existing test paths receive inert comments;
and the new ordinary-test path contains inert probe content. On every supported Python matrix the
frozen suite must yield exactly 96 sentinel failures, zero frozen passes, and no unrelated failure,
collection/setup/teardown error, skip, xfail/xpass, or deselection. Ordinary/control suites must
remain green. The probe is closed unmerged and is never marked Ready.

## Authoritative causal and profile provenance

Authoritative v5 rows use:

- `outcome_semantics_version = "v5_exact_outcome_window_provenance"`;
- `outcome_window_semantics_version = "exact-minute-outcome-window-v1"`;
- `actionable_event_semantics_version = "range-actionable-prefix-invariance-v1"`;
- exact nonnegative integer `decision_time_ms == signal_time_ms`;
- `decision_time_source = "event_decision_time"` and
  `causal_provenance_complete_bool = True`;
- `entry_time_ms` equal to the first minute boundary strictly after the decision, and
  `outcome_end_exclusive_ms = entry_time_ms + horizon * 60_000`;
- nonblank event ID, symbol, regime ID, range/outcome run IDs, event range profile, and outcome
  profile, with `profile_name == range_profile_name` and valid `low < mid < high` range bounds.

The current canonical actionable-event producer emits equal decision and signal times. Explicit
mismatch, negative/noninteger time, unsupported upstream version, or a versioned event missing its
decision/profile fails closed. The legacy direct-call compatibility path may derive decision from
an unversioned signal, but it is marked `legacy_signal_fallback`, remains non-authoritative v4, and
cannot pass the shared audit or summary gate. The v5 semantic and exact-window versions both enter
the deterministic outcome-ID material; `outcome_match_key` remains stable for cross-version joins.

## Exact minute grid and diagnostics

For positive exact-integer horizon `h`, the only expected candle timestamps are
`{entry + k * 60_000 | 0 <= k < h}`. Completeness and future-outcome eligibility are true only
when every expected timestamp appears exactly once and there are no in-window off-grid rows,
duplicate timestamps, invalid timestamp dtypes, or invalid OHLC rows. A nullable candle timestamp
rejects the computation; a fractional/float timestamp column cannot be truncated into the grid.

Any nonempty candle frame missing `open`, `high`, `low`, or `close` is rejected identically by both
cores. A completely empty frame remains an explicit missing window. The OHLC envelope requires
finite positive open/high/low/close values and
`low <= min(open, close) <= max(open, close) <= high`. Zero volume is a diagnostic and does not by
itself make an otherwise exact window ineligible.

Every row persists exact nonnegative integer diagnostics for expected, observed, covered, missing,
off-grid, duplicate, invalid-timestamp, invalid-OHLC, available, and zero-volume rows. Counts must
conserve the horizon, be bounded by available rows, and satisfy the disjoint accounting identity
`observed + on-grid duplicates + off-grid + invalid timestamps = rows available`. The ordered
ineligibility reason is composed
from `missing_minutes`, `off_grid_rows`, `duplicate_timestamps`, `invalid_timestamps`, and
`invalid_ohlc`. The exclusive-end candle is never part of the horizon.

Horizons are nonempty unique exact positive integers; grid-cell numbers are nonempty unique exact
integers of at least two; SL ATR buffers are nonempty unique finite nonnegative numbers; and the
outcome profile is nonblank. Invalid domains fail before computation.

## Nullable claims and internal identities

When a window is ineligible, every candle-derived horizon claim is `NULL`: first exit/SL side,
ambiguity, time and minutes; inside count/minutes/ratio; excursion fields; mark deviation; every
grid crossing/touch/activity field; `sl_hit_bool`; and every `label_*` field. Static grid/SL
geometry, identifiers/provenance, funding coverage/context, mark-row count, completeness
diagnostics, and zero-volume count remain available. Funding aggregates are explicitly contextual
diagnostics rather than an assertion that the candle horizon was complete.

When eligible, required side/boolean/numeric claims are non-null. A `none` side has null event
time/minutes; a non-`none` side has an on-grid time inside the exclusive window and matching minute
offset. Ambiguity flags, SL-hit state, and all five labels equal their defining side/activity
identities. Inside minutes equal inside candle count, the ratio equals count divided by horizon,
and the count does not exceed the horizon. Close-cross, legacy grid-cross, and lower activity
aliases are equal; lower activity does not exceed intrabar/upper activity; internal counts do not
exceed full counts; and unique levels touched do not exceed stored grid levels.

## Cross-probe invariance and summary gate

The shared validator is the single gate used by both the CLI semantic audit and summary builder.
It rejects missing fields, wrong exact Python types, nonfinite values, bad IDs, mixed versions,
impossible diagnostics, contradictory claims, duplicate composite rows, and duplicate IDs.

Within one `(range_action_event_id, horizon)`, causal times, versions, profiles, range bounds,
completeness diagnostics, exit/inside/excursion/funding/mark context, and stayed-in-range label are
invariant across every grid/SL expansion. First-SL claims are invariant across grids for the same
SL buffer. Grid activity claims are invariant across SL buffers for the same grid-cell count.

The summary builder validates the complete frame before selecting any representative row. It
publishes total, eligible, and ineligible counts/rates, and computes exit, SL, and grid claims only
from eligible rows. With zero eligible rows, claim distributions are empty and aggregates are
null—not synthetic zero-percent success. Funding coverage diagnostics may still use all rows.

## Safety boundary

All frozen and ordinary acceptance uses synthetic in-memory Polars frames, temporary local files,
and monkeypatched read boundaries. It performs no public/private request, credential read, Bybit
call, order/grid operation, live execution, Telegram action, or external mutation. Existing local
research I/O authority is not expanded.
