# Setup and Test Runbook

## 1. Supported environment

Python 3.12+. Current CI validates Python 3.12 and 3.14 on Ubuntu. Windows is the owner workstation target; WSL2/Ubuntu is recommended for the full project because atomic seed installation uses Linux `/proc/self/fd` and `renameat2(RENAME_NOREPLACE)`. Native Windows remains suitable for the documented offline checks, but full cross-platform seed-install support is not claimed. Linux VPS/self-hosted runner is a future deployment target, not an existing capability.

## 2. Installation

Windows PowerShell:

~~~powershell
git clone https://github.com/brullik/bybit-grid-research.git
Set-Location bybit-grid-research
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
~~~

POSIX:

~~~bash
git clone https://github.com/brullik/bybit-grid-research.git
cd bybit-grid-research
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
~~~

Create `.env` only on the trusted machine. Leave secrets blank for offline work. Never commit `.env`. If the destination already exists, inspect it instead of overwriting it.

## 3. Extended local offline verification

From repository root:

~~~bash
python scripts/check_numeric_environment.py
python scripts/check_no_live_execution.py
python -m compileall -q src tests scripts
python -m pytest tests -q
python -m pytest -q
ruff check .
python -m pip check
~~~

A failure blocks progression. Do not skip, xfail, weaken tests or bypass PM scope.

`python -m pytest tests -q` and `python -m pytest -q` currently both select the ordinary suite because `pyproject.toml` sets `testpaths = ["tests"]`; both spellings are retained here for contributor diagnostics. Neither reproduces the isolated base-controlled `pm_acceptance` staging performed by GitHub. The workflow's supplemental order is numeric check, pip check, no-live audit, compile, pytest, Ruff and `git diff --check`.

### GitHub Draft and Ready lifecycle

For a Draft PR, inspect the component jobs: `protected-paths`, `acceptance (3.12)` and `acceptance (3.14)`. The aggregate `pm-acceptance` intentionally reports failure while `draft=true`, even when all three component jobs are green; that expected Draft aggregate is not a material-test failure. If a component job fails, keep the PR Draft and fix the exact cause. When all three component jobs are green, mark the unchanged PR Ready for review. Ready starts a new run: merge only after its component jobs and aggregate `pm-acceptance` are all green. Never merge a pending, unknown or failed Ready status.

## 4. Public-data boundary

Public scripts may require network but do not require credentials. Start with scripts/smoke_public_api.py and inspect scripts/run_bybit_public_batch_evidence.py. Run them only as an explicit owner-network step and preserve redacted evidence. The strict 06.4C–06.4F chain currently accepts supplied bytes and builds in-memory evidence; it is not yet an end-to-end downloader or canonical-store publication pipeline.

Legacy scripts and strict/canonical paths are not interchangeable. Range/outcome scripts still read data/raw; do not claim a canonical E2E result.

### Fixed public-batch capture

The current capture is intentionally fixed to run id `bybit_public_batch_063b_btcusdt_v1`, BTCUSDT, 1001 kline rows and 100 funding-lookback days. Use a fresh output root: an existing final run directory is a fail-closed error.

~~~bash
python scripts/run_bybit_public_batch_evidence.py --run-id bybit_public_batch_063b_btcusdt_v1 --symbol BTCUSDT --kline-row-count 1001 --funding-lookback-days 100 --output-root data/processed/public_batch_runs_owner_20260717 --base-url https://api.bybit.com --timeout-seconds 30
~~~

Build and independently validate the public review pack:

~~~bash
python scripts/make_bybit_public_batch_review_pack.py --run-id bybit_public_batch_063b_btcusdt_v1 --input-root data/processed/public_batch_runs_owner_20260717 --output data/processed/review_packs/bybit_public_batch_063b_btcusdt_v1.zip

python scripts/check_bybit_public_batch_review_pack.py --zip data/processed/review_packs/bybit_public_batch_063b_btcusdt_v1.zip --run-id bybit_public_batch_063b_btcusdt_v1
~~~

After the checker succeeds, compute and record the review-pack SHA-256 on the trusted machine. PowerShell:

~~~powershell
(Get-FileHash data/processed/review_packs/bybit_public_batch_063b_btcusdt_v1.zip -Algorithm SHA256).Hash.ToLowerInvariant()
~~~

POSIX:

~~~bash
sha256sum data/processed/review_packs/bybit_public_batch_063b_btcusdt_v1.zip
~~~

Copy exactly the 64 lowercase hexadecimal characters, replace `REPLACE_WITH_64_LOWERCASE_HEX` below, then import into an absent/fresh canonical store and audit it. Do not reuse a digest from another file or run:

~~~bash
python scripts/import_bybit_public_review_pack_to_store.py --review-pack data/processed/review_packs/bybit_public_batch_063b_btcusdt_v1.zip --store-root data/canonical_market_store --expected-run-id bybit_public_batch_063b_btcusdt_v1 --expected-sha256 REPLACE_WITH_64_LOWERCASE_HEX

python scripts/audit_bybit_public_parquet_store.py --store-root data/canonical_market_store
~~~

Create and check the portable seed pack:

~~~bash
python scripts/make_bybit_public_parquet_seed_review_pack.py --store-root data/canonical_market_store --output data/processed/bybit_public_batch_063b_btcusdt_v1-store-seed.zip

python scripts/check_bybit_public_parquet_seed_review_pack.py --review-pack data/processed/bybit_public_batch_063b_btcusdt_v1-store-seed.zip
~~~

The library's atomic `install_seed_review_pack()` boundary is Linux-specific, requires an absent destination, `/proc/self/fd` and `renameat2(RENAME_NOREPLACE)`, and currently has no canonical operator CLI. Do not improvise a native-Windows overwrite/rename substitute.

This proves only the bounded fixed batch and its store import. It does not prove broad historical coverage or the missing canonical research E2E.

## 5. Private validate boundary

Private calls are not part of the default runbook. P0 supports only exact mainnet read-only GET and /v5/fgridbot/validate. Before any owner-private run: #133 and security assurance must be clean, key must have no withdrawal permission, secrets stay in local/approved secret storage, and an explicit owner checkpoint is required. create/close/order/withdraw remain forbidden.

## 6. VPS and self-hosted runner

No deployment workflow, systemd unit, container or self-hosted runner configuration is currently represented. Do not place secrets in repository variables, logs or agent context. A future deployment task must freeze host hardening, least privilege, secret injection, monitoring, backup, rollback and kill-switch behavior.

## 7. Troubleshooting

- Import error: confirm the venv is active and rerun python -m pip install -e ".[dev]".
- Numeric environment failure: use supported Python/dependency ranges; do not silence the check.
- no-live violation: inspect the reported source; do not add an allowlist outside a PM task.
- PM scope failure: compare the PR diff with pm_acceptance/active_task.json.
- Pending/failed CI component job: keep Draft and inspect the exact Actions job. An aggregate failure caused only by `draft=true` is expected; after green component jobs, mark Ready and require a new fully green run; never merge unknown status.
- Data gap/provenance failure: stop and regenerate evidence; never fill silently.
- Validate boundary error: do not override endpoint/origin/settings; treat it as fail closed.
- Encoding on Windows: use UTF-8 and keep generated artifacts outside Git.

## 8. Safe handoff

Report only commands, sanitized counts, rule IDs, commit SHAs and redacted summaries. Raw secrets or scanner matches remain on the owner machine.
