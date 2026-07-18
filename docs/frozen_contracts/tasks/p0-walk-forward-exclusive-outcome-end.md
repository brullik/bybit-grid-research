# Frozen task contract: P0 persisted exclusive outcome end in walk-forward

Task ID: `p0-walk-forward-exclusive-outcome-end`
Issue: `#156`
Contract version: `persisted-exclusive-outcome-end-walk-forward-v1`
RED sentinel: `persisted_exclusive_outcome_end_walk_forward_contract_unavailable`
Task-definition base: `cb2e55cad62c821754e6990ad8ffb38c3a8eb740`

This task removes a P0 research-validity defect. Walk-forward currently reconstructs an outcome end
from signal time, although the authoritative outcome starts at the next minute. That can admit a
label whose final candle lies beyond its role boundary while the leakage audit remains green. The
task makes the v5 persisted exclusive end the only outcome-boundary authority shared by scoring
grains, fold construction, leakage audit, and review-pack closure. It grants no network,
credential, Bybit, live, order, grid, position, wallet, Telegram, or trading authority.

## Exact implementation scope

The implementation PR must change all and only these eight paths:

1. `src/bybit_grid/research/scoring/outcome_grains.py`
2. `src/bybit_grid/research/walk_forward/splits.py`
3. `src/bybit_grid/research/walk_forward/leakage_audit.py`
4. `scripts/check_scoring_review_pack.py`
5. `scripts/make_scoring_review_pack.py`
6. `tests/test_sprint_05_cost_scoring_walkforward.py`
7. `tests/test_sprint_05_6_review_pack_closure.py`
8. `tests/test_persisted_exclusive_outcome_end_walk_forward.py`

The last path is new. No outcome producer, outcome store, outcome-summary module, parameter/risk
contract, report generator, workflow, dependency, PM checker, protected path, live-execution path,
historical artifact, or historical branch change is authorized. Issue `#158` already established
the persisted v5 source fields; this task propagates and consumes them without reconstructing them.

## Availability gate and mandatory RED

The frozen suite contains exactly 32 collected nodes: one harness node and 31 embedded ordinary
nodes. Every complete `test_*` function calls
`_available()` as its first statement. Availability requires one exact top-level literal
assignment in each of the five production paths:

```python
PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
```

The ordinary test requires one exact top-level literal assignment:

```python
PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_TEST_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
```

Its complete UTF-8/LF raw bytes are embedded once as `ORDINARY_TEST_SOURCE` and pinned at SHA-256
`e373510ac2ac6f8780e97331687120e7f6b0d52fcbeeaa764f8db373d42d85a7`. The complete frozen-suite
raw bytes are SHA-256 `1b77336ba734f0e6b464c9f8304add0c21c707703d800f699f8e68f5e1f4b09e`.

After task-definition merge, a mandatory fresh Draft `probe/` PR changes all eight required paths
and no others. The five production paths and two existing tests receive inert comment-only edits;
the new ordinary-test path contains inert probe content. On every supported Python matrix the
frozen suite must yield exactly 32 sentinel failures, zero frozen passes, and no
unrelated failure, collection/setup/teardown error, skip, xfail/xpass, or deselection. Ordinary and
control suites must remain green. The probe is closed unmerged and is never marked Ready.

## Canonical persisted boundary contract

The only accepted and emitted boundary field is `outcome_end_exclusive_ms`. The legacy
`outcome_end_ms` field is forbidden even when the canonical field is also present. Missing,
nullable, boolean, floating, negative, reconstructed, or conflicting exclusive ends fail closed;
there is no signal-time or horizon fallback. The accepted row must carry exact v5 causal/window
provenance, exact boolean `causal_provenance_complete_bool = true`, and exact booleans for both
`future_data_complete_bool` and `future_outcome_eligible_bool`. The two future booleans must be
equal but may both be false, which produces `ineligible_max_horizon`; they are never coerced from
integers or strings. The row pins
`outcome_semantics_version = "v5_exact_outcome_window_provenance"` and
`outcome_window_semantics_version = "exact-minute-outcome-window-v1"`,
`actionable_event_semantics_version = "range-actionable-prefix-invariance-v1"`, and
`decision_time_source = "event_decision_time"`. Event ID, regime ID, symbol, and every
version/source field named above are required, non-null, and nonblank. Range/outcome run IDs and
range/outcome profiles are outside this task's required persisted-boundary contract and are
neither made mandatory nor granted new semantics by this task.
Exact-integer decision, signal, entry, horizon, and exclusive-end values are nonnegative (horizon
strictly positive) and satisfy the upstream causal identities:
`decision_time_ms == signal_time_ms`,
`entry_time_ms == ((signal_time_ms // 60_000) + 1) * 60_000`, and persisted exclusive end equals
`entry_time_ms + future_horizon_minutes * 60_000`. This identity is validated to reject corrupt
persistence; it is never used to synthesize a missing end or replace the persisted value used for
boundary decisions. The configured maximum horizon is also an exact positive integer.

Scoring grain outputs use:

- `grain_contract_version = "grain_contract_v4_persisted_exclusive_outcome_end"`;
- `outcome_boundary_semantics_version = "persisted-exclusive-outcome-end-v1"`;
- the persisted `outcome_end_exclusive_ms`, causal times, eligibility, and outcome semantic fields
  as whole-row invariants at every grain that can feed walk-forward;
- no legacy alias and no derived substitute.

The returned and persisted grain-contract audit also pins
`outcome_boundary_semantics_version = "persisted-exclusive-outcome-end-v1"`, persisted-required
true, derived count zero, and legacy-column-allowed false. A current grain frame paired with a stale
or missing boundary-semantic audit is not v4 closure.

Whole-row invariance is strict. After legitimate grid/SL raw rows have been reduced to the
event-horizon grain, any duplicate `(range_action_event_id, future_horizon_minutes)` in the
walk-forward input fails before folds are built, including a byte-for-byte identical duplicate.
Invariant fields must already agree across each raw event/horizon grid/SL expansion. Conflicting
event-invariant symbol, regime, decision, signal, entry, boundary, profile, eligibility, or
semantics metadata across horizons also fails. Integer and boolean validation uses exact types
rather than coercion, so `True`, `1.0`, and numeric strings cannot masquerade as timestamps or
contract booleans. These columns are required at the persisted event-horizon grain; being absent
from an old allowlist is a contract failure, not permission to reconstruct them downstream.

## Max-horizon selection and disjoint coverage

For each event and fold, walk-forward consumes the row whose horizon is exactly the configured
maximum horizon. It copies that row's persisted exclusive end; it never computes the end from
signal, decision, entry, horizon, row order, another horizon, or a profile default.

All source rows and per-event invariants are validated before the fold timeline or any disposition
is constructed. A corrupt lower- or maximum-horizon row, bad exact type, mixed/wrong/null version,
identity conflict, unequal future flags, or invalid causal identity fails the complete build. Only
a genuinely absent valid maximum-horizon row is a category rather than an input error.

An event with no exact maximum-horizon row is classified `missing_max_horizon`. An event with
exactly one maximum-horizon row whose completeness or eligibility is false is classified
`ineligible_max_horizon`. Neither condition may be silently dropped or collapsed into a generic
boundary exclusion. Fold-universe start/end are computed from all source events, not just events
that have an eligible maximum-horizon row; missing or ineligible events cannot shrink the timeline.

Every source event receives exactly one of these disjoint per-fold categories, listed in
deterministic first-match precedence:

- `missing_max_horizon`;
- `ineligible_max_horizon`;
- `outside_fold_window`;
- `purge_gap`;
- `embargo_gap`;
- `train_horizon_boundary`;
- `validation_horizon_boundary`;
- `test_horizon_boundary`;
- `cross_role_regime_excluded`;
- `train_assigned`;
- `validation_assigned`;
- `test_assigned`;
- `unassigned`.

Cross-role regime detection uses only tentative rows that have already passed maximum-horizon,
window/gap, and own-role boundary checks; an excluded boundary row cannot contaminate a regime and
change another event's reason.

Counts, event identities, assigned split rows, excluded rows, and published totals must reconcile
exactly for every fold. No event may disappear, enter two categories, or be counted at a different
horizon from the persisted row used for its boundary decision. `unassigned` is retained as a
diagnostic enum value, but an accepted build/audit/pack requires `unassigned_event_count == 0` and
no ledger row may carry it.

Fold construction also emits `walk_forward_event_eligibility.parquet`, a full disposition ledger
with exactly one row per `(fold_id, source event)`, including excluded events. Each row records the
single canonical disposition reason, assigned role when any, source-event identity, causal signal,
decision and entry times, selected maximum horizon, canonical persisted exclusive end, and the
applicable train/validation/test role bounds. A genuinely missing maximum-horizon row records exact
configured `max_outcome_horizon_minutes`, but its selected `future_horizon_minutes`, persisted end,
completeness, and eligibility are null with the exact `missing_max_horizon` reason; no value is
fabricated. Those nulls are permitted only in this derived ledger case and never in a canonical
source, eligible, or split row.
Ledger rows pin the boundary semantics and contain no legacy end. Ledger totals reconcile both to
the per-reason coverage summary and to every fold/role assigned-row summary. Every assigned ledger
row has exactly one matching row in `walk_forward_splits.parquet` with identical event, fold, role,
causal times, persisted end, and bounds; every split row has exactly one such ledger row. Excluded
ledger rows have no split-row counterpart.

The authoritative source-event set is derived before maximum-horizon selection. Every fold's
ledger event set equals it exactly, so the row identity is
`ledger_rows == fold_count * source_event_count`. Coverage contains exactly one summary row for
every `(fold_id, reason)` in the complete enum, including explicit zero counts. Each count equals a
group-by over ledger rows, and every fold assigned/boundary/gap/missing/ineligible total equals the
corresponding reason groups. Removing an event while decrementing a stored total, relabeling a
boundary as a gap while preserving aggregate totals, or duplicating an event cannot reconcile.

## Exact role-boundary semantics

Signal membership is half-open and is evaluated against the candidate role's own bounds:

```text
role_start_ms <= signal_time_ms < role_end_ms
```

The persisted exclusive label end is evaluated against that same role's own end:

```text
outcome_end_exclusive_ms <= role_end_ms
```

Exact equality is admissible because the persisted end is exclusive; one millisecond beyond the
role end is excluded. Train is checked against train end, validation against validation end, and
test against test end—not against the start of the next role. Purge and embargo gaps remain
separate exclusions. Boundary comparisons do not use profile duration arithmetic, a reconstructed
end, or a neighboring role's boundary.

All rows for a fold agree exactly on fold ID, profile/configuration, boundary semantics, and role
bounds. Intervals are strictly ordered train, purge, validation, embargo, test; purge/embargo widths
equal the configured gaps; and the role-end map is exactly train to train end, validation to
validation end, and test to test end. A forged train end inside the train/validation gap or forged
validation end inside the validation/test gap fails even if a label would fit that looser bound.

The assigned split row retains the canonical persisted end and
`outcome_boundary_semantics_version`. No split output or coverage artifact may emit the legacy
field. Regime isolation remains enforced after temporal eligibility; cross-role regimes are
excluded and reconciled explicitly.

## Leakage audit and review-pack closure

`audit_splits(splits)` independently performs row-level validation of every assigned row against
its own fold/role signal bounds and role end using the canonical persisted column. It rejects a
legacy column, a missing or invalid canonical end, stale boundary semantics, inconsistent fold
metadata, duplicate assignments, or any train/validation/test label overrun. It does not pretend
that assigned rows alone prove the disposition of excluded source events. Full ledger, coverage,
and split reconciliation is performed by the write/pack closure path, which has all three inputs.
An empty artifact cannot pass by vacuous booleans.

Coverage metadata, temporal-leakage metadata, and report-leakage metadata all pin:

```json
{
  "outcome_boundary_semantics_version": "persisted-exclusive-outcome-end-v1",
  "persisted_outcome_end_required_bool": true,
  "derived_outcome_end_count": 0,
  "legacy_outcome_end_column_allowed_bool": false
}
```

The review-pack manifest pins:

```json
{
  "review_pack_schema_version": "scoring_review_pack_v5_persisted_outcome_boundary",
  "grain_contract_version": "grain_contract_v4_persisted_exclusive_outcome_end",
  "outcome_boundary_semantics_version": "persisted-exclusive-outcome-end-v1"
}
```

`make_pack(scoring_run_id)` uses the reports directory but unconditionally refreshes exactly seven
canonical boundary members from the current data-backed artifacts before zipping:
`walk_forward_event_eligibility.parquet`, `walk_forward_splits.parquet`,
`walk_forward_fold_summary.parquet`, `walk_forward_exclusion_reason_summary.parquet`,
`walk_forward_coverage_audit.json`, `walk_forward_temporal_leakage_audit.json`, and
`walk_forward_leakage_audit_summary.json`. It does not claim a fresh staging directory or
unconditional replacement of non-boundary report members. The finished review pack has exactly 31
members and is emitted only when its split rows, full disposition ledger, coverage, reconciliation,
leakage audit, scoring-run identity, and manifest agree. The manifest inventories and hashes both
new Parquet artifacts, and every other required member, under the same hash policy.

`check_zip(pack, expected_scoring_run_id)` proves internal closure of the 31-member bundle. It
independently recomputes
every ledger disposition that is provable from canonical ledger eligibility, causal times, role
bounds, persisted end, purge/embargo placement, and cross-role regime evidence rather than trusting
stored reason labels, counts, summaries, or precomputed booleans. The maker proves a genuinely
missing maximum-horizon row against the canonical source while building; without an externally
trusted source inventory, the self-contained checker validates its required null/end/reason shape,
the identical event universe in every fold, and all internal reconciliation but does not claim to
distinguish a coherent replay of an older bundle. It then performs a bidirectional exact
assigned-ledger-to-split row reconciliation. It returns errors for a missing/duplicate ledger or
split row, a recomputed reason mismatch, reason or fold-summary drift, legacy or mixed
schema/grain/boundary versions, a legacy column in any artifact (including a rehashed disposition
ledger that also retains the canonical end), any nonzero derived count, missing
persisted-required proof, stale booleans, an unexpected pack member/count, a hash mismatch, a
hidden overrun, or tampering in either the manifest or an inner artifact. A collection of
precomputed `true` flags is not closure; the checker must validate the pinned evidence and exact
values.

The maker and checker preserve their public APIs and local-file-only authority. They do not fetch
data, read credentials, contact Bybit, mutate a run, or perform live/trading actions.

## Safety boundary

All frozen and ordinary acceptance uses synthetic in-memory Polars frames, deterministic temporary
local files, and monkeypatched local read boundaries. Tests must not make public/private requests,
read credentials, call Bybit, place/cancel orders, create grids or positions, write outside pytest
temporary directories, invoke Telegram, or mutate external state. Parameter/risk/live gates remain
false and existing research-only safety requirements are not weakened.
