# Frozen task contract: P0 range-actionable prefix invariance

Task ID: `p0-range-actionable-prefix-invariance`
Issue: `#151`
Contract version: `range-actionable-prefix-invariance-v1`
RED sentinel: `range_actionable_prefix_invariance_contract_unavailable`
Audit source baseline named by issue `#151`: `f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`

This task removes lookahead leakage from actionable range events. An event may become visible only
at the first timestamp whose prefix contains all qualification evidence. Appending later rows must
not create, remove, rename, or rewrite any event whose decision timestamp is already in that
prefix. The contract is offline and deterministic; it authorizes no exchange call or trading
mutation.

At task design time, `src/bybit_grid/research/range_actionable_events.py` has Git blob
`b3a2914f22b99bdf93b17c5bc0027fc4d6419a39` and raw-byte SHA-256
`dbf21e83db8f0db39075c75018893eb534febeb30af561fce0a915ab320465a3`. The task-definition PR base
commit is the activation baseline of record. The new ordinary test has no activation-baseline blob
and its final raw-byte SHA-256 is pinned by the frozen availability gate.

## Exact implementation scope

The implementation PR must change both paths below and no others:

1. `src/bybit_grid/research/range_actionable_events.py`
2. `tests/test_range_actionable_prefix_invariance.py`

The existing public entry points remain available:

- `build_actionable_events(raw, regime_cfg=None, event_cfg=None)`;
- `stable_action_event_id(regime_id, signal_time_ms, raw_candidate_id)`.

This task does not authorize changes to profiles, coalescing, feature extraction, other tests,
dependencies, workflows, PM enforcement, data artifacts, reports, settings, API clients,
credentials, order/grid creation, execution scripts, or historical branches.

## Availability gate and mandatory RED

The frozen suite contains exactly 18 plain synchronous tests. Every test function's first
statement is `_available()`. Availability requires:

- `bybit_grid.research.range_actionable_events` to contain exactly one top-level literal assignment
  and expose
  `RANGE_ACTIONABLE_PREFIX_INVARIANCE_CONTRACT =
  "range-actionable-prefix-invariance-v1"`;
- the new ordinary test to contain exactly one top-level
  `RANGE_ACTIONABLE_PREFIX_INVARIANCE_TEST_CONTRACT =
  "range-actionable-prefix-invariance-v1"` assignment and to match the raw-byte SHA-256 pinned in
  the frozen suite.

From the task-definition merge, the mandatory inert probe must change both exact required
implementation paths and only those paths. The new ordinary test path must contain only inert
probe content. On every supported Python matrix the probe must produce exactly 18 failures, each
terminating in
`RuntimeError("range_actionable_prefix_invariance_contract_unavailable")`. The probe must be
closed unmerged. Collection errors, unrelated failures, skips, xfails, partial required-path
scope, or a different failure reason do not satisfy RED.

## Timestamp-prefix qualification

Rows are processed as timestamp batches after a deterministic total ordering. All rows with one
`signal_time_ms` are simultaneously knowable; input row order inside that timestamp has no
semantic meaning. A symbol/profile/cluster regime first qualifies at the earliest timestamp batch
where all three profile thresholds are true:

| Profile | Inclusive duration | Raw candidates | Unique lookbacks |
| --- | ---: | ---: | ---: |
| `actionable_density_v2` | 15 minutes | 5 | 2 |
| `actionable_density_v3` | 30 minutes | 10 | 2 |
| `strict_actionable_v2` | 60 minutes | 20 | 3 |

At a cutoff, inclusive duration is exactly
`((decision_time_ms - first_seen_time_ms) // 60_000) + 1`. Elapsed-time ceiling, completed-future
regime duration, or a later candidate count must not qualify an earlier prefix. Duration alone,
candidate count alone, or lookback diversity alone is insufficient.

The primary event is sourced only from the complete first qualifying timestamp batch. Its
`decision_time_ms` and `signal_time_ms` are identical. Its `decision_time_utc` and
`signal_time_utc` are the same UTC ISO-8601 rendering. Event candidate fields, including raw
candidate identity, best lookback, range bounds, and quality fields, are copied from the selected
decision-time row. `regime_duration_minutes`, `raw_candidates_in_regime`, and numerically sorted,
comma-separated `lookbacks_observed` are snapshots containing only evidence available through the
decision timestamp. Later rows, scores, lookbacks, or counts cannot rewrite that snapshot.

For every input timestamp cutoff, running on the cutoff prefix must return exactly the same event
rows as filtering the full-input result to `decision_time_ms <= cutoff`. Equality includes every
field and identifier, not only event counts.

## Deterministic selection and versioned identifiers

When multiple candidates exist at the decision timestamp, the selected candidate is the minimum
under this total key:

1. `range_quality_score` descending;
2. `midline_crosses` descending;
3. `lookback_minutes` descending;
4. `raw_candidate_id` ascending.

The event contains
`actionable_event_semantics_version = "range-actionable-prefix-invariance-v1"`. The stable event
identifier is the first 32 lowercase hexadecimal characters of:

```text
sha256("range-actionable-prefix-invariance-v1|<regime_id>|<decision_time_ms>|<raw_candidate_id>")
```

The same logical input must produce the same full rows and IDs under reversed, rotated,
interleaved, or otherwise permuted input order. Distinct logical groups must not share an ID.

## Isolation, safe failure, and bounded reentry

Qualification evidence never crosses symbol, profile, actionable cluster, or coalescer gap
boundaries. A gap strictly greater than the configured in-regime maximum starts a new regime; the
two sides cannot pool duration, candidates, or lookbacks. Unknown profiles, empty frames, missing
required columns, null required decision values, and unusable required row evidence fail closed to
no actionable event rather than raising or guessing.

Default behavior emits at most one primary event per regime. Enabling reentry cannot create an
event before primary qualification. Reentry fails closed unless a later row contains an explicit,
finite, non-boolean `minutes_outside_midzone_before_reentry` value meeting the configured minimum.
Eligible reentries are chronological and the total number of events remains bounded by
`max_events_per_regime`, with the primary event counting toward the bound. Missing or below-limit
evidence emits no reentry.

## Safety boundary

All acceptance cases use synthetic in-memory Polars frames. They perform no network access, read
no credentials or private artifacts, execute no Bybit endpoint, place no order, create no grid,
and mutate no trading or external state.
