from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import polars as pl

from scripts.calibrate_actionable_density import blockers


def test_density_report_uses_perf_raw_when_raw_parquet_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("data/processed/range_runs/r1")
    (root / "summary").mkdir(parents=True)
    (root / "summary" / "range_candidate_perf.json").write_text(json.dumps({"raw_candidate_rows_written": 100, "actionable_event_rows_written": 10}), encoding="utf-8")
    action_dir = root / "actionable_events" / "symbol=BTCUSDT" / "year=1970" / "month=1"
    action_dir.mkdir(parents=True)
    pl.DataFrame({"symbol": ["BTCUSDT"] * 10, "signal_time_ms": list(range(10)), "best_lookback_minutes": [30] * 10, "range_action_event_id": [f"id{i}" for i in range(10)]}).write_parquet(action_dir / "candidates.parquet")
    subprocess.run([sys.executable, str(Path(__file__).parents[1] / "scripts/report_range_candidate_density.py"), "--run-id", "r1"], check=True)
    row = pl.read_parquet(root / "summary" / "range_density_summary.parquet").to_dicts()[0]
    assert row["raw_candidates_total"] == 100
    assert row["raw_to_actionable_compression_ratio"] == 10


def test_review_pack_checker_rejects_global_report(tmp_path):
    z = tmp_path / "bad.zip"
    with ZipFile(z, "w") as zf:
        zf.writestr("reports/sprint_03_range_candidate_report.md", "stale")
    res = subprocess.run([sys.executable, "scripts/check_pm_review_pack.py", "--zip", str(z), "--run-id", "r1"], text=True, capture_output=True)
    assert res.returncode != 0
    assert "stale_global_reports" in res.stderr


def test_calibration_blockers_and_pass_logic():
    passing = {"actionable_event_rows_written": 1, "raw_to_actionable_compression_ratio": 11, "actionable_events_per_symbol_day_p50": 50, "actionable_events_per_symbol_day_p90": 100, "actionable_events_per_symbol_day_p99": 200, "symbols_with_actionable_events": 8, "duplicate_action_event_id_count": 0}
    assert blockers(passing) == []
    failing = {**passing, "raw_to_actionable_compression_ratio": 2, "symbols_with_actionable_events": 3}
    assert "compression<10.0" in blockers(failing)
    assert "symbols_with_actionable_events<8" in blockers(failing)
