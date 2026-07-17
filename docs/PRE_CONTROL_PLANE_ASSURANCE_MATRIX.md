<!-- assurance-contract: pre-control-plane-v1 -->
# Pre-control-plane assurance matrix

## Scope, source, and verdict

This is the immutable read-only evidence matrix for issue #134. It audits the
implementation introduced by PR #1–66 only as it survives on current `main` at
`f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f`. The authoritative checkpoint is
issue comment `4999418554`.

`task_id`: `pre-control-plane-assurance-matrix`
`issue_134_state`: `OPEN`
`issue_134_closeable`: `false`
`implementation_authorized`: `false`
`credentials_authorized`: `false`
`private_api_authorized`: `false`
`public_network_capture_authorized`: `false`
`live_execution_authorized`: `false`
`trading_mutation_authorized`: `false`

A green current suite is not retroactive proof. Issue #134 remains open while any
`CURRENT_UNPROVEN` component lacks its own completed PM task, closed-unmerged RED
probe, fresh-main implementation, and task-close lifecycle.

## Audit method and safety facts

The audit inspected current source, PR metadata, changed-path inventories, present
tests, frozen contracts, and later governed lifecycles. Historical branch code was
not checked out, imported, or executed. No credential, private Bybit call, public
Bybit capture, live action, or trading mutation was used.

PR #1–66 contain exactly 280 unique historical paths. Exactly 272 survive on the
audit ref. The eight removed paths are the temporary `numpy/__init__.py` shim and
seven superseded store-test files recorded verbatim in the machine manifest.
The manifest gives every PR as an individual row; range notation never substitutes
for any of the 66 ledger entries.

## Component classifications

The vocabulary is deliberately narrow:

- `OBSOLETE`: a placeholder or abandoned scaffold, not an implemented system.
- `SUPERSEDED_GOVERNED`: a later accepted PM lifecycle proves the named boundary.
- `CURRENT_PROVEN_BOUNDED`: current evidence proves only the stated synthetic or
  offline boundary.
- `CURRENT_UNPROVEN`: production-relevant behavior still needs adversarial proof.
- `LEGACY_NONCANONICAL`: runnable legacy code that has no canonical authority.
- `QUARANTINED_EVIDENCE`: invalid evidence that cannot support a claim.

| ID | PR source | Component and current evidence | Classification | Governed evidence or residual owner |
|---|---|---|---|---|
| C01 | #1–5 | Private dispatch, payload and refusal in `src/bybit_grid/bybit/client.py`, `fgrid_payloads.py`, and `validate_only.py` | `SUPERSEDED_GOVERNED` | #135+#139+#140/#141/#142/#143 |
| C02 | #1–5 | Final log/report sink redaction in `src/bybit_grid/logging.py` and `src/bybit_grid/reporting.py` | `CURRENT_UNPROVEN` | #148 |
| C03 | #1–5 | HTTP/API response-envelope admission in `src/bybit_grid/bybit/client.py` and `models.py` | `CURRENT_UNPROVEN` | #149 |
| C04 | #1–5 | Raw Parquet storage foundation under legacy `data/raw` consumers | `LEGACY_NONCANONICAL` | #153, #131 |
| C05 | #1 | `backtest/grid_simulator.py`, `research/features.py`, and most `live/` modules are placeholders | `OBSOLETE` | #131 |
| C06 | #6–13 | Universe pagination, uniqueness and snapshot integrity | `CURRENT_UNPROVEN` | #152, #131 |
| C07 | #6–13 | Native validate result and minimum-investment proxy semantics | `CURRENT_UNPROVEN` | #150, #154, #131 |
| C08 | #6–13 | Legacy download/readiness and share-history authority | `LEGACY_NONCANONICAL` | #153, #131, #133 |
| C09 | #14–18 | Causal actionable range decision time | `CURRENT_UNPROVEN` | #151, #131 |
| C10 | #14–18 | Python-reference versus NumPy-fast range parity | `CURRENT_UNPROVEN` | #155, #131 |
| C11 | #19–27 | Exact outcome cadence, completeness and provenance | `CURRENT_UNPROVEN` | #158, #131 |
| C12 | #28–35 | Scoring and walk-forward selection boundaries | `CURRENT_UNPROVEN` | #156, #158, #131 |
| C13 | #36–42 | Decimal neutral-grid semantic state machine on frozen synthetic scenarios | `CURRENT_PROVEN_BOUNDED` | native/risk remain #131 |
| C14 | #43–50 | OHLC two-minimal-path replay on frozen synthetic scenarios | `CURRENT_PROVEN_BOUNDED` | adapter #161; native/E2E #131 |
| C15 | #51–58 | Public-batch parsing and evidence lifecycle with offline/mock inputs | `CURRENT_PROVEN_BOUNDED` | real completeness #131 |
| C16 | #59–66 | Store models/parsing, chunk I/O, Decimal identity, graph audit, seed pack and atomic seed install | `SUPERSEDED_GOVERNED` | #71–#108 accepted chains below |
| C17 | #59–66 | General import committed-key preflight and crash recovery | `CURRENT_UNPROVEN` | #157, #159, #131 |
| C18 | #62–66 | PR #66 61-row material-coverage claim; 56 mapped tests are padding/no-op | `QUARANTINED_EVIDENCE` | #160 |
| C19 | #43–66 | Canonical `ReplaySlice` to OHLC adapter and vertical replay path | `CURRENT_UNPROVEN` | #161, #131 |

## Current path dispositions and bounded truth

The ledger itself is the complete path register. For each path in the union of
`prs[*].changed_paths`, membership in `removed_paths` means `REMOVED`;
otherwise it means `SURVIVES_CURRENT`. This deterministic rule reconciles
280 = 272 + 8 and prevents an invented or duplicated path from hiding in prose.

Concrete current evidence is intentionally limited:

- `src/bybit_grid/bybit/validate_only.py` locks the canonical mainnet origin, three
  read-only private GET paths, sole `/v5/fgridbot/validate` POST, neutral mode and
  geometric type; create and close remain unavailable.
- `src/bybit_grid/bybit/client.py` refuses generic private POST, uses a private
  transport without environment trust or redirects, and leaves strict response
  admission unproven under #149.
- `src/bybit_grid/backtest/grid_simulator.py` is a literal placeholder.
- `src/bybit_grid/research/scoring/components.py` says
  `proxy_only_bool=true`, `risk_model_status=NOT_YET_PROVEN`, and
  `risk_budget_proven_bool=false`.
- `src/bybit_grid/research/walk_forward/splits.py` says
  `sufficient_for_parameter_selection_bool=false`.
- `src/bybit_grid/data/market_store/reader.py` yields `ReplaySlice`; no audited
  adapter to `src/bybit_grid/backtest/ohlc_replay/replay.py` exists yet.
- `scripts/build_range_candidates.py` and
  `scripts/build_candidate_outcomes.py` still consume legacy `data/raw/**`.
  Those paths are runnable, noncanonical, may false-pass, and are never
  authoritative research evidence.

The bounded synthetic neutral-grid/OHLC contracts do not prove native equivalence,
liquidation, the 5 USDT total-loss budget, profitability, or live readiness.
Offline/mock public-batch evidence does not prove real capture completeness.
Atomic seed installation does not prove general market-store import atomicity.

## Governed supersession and quarantine

Accepted chains are exactly:

- `#71/#74/#75/#76`: strict persisted models and parsers.
- `#77/#78/#79/#80`: strict chunk paths and I/O.
- `#81/#82/#83/#84`: context-free Decimal identity.
- `#87/#88/#89/#90`: canonical market-store graph audit.
- `#91/#92/#93/#94`: portable owner seed pack.
- `#104+#105/#106/#107/#108`: corrected atomic owner seed install.
- `#110/#111/#112/#113`: bounded historical capture plan.
- `#115/#116/#117/#118`: offline historical response acceptance.
- `#120/#121/#122/#123`: offline transcript reconciliation.
- `#125/#126/#127/#128`: offline historical evidence layout.
- `#135+#139+#140/#141/#142/#143`: corrected fail-closed private boundary.

In each accepted chain, the RED PR is evidence only and closed unmerged. The exact
quarantine is `#67`, `#68`, `#95-#103`, and `#136-#138`. Quarantined
chains grant no proof, supersession authority, implementation authority, or
permission to run historical code.

## Residual bounded owners

The registry is exact and atomic: #129 owns the corrected archive lifecycle; #131
owns canonical acquisition/E2E/scoring/risk work; #133 owns full-history,
secret/export hygiene. New bounded issues are #148, #149, #150, #151, #152, #153,
#154, #155, #156, #157, #158, #159, #160, and #161. No shorthand range in this
sentence replaces the individual records and descriptions in the manifest.

None of these issues authorizes implementation by itself. Every fix requires an
exact PM task, mandatory RED closed unmerged, fresh-main bounded implementation,
green acceptance, and task-close transition.

## Frozen machine manifest

The following visible JSON is the exact audit input. It is data, not executable
code, and is validated with duplicate-key rejection and canonical digests.

```json
{
  "audit_ref": "f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f",
  "method": {
    "historical_code_executed": false,
    "historical_code_imported": false,
    "credentials_used": false,
    "private_api_called": false,
    "bybit_public_capture_used": false,
    "live_execution_used": false,
    "trading_mutation_used": false,
    "current_green_is_retroactive_proof": false
  },
  "unique_historical_path_count": 280,
  "surviving_current_path_count": 272,
  "removed_paths": [
    "numpy/__init__.py",
    "tests/test_sprint_06_4a_3_3_governance_cli.py",
    "tests/test_sprint_06_4a_3_3_import_audit.py",
    "tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py",
    "tests/test_sprint_06_4a_3_3_schema_plan_writer.py",
    "tests/test_sprint_06_4a_3_3_semantic_pack_cli.py",
    "tests/test_sprint_06_4a_3_material_behaviors.py",
    "tests/test_sprint_06_behavior_coverage_material_nodes.py"
  ],
  "residual_issues": {
    "129": "corrected deterministic archive lifecycle",
    "131": "canonical acquisition/E2E/scoring/risk umbrella",
    "133": "full-history secret/export hygiene",
    "148": "sink-safe redaction",
    "149": "strict API response envelopes",
    "150": "native grid validate result semantics",
    "151": "prefix-invariant actionable decisions",
    "152": "complete unique universe snapshots",
    "153": "quarantine legacy raw readiness",
    "154": "remove minimum investment as risk authority",
    "155": "reference/fast range config parity",
    "156": "persisted exclusive outcome end in walk-forward",
    "157": "committed-key preflight safety",
    "158": "exact outcome completeness and provenance",
    "159": "import failure cleanup and recovery",
    "160": "retire padded 06.4A.3 evidence",
    "161": "canonical ReplaySlice to OHLC adapter"
  },
  "accepted_governed_chains": [
    "#71/#74/#75/#76",
    "#77/#78/#79/#80",
    "#81/#82/#83/#84",
    "#87/#88/#89/#90",
    "#91/#92/#93/#94",
    "#104+#105/#106/#107/#108",
    "#110/#111/#112/#113",
    "#115/#116/#117/#118",
    "#120/#121/#122/#123",
    "#125/#126/#127/#128",
    "#135+#139+#140/#141/#142/#143"
  ],
  "quarantined_chains": [
    "#67",
    "#68",
    "#95-#103",
    "#136-#138"
  ],
  "disposition_summary": [
    {
      "historical_prs": "#1-#5",
      "summary": "private dispatch/payload/refusal later governed; redaction/response semantics unproven; raw store superseded; placeholders obsolete",
      "issues": [
        148,
        149
      ]
    },
    {
      "historical_prs": "#6-#13",
      "summary": "universe/validate/data/readiness largely unproven or legacy",
      "issues": [
        150,
        152,
        153,
        154,
        131,
        133
      ]
    },
    {
      "historical_prs": "#14-#18",
      "summary": "range components current and unproven for causal decision and true parity",
      "issues": [
        151,
        155,
        131
      ]
    },
    {
      "historical_prs": "#19-#27",
      "summary": "outcome core partly hardened but exact cadence/provenance/equivalence/run immutability unproven",
      "issues": [
        158,
        131
      ]
    },
    {
      "historical_prs": "#28-#35",
      "summary": "proxy/status safeguards partly proven; exact horizon boundary and real selection unproven",
      "issues": [
        156,
        158,
        131
      ]
    },
    {
      "historical_prs": "#36-#42",
      "summary": "neutral-grid bounded synthetic reference contract proven; native/risk unproven",
      "issues": [
        131
      ]
    },
    {
      "historical_prs": "#43-#50",
      "summary": "OHLC two-minimal-path synthetic contract proven; canonical adapter/native equivalence unproven",
      "issues": [
        161,
        131
      ]
    },
    {
      "historical_prs": "#51-#58",
      "summary": "public batch offline/mock proven; real completeness and resource bounds unproven",
      "issues": [
        131
      ]
    },
    {
      "historical_prs": "#59-#66",
      "summary": "selected store boundaries later governed; padded evidence and import/adapter gaps remain",
      "issues": [
        157,
        159,
        160,
        161,
        131
      ]
    }
  ],
  "prs": [
    {
      "pr": 1,
      "title": "Implement Sprint 01 API/data feasibility foundation",
      "merge_sha": "fc25e314713b5d2a94e75736d559857884a752cf",
      "slice": "signing_transport_redaction",
      "changed_paths": [
        ".env.example",
        "config/bybit.yaml",
        "config/research.yaml",
        "config/risk.yaml",
        "reports/sprint_01_api_report.md",
        "scripts/download_sample_data.py",
        "scripts/smoke_private_account.py",
        "scripts/smoke_public_api.py",
        "scripts/validate_sample_grid.py",
        "src/bybit_grid/__init__.py",
        "src/bybit_grid/backtest/__init__.py",
        "src/bybit_grid/backtest/grid_simulator.py",
        "src/bybit_grid/bybit/__init__.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/bybit/models.py",
        "src/bybit_grid/bybit/rate_limit.py",
        "src/bybit_grid/bybit/signing.py",
        "src/bybit_grid/config.py",
        "src/bybit_grid/data/__init__.py",
        "src/bybit_grid/data/funding.py",
        "src/bybit_grid/data/instruments.py",
        "src/bybit_grid/data/klines.py",
        "src/bybit_grid/data/mark_klines.py",
        "src/bybit_grid/data/quality.py",
        "src/bybit_grid/data/storage.py",
        "src/bybit_grid/data/tickers.py",
        "src/bybit_grid/live/__init__.py",
        "src/bybit_grid/live/execution_engine.py",
        "src/bybit_grid/live/risk_manager.py",
        "src/bybit_grid/live/signal_engine.py",
        "src/bybit_grid/live/state_store.py",
        "src/bybit_grid/live/telegram_bot.py",
        "src/bybit_grid/logging.py",
        "src/bybit_grid/reporting.py",
        "src/bybit_grid/research/__init__.py",
        "src/bybit_grid/research/features.py",
        "src/bybit_grid/research/range_candidates.py",
        "tests/test_gap_detection.py",
        "tests/test_pagination.py",
        "tests/test_redaction.py",
        "tests/test_signing.py",
        "tests/test_storage_paths.py"
      ]
    },
    {
      "pr": 2,
      "title": "Sprint 01.5: API/data correctness hotfixes (private POST, GET signing, mark klines, quality, redaction, reporting)",
      "merge_sha": "f9826b9eec9891618c58013757d5a1b8e710347f",
      "slice": "signing_transport_redaction",
      "changed_paths": [
        ".env.example",
        "reports/sprint_01_api_report.md",
        "scripts/download_sample_data.py",
        "scripts/smoke_private_account.py",
        "scripts/smoke_public_api.py",
        "scripts/validate_sample_grid.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/bybit/models.py",
        "src/bybit_grid/bybit/rate_limit.py",
        "src/bybit_grid/bybit/signing.py",
        "src/bybit_grid/config.py",
        "src/bybit_grid/data/funding.py",
        "src/bybit_grid/data/instruments.py",
        "src/bybit_grid/data/klines.py",
        "src/bybit_grid/data/mark_klines.py",
        "src/bybit_grid/data/quality.py",
        "src/bybit_grid/data/storage.py",
        "src/bybit_grid/data/tickers.py",
        "src/bybit_grid/live/execution_engine.py",
        "src/bybit_grid/logging.py",
        "src/bybit_grid/reporting.py",
        "tests/test_gap_detection.py",
        "tests/test_pagination.py",
        "tests/test_redaction.py",
        "tests/test_signing.py",
        "tests/test_sprint_01_5_hotfix.py",
        "tests/test_storage_paths.py"
      ]
    },
    {
      "pr": 3,
      "title": "Fix Polars partition writes for sample data",
      "merge_sha": "0301de82ec949854c2fc2407926d550c7a822dc9",
      "slice": "signing_transport_redaction",
      "changed_paths": [
        "reports/sprint_01_api_report.md",
        "scripts/download_sample_data.py",
        "src/bybit_grid/data/funding.py",
        "src/bybit_grid/data/klines.py",
        "src/bybit_grid/data/mark_klines.py",
        "src/bybit_grid/data/quality.py",
        "tests/test_sprint_01_6_hotfix.py"
      ]
    },
    {
      "pr": 4,
      "title": "Add private account smoke and futures-grid validate-only payloads",
      "merge_sha": "f0222439f9b45252830f0f409512962083ffc396",
      "slice": "signing_transport_redaction",
      "changed_paths": [
        ".env.example",
        "reports/sprint_01_api_report.md",
        "scripts/smoke_private_account.py",
        "scripts/validate_sample_grid.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/bybit/fgrid_payloads.py",
        "src/bybit_grid/bybit/models.py",
        "src/bybit_grid/config.py",
        "tests/test_sprint_01_7_fgrid.py"
      ]
    },
    {
      "pr": 5,
      "title": "Hotfix: Bybit response parser + private account snapshot redaction",
      "merge_sha": "b45aaaf8f391342a356131fa23911b2d5d9cc298",
      "slice": "signing_transport_redaction",
      "changed_paths": [
        "scripts/smoke_private_account.py",
        "src/bybit_grid/bybit/client.py",
        "tests/test_sprint_01_8_hotfix.py"
      ]
    },
    {
      "pr": 6,
      "title": "Sprint 02: Universe builder, FGrid constraint mapper, download manifest & reporting",
      "merge_sha": "e8f32840ec8add1bd41350e003565b35e7918e92",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/build_download_manifest.py",
        "scripts/build_universe.py",
        "scripts/download_universe_data.py",
        "scripts/report_universe_quality.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "src/bybit_grid/bybit/fgrid_constraints.py",
        "src/bybit_grid/data/download_manifest.py",
        "src/bybit_grid/universe/__init__.py",
        "src/bybit_grid/universe/builder.py",
        "tests/test_sprint_02.py"
      ]
    },
    {
      "pr": 7,
      "title": "Sprint 02.1: download policy, threaded downloader, UTF-8 reports, and FGrid fixes",
      "merge_sha": "d05426dbb20e13ccb137afeeab316bc970d090b5",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/build_download_manifest.py",
        "scripts/download_universe_data.py",
        "scripts/report_universe_quality.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/bybit/fgrid_constraints.py",
        "src/bybit_grid/bybit/rate_limit.py",
        "src/bybit_grid/data/download_manifest.py",
        "src/bybit_grid/universe/builder.py",
        "tests/test_sprint_02_1.py"
      ]
    },
    {
      "pr": 8,
      "title": "Add native FGrid feasibility sweep and data hygiene fixes",
      "merge_sha": "5d1cb5beb10e491e04842daf4298688c9f7157f3",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "pyproject.toml",
        "scripts/__init__.py",
        "scripts/analyze_fgrid_min_investment.py",
        "scripts/build_download_manifest.py",
        "scripts/clean_generated_artifacts.py",
        "scripts/download_universe_data.py",
        "scripts/make_share_zip.py",
        "scripts/report_universe_quality.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "src/bybit_grid/bybit/fgrid_constraints.py",
        "src/bybit_grid/bybit/fgrid_feasibility.py",
        "src/bybit_grid/data/download_manifest.py",
        "src/bybit_grid/data/funding_quality.py",
        "tests/test_sprint_02_1.py",
        "tests/test_sprint_02_2.py"
      ]
    },
    {
      "pr": 9,
      "title": "Add FAST FGrid min-investment sweep and shared rate-limited validate loop",
      "merge_sha": "18e407782d33b7170f739ffd350cd5c043852543",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "config/performance.yml",
        "scripts/analyze_fgrid_min_investment.py",
        "scripts/build_universe.py",
        "scripts/download_universe_data.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "src/bybit_grid/bybit/fgrid_min_sweep.py",
        "tests/test_sprint_02_3_fast_sweep.py"
      ]
    },
    {
      "pr": 10,
      "title": "Guard real fgrid validate sweep, purge skipped constraints, track API calls & fix analyzer",
      "merge_sha": "14eb3f8bdd6b28791ce7fb3f002e5f50bc9155ae",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/analyze_fgrid_min_investment.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/bybit/fgrid_feasibility.py",
        "src/bybit_grid/bybit/fgrid_min_sweep.py",
        "tests/test_sprint_02_4_hotfix.py"
      ]
    },
    {
      "pr": 11,
      "title": "FAST pipeline: auto-bootstrap universe + one-command feasibility orchestrator",
      "merge_sha": "b727b41f4c1ac10bcb26d399e65eb5d7ca1a367a",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/analyze_fgrid_min_investment.py",
        "scripts/build_universe.py",
        "scripts/run_fast_feasibility_pipeline.py",
        "scripts/validate_universe_fgrid_constraints.py",
        "tests/test_sprint_02_5_pipeline.py"
      ]
    },
    {
      "pr": 12,
      "title": "Risk-aware research universe readiness: rename feasibility, add risk-proxies, download manifest & reports",
      "merge_sha": "cba345387171d49866a79114b1dd25ea3c926054",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/analyze_fgrid_min_investment.py",
        "scripts/build_research_download_manifest.py",
        "scripts/build_research_eligible_universe.py",
        "scripts/report_research_readiness.py",
        "src/bybit_grid/bybit/fgrid_constraints.py",
        "src/bybit_grid/bybit/fgrid_feasibility.py",
        "src/bybit_grid/data/download_manifest.py",
        "tests/test_sprint_02_6.py"
      ]
    },
    {
      "pr": 13,
      "title": "Fix Sprint 02.7 quality reporting and share hygiene",
      "merge_sha": "342dc713d11ab0971f19f716c5780a2358ae2268",
      "slice": "pagination_quality_universe_validate",
      "changed_paths": [
        "scripts/check_share_hygiene.py",
        "scripts/make_share_zip.py",
        "scripts/report_research_readiness.py",
        "scripts/report_universe_quality.py",
        "tests/test_sprint_02_7_quality_report.py"
      ]
    },
    {
      "pr": 14,
      "title": "Add Sprint 03 range candidate dataset tooling",
      "merge_sha": "f2f37c8ba0855f498d1db79ba95106baf7624dc8",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_range_candidates.py",
        "scripts/report_range_candidates.py",
        "src/bybit_grid/research/range_candidate_store.py",
        "src/bybit_grid/research/range_candidate_summary.py",
        "src/bybit_grid/research/range_detector.py",
        "src/bybit_grid/research/range_features.py",
        "tests/test_sprint_03_range_candidates.py"
      ]
    },
    {
      "pr": 15,
      "title": "Add Sprint 03.1 range event calibration layer",
      "merge_sha": "52c656c7632b7f8d0b37e3380f1fd6957fbae4f0",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_range_candidates.py",
        "scripts/report_range_candidate_density.py",
        "scripts/report_range_candidates.py",
        "src/bybit_grid/research/range_candidate_store.py",
        "src/bybit_grid/research/range_detector.py",
        "src/bybit_grid/research/range_event_coalescer.py",
        "src/bybit_grid/research/range_profiles.py",
        "tests/test_sprint_03_range_candidates.py"
      ]
    },
    {
      "pr": 16,
      "title": "Add isolated actionable range event pipeline",
      "merge_sha": "14ef5c6df3c66c846a87e9f686ac1132f68c1adb",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_range_candidates.py",
        "scripts/calibrate_range_event_density.py",
        "scripts/list_range_runs.py",
        "scripts/purge_range_run.py",
        "scripts/report_range_candidate_density.py",
        "scripts/report_range_candidates.py",
        "src/bybit_grid/research/range_actionable_events.py",
        "src/bybit_grid/research/range_candidate_store.py",
        "src/bybit_grid/research/range_detector.py",
        "src/bybit_grid/research/range_profiles.py",
        "src/bybit_grid/research/range_regime_coalescer.py"
      ]
    },
    {
      "pr": 17,
      "title": "Add fast range core interface, numpy_fast kernel, profiler, and PM review pack",
      "merge_sha": "ea230cbbea6fc5b2fdbfb2ad09a4adc46d31f967",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "docs/performance_core_plan.md",
        "pyproject.toml",
        "scripts/build_range_candidates.py",
        "scripts/make_pm_review_pack.py",
        "scripts/profile_range_core.py",
        "src/bybit_grid/research/range_candidate_summary.py",
        "src/bybit_grid/research/range_core/__init__.py",
        "src/bybit_grid/research/range_core/adapter.py",
        "src/bybit_grid/research/range_core/models.py",
        "src/bybit_grid/research/range_core/numpy_fast.py",
        "src/bybit_grid/research/range_core/python_reference.py",
        "src/bybit_grid/research/range_detector.py",
        "src/bybit_grid/research/range_profiles.py",
        "tests/test_sprint_03_3_fast_core.py"
      ]
    },
    {
      "pr": 18,
      "title": "Actionable density calibration and run-isolated PM review packs",
      "merge_sha": "de163eb9509206a505167ad4f562d535b44f0b8d",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_range_candidates.py",
        "scripts/calibrate_actionable_density.py",
        "scripts/check_pm_review_pack.py",
        "scripts/make_pm_review_pack.py",
        "scripts/profile_range_core.py",
        "scripts/report_range_candidate_density.py",
        "scripts/report_range_candidates.py",
        "src/bybit_grid/research/range_actionable_events.py",
        "src/bybit_grid/research/range_profiles.py",
        "tests/test_sprint_03_4_density_pack.py"
      ]
    },
    {
      "pr": 19,
      "title": "Add Sprint 04 candidate outcome labeling pipeline",
      "merge_sha": "1ef843f4471c6da3a1470bd8aab8d43d653a7da6",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_candidate_outcomes.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/make_outcome_review_pack.py",
        "scripts/report_candidate_outcomes.py",
        "src/bybit_grid/research/outcome_core/funding_join.py",
        "src/bybit_grid/research/outcome_core/grid_crossings.py",
        "src/bybit_grid/research/outcome_core/models.py",
        "src/bybit_grid/research/outcome_core/outcome_numpy.py",
        "src/bybit_grid/research/outcome_store.py",
        "src/bybit_grid/research/outcome_summary.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 20,
      "title": "Fix outcome dedupe, add funding diagnostics, repair tool, and tighten review-pack gates",
      "merge_sha": "dee93647b2b16452a31b9318d7afe4a977bff301",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "numpy/__init__.py",
        "scripts/build_candidate_outcomes.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/repair_outcome_run.py",
        "src/bybit_grid/research/outcome_core/funding_join.py",
        "src/bybit_grid/research/outcome_store.py",
        "src/bybit_grid/research/outcome_summary.py",
        "src/bybit_grid/research/range_core/adapter.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 21,
      "title": "Finalize outcome gate hygiene — remove local numpy shim, JSON & review-pack fixes",
      "merge_sha": "97d4a8a57dd34887bb573ebc971926829058c71b",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "numpy/__init__.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/report_candidate_outcomes.py",
        "src/bybit_grid/research/outcome_summary.py",
        "src/bybit_grid/research/range_core/adapter.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 22,
      "title": "Fix NumPy environment guard and add numeric environment doctor",
      "merge_sha": "d3e38e88c488ac7e3334551e4582738da80e0b1a",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "pyproject.toml",
        "scripts/check_numeric_environment.py",
        "src/bybit_grid/research/range_core/adapter.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 23,
      "title": "Add v3 ATR-correct SL proxy, ambiguity handling, and activity-proxy summaries",
      "merge_sha": "87ec244f5c670a005b71b1c4945dd7edad35ffa2",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/audit_outcome_semantics.py",
        "scripts/build_candidate_outcomes.py",
        "src/bybit_grid/research/outcome_core/grid_crossings.py",
        "src/bybit_grid/research/outcome_core/outcome_numpy.py",
        "src/bybit_grid/research/outcome_core/sl_proxy.py",
        "src/bybit_grid/research/outcome_summary.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 24,
      "title": "Align outcome grid geometry with native Bybit cells",
      "merge_sha": "2ec25b7503935165737071a4df160db035d0f022",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/audit_outcome_semantics.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/compare_outcome_runs.py",
        "scripts/make_outcome_review_pack.py",
        "src/bybit_grid/research/outcome_core/grid_crossings.py",
        "src/bybit_grid/research/outcome_core/outcome_numpy.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 25,
      "title": "Repair outcome grid serialization and add fast-core scaffolding",
      "merge_sha": "6f7a682ea886cf6532cde302e6f1d708141f05ae",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/audit_outcome_semantics.py",
        "scripts/benchmark_outcome_cores.py",
        "scripts/build_candidate_outcomes.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/make_outcome_review_pack.py",
        "scripts/profile_outcome_core.py",
        "scripts/repair_outcome_grid_serialization.py",
        "src/bybit_grid/research/outcome_core/grid_crossings.py",
        "src/bybit_grid/research/outcome_core/outcome_fast.py",
        "src/bybit_grid/research/outcome_core/outcome_numpy.py",
        "src/bybit_grid/research/outcome_core/outcome_reference.py",
        "src/bybit_grid/research/outcome_core/symbol_arrays.py",
        "tests/test_sprint_04_5_outcome_core.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 26,
      "title": "Implement vectorized outcome core and review-pack manifest",
      "merge_sha": "48093d2feeb3a89458ffd46c149028194d7b9f99",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/benchmark_outcome_cores.py",
        "scripts/benchmark_outcome_executors.py",
        "scripts/build_candidate_outcomes.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/make_outcome_review_pack.py",
        "src/bybit_grid/research/outcome_core/outcome_fast.py",
        "src/bybit_grid/research/outcome_reporting.py",
        "tests/test_sprint_04_6_outcome_core.py"
      ]
    },
    {
      "pr": 27,
      "title": "Add canonical input loader, input-hygiene artifacts, and real equivalence gate",
      "merge_sha": "d388323d6ae0c6f7e7ac988080e430e541aebd1f",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/audit_outcome_semantics.py",
        "scripts/benchmark_outcome_cores.py",
        "scripts/build_candidate_outcomes.py",
        "scripts/check_outcome_review_pack.py",
        "scripts/make_outcome_review_pack.py",
        "src/bybit_grid/research/outcome_core/input_loader.py",
        "tests/test_sprint_04_7_input_equivalence.py",
        "tests/test_sprint_04_candidate_outcomes.py"
      ]
    },
    {
      "pr": 28,
      "title": "Sprint 05: Add cost & scoring framework, AST safety audit, and purged walk‑forward splits",
      "merge_sha": "3ce9eeb6a63d9e8d8c4ac0bf9fb6f4dff6a79026",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "config/cost_scenarios.example.yml",
        "config/cost_scenarios.yml",
        "scripts/audit_walk_forward_splits.py",
        "scripts/build_outcome_grains.py",
        "scripts/build_outcome_scoring_dataset.py",
        "scripts/build_walk_forward_splits.py",
        "scripts/check_no_live_execution.py",
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "scripts/report_cost_and_scoring.py",
        "scripts/snapshot_fee_rates.py",
        "src/bybit_grid/common/source_safety_audit.py",
        "src/bybit_grid/research/cost_model/cycle_costs.py",
        "src/bybit_grid/research/cost_model/fee_snapshot.py",
        "src/bybit_grid/research/cost_model/models.py",
        "src/bybit_grid/research/scoring/components.py",
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "src/bybit_grid/research/walk_forward/leakage_audit.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "tests/test_sprint_04_7_input_equivalence.py",
        "tests/test_sprint_05_cost_scoring_walkforward.py"
      ]
    },
    {
      "pr": 29,
      "title": "Fix Sprint 05 scoring integrity gates",
      "merge_sha": "cf5a47c233ecb8016152e26ef6a62f34d226ddff",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_outcome_scoring_dataset.py",
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "scripts/report_cost_and_scoring.py",
        "src/bybit_grid/research/cost_model/cycle_costs.py",
        "src/bybit_grid/research/scoring/components.py",
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "src/bybit_grid/research/walk_forward/leakage_audit.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "tests/test_sprint_05_cost_scoring_walkforward.py"
      ]
    },
    {
      "pr": 30,
      "title": "Finalize Sprint 05.2 scoring audits",
      "merge_sha": "c186b2fefc72b3e6719b5486bdacc27c33f38ca7",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "src/bybit_grid/research/cost_model/cycle_costs.py",
        "src/bybit_grid/research/scoring/components.py",
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "src/bybit_grid/research/walk_forward/splits.py"
      ]
    },
    {
      "pr": 31,
      "title": "Finalize scoring provenance, whole-row grain contract & walk-forward coverage audits",
      "merge_sha": "0d9b0afc265a06de84d3edc0f95829c8ef5af7a4",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/build_outcome_scoring_dataset.py",
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "scripts/report_cost_and_scoring.py",
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "tests/test_sprint_05_cost_scoring_walkforward.py"
      ]
    },
    {
      "pr": 32,
      "title": "Finalize cost-grain and walk-forward reconciliation audits",
      "merge_sha": "cfed134eab34d5e888c4b5441452ea074ea2a3ce",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/check_scoring_review_pack.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "tests/test_sprint_05_cost_scoring_walkforward.py"
      ]
    },
    {
      "pr": 33,
      "title": "Finalize category contract and atomic scoring runs",
      "merge_sha": "efc44433539e17cd0ce8035d0ad9051e57c65d14",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "tests/test_sprint_05_cost_scoring_walkforward.py"
      ]
    },
    {
      "pr": 34,
      "title": "Close scoring review pack evidence gaps",
      "merge_sha": "fc49d727691425eaca173475ba08cf83e3394c46",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
        "tests/test_sprint_05_6_review_pack_closure.py"
      ]
    },
    {
      "pr": 35,
      "title": "Harden scoring review pack manifest contract checks",
      "merge_sha": "463ff59f159e76a83938eca70cb811f651578f08",
      "slice": "range_outcome_scoring",
      "changed_paths": [
        "scripts/check_scoring_review_pack.py",
        "src/bybit_grid/research/scoring/score_builder.py",
        "tests/test_sprint_05_6_review_pack_closure.py"
      ]
    },
    {
      "pr": 36,
      "title": "Add neutral grid reference state machine (Sprint 06.1A)",
      "merge_sha": "bb67a6c0fdc5e2c7644fb5b5312af46f936e7622",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "src/bybit_grid/backtest/neutral_grid/__init__.py",
        "src/bybit_grid/backtest/neutral_grid/accounting.py",
        "src/bybit_grid/backtest/neutral_grid/audit.py",
        "src/bybit_grid/backtest/neutral_grid/engine.py",
        "src/bybit_grid/backtest/neutral_grid/geometry.py",
        "src/bybit_grid/backtest/neutral_grid/models.py",
        "tests/test_sprint_06_1a_neutral_grid_state_machine.py"
      ]
    },
    {
      "pr": 37,
      "title": "Harden neutral grid state machine and independent audit",
      "merge_sha": "1ad8bcd2ff18b6450609d2751a35de84bb122503",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "src/bybit_grid/backtest/neutral_grid/accounting.py",
        "src/bybit_grid/backtest/neutral_grid/audit.py",
        "src/bybit_grid/backtest/neutral_grid/engine.py",
        "src/bybit_grid/backtest/neutral_grid/geometry.py",
        "src/bybit_grid/backtest/neutral_grid/models.py",
        "tests/test_sprint_06_1a_1_state_machine_hardening.py"
      ]
    },
    {
      "pr": 38,
      "title": "Close canonical geometry and audit gaps",
      "merge_sha": "d11248000e198800bfb5aacd505c6463caa6b648",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "src/bybit_grid/backtest/neutral_grid/audit.py",
        "src/bybit_grid/backtest/neutral_grid/engine.py",
        "src/bybit_grid/backtest/neutral_grid/geometry.py",
        "src/bybit_grid/backtest/neutral_grid/models.py",
        "tests/test_sprint_06_1a_1_state_machine_hardening.py",
        "tests/test_sprint_06_1a_2_canonical_geometry_and_audit_closure.py",
        "tests/test_sprint_06_1a_neutral_grid_state_machine.py"
      ]
    },
    {
      "pr": 39,
      "title": "Add synthetic scenario evidence, replay audit, and review-pack tooling (Sprint 06.1B)",
      "merge_sha": "5bb0d7fcac8ba4a232d71295f7aed6d4af8dc393",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "scripts/check_state_machine_review_pack.py",
        "scripts/make_state_machine_review_pack.py",
        "scripts/run_neutral_grid_synthetic_matrix.py",
        "src/bybit_grid/backtest/neutral_grid/__init__.py",
        "src/bybit_grid/backtest/neutral_grid/audit.py",
        "src/bybit_grid/backtest/neutral_grid/engine.py",
        "src/bybit_grid/backtest/neutral_grid/models.py",
        "src/bybit_grid/backtest/neutral_grid/scenario_audit.py",
        "src/bybit_grid/backtest/neutral_grid/scenarios.py",
        "src/bybit_grid/backtest/neutral_grid/serialization.py",
        "tests/test_sprint_06_1b_synthetic_scenario_evidence.py"
      ]
    },
    {
      "pr": 40,
      "title": "Close state machine evidence checker workflow",
      "merge_sha": "915d7fd07660a812e4902dd8800836e30b9cd2cb",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        ".gitignore",
        "scripts/check_state_machine_review_pack.py",
        "scripts/make_state_machine_review_pack.py",
        "scripts/run_neutral_grid_synthetic_matrix.py",
        "src/bybit_grid/backtest/neutral_grid/evidence.py",
        "src/bybit_grid/backtest/neutral_grid/scenario_audit.py",
        "tests/test_sprint_06_1b_1_evidence_checker_closure.py",
        "tests/test_sprint_06_1b_synthetic_scenario_evidence.py"
      ]
    },
    {
      "pr": 41,
      "title": "Close canonical v2 state machine evidence contract",
      "merge_sha": "23936218a8c3488ad892f5b4a646a87713d174af",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "scripts/check_state_machine_review_pack.py",
        "scripts/make_state_machine_review_pack.py",
        "scripts/run_neutral_grid_synthetic_matrix.py",
        "src/bybit_grid/backtest/neutral_grid/evidence.py",
        "src/bybit_grid/backtest/neutral_grid/scenarios.py",
        "tests/test_sprint_06_1b_1_evidence_checker_closure.py",
        "tests/test_sprint_06_1b_2_exact_base_and_canonical_evidence.py",
        "tests/test_sprint_06_1b_synthetic_scenario_evidence.py"
      ]
    },
    {
      "pr": 42,
      "title": "Enforce strict JSON evidence type identity",
      "merge_sha": "b8dda3b0c95e68d31d2ef164b06edb30eaaee695",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/native_neutral_grid_reference_contract_v1.md",
        "scripts/make_state_machine_review_pack.py",
        "src/bybit_grid/backtest/neutral_grid/evidence.py",
        "src/bybit_grid/backtest/neutral_grid/serialization.py",
        "tests/test_sprint_06_1b_3_strict_json_type_identity.py"
      ]
    },
    {
      "pr": 43,
      "title": "Add OHLC 1m minimal-path replay core",
      "merge_sha": "3d04839d4848c941e01be01c9d4405a810c35c2d",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "src/bybit_grid/backtest/ohlc_replay/__init__.py",
        "src/bybit_grid/backtest/ohlc_replay/audit.py",
        "src/bybit_grid/backtest/ohlc_replay/envelope.py",
        "src/bybit_grid/backtest/ohlc_replay/models.py",
        "src/bybit_grid/backtest/ohlc_replay/paths.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "tests/test_sprint_06_2a_ohlc_minimal_path_replay.py"
      ]
    },
    {
      "pr": 44,
      "title": "Harden OHLC replay provenance audit",
      "merge_sha": "bb27ec8d0310e17776bce9eb0f35836a3b5a9899",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "src/bybit_grid/backtest/ohlc_replay/__init__.py",
        "src/bybit_grid/backtest/ohlc_replay/audit.py",
        "src/bybit_grid/backtest/ohlc_replay/envelope.py",
        "src/bybit_grid/backtest/ohlc_replay/models.py",
        "src/bybit_grid/backtest/ohlc_replay/paths.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "tests/test_sprint_06_2a_1_ohlc_replay_provenance_audit_and_envelope_closure.py"
      ]
    },
    {
      "pr": 45,
      "title": "Harden OHLC replay snapshot identity and funding provenance",
      "merge_sha": "107237a1bc9d90da7bec2d92da1e8fc7b03b4a8e",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "src/bybit_grid/backtest/ohlc_replay/audit.py",
        "src/bybit_grid/backtest/ohlc_replay/models.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "tests/test_sprint_06_2a_1_ohlc_replay_provenance_audit_and_envelope_closure.py",
        "tests/test_sprint_06_2a_2_strict_snapshot_identity_and_funding_provenance.py",
        "tests/test_sprint_06_2a_ohlc_minimal_path_replay.py"
      ]
    },
    {
      "pr": 46,
      "title": "Persisted OHLC evidence gate: funding provenance, frozen scenarios, canonical evidence & runner",
      "merge_sha": "3b2385605cf24e2e7b291ed4255ed0c2e858056a",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "scripts/check_ohlc_replay_review_pack.py",
        "scripts/make_ohlc_replay_review_pack.py",
        "scripts/run_ohlc_replay_synthetic_matrix.py",
        "src/bybit_grid/backtest/ohlc_replay/__init__.py",
        "src/bybit_grid/backtest/ohlc_replay/audit.py",
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/backtest/ohlc_replay/models.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "src/bybit_grid/backtest/ohlc_replay/scenarios.py",
        "tests/test_sprint_06_2b_persisted_ohlc_evidence.py"
      ]
    },
    {
      "pr": 47,
      "title": "Close OHLC replay v2 evidence audit",
      "merge_sha": "3ddf151911726c19e24e84bd04fece0acf50a9d5",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/backtest/ohlc_replay/scenarios.py",
        "tests/test_sprint_06_2b_1_catalog_semantics_and_evidence_closure.py",
        "tests/test_sprint_06_2b_persisted_ohlc_evidence.py"
      ]
    },
    {
      "pr": 48,
      "title": "Close OHLC evidence contract hygiene gaps",
      "merge_sha": "25f589ca9604b0f33e5411e30052de561fe8efef",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "docs/ohlc_minimal_path_replay_contract_v1.md",
        "scripts/run_ohlc_replay_synthetic_matrix.py",
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/backtest/ohlc_replay/scenarios.py",
        "tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py"
      ]
    },
    {
      "pr": 49,
      "title": "Close OHLC geometric audit guardrails",
      "merge_sha": "32da850b3d5fe4c02ca58604038c3a30c73dcfb6",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/backtest/ohlc_replay/scenarios.py",
        "tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py",
        "tests/test_sprint_06_2b_3_geometric_audit_and_guardrail_closure.py"
      ]
    },
    {
      "pr": 50,
      "title": "Close OHLC independent evidence audit — derive guardrails & strict contract audit (v4)",
      "merge_sha": "7de15292b07ac79fe27eed6b5fc7e9991c0c2641",
      "slice": "neutral_grid_ohlc",
      "changed_paths": [
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/backtest/ohlc_replay/scenarios.py",
        "tests/test_sprint_06_2b_2_cross_platform_and_evidence_contract_closure.py",
        "tests/test_sprint_06_2b_3_1_independent_evidence_truthfulness.py"
      ]
    },
    {
      "pr": 51,
      "title": "Add Bybit public-batch input contract v1 and core implementation",
      "merge_sha": "78df372ce72eddc41f3c6c20db766148a12ea1d2",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "scripts/smoke_bybit_public_batch_contract.py",
        "src/bybit_grid/backtest/ohlc_replay/evidence.py",
        "src/bybit_grid/data/public_batch/__init__.py",
        "src/bybit_grid/data/public_batch/assemble.py",
        "src/bybit_grid/data/public_batch/audit.py",
        "src/bybit_grid/data/public_batch/models.py",
        "src/bybit_grid/data/public_batch/pagination.py",
        "src/bybit_grid/data/public_batch/parsers.py",
        "tests/test_sprint_06_3a_bybit_public_batch_input_contract.py"
      ]
    },
    {
      "pr": 52,
      "title": "Contract-type-aware instrument parsing and universe audit (Sprint 06.3A.1)",
      "merge_sha": "0536d12a4e46e5118719e1005aa34fe5004b75f6",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "scripts/smoke_bybit_public_batch_contract.py",
        "src/bybit_grid/data/public_batch/audit.py",
        "src/bybit_grid/data/public_batch/models.py",
        "src/bybit_grid/data/public_batch/pagination.py",
        "tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py"
      ]
    },
    {
      "pr": 53,
      "title": "Add persisted Bybit public batch evidence gate",
      "merge_sha": "e54f3d57843f9b16f2689a5b09ae2000710e8366",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "scripts/check_bybit_public_batch_review_pack.py",
        "scripts/make_bybit_public_batch_review_pack.py",
        "scripts/run_bybit_public_batch_evidence.py",
        "src/bybit_grid/data/public_batch/assemble.py",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/pagination.py",
        "src/bybit_grid/data/public_batch/recording.py",
        "tests/test_sprint_06_3b_persisted_public_batch_evidence.py"
      ]
    },
    {
      "pr": 54,
      "title": "Implement owner public capture lifecycle and persisted-input-first semantic review-pack validation",
      "merge_sha": "8413eb39caac6cffcba3dd095da9e0d78b0b2121",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "scripts/make_bybit_public_batch_review_pack.py",
        "scripts/run_bybit_public_batch_evidence.py",
        "src/bybit_grid/data/public_batch/assemble.py",
        "src/bybit_grid/data/public_batch/capture.py",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/models.py",
        "src/bybit_grid/data/public_batch/pagination.py",
        "src/bybit_grid/data/public_batch/reconstruct.py",
        "src/bybit_grid/data/public_batch/recording.py",
        "tests/test_sprint_06_3b_1_owner_capture_semantic_closure.py"
      ]
    },
    {
      "pr": 55,
      "title": "Close Sprint 06.3B.2 — shared persisted-evidence validator, strict canonical JSONL, and owner probe",
      "merge_sha": "c66ef669932fd96a324db38e322cb45688f6baba",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "scripts/probe_bybit_public_connectivity.py",
        "scripts/run_bybit_public_batch_evidence.py",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/reconstruct.py",
        "src/bybit_grid/data/public_batch/recording.py",
        "tests/test_sprint_06_3b_2_true_semantic_closure.py",
        "tests/test_sprint_06_3b_persisted_public_batch_evidence.py"
      ]
    },
    {
      "pr": 56,
      "title": "Close owner lifecycle executability sprint",
      "merge_sha": "0e7a8296a2680eebb3c79edfb084d73c6f53fc42",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "scripts/run_bybit_public_batch_evidence.py",
        "src/bybit_grid/data/public_batch/audit.py",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/models.py",
        "src/bybit_grid/data/public_batch/reconstruct.py",
        "src/bybit_grid/data/public_batch/recording.py",
        "tests/test_sprint_06_3a_1_contract_type_aware_instrument_parsing.py",
        "tests/test_sprint_06_3b_2_true_semantic_closure.py",
        "tests/test_sprint_06_3b_3_owner_lifecycle_executability.py"
      ]
    },
    {
      "pr": 57,
      "title": "Close public batch evidence truthfulness regressions",
      "merge_sha": "9f225132a2b4ad5bf4035c65b124c4242223e8f4",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/reconstruct.py",
        "tests/test_sprint_06_3b_3_1_evidence_truthfulness.py",
        "tests/test_sprint_06_3b_3_owner_lifecycle_executability.py"
      ]
    },
    {
      "pr": 58,
      "title": "Two-phase reproducibility build for public batch; persist derived audit and add synthetic lifecycle tests",
      "merge_sha": "b9722b3af5fef3a9f088e098a1158e60a7f9a507",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_batch_input_contract_v1.md",
        "docs/sprint_06_3b_3_2_behavior_coverage.md",
        "src/bybit_grid/data/public_batch/evidence.py",
        "src/bybit_grid/data/public_batch/reconstruct.py",
        "tests/test_sprint_06_3b_3_2_reproducibility_and_lifecycle.py"
      ]
    },
    {
      "pr": 59,
      "title": "Add Sprint 06.4A canonical Parquet market-store package, contract, and tests",
      "merge_sha": "a74216b5f08376d15b2c4e56d489b12b2d435d7b",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "PROJECT_BOARD.md",
        "docs/bybit_public_parquet_store_contract_v1.md",
        "docs/sprint_06_3b_3_2_behavior_coverage.md",
        "docs/sprint_06_4a_behavior_coverage.md",
        "scripts/audit_bybit_public_parquet_store.py",
        "scripts/check_bybit_public_parquet_seed_review_pack.py",
        "scripts/hash_source_tree.py",
        "scripts/import_bybit_public_review_pack_to_store.py",
        "scripts/make_bybit_public_parquet_seed_review_pack.py",
        "scripts/plan_bybit_public_store_repairs.py",
        "src/bybit_grid/common/source_tree.py",
        "src/bybit_grid/data/market_store/__init__.py",
        "src/bybit_grid/data/market_store/audit.py",
        "src/bybit_grid/data/market_store/canonical.py",
        "src/bybit_grid/data/market_store/coverage.py",
        "src/bybit_grid/data/market_store/duckdb_views.py",
        "src/bybit_grid/data/market_store/evidence.py",
        "src/bybit_grid/data/market_store/import_public_batch.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/paths.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/data/market_store/resume.py",
        "src/bybit_grid/data/market_store/schemas.py",
        "src/bybit_grid/data/market_store/writer.py",
        "tests/test_sprint_06_4a_atomic_import_and_roundtrip.py",
        "tests/test_sprint_06_4a_coverage_resume_gap_repair.py",
        "tests/test_sprint_06_4a_parquet_store_contract.py",
        "tests/test_sprint_06_4a_store_evidence_pack.py"
      ]
    },
    {
      "pr": 60,
      "title": "Strict canonical Parquet store validation, behavior-coverage verifier, and CLIs",
      "merge_sha": "15366ff8b94ace6149483ba7e34f0aa3f5b2fa28",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/sprint_06_3b_3_2_behavior_coverage.md",
        "docs/sprint_06_4a_behavior_coverage.md",
        "scripts/audit_bybit_public_parquet_store.py",
        "scripts/check_behavior_coverage_maps.py",
        "scripts/check_bybit_public_parquet_seed_review_pack.py",
        "scripts/hash_source_tree.py",
        "scripts/import_bybit_public_review_pack_to_store.py",
        "scripts/make_bybit_public_parquet_seed_review_pack.py",
        "scripts/plan_bybit_public_store_repairs.py",
        "src/bybit_grid/common/pytest_coverage_map.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/paths.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/data/market_store/schemas.py",
        "src/bybit_grid/data/market_store/writer.py",
        "tests/test_sprint_06_behavior_coverage_material_nodes.py"
      ]
    },
    {
      "pr": 61,
      "title": "Close sprint 06.4A.2 store lifecycle",
      "merge_sha": "210432054f3fe3f6d7473e219a165b310d6182cf",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/bybit_public_parquet_store_contract_v1.md",
        "docs/sprint_06_3b_3_2_behavior_coverage.md",
        "docs/sprint_06_4a_behavior_coverage.md",
        "scripts/audit_bybit_public_parquet_store.py",
        "scripts/check_behavior_coverage_maps.py",
        "scripts/check_bybit_public_parquet_seed_review_pack.py",
        "scripts/import_bybit_public_review_pack_to_store.py",
        "scripts/make_bybit_public_parquet_seed_review_pack.py",
        "scripts/plan_bybit_public_store_repairs.py",
        "src/bybit_grid/common/pytest_coverage_map.py",
        "src/bybit_grid/common/strict_cli.py",
        "src/bybit_grid/data/market_store/audit.py",
        "src/bybit_grid/data/market_store/duckdb_views.py",
        "src/bybit_grid/data/market_store/import_public_batch.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/planner.py",
        "src/bybit_grid/data/market_store/schemas.py",
        "tests/test_sprint_06_4a_2_real_store_lifecycle.py",
        "tests/test_sprint_06_behavior_coverage_material_nodes.py"
      ]
    },
    {
      "pr": 62,
      "title": "Add Sprint 06.4A.3 required behavior gate",
      "merge_sha": "ff7b37a2a205386555ce1c8d68ce3ecbf589930d",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/sprint_06_4a_3_required_behaviors.json",
        "src/bybit_grid/common/pytest_coverage_map.py",
        "src/bybit_grid/data/market_store/canonical.py",
        "src/bybit_grid/data/market_store/models.py",
        "tests/test_sprint_06_4a_3_required_behaviors.py"
      ]
    },
    {
      "pr": 63,
      "title": "Close Sprint 06.4A.3 behavior coverage gaps",
      "merge_sha": "ef1523c9475b51bdc67714beca4720605f6b04da",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/sprint_06_4a_3_required_behaviors.json",
        "src/bybit_grid/common/pytest_coverage_map.py",
        "src/bybit_grid/data/market_store/resume.py",
        "src/bybit_grid/data/market_store/schemas.py",
        "tests/test_sprint_06_4a_3_material_behaviors.py",
        "tests/test_sprint_06_4a_3_required_behaviors.py"
      ]
    },
    {
      "pr": 64,
      "title": "Close market store graph semantics",
      "merge_sha": "db4df380cfc47acbfcbc4e937197ba20a77b34b2",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "src/bybit_grid/cli/__init__.py",
        "src/bybit_grid/cli/market_store_audit.py",
        "src/bybit_grid/data/market_store/audit.py",
        "src/bybit_grid/data/market_store/canonical.py",
        "src/bybit_grid/data/market_store/coverage.py",
        "src/bybit_grid/data/market_store/evidence.py",
        "src/bybit_grid/data/market_store/import_public_batch.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/data/market_store/resume.py",
        "src/bybit_grid/data/market_store/writer.py",
        "tests/test_sprint_06_4a_3_2_cli_lifecycle.py",
        "tests/test_sprint_06_4a_3_2_import_noop_store_graph.py",
        "tests/test_sprint_06_4a_3_2_replay_coverage_resume.py",
        "tests/test_sprint_06_4a_3_2_semantic_seed_pack.py",
        "tests/test_sprint_06_4a_3_2_writer_preflight_atomicity.py",
        "tests/test_sprint_06_4a_3_material_behaviors.py",
        "tests/test_sprint_06_4a_atomic_import_and_roundtrip.py"
      ]
    },
    {
      "pr": 65,
      "title": "Sprint 06.4A.3.3: deterministic import transaction, strict parsing, deep immutability, and governance tests",
      "merge_sha": "b7051a41014fe69e5cb67f65c4ed38ff96a12dec",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/sprint_06_4a_3_required_behaviors.json",
        "src/bybit_grid/common/strict_cli.py",
        "src/bybit_grid/data/market_store/audit.py",
        "src/bybit_grid/data/market_store/canonical.py",
        "src/bybit_grid/data/market_store/coverage.py",
        "src/bybit_grid/data/market_store/duckdb_views.py",
        "src/bybit_grid/data/market_store/evidence.py",
        "src/bybit_grid/data/market_store/import_public_batch.py",
        "src/bybit_grid/data/market_store/inventory.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/parsing.py",
        "src/bybit_grid/data/market_store/paths.py",
        "src/bybit_grid/data/market_store/planner.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/data/market_store/resume.py",
        "src/bybit_grid/data/market_store/transaction.py",
        "src/bybit_grid/data/market_store/writer.py",
        "tests/helpers/synthetic_market_store_fixture.py",
        "tests/test_sprint_06_4a_3_3_governance_cli.py",
        "tests/test_sprint_06_4a_3_3_import_audit.py",
        "tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py",
        "tests/test_sprint_06_4a_3_3_schema_plan_writer.py",
        "tests/test_sprint_06_4a_3_3_semantic_pack_cli.py"
      ]
    },
    {
      "pr": 66,
      "title": "Sprint 06.4A.3.4: enforce material tests, immutable review-pack loading, chunk/transaction/audit hardening",
      "merge_sha": "ae47603ca34030f6a019a9eeb5d99699bbeee570",
      "slice": "public_batch_market_store",
      "changed_paths": [
        "docs/sprint_06_4a_3_required_behaviors.json",
        "scripts/check_behavior_coverage_maps.py",
        "src/bybit_grid/common/pytest_coverage_map.py",
        "src/bybit_grid/data/market_store/audit.py",
        "src/bybit_grid/data/market_store/import_public_batch.py",
        "src/bybit_grid/data/market_store/models.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/data/market_store/transaction.py",
        "tests/helpers/synthetic_market_store_fixture.py",
        "tests/test_sprint_06_4a_3_3_governance_cli.py",
        "tests/test_sprint_06_4a_3_3_import_audit.py",
        "tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py",
        "tests/test_sprint_06_4a_3_3_schema_plan_writer.py",
        "tests/test_sprint_06_4a_3_3_semantic_pack_cli.py",
        "tests/test_sprint_06_4a_3_4_governance_cli.py",
        "tests/test_sprint_06_4a_3_4_import_audit.py",
        "tests/test_sprint_06_4a_3_4_replay_coverage_resume_duckdb.py",
        "tests/test_sprint_06_4a_3_4_schema_plan_writer.py",
        "tests/test_sprint_06_4a_3_4_semantic_pack_cli.py"
      ]
    }
  ]
}
```

## Fail-closed conclusion

`native_equivalence_proven`: `false`
`liquidation_proven`: `false`
`risk_budget_proven`: `false`
`profitability_proven`: `false`
`real_public_completeness_proven`: `false`
`legacy_raw_authoritative`: `false`
`canonical_e2e_proven`: `false`
`general_import_atomicity_proven`: `false`
`parameter_selection_sufficient`: `false`
`live_readiness`: `false`

This matrix publishes assurance evidence only. It changes no production behavior
and grants no credential, network, private API, public capture, live execution,
order, transfer, withdrawal, position, or trading-mutation authority.
