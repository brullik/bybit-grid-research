# Sprint 06.2A.2 — Strict Snapshot Identity and Funding Provenance Closure

## PM authorization

Sprint 06.2A and the functional parts of 06.2A.1 are accepted. This is the final in-memory OHLC adapter hardening before persisted OHLC evidence is allowed.

This task is text-only.

## Binary/generated-file prohibition

Do not add, modify or commit:

```text
*.zip
*.parquet
*.jsonl generated evidence
*.db / *.sqlite
market data
generated reports
.env
API keys
caches
```

Temporary artifacts under pytest `tmp_path` are allowed. Codex returns only source/test/doc changes and text output.

## Frozen scope

Do not change:

```text
neutral-grid geometry
position accounting
average entry
realized/unrealized PnL
completed-grid-cycle formulas
fee formulas
funding formula
termination/slippage formulas
OHLC = open -> high -> low -> close
OLHC = open -> low -> high -> close
consecutive-duplicate price removal
funding-before-price boundary order
termination prefix behavior
cycle envelope regression min=1, max=2
```

No:

```text
Bybit private API
live/testnet/demo trading
Telegram
historical parameter selection
Parquet integration
review-pack builder/checker
profitability claim
native-equivalence claim
liquidation model
5 USDT risk proof
```

Preserve all risk/readiness proof flags as false.

## Required red tests before implementation

Add tests that reproduce every current defect below before fixing it.

### A. Replay result type aliases accepted

Use a one-candle ambiguous replay whose source-derived counts equal 0 or 1. Prove the current audit incorrectly accepts at least:

```text
candle_count_input=1 -> True
candle_count_processed=1 -> True
candles_not_processed_after_termination=0 -> False
ambiguous_candle_count=1 -> True
terminated_bool=False -> 0
category/symbol exact str -> str subclass
```

Also use a flat/zero-PnL case and prove an `int 0` cannot substitute for `Decimal("0")`.

### B. Mutable evidence containers accepted

Prove the current audit accepts:

```text
source_candles tuple -> list
source_funding_observations tuple -> list
```

### C. Alternate valid nested state-machine result accepted

Use this exact deterministic reproduction:

```text
config:
  category=linear
  symbol=BTCUSDT
  lower_price=80
  upper_price=120
  base_price=100
  grid_cell_number=6
  quantity_per_grid_base=0.01
  maker_fee_rate=0.001
  taker_fee_rate=0.001

candle:
  open_time_ms=60000
  open=94
  high=96
  low=82
  close=92
```

Generate OHLC and OLHC replay results. They have the same top-level final PnL but different nested ledgers. Replace only the OHLC `state_machine_result` with the OLHC nested result. The hardened audit must reject it.

### D. Envelope type aliases accepted

Prove rejection is required for at least:

```text
ambiguous_candle_count=1 -> True
exact_assignment_count=2 -> 2.0
path_sensitive_bool=False -> 0
Decimal zero PnL width -> int 0
assignment_results tuple -> list
completed_cycle_count=1 -> True
```

### E. Invalid funding containers accepted

Prove these are currently silently treated as empty and must instead fail with stable `ValueError`:

```text
False
0
""
b""
{}
```

### F. Missing source provenance

Add tests proving the final implementation rejects:

```text
FundingObservation symbol != config/candle symbol
FundingObservation category != linear
FundingObservation symbol with leading/trailing whitespace
mixed synthetic and Bybit candle sources in one replay
```

## Task 1 — FundingObservation instrument provenance

Change `FundingObservation` before persisted evidence is introduced.

Required fields:

```text
category: str
symbol: str
time_ms: int
funding_rate: Decimal
mark_price: Decimal
```

Runtime requirements:

```text
type(category) is str
category == "linear"
type(symbol) is str
symbol is non-empty
symbol == symbol.strip()
time_ms is int, not bool, non-negative, minute-aligned
funding_rate is finite Decimal
mark_price is finite positive Decimal
```

Update all existing tests/call sites.

`validate_funding_observations()` must require every observation to match the replay config/candle category and symbol exactly.

Do not infer or default category/symbol.

## Task 2 — Strict public sequence inputs

Do not use falsey-coalescing such as:

```python
tuple(funding or ())
```

Contracts:

```text
funding_observations is None OR an actual non-string Sequence
candles is an actual non-string Sequence
path policy is MinimalPathPolicy OR an actual non-string Sequence
```

Reject:

```text
bool
int
float
str
bytes
mapping
arbitrary non-sequence object
```

with stable `ValueError`, not incidental `TypeError`/`AttributeError`.

Empty funding sequence is valid. Empty candle sequence remains invalid.

Use exact item types where the contract says exact runtime model:

```text
type(candle) is OhlcCandle1m
type(funding observation) is FundingObservation
```

## Task 3 — Uniform candle-source contract

A replay may contain only one `CandleSource` value.

Reject a sequence mixing:

```text
synthetic_1m
bybit_trade_kline_1m
```

The result must expose the source unambiguously. Either:

1. add `candle_source: CandleSource` to `OhlcReplayResult`, or
2. enforce/derive it from an exact retained tuple and validate it in every audit.

Prefer an explicit result field because persisted evidence will need it.

## Task 4 — Explicit source config evidence

Add to `OhlcReplayResult`:

```text
source_config: NeutralGridConfig
```

Requirements:

```text
type(source_config) is NeutralGridConfig
source_config == state_machine_result.config using strict typed identity
source_config category/symbol match candles and funding observations
fresh replay uses source_config, not the stored nested result's config
```

This makes input provenance explicit before the persisted-evidence sprint.

## Task 5 — Exact replay snapshot shape validation

Create a fail-closed helper used at the start of `audit_ohlc_replay_result()`.

Require exact field/container types:

```text
result type is exactly OhlcReplayResult
category/symbol are exact str
entry/count fields are exact int, never bool
terminated/state-machine-audit flags are exact bool
final prices/PnL are finite Decimal
path_policies is exact tuple of MinimalPathPolicy
source_candles is exact tuple of exact OhlcCandle1m
source_funding_observations is exact tuple of exact FundingObservation
generated_events is exact tuple of exact GeneratedReplayEvent
state_machine_result is exact SimulationResult
source_config is exact NeutralGridConfig
termination_reason is exact str or None
```

Validate non-negative counts and obvious internal ranges before fresh replay.

The audit must reject mutable `list` substitutions even when their elements are otherwise identical.

## Task 6 — Strict recursive identity comparison

Python `==` is insufficient because:

```text
True == 1
False == 0
2 == 2.0
Decimal("0") == 0
```

Implement one strict comparison path for replay evidence.

Acceptable approaches:

### Option A — strict recursive comparator

Require:

```text
type(left) is type(right)
Enum members match by exact enum type/member
Decimal values are Decimal on both sides and equal
frozen dataclasses compare every field recursively
tuples compare length/items recursively
mappings compare exact key sets and values recursively
no bool/int/float coercion
```

### Option B — canonical typed normalization plus explicit shape validation

The representation must preserve bool/int/Decimal/enum/container identity and include the entire nested state-machine result.

Do not use a normalizer that converts tuple and list to the same representation unless Task 5 has already rejected the list.

Return stable mismatch paths/codes.

## Task 7 — Bind the entire nested state-machine result to fresh replay

`audit_ohlc_replay_result()` must:

1. validate exact snapshot shape;
2. validate source config/candles/funding provenance;
3. reconstruct the expected schedule;
4. run a fresh replay using `source_config`;
5. rerun `audit_simulation_result()` on the stored nested result;
6. require strict identity between the entire stored and fresh `OhlcReplayResult`, including the entire nested `SimulationResult`;
7. still produce useful named failures rather than a traceback.

At minimum it must separately identify:

```text
source_config_mismatch
replay_scalar_type_mismatch
source_container_type_mismatch
generated_event_stream_mismatch
state_machine_result_mismatch
state_machine_audit_failed
```

The concrete alternate-path nested-result substitution from the red test must fail specifically because the stored ledger/order/cycle state does not match the fresh path replay.

## Task 8 — Exact envelope snapshot shape

At the start of `audit_minimal_path_ambiguity_envelope()` require:

```text
envelope type is exactly MinimalPathAmbiguityEnvelope
ambiguous/exact/cycle counts are exact int, never bool
all completion/path-sensitive/guardrail fields are exact bool
all PnL/fee fields are finite Decimal
min_assignment/max_assignment are exact tuple of MinimalPathPolicy
termination_reasons_observed is exact tuple of exact str or None
assignment_results is exact tuple of exact OhlcReplayResult
```

Reject list, float and boolean aliases.

## Task 9 — Strict full envelope reconciliation

After every assignment result passes the hardened replay audit:

1. reconstruct the exact Cartesian policy set;
2. rebuild the expected envelope from the assignment results;
3. compare the full stored envelope to the recomputed envelope using strict typed identity;
4. preserve deterministic assignment ordering and PnL tie-breaking;
5. preserve the accepted cycle regression min=1/max=2;
6. preserve all four intrabar/global proof flags as exact false.

Do not use type-loose equality for any aggregate.

## Task 10 — Expanded adversarial regression tests

Create:

```text
tests/test_sprint_06_2a_2_strict_snapshot_identity_and_funding_provenance.py
```

At minimum cover separately:

1. Replay count `1 -> True` rejection.
2. Replay zero count `0 -> False` rejection.
3. `terminated_bool=False -> 0` rejection.
4. Exact `str` versus str-subclass rejection.
5. Decimal zero versus int zero rejection.
6. `source_candles tuple -> list` rejection.
7. `source_funding_observations tuple -> list` rejection.
8. `generated_events tuple -> list` rejection.
9. `path_policies tuple -> list` rejection.
10. Alternate-path nested SimulationResult substitution rejection using the frozen concrete example.
11. Nested config mismatch rejection.
12. Valid fresh replay still passes for OHLC and OLHC.
13. Funding `False`, `0`, `""`, `b""`, `{}` rejection.
14. Funding category mismatch rejection.
15. Funding symbol mismatch rejection.
16. Funding whitespace symbol rejection.
17. Mixed candle source rejection.
18. Valid same-source synthetic replay passes.
19. Valid same-source Bybit replay passes.
20. Envelope `1 -> True` count rejection.
21. Envelope `2 -> 2.0` count rejection.
22. Envelope Decimal zero -> int zero rejection.
23. Envelope bool -> int rejection.
24. Envelope assignment-results tuple -> list rejection.
25. Envelope completed-cycle count `1 -> True` rejection.
26. Every valid assignment passes strict replay audit.
27. Exact envelope reconstruction still passes.
28. Concrete cycle bounds remain min=1/max=2.
29. Seeded randomized short-path smoke: generated valid results/envelopes pass their audits.
30. All risk/readiness flags remain false.
31. No private/live API or Telegram surface.

Use small deterministic fixtures only. No owner market data.

## Task 11 — Contract documentation

Update:

```text
docs/ohlc_minimal_path_replay_contract_v1.md
```

Add a Sprint 06.2A.2 section documenting:

```text
exact Python runtime type identity
immutable tuple evidence
explicit source_config
uniform CandleSource
funding category/symbol provenance
strict non-falsey sequence inputs
whole-result fresh replay comparison
whole-envelope strict reconciliation
```

Do not claim complete tick-path reconstruction, native equivalence or a true global PnL bound.

## Required commands

```powershell
python scripts/check_numeric_environment.py
python -m pip check
python scripts/check_no_live_execution.py

python -m pytest tests/test_sprint_06_1a_neutral_grid_state_machine.py -q
python -m pytest tests/test_sprint_06_1a_1_state_machine_hardening.py -q
python -m pytest tests/test_sprint_06_1a_2_canonical_geometry_and_audit_closure.py -q
python -m pytest tests/test_sprint_06_1b_synthetic_scenario_evidence.py -q
python -m pytest tests/test_sprint_06_1b_1_evidence_checker_closure.py -q
python -m pytest tests/test_sprint_06_1b_2_exact_base_and_canonical_evidence.py -q
python -m pytest tests/test_sprint_06_1b_3_strict_json_type_identity.py -q
python -m pytest tests/test_sprint_06_2a_ohlc_minimal_path_replay.py -q
python -m pytest tests/test_sprint_06_2a_1_ohlc_replay_provenance_audit_and_envelope_closure.py -q
python -m pytest tests/test_sprint_06_2a_2_strict_snapshot_identity_and_funding_provenance.py -q
python -m pytest -q

ruff check .
git diff --check
```

If Git is unavailable, report it without failing the Python work.

## Acceptance criteria

```text
all tests pass
Ruff passes
no-live audit passes
no generated/binary files added
frozen economics unchanged
frozen OHLC/OLHC paths unchanged
FundingObservation carries exact category/symbol provenance
invalid falsey funding containers rejected
mixed candle sources rejected
source_config retained explicitly
all retained evidence containers are exact tuples
all replay scalar/container types exact
entire stored nested state-machine result equals fresh replay
alternate valid nested result substitution rejected
entire envelope reconciles with strict typed identity
cycle min/max regression remains 1..2
risk_budget_proven_bool = false
parameter_selection_performed_bool = false
profitability_claims_present_bool = false
live_execution_present_bool = false
```

## Required return to PM

Return text only:

```text
commit hash, when available
changed text files
git diff --stat
full pytest output
06.2A focused output
06.2A.1 focused output
06.2A.2 focused output
Ruff output
no-live audit output
numeric environment output
pip check output
git diff --check output or Git-unavailable note
FundingObservation provenance summary
strict input-container summary
snapshot shape/type summary
whole-result fresh replay comparison summary
alternate nested-result regression summary
envelope strict identity summary
randomized audit-smoke summary
all proof/readiness flag values
known remaining limitations
```

Do not generate or upload a review pack in this sprint.
