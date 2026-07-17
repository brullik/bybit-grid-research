# Minimal-live Definition of Done

Ниже перечислены gates. Если пункт не подтверждён свежим evidence, он считается невыполненным.

Exact current and policy state:

~~~text
`current_minimal_live_ready`: `false`
`live_execution_authorized`: `false`
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
~~~

## A. Offline research product

- [ ] Verified public history reaches canonical store with completeness/provenance.
- [ ] Range candidates read only the canonical store; no silent legacy fallback.
- [ ] Every candidate runs semantic neutral geometric replay.
- [ ] Native quantity, levels and termination mapping are validated.
- [ ] Fees, spread, slippage, funding, liquidation and forced SL are included.
- [ ] Worst-case total loss is at most 5 USDT for capital 500 USDT.
- [ ] Walk-forward/OOS selection is leakage-free and sufficient.
- [ ] One grid per instrument and initial global cap 1 are enforced.
- [ ] insufficient_evidence and no_policy_passes fail closed.
- [ ] Deterministic synthetic E2E passes before owner public history.

## B. Repository and assurance

- [ ] #133 full-history secret scan and retention proof are clean.
- [ ] Required ruleset/branch protection is exported and verified.
- [ ] #134 classifies and revalidates relevant behavior from PR #1–66.
- [ ] All discovered gaps complete their own governed RED/fix/close lifecycle.
- [ ] Documentation and runbooks match current main.

## C. Performance evidence

- [ ] OOS profit factor is at least 1.25 after all costs.
- [ ] Expected value is at least +0.05R, where R is 5 USDT.
- [ ] Historical portfolio max drawdown at cap 1–3 is at most 20%.
- [ ] Any result above 25% max drawdown is rejected.
- [ ] Monte Carlo probability of 50% drawdown over 1000 signals is at most 10%.
- [ ] Single-symbol contribution is at most 25% of final net profit.
- [ ] Worst 1% outcomes preserve the 5 USDT risk model.
- [ ] A final NO-GO remains an accepted outcome.

## D. Exchange/account safety

- [x] Validate-only P0 transport boundary completed by #142/#143.
- [ ] Bybit product/account/region eligibility is owner-verified.
- [ ] API key has read+trade only when needed and no withdrawal permission.
- [ ] Credential storage, rotation and redaction are tested outside repository logs.
- [ ] Mainnet minimum investment and 5 USDT total-loss model both pass.
- [ ] Kill switch, idempotency, reconciliation and recovery are proven.
- [ ] Durable state survives restart and reconciles every ambiguous request outcome before retry.

## E. Live and operations

- [ ] create/close native grid lifecycle is separately designed and frozen.
- [ ] Telegram signal, manual confirmation, status, SL, errors and emergency are implemented.
- [ ] First live actions require manual Telegram confirmation.
- [ ] Each confirmation is single-use, expiring and bound to the exact immutable payload and risk.
- [ ] Emergency stop blocks new entries until manual resume; active-grid handling is separately frozen and tested.
- [ ] Linux VPS/self-hosted runner deployment, monitoring, backup and rollback are proven.
- [ ] Initial global concurrency cap 1 is enforced end to end.
- [ ] 100 confirmed operations without systemic errors plus performance gates precede semi-auto.

## Owner-only checkpoints

Owner approval is required before credentials, any private/local Bybit run, owner public-history acquisition, deployment and every first live mutation. Flags or a passing unit test never substitute for approval.

Current verdict: Minimal-live DoD is unmet. No live trading is authorized.
