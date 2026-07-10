from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core.funding_join import aggregate_funding
from bybit_grid.research.outcome_core.grid_crossings import count_level_crossings, geometric_grid_levels
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes, deterministic_outcome_id
from bybit_grid.research.outcome_store import write_partitioned_outcomes


def event():
    return {"range_action_event_id":"a1","range_regime_id":"r1","symbol":"BTCUSDT","signal_time_ms":0,"range_low":100.0,"range_high":110.0,"range_mid":105.0,"range_height_atr_14":1.0}

def klines(vals):
    return pl.DataFrame({"open_time_ms":[60_000*(i+1) for i in range(len(vals))],"open":[v[0] for v in vals],"high":[v[1] for v in vals],"low":[v[2] for v in vals],"close":[v[3] for v in vals],"volume":[1.0]*len(vals)})

def test_no_lookahead_future_starts_after_signal_and_missing():
    out=compute_event_outcomes(event(), klines([(105,106,104,105)]), pl.DataFrame(), pl.DataFrame(), [2], [5], [0.5])[0]
    assert out["entry_time_ms"] == 60_000
    assert out["future_rows_available"] == 1
    assert out["future_missing_minutes_count"] == 1
    assert not out["future_data_complete_bool"]

def test_first_exit_side_time_and_sl_upper_lower():
    up=compute_event_outcomes(event(), klines([(105,111,104,109)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.0])[0]
    assert (up["first_exit_side"], up["first_exit_time_ms"], up["first_sl_side"]) == ("up",60_000,"upper")
    dn=compute_event_outcomes(event(), klines([(105,106,99,101)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.0])[0]
    assert (dn["first_exit_side"], dn["first_sl_side"]) == ("down","lower")

def test_grid_crossing_count_and_monotonicity():
    levels=geometric_grid_levels(100, 110, 5)
    assert np.all(np.diff(levels) > 0)
    assert count_level_crossings(np.array([100, 105, 110], dtype=float), np.array([102, 108], dtype=float)) == 2

def test_funding_aggregation_by_horizon():
    f=pl.DataFrame({"funding_time_ms":[60_000,120_000,240_000],"funding_rate":[0.1,-0.2,0.3]})
    got=aggregate_funding(f, 0, 180_000)
    assert got["funding_rows_in_horizon"] == 2
    assert round(got["funding_rate_sum"], 6) == -0.1
    assert round(got["funding_rate_abs_sum"], 6) == 0.3

def test_deterministic_outcome_id():
    assert deterministic_outcome_id("a", 60, 10, 0.5) == deterministic_outcome_id("a", 60, 10, 0.5)
    assert deterministic_outcome_id("a", 60, 10, 0.5) != deterministic_outcome_id("a", 60, 20, 0.5)

def test_partition_write_and_dedupe(tmp_path: Path):
    row=compute_event_outcomes(event(), klines([(105,106,104,105)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.5])[0]
    df=pl.DataFrame([row,row])
    paths=write_partitioned_outcomes(df, tmp_path)
    assert len(paths)==1
    assert pl.read_parquet(paths[0]).height == 1

def test_review_pack_allowlist(tmp_path: Path):
    p=tmp_path/'pack.zip'
    with zipfile.ZipFile(p,'w') as z:
        for n in ['outcome_report.md','outcome_quality_report.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json']:
            z.writestr(n, 'x')
    with zipfile.ZipFile(p) as z:
        assert set(z.namelist()) == {'outcome_report.md','outcome_quality_report.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json'}

def test_no_live_create_close_order_code_in_outcome_files():
    for path in list(Path('src/bybit_grid/research').glob('outcome*.py')) + list(Path('src/bybit_grid/research/outcome_core').glob('*.py')) + list(Path('scripts').glob('*outcome*.py')):
        txt=path.read_text().lower()
        assert 'create order' not in txt and 'close order' not in txt and 'telegram' not in txt

def test_partition_write_dedupes_across_append(tmp_path: Path):
    row=compute_event_outcomes(event(), klines([(105,106,104,105)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.5])[0]
    paths=write_partitioned_outcomes(pl.DataFrame([row]), tmp_path)
    write_partitioned_outcomes(pl.DataFrame([row]), tmp_path)
    assert pl.read_parquet(paths[0]).height == 1


def test_funding_aggregation_recognizes_sprint02_columns_and_statuses():
    f=pl.DataFrame({"funding_rate_timestamp_ms":[60_000,120_000],"funding_rate":[0.1,0.2]})
    got=aggregate_funding(f, 0, 180_000)
    assert got["funding_rows_in_horizon"] == 2
    assert got["funding_source_status"] == "ok"
    assert got["funding_rate_mean"] == 0.15000000000000002
    assert aggregate_funding(pl.DataFrame(), 0, 1)["funding_source_status"] == "missing_file"
    assert aggregate_funding(f, 180_000, 240_000)["funding_source_status"] == "no_overlap"


def test_funding_aggregation_empty_file_status():
    got = aggregate_funding(pl.DataFrame({"unexpected": [1]}), 0, 1)
    assert got["funding_source_status"] == "empty_file"


def test_imported_numpy_is_not_project_root_shim():
    project_root = Path.cwd().resolve()
    numpy_file = Path(np.__file__).resolve()
    assert not numpy_file.is_relative_to(project_root)
    assert not (project_root / "numpy").exists()
    assert not (project_root / "numpy.py").exists()


def _write_minimal_review_pack(path: Path, perf: dict) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("outcome_report.md", "# report\n")
        z.writestr("outcome_quality_report.md", "# quality\n")
        z.writestr("outcome_summary.parquet", b"placeholder")
        z.writestr("outcome_quality_summary.parquet", b"placeholder")
        z.writestr("outcome_perf.json", json.dumps(perf))


def test_review_pack_checker_rejects_zero_rows_and_missing_funding_diagnostics(tmp_path: Path):
    base_perf = {
        "outcome_rows_total": 1,
        "unique_outcome_id_count": 1,
        "duplicate_range_action_event_horizon_grid_sl_rows": 0,
        "funding_rows_total": 1,
        "funding_files_found_count": 1,
        "funding_symbols_with_files": ["BTCUSDT"],
        "funding_rows_scanned_total": 1,
        "funding_rows_joined_total": 1,
        "funding_join_coverage_rate": 1.0,
        "funding_missing_symbols": [],
        "funding_source_status_counts": {"ok": 1},
        "funding_zero_reason": "",
    }
    zero_pack = tmp_path / "zero.zip"
    _write_minimal_review_pack(zero_pack, base_perf | {"outcome_rows_total": 0})
    zero = subprocess.run(
        [sys.executable, "scripts/check_outcome_review_pack.py", "--zip", str(zero_pack), "--outcome-run-id", "test"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert zero.returncode != 0
    assert "outcome_rows_total" in zero.stderr

    missing_pack = tmp_path / "missing.zip"
    bad_perf = dict(base_perf)
    bad_perf.pop("funding_rows_total")
    _write_minimal_review_pack(missing_pack, bad_perf)
    missing = subprocess.run(
        [sys.executable, "scripts/check_outcome_review_pack.py", "--zip", str(missing_pack), "--outcome-run-id", "test"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "missing funding diagnostics" in missing.stderr


def test_report_candidate_outcomes_stdout_is_parseable_json(tmp_path: Path):
    rid = "pytest_json_report"
    root = Path("data/processed/outcome_runs") / rid
    (root / "outcomes").mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, "scripts/report_candidate_outcomes.py", "--outcome-run-id", rid],
            text=True,
            capture_output=True,
            check=True,
        )
        parsed = json.loads(result.stdout)
        assert parsed["outcome_rows_total"] == 0
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(Path("reports/outcome_runs") / rid, ignore_errors=True)
