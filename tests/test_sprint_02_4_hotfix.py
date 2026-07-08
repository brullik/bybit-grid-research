import json
import os
import subprocess
import sys
from pathlib import Path

import polars as pl

from bybit_grid.bybit.fgrid_feasibility import summarize_min_investment
from bybit_grid.bybit.fgrid_min_sweep import progress_line

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_universe_fgrid_constraints.py"
ANALYZE = ROOT / "scripts" / "analyze_fgrid_min_investment.py"


def _env(**overrides):
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(ROOT / "src"), **overrides})
    return env


def _universe(path: Path) -> Path:
    universe = path / "universe.parquet"
    pl.DataFrame(
        {"symbol": ["BTCUSDT"], "lastPrice": [65000.0], "tickSize": ["0.1"], "maxLeverage": ["100"]}
    ).write_parquet(universe)
    return universe


def test_real_sweep_exits_before_writing_rows_when_validate_disabled(tmp_path):
    universe = _universe(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--universe", str(universe), "--max-symbols", "1"],
        cwd=tmp_path,
        env=_env(GRID_VALIDATE_ENABLED="false"),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "GRID_VALIDATE_ENABLED=false" in result.stderr
    assert not (tmp_path / "data/processed/fgrid_validate_constraints.parquet").exists()


def test_dry_run_plan_works_when_validate_disabled(tmp_path):
    universe = _universe(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--universe", str(universe), "--dry-run-plan"],
        cwd=tmp_path,
        env=_env(GRID_VALIDATE_ENABLED="false"),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "planned_requests<=" in result.stdout


def test_purge_removes_skipped_rows_and_raw_json(tmp_path):
    raw_dir = tmp_path / "data/processed/fgrid_validate_raw_redacted"
    raw_dir.mkdir(parents=True)
    skipped = raw_dir / "skipped.json"
    real = raw_dir / "real.json"
    skipped.write_text(json.dumps({"skipped": True}), encoding="utf-8")
    real.write_text(json.dumps({"retCode": 0}), encoding="utf-8")
    out = tmp_path / "data/processed/fgrid_validate_constraints.parquet"
    pl.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "blocker_reason": ["investment_min_missing", None],
            "raw_response_path_redacted": [str(skipped), str(real)],
            "investment_min": [None, 10.0],
            "retCode": [None, 0],
            "status_code": [None, 200],
        }
    ).write_parquet(out)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--purge-skipped-constraints"],
        cwd=tmp_path,
        env=_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "removed_rows=1" in result.stdout
    assert "remaining_rows=1" in result.stdout
    assert "removed_raw_files=1" in result.stdout
    assert not skipped.exists()
    assert real.exists()
    assert pl.read_parquet(out).height == 1


def test_analyzer_handles_all_null_investment_without_crash(tmp_path):
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    pl.DataFrame(
        {"symbol": ["BTCUSDT"], "investment_min": [None], "feasible_bybit": [False]}
    ).write_parquet(processed / "fgrid_validate_constraints.parquet")
    result = subprocess.run(
        [sys.executable, str(ANALYZE)], cwd=tmp_path, env=_env(), text=True, capture_output=True
    )
    assert result.returncode != 0
    assert "No real investment_min values found" in result.stdout
    _, aggregate = summarize_min_investment(pl.read_parquet(processed / "fgrid_validate_constraints.parquet"))
    assert aggregate["min_investment_median_by_symbol"] is None


def test_progress_line_includes_api_call_metrics():
    line = progress_line(5, 10, 0.0, api_calls=3)
    assert "done_rows=5" in line
    assert "api_calls=3" in line
    assert "api_rps=" in line


def test_no_create_close_implementation_was_introduced():
    client_source = (ROOT / "src/bybit_grid/bybit/client.py").read_text()
    assert "raise NotImplementedError(\"Live grid bot create is forbidden" in client_source
    assert "raise NotImplementedError(\"Live grid bot close is forbidden" in client_source
