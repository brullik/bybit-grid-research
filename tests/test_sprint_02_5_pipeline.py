from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "scripts" / "validate_universe_fgrid_constraints.py"


def _env(**overrides):
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT), **overrides})
    return env


def _write_universe(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {"symbol": ["BTCUSDT"], "lastPrice": [65000.0], "tickSize": ["0.1"], "maxLeverage": ["100"]}
    ).write_parquet(path)


def test_missing_universe_friendly_message_no_file_not_found(tmp_path):
    result = subprocess.run(
        [sys.executable, str(VALIDATE), "--dry-run-plan"],
        cwd=tmp_path,
        env=_env(GRID_VALIDATE_ENABLED="false"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "missing_universe=data/processed/universe_selected.parquet" in result.stdout
    assert "Or rerun this command with --auto-build-universe." in result.stdout
    assert "FileNotFoundError" not in result.stderr + result.stdout


def test_auto_build_universe_calls_builder_when_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    import scripts.validate_universe_fgrid_constraints as mod

    called = {}

    def fake_build(min_turnover, max_symbols):
        called["args"] = (min_turnover, max_symbols)
        _write_universe(Path("data/processed/universe_selected.parquet"))
        Path("reports").mkdir()
        Path("reports/sprint_02_universe_report.md").write_text("report", encoding="utf-8")
        return {"selected_count": 1}

    monkeypatch.setattr(mod, "build_universe", fake_build)
    monkeypatch.setattr(sys, "argv", ["validate", "--dry-run-plan", "--auto-build-universe"])
    mod.main()
    out = capsys.readouterr().out
    assert called["args"] == (5_000_000, 150)
    assert "step=build_universe status=ok selected_count=1" in out


def test_orchestrator_dry_run_only_builds_and_plans_without_private_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    import scripts.run_fast_feasibility_pipeline as orch

    def fake_build(min_turnover, max_symbols):
        _write_universe(Path("data/processed/universe_selected.parquet"))
        return {"selected_count": 1}

    monkeypatch.setattr(orch, "build_universe", fake_build)
    monkeypatch.setattr(sys, "argv", ["run", "--max-symbols", "1", "--fast-max", "--dry-run-only"])
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_API_SECRET", raising=False)
    orch.main()
    out = capsys.readouterr().out
    assert "step=build_universe status=ok selected_count=1" in out
    assert "step=dry_run_plan planned_requests=" in out


def test_orchestrator_real_run_refuses_when_validate_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.run_fast_feasibility_pipeline as orch

    _write_universe(Path("data/processed/universe_selected.parquet"))
    monkeypatch.setenv("GRID_VALIDATE_ENABLED", "false")
    monkeypatch.setattr(sys, "argv", ["run", "--max-symbols", "1", "--fast-max"])
    with pytest.raises(SystemExit) as exc:
        orch.main()
    assert "GRID_VALIDATE_ENABLED=false. Set it true for real sweep" in str(exc.value)


def test_analyzer_threshold_summary_output(tmp_path):
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "investment_min": [4.0, 20.0],
            "feasible_bybit": [True, True],
            "range_width_pct": [0.01, 0.01],
            "cell_number_requested": [2, 2],
            "leverage_requested": [100, 100],
            "init_margin_requested": [100.0, 100.0],
            "stop_loss_mult": [0.98, 0.98],
        }
    ).write_parquet(processed / "fgrid_validate_constraints.parquet")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/analyze_fgrid_min_investment.py")],
        cwd=tmp_path,
        env=_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "investment_min_non_null_rows=2" in result.stdout
    assert "symbols_feasible_at_5=1" in result.stdout
    assert "symbols_feasible_at_25=2" in result.stdout


def test_create_close_remain_not_implemented_explicit():
    from bybit_grid.bybit.client import BybitClient
    from bybit_grid.config import Settings
    from bybit_grid.live.execution_engine import ExecutionEngine

    client = BybitClient(Settings(live_trading_enabled=True, allow_live_trading="YES"))
    with pytest.raises(NotImplementedError):
        client.create_grid_bot(runtime_live=True)
    with pytest.raises(NotImplementedError):
        client.close_grid_bot(runtime_live=True)
    engine = ExecutionEngine(Settings(live_trading_enabled=True, allow_live_trading="YES"))
    with pytest.raises(NotImplementedError):
        engine.create_grid_bot(runtime_live=True)
    with pytest.raises(NotImplementedError):
        engine.close_grid_bot(runtime_live=True)
    client.close()
