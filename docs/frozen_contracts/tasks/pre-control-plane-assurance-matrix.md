# Frozen contract — pre-control-plane assurance matrix

## Scope and authority

Task ID: `pre-control-plane-assurance-matrix`.

This documentation-only task publishes the read-only assurance result required by
issue #134 for implementation introduced by PR #1–66 before the immutable PM
control plane. The audit source is current `main` at
`f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`, with the completed checkpoint in
issue comment `4999418554`.

The task-definition PR changes exactly:

1. `pm_acceptance/active_task.json`;
2. `pm_acceptance/tasks/pre-control-plane-assurance-matrix/`
   `test_pre_control_plane_assurance_matrix.py`;
3. `docs/frozen_contracts/tasks/pre-control-plane-assurance-matrix.md`.

The implementation PR changes exactly one path:

```text
docs/PRE_CONTROL_PLANE_ASSURANCE_MATRIX.md
```

No production source, script, ordinary test, checker, workflow, dependency,
configuration, lock file, PM acceptance file, frozen contract, generated evidence,
credential, network boundary, private API behavior, public capture behavior, or
live/trading behavior may change in the implementation PR. Passing this contract
publishes evidence only and does not close issue #134.

## Availability and mandatory RED

The document is strict UTF-8 and begins at byte zero with:

```text
<!-- assurance-contract: pre-control-plane-v1 -->
```

HTML comments are stripped before material checks. The visible document is at
least 60,000 characters, has the exact H1 and required H2 sections, and contains
exactly one visible fenced JSON manifest. Missing, unreadable, comment-only,
marker-relocated, short, malformed, duplicate-key, or non-object content is
unavailable.

Every one of exactly 24 plain synchronous frozen tests calls the availability
gate first. The unmodified baseline and a marker/comment-only or comment-only
mandatory RED probe therefore collect exactly 24 tests and fail exactly 24 times
with:

```text
RuntimeError: pre_control_plane_assurance_matrix_unavailable
```

There may be no pass, skip, xfail, collection error, or different failure in the
mandatory RED profile. The RED PR changes the required document path only, is
never merged, and is closed unmerged after both supported Python matrices prove
the exact result.

## Exact historical ledger and path inventory

The visible JSON manifest is the authoritative input, not executable code. Its
raw source ledger SHA-256 before embedding is:

```text
100c6cd4b472371bc2752b3cb1442f32151390cbfa54cad0dbc215d20caae80e
```

Its canonical JSON SHA-256 after parsing, using UTF-8, unescaped Unicode, sorted
keys and compact separators, is:

```text
c75783455ad5a5f21bbd718805691689f461f432cd0e9f853c454e7e9fc22e0e
```

The manifest has exactly the frozen top-level fields and contains 66 atomic PR
records. PR identifiers are strict integers in order `1..66`; range shorthand
cannot replace records. Every row has its exact title, unique lowercase 40-hex
merge SHA, slice, and nonempty sorted duplicate-free changed-path list.

Slice membership is exact:

- #1–5: `signing_transport_redaction`;
- #6–13: `pagination_quality_universe_validate`;
- #14–35: `range_outcome_scoring`;
- #36–50: `neutral_grid_ohlc`;
- #51–66: `public_batch_market_store`.

The changed-path union has exactly 280 normalized relative paths. Exactly 272 are
files on the audit tree and exactly eight are removed. The removed list is:

1. `numpy/__init__.py`;
2. `tests/test_sprint_06_4a_3_3_governance_cli.py`;
3. `tests/test_sprint_06_4a_3_3_import_audit.py`;
4. `tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py`;
5. `tests/test_sprint_06_4a_3_3_schema_plan_writer.py`;
6. `tests/test_sprint_06_4a_3_3_semantic_pack_cli.py`;
7. `tests/test_sprint_06_4a_3_material_behaviors.py`;
8. `tests/test_sprint_06_behavior_coverage_material_nodes.py`.

All other manifest paths must be contained current files. Absolute paths,
traversal, glob/query/anchor syntax, duplicates, invented paths, or replacing a
path with another existing but unrelated path fail the frozen digest or path
checks.

## Audit method and non-retroactivity

All eight method facts are strict Boolean false:

- historical code was neither imported nor executed;
- credentials were not used;
- private API was not called;
- Bybit public capture was not used;
- live execution was not used;
- trading mutation was not used;
- a current green suite is not retroactive proof.

The matrix must not imply that historical branch execution, current test count,
merged status, or early PR title proves old behavior. It audits current main only.

## Component disposition vocabulary

The human-readable matrix has exactly component rows C01–C19 and uses only:

- `OBSOLETE`;
- `SUPERSEDED_GOVERNED`;
- `CURRENT_PROVEN_BOUNDED`;
- `CURRENT_UNPROVEN`;
- `LEGACY_NONCANONICAL`;
- `QUARANTINED_EVIDENCE`.

The exact classifications are frozen by the tests. They separate later-governed
private dispatch and selected store boundaries from still-unproven redaction,
response admission, universe/native validation, causal range logic, exact outcome
windows, selection, store import recovery, and canonical ReplaySlice-to-OHLC
wiring. Placeholder `grid_simulator`, research, and live modules are not described
as implemented systems.

Neutral-grid and OHLC evidence proves only bounded frozen synthetic reference
contracts. Public-batch evidence proves only offline/mock behavior. Neither may be
expanded into native equivalence, liquidation, risk-budget, profitability, real
capture completeness, E2E, deployment, or live-readiness claims. Legacy
`data/raw/**` consumers are runnable but noncanonical, can false-pass, and are not
authoritative.

## Governed supersession and invalid evidence

Accepted chains are exactly:

```text
#71/#74/#75/#76
#77/#78/#79/#80
#81/#82/#83/#84
#87/#88/#89/#90
#91/#92/#93/#94
#104+#105/#106/#107/#108
#110/#111/#112/#113
#115/#116/#117/#118
#120/#121/#122/#123
#125/#126/#127/#128
#135+#139+#140/#141/#142/#143
```

These govern only their named boundaries: persisted models/parsers, chunk paths
and I/O, Decimal identity, graph audit, portable seed pack, atomic seed install,
strict offline historical stages, and corrected private read/validate-only
dispatch. In each chain, RED evidence is closed unmerged.

The exact quarantine is `#67`, `#68`, `#95-#103`, and `#136-#138`. It grants no
proof or supersession authority. PR #66's claim of 61 material rows is explicitly
invalidated because 56 mapped tests are padding/no-op; issue #160 owns repair.
Atomic seed installation is never presented as proof of general import atomicity.

## Residual issues and issue #134 verdict

The manifest contains exact descriptions for 17 atomic owners:

```text
#129 #131 #133
#148 #149 #150 #151 #152 #153 #154
#155 #156 #157 #158 #159 #160 #161
```

Every #148–161 gap appears in a component/disposition mapping. #129 owns the
corrected archive lifecycle, #131 owns canonical acquisition/E2E/scoring/risk, and
#133 owns full-history secret/export hygiene. No shorthand range may replace the
individual manifest records.

Issue #134 stays `OPEN` with `issue_134_closeable: false` while any
`CURRENT_UNPROVEN` component lacks a completed bounded lifecycle. The matrix sets
all implementation, credential, private API, public network capture, live
execution, and trading mutation authority pairs to `false`. It also sets native
equivalence, liquidation, risk budget, profitability, real public completeness,
legacy authority, canonical E2E, general import atomicity, parameter-selection
sufficiency, and live readiness to `false`.

Every repair requires a separate exact PM task, mandatory RED closed unmerged,
fresh-main bounded implementation, green acceptance, and task-close transition.
No mixed audit implementation PR is authorized.

## Required GREEN evidence

Before publication, verify:

- exactly 24 frozen tests pass on the complete current repository;
- all 272 surviving historical paths are contained current files and the eight
  removed paths remain absent;
- the machine manifest canonical digest is exact;
- the 19 component rows, nine disposition spans, 11 accepted chains, four
  quarantined entries, and 17 residual issues are exact;
- marker/comment-only RED produces the exact 24-sentinel profile;
- mutations for padding, PR ranges, duplicate PR/path/key, missing/invented path,
  wrong SHA/title/slice, overclaim, accepted quarantine, missing issue, PR #66
  rehabilitation, or false-to-true safety changes fail;
- the frozen test compiles and passes Ruff formatting/lint checks.

Ordinary repository checks remain required by the base-owned workflow. No test or
document command in this task authorizes network access, credentials, historical
code execution, private API, public capture, or live/trading mutation.
