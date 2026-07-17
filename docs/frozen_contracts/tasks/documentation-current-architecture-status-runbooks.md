# Documentation — current architecture, status, evidence, and runbooks

## Scope and authority

Task ID: `documentation-current-architecture-status-runbooks`.

This documentation-only task closes issue #132 against the production-code audit baseline
`35a3b9c05b1bf3d86756e449b2735bef0893bc45`, merged by PR #143. It replaces bootstrap-era
claims with repository-verifiable status and gives a first-time contributor a safe setup,
verification, evidence, and troubleshooting route.

Passing this task proves only that the named documents accurately describe the bounded current
repository. It grants no network, credential, private-request, order, withdrawal, transfer,
position, native-grid create/close, Telegram, VPS, self-hosted-runner, deployment, or live
authority.

The task-definition PR changes exactly these three protected paths:

- `pm_acceptance/active_task.json`;
- `pm_acceptance/tasks/documentation-current-architecture-status-runbooks/`
  `test_current_architecture_status_runbooks.py`;
- `docs/frozen_contracts/tasks/documentation-current-architecture-status-runbooks.md`.

The later implementation PR changes exactly these thirteen required paths:

1. `.env.example`;
2. `00_PROJECT_CONTEXT_FOR_CODEX.md`;
3. `01_PROJECT_RULES.md`;
4. `02_TECHNICAL_SPEC.md`;
5. `03_SPRINT_01_API_DATA_FEASIBILITY.md`;
6. `04_CODEX_PROMPT_SPRINT_01.md`;
7. `05_RISK_AND_RESEARCH_POLICY.md`;
8. `PROJECT_BOARD.md`;
9. `README.md`;
10. `docs/CURRENT_ARCHITECTURE_AND_STATUS.md`;
11. `docs/EVIDENCE_MAP.md`;
12. `docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md`;
13. `docs/SETUP_TEST_RUNBOOK.md`.

No production source, script, workflow, dependency, lock file, ordinary test, checker, package
export, generated artifact, evidence artifact, acceptance test, or frozen contract may change in
the implementation PR. Base-owned tests may not be weakened, moved, skipped, or replaced.

## Availability and RED contract

All thirteen paths are UTF-8 text. `README.md` starts with the exact marker:

```text
<!-- documentation-contract: current-v1 -->
```

HTML comments are removed before substantive-length checks, so comment padding cannot satisfy
the contract. Visible minimum sizes are:

| Path | Minimum characters |
|---|---:|
| `.env.example` | 300 |
| `00_PROJECT_CONTEXT_FOR_CODEX.md` | 600 |
| `01_PROJECT_RULES.md` | 900 |
| `02_TECHNICAL_SPEC.md` | 900 |
| `03_SPRINT_01_API_DATA_FEASIBILITY.md` | 400 |
| `04_CODEX_PROMPT_SPRINT_01.md` | 400 |
| `05_RISK_AND_RESEARCH_POLICY.md` | 900 |
| `PROJECT_BOARD.md` | 500 |
| `README.md` | 1,000 |
| `docs/CURRENT_ARCHITECTURE_AND_STATUS.md` | 1,200 |
| `docs/EVIDENCE_MAP.md` | 1,200 |
| `docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md` | 1,200 |
| `docs/SETUP_TEST_RUNBOOK.md` | 1,200 |

Every Markdown file has one visible H1 as its first nonblank line and at least one visible H2.
Until all availability conditions hold, every material test raises exactly:

```text
current_documentation_unavailable
```

The unmodified baseline and mandatory comment-only/stub RED probe each collect exactly 24 tests
and produce 24 exact `RuntimeError: current_documentation_unavailable` failures: zero pass, skip,
xfail, collection error, or other failure. The RED probe changes every required path, but may only
append inert comments to existing files and create the four absent documents as inert stubs. It is
closed unmerged after both Python matrices prove the exact failure profile.

## Binding product and risk truth

The documentation consistently preserves these binding constraints:

- research capital: 500 USDT;
- maximum total loss per grid: 5 USDT, not investment size;
- one active grid per instrument;
- initial global concurrency cap: 1;
- native Bybit USDT linear perpetual Futures Grid only;
- neutral mode and geometric grid type only;
- SL-only V1 exit;
- TP and trailing forbidden;
- API key without withdrawal permission;
- first live actions require manual Telegram confirmation.

Each risk-bearing current document contains the exact, non-conflicting pairs:

```text
`capital_usdt`: `500`
`max_loss_per_grid_usdt`: `5`
`max_grids_per_instrument`: `1`
`initial_global_concurrency_cap`: `1`
`grid_mode`: `neutral`
`grid_type`: `geometric`
`exit_policy`: `SL-only`
`take_profit_enabled`: `false`
`trailing_enabled`: `false`
`withdrawals_authorized`: `false`
`first_live_requires_manual_telegram_confirmation`: `true`
```

A second value for any key fails. A prose line that positively claims TP, trailing, or withdrawal
authority without a same-line negative also fails; exact false pairs cannot be contradicted by
free text.

The documents state these as future gates, not implemented live behavior. They also preserve
no-lookahead, train/validation/test, out-of-symbol, stress, cost, concentration, drawdown, Monte
Carlo, OOS profit-factor, expected-value, paper/shadow, and semi-auto thresholds already present
in the binding research policy.

## Current capability status

The current documentation says the project is not a ready trading bot. It may claim only bounded
components supported by current source and evidence:

- public API/data components;
- canonical Parquet market-store models, atomic writer, audit, reader, coverage/resume, and
  read-only in-memory DuckDB views;
- range reference/NumPy and event components;
- Decimal neutral-grid semantic state machine;
- minimal-path OHLC replay;
- pure-offline historical plan, response admission, transcript, and in-memory layout;
- exact fail-closed private read/validate-only boundary.

It explicitly records the missing vertical path:

```text
historical evidence
  -> canonical store
  -> canonical reader
  -> range candidates
  -> semantic neutral/geometric replay
  -> complete costs and forced SL
  -> walk-forward/OOS selection
  -> bounded decision
```

The legacy range/outcome scripts still consume `data/raw/klines`,
`data/raw/mark_klines`, and `data/raw/funding`; no silent fallback may be presented as canonical
E2E evidence. Outcome/scoring remains proxy-only. Native quantity and termination mapping,
liquidation, the 5 USDT risk budget, parameter sufficiency, portfolio decision, and profitability
remain unproven.

`src/bybit_grid/backtest/grid_simulator.py`, research placeholders, and much of `live/` are not
represented as implemented systems. Telegram runtime, live execution, reconciliation, deployment,
and VPS/self-hosted-runner support remain unavailable.

`README.md` contains exact false status pairs for live execution, Telegram runtime, and VPS
deployment. `docs/CURRENT_ARCHITECTURE_AND_STATUS.md` contains exact false status pairs for
create-grid, close-grid, Telegram runtime, live execution, and VPS deployment. A same-line positive
availability, implementation, or authorization claim without an explicit negative fails.

## Private validate-only boundary

The documents describe, but do not execute, the current exact boundary:

- mainnet origin `https://api.bybit.com`;
- read-only GET `/v5/account/info`;
- read-only GET `/v5/account/wallet-balance`;
- read-only GET `/v5/account/fee-rate`;
- sole private POST `/v5/fgridbot/validate`;
- neutral/geometric, stop-loss-only payload;
- `trust_env=False` and `follow_redirects=False` private transport;
- generic private POST refused by `generic_private_post_forbidden`;
- `create_grid_bot` and `close_grid_bot` unavailable.

No real credential use is permitted before issue #133 and the security assurance gates. A setting,
environment flag, dry run, passing test, or validate success never creates live authority.

## Exact environment example

Ignoring comments and blank lines, `.env.example` has exactly the uppercase fields of
`bybit_grid.config.Settings`, once each, with these values:

```dotenv
BYBIT_ENV=mainnet
BYBIT_API_BASE_URL=https://api.bybit.com
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_RECV_WINDOW=5000
LIVE_TRADING_ENABLED=false
ALLOW_LIVE_TRADING=NO
DATA_DIR=./data
LOG_LEVEL=INFO
GRID_VALIDATE_ENABLED=false
BYBIT_FGRID_VALIDATE_PATH=/v5/fgridbot/validate
BYBIT_FGRID_GRID_MODE_NEUTRAL=1
BYBIT_FGRID_GRID_TYPE_GEOMETRIC=2
```

Telegram and create/close/detail variables are absent because those capabilities are not current
Settings fields. Secrets remain blank and every sensitive feature remains disabled.

## Current documents and roadmap

`README.md` is the current entry point, not a starter-package instruction. It links every current
document and `.env.example`, supplies Windows and POSIX offline setup, lists the full safe check
set, and distinguishes implemented components from missing E2E/live capabilities.

`00_PROJECT_CONTEXT_FOR_CODEX.md` instructs agents to read `AGENTS.md`, then
`pm_acceptance/active_task.json`, and treats `NO_ACTIVE_IMPLEMENTATION` as no production-edit
authority.

`01_PROJECT_RULES.md` contains the binding product, risk, secret, data, research, governance,
future Telegram, emergency, and ranking policy without pretending those future capabilities exist.

`02_TECHNICAL_SPEC.md` is a status-aware component map. It distinguishes canonical Parquet from
read-only DuckDB views, strict historical boundaries from network acquisition, and legacy inputs
from the missing canonical vertical path.

`03_SPRINT_01_API_DATA_FEASIBILITY.md` and `04_CODEX_PROMPT_SPRINT_01.md` are explicit historical
archives with no current implementation, private, or live authority.

`PROJECT_BOARD.md` records completed P0 evidence and the ordered open work: #132 documentation,
#133 history/secret gate, #134 pre-control-plane assurance, corrected #129 archive lifecycle, and
bounded #131 E2E tasks. Planning order is not implementation authority.

## Evidence map

`docs/EVIDENCE_MAP.md` distinguishes merged task/implementation/close changes from mandatory RED
probes closed unmerged. It indexes:

- the PM control plane and canonical-store lifecycles;
- strict historical lifecycles #110–#128;
- final P0 chain #135, #139–#143;
- Ready CI runs 29540177525 and 29553808388;
- 513 ordinary tests on the recorded P0 implementation run;
- the pre-control-plane PR #1–66 assurance gap tracked by #134;
- the full-history/ref-retention gap tracked by #133.

Current green tests are explicitly not retroactive proof for PR #1–66, end-to-end product proof,
profitability proof, or a completed full-history secret scan.

## Setup, public workflow, and troubleshooting

`docs/SETUP_TEST_RUNBOOK.md` includes Python 3.12+ setup for Windows PowerShell and POSIX, while
identifying Ubuntu/WSL2 as the full environment for Linux-specific atomic seed installation. It
contains these safe local checks:

```text
python scripts/check_numeric_environment.py
python scripts/check_no_live_execution.py
python -m compileall -q src tests scripts
python -m pytest tests -q
python -m pytest -q
ruff check .
ruff format --check .
python -m pip check
```

It explains that ordinary pytest does not reproduce base-controlled PM staging. It documents the
owner-network public smoke/fixed-batch route, review-pack validation, SHA-pinned canonical-store
import, store audit, portable seed-pack creation/check, and the Linux no-replace seed-install
boundary. The fixed batch is not described as a broad historical downloader.

Troubleshooting remains fail closed for numeric, no-live, scope, pending/failed CI, data
gap/provenance, and validate errors. The document forbids skipping checks, silently filling gaps,
weakening endpoint/origin policy, and merging an unknown status.

## Minimal-live Definition of Done

`docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md` is an unmet sequential gate. It includes at least 20
unchecked items and the completed validate-only P0 item, while requiring:

- canonical store-to-decision E2E;
- semantic neutral/geometric replay;
- complete costs, liquidation, forced SL, and 5 USDT risk proof for 500 USDT capital;
- leakage-free walk-forward/OOS and an explicit `no_policy_passes` outcome;
- one grid per instrument and global cap 1;
- #133 and #134 assurance;
- no withdrawal permission;
- exact, expiring manual Telegram approval for first live actions;
- durable state/restart/reconciliation and ambiguous-outcome handling;
- emergency and VPS/self-hosted-runner operational gates;
- exact performance thresholds and 100 confirmed operations before semi-auto.

The current verdict is exact and remains false:

```text
Current verdict: Minimal-live DoD is unmet. No live trading is authorized.
```

The only checked checklist item is exactly
`Validate-only P0 transport boundary completed by #142/#143.` Every other checklist item remains
unchecked. Exact pairs keep both current minimal-live readiness and live authority false.

## Exact material acceptance set

The frozen file contains exactly 24 plain synchronous `test_*` functions. It checks current entry
points, link/path integrity, historical tombstones, exact Settings parity, safe defaults, real
source paths and claims, legacy versus strict data paths, missing E2E links, proxy/selection/risk
truthfulness, completed lifecycle evidence, pre-control-plane/history caveats, setup commands,
public/private/VPS boundaries, troubleshooting, and the unmet minimal-live DoD.

Semantic checks run on Markdown with HTML comments removed. Relative links must resolve to files
inside the implementation root; absolute paths and traversal outside the repository fail. The
suite rejects conflicting risk/live prose, unsafe alternate environment defaults, extra checked
live gates, and link targets outside the repository.

Implementation GREEN requires 24/24 material tests plus every ordinary workflow gate on Python
3.12 and 3.14. Passing documentation is not an authorization to trade or to supply credentials.
