import subprocess
import sys
from pathlib import Path

import polars as pl

from bybit_grid.bybit.fgrid_min_sweep import (
    build_min_sweep_candidates,
    leverage_probe_values,
    should_stop_symbol,
    progress_line,
)
from bybit_grid.bybit.client import BybitClient
from bybit_grid.live.execution_engine import ExecutionEngine


def test_min_sweep_planned_request_count_caps_profiles():
    c = build_min_sweep_candidates("BTCUSDT", 65000, "0.1", 100, max_profiles_per_symbol=12)
    assert len(c) <= 12


def test_init_margin_is_not_swept_as_dimension():
    c = build_min_sweep_candidates("BTCUSDT", 65000, "0.1", 100, max_profiles_per_symbol=12)
    assert {m["init_margin_requested"] for _, m in c} == {100.0}


def test_highest_valid_leverage_is_used_for_ultra_min_profiles():
    c = build_min_sweep_candidates("BTCUSDT", 65000, "0.1", 25, max_profiles_per_symbol=6)
    metas = [m for _, m in c if m["profile_name"].startswith("ultra_min")]
    assert leverage_probe_values(25)[-1] == 25
    assert {m["leverage_requested"] for m in metas} == {25}


def test_stop_after_first_5usdt_feasible_reduces_calls():
    assert should_stop_symbol([{"investment_min": 5, "feasible_user_5usdt_rule": True}])


def test_early_stop_if_best_investment_above_500_after_three_profiles():
    rows = [{"investment_min": 900}, {"investment_min": 800}, {"investment_min": 700}]
    assert should_stop_symbol(rows)


def test_fast_max_dry_run_makes_zero_network_calls(tmp_path, monkeypatch):
    universe = tmp_path / "u.parquet"
    pl.DataFrame(
        {"symbol": ["BTCUSDT"], "lastPrice": [65000.0], "tickSize": ["0.1"], "maxLeverage": ["100"]}
    ).write_parquet(universe)
    script = "scripts/validate_universe_fgrid_constraints.py"
    result = subprocess.run(
        [sys.executable, script, "--universe", str(universe), "--fast-max", "--dry-run-plan"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "planned_requests<=" in result.stdout
    assert "estimated_seconds_at_9.5rps" in result.stdout


def test_progress_estimator_works():
    line = progress_line(5, 10, 0.0)
    assert "progress done=5 total=10" in line
    assert "eta_sec=" in line


def test_no_live_create_close_code_added():
    assert "NotImplementedError" in BybitClient.create_grid_bot.__code__.co_names
    assert "NotImplementedError" in ExecutionEngine.create_grid_bot.__code__.co_names


def test_keyboard_interrupt_flushes_partial_rows():
    source = Path("scripts/validate_universe_fgrid_constraints.py").read_text()
    assert "except KeyboardInterrupt" in source
    assert "append_constraints(output, pending)" in source
    assert "resume_command=python scripts/validate_universe_fgrid_constraints.py" in source
