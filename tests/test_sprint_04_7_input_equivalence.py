from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from bybit_grid.research.outcome_core.input_loader import (
    discover_unique_parquet_files,
    load_canonical_symbol_frames,
)
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes


def _write_all_roots(
    tmp_path: Path, symbol: str, funding: pl.DataFrame | None = None
) -> tuple[Path, Path, Path]:
    k = tmp_path / "klines" / f"symbol={symbol}"
    m = tmp_path / "mark_klines" / f"symbol={symbol}"
    f = tmp_path / "funding" / f"symbol={symbol}"
    for d in (k, m, f):
        d.mkdir(parents=True)
    base = pl.DataFrame(
        {
            "open_time_ms": [1, 1, 2],
            "open": [1.0, 1.0, 2.0],
            "high": [1.1, 1.1, 2.1],
            "low": [0.9, 0.9, 1.9],
            "close": [1.0, 1.0, 2.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    base.write_parquet(k / "part.parquet")
    base.write_parquet(m / "part.parquet")
    (
        funding
        if funding is not None
        else pl.DataFrame(
            {"funding_rate_timestamp_ms": [1, 1, 2], "funding_rate": [0.1, 0.1, 0.2]}
        )
    ).write_parquet(f / "part.parquet")
    return tmp_path / "klines", tmp_path / "mark_klines", tmp_path / "funding"


def test_overlapping_globs_return_physical_file_once(tmp_path: Path):
    symbol = "BTCUSDT"
    roots = _write_all_roots(tmp_path, symbol)
    files = discover_unique_parquet_files(roots[0], symbol)
    assert len(files) == 1


def test_duplicate_timestamps_removed_deterministically_and_funding_not_doubled(
    tmp_path: Path,
):
    symbol = "BTCUSDT"
    roots = _write_all_roots(tmp_path, symbol)
    klines, marks, funding, diag = load_canonical_symbol_frames(
        symbol, klines_root=roots[0], mark_root=roots[1], funding_root=roots[2]
    )
    assert klines["open_time_ms"].to_list() == [1, 2]
    assert marks["open_time_ms"].to_list() == [1, 2]
    assert funding["funding_rate_timestamp_ms"].to_list() == [1, 2]
    assert diag.funding_file_refs_found > diag.funding_unique_files
    assert diag.funding_rows_before_timestamp_dedupe == 3
    assert diag.funding_rows_after_timestamp_dedupe == 2


def test_contradictory_duplicate_timestamps_fail(tmp_path: Path):
    symbol = "BTCUSDT"
    funding = pl.DataFrame(
        {"funding_rate_timestamp_ms": [1, 1], "funding_rate": [0.1, 0.2]}
    )
    roots = _write_all_roots(tmp_path, symbol, funding)
    with pytest.raises(ValueError, match="conflicting duplicate funding timestamps"):
        load_canonical_symbol_frames(
            symbol, klines_root=roots[0], mark_root=roots[1], funding_root=roots[2]
        )


def test_semantic_audit_rejects_impossible_exact_grid_diagnostics(tmp_path: Path):
    run_id = f"audit_bad_test_{tmp_path.name}"
    run_root = Path("data/processed/outcome_runs") / run_id
    import shutil

    shutil.rmtree(run_root, ignore_errors=True)
    root = run_root / "outcomes/symbol=BTCUSDT"
    root.mkdir(parents=True, exist_ok=True)
    row = compute_event_outcomes(
        {
            "range_action_event_id": "e",
            "range_regime_id": "r",
            "symbol": "BTCUSDT",
            "profile_name": "range-actionable-v1",
            "actionable_event_semantics_version": "range-actionable-prefix-invariance-v1",
            "decision_time_ms": 0,
            "signal_time_ms": 0,
            "range_low": 1.0,
            "range_high": 2.0,
            "range_mid": 1.5,
            "atr_14_abs": 0.25,
        },
        pl.DataFrame(
            {
                "open_time_ms": [60_000],
                "open": [1.5],
                "high": [1.6],
                "low": [1.4],
                "close": [1.5],
                "volume": [1.0],
            }
        ),
        pl.DataFrame(),
        pl.DataFrame(),
        [1],
        [5],
        [0.0],
    )[0]
    row["future_rows_available"] = 0
    pl.DataFrame([row]).write_parquet(root / "part.parquet")
    s = run_root / "summary"
    s.mkdir(parents=True, exist_ok=True)
    (s / "outcome_input_hygiene.json").write_text(
        json.dumps({"input_hygiene_ok": True})
    )
    res = subprocess.run(
        [
            sys.executable,
            "scripts/audit_outcome_semantics.py",
            "--outcome-run-id",
            run_id,
        ],
        text=True,
        capture_output=True,
    )
    assert res.returncode != 0
    assert "outcome window grid diagnostics do not conserve horizon" in res.stdout


def test_no_live_order_telegram_additions():
    from bybit_grid.common.source_safety_audit import audit_source_tree

    result = audit_source_tree(Path.cwd())
    assert result.ok, result.violations
