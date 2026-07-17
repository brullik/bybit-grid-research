from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

from bybit_grid.research.outcome_core import outcome_fast, outcome_numpy
from bybit_grid.research.outcome_core.funding_join import aggregate_funding
from bybit_grid.research.outcome_core.grid_crossings import count_level_crossings, geometric_grid_levels
from bybit_grid.research.outcome_core.outcome_numpy import compute_event_outcomes, deterministic_outcome_id, outcome_match_key
from bybit_grid.research.outcome_core.sl_proxy import compute_sl_proxy
from bybit_grid.research.outcome_store import write_partitioned_outcomes
from bybit_grid.research.outcome_summary import build_summaries
from bybit_grid.research.outcome_semantics import validate_outcome_window_semantics
from bybit_grid.research.range_core.adapter import numpy_is_project_shadow


def event():
    return {"range_action_event_id":"a1","range_regime_id":"r1","symbol":"BTCUSDT","profile_name":"range-actionable-v1","actionable_event_semantics_version":"range-actionable-prefix-invariance-v1","decision_time_ms":0,"signal_time_ms":0,"range_low":100.0,"range_high":110.0,"range_mid":105.0,"range_height_atr_14":1.0}

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
        for n in ['outcome_report.md','outcome_quality_report.md','outcome_semantic_audit.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json','outcome_semantic_audit.json']:
            z.writestr(n, 'x')
    with zipfile.ZipFile(p) as z:
        assert set(z.namelist()) == {'outcome_report.md','outcome_quality_report.md','outcome_semantic_audit.md','outcome_summary.parquet','outcome_quality_summary.parquet','outcome_perf.json','outcome_semantic_audit.json'}

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
    assert not numpy_is_project_shadow(numpy_file, project_root)
    assert not (project_root / "numpy").exists()
    assert not (project_root / "numpy.py").exists()


def test_numpy_shadow_detection_allows_project_venv_site_packages():
    project_root = Path.cwd().resolve()
    venv_numpy = project_root / ".venv" / "Lib" / "site-packages" / "numpy" / "__init__.py"
    assert not numpy_is_project_shadow(venv_numpy, project_root)
    assert numpy_is_project_shadow(project_root / "numpy" / "__init__.py", project_root)
    assert numpy_is_project_shadow(project_root / "numpy.py", project_root)


def _write_minimal_review_pack(path: Path, perf: dict) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("outcome_report.md", "# report\n")
        z.writestr("outcome_quality_report.md", "# quality\n")
        z.writestr("outcome_summary.parquet", b"placeholder")
        z.writestr("outcome_quality_summary.parquet", b"placeholder")
        z.writestr("outcome_perf.json", json.dumps(perf))
        z.writestr("outcome_semantic_audit.md", "# audit\n")
        z.writestr("outcome_semantic_audit.json", json.dumps({"semantic_audit_ok": True, "outcome_semantics_version": "v5_exact_outcome_window_provenance", "checks": {"grid_count_rows_failed": 0}}))
        z.writestr("outcome_input_hygiene.json", json.dumps({"input_hygiene_ok": True}))
        z.writestr("outcome_input_hygiene_by_symbol.parquet", b"placeholder")
        z.writestr("outcome_core_equivalence_report.json", json.dumps({"equivalence_ok": True}))
        z.writestr("outcome_grid_serialization_repair_report.json", json.dumps({"non_grid_drift_count": 0, "semantic_audit_ok": True}))


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



def test_v3_atr_unit_derivation_and_half_atr_boundary():
    sl = compute_sl_proxy({"range_height_atr_14": 4.0}, 100.0, 108.0, 0.5)
    assert sl.sl_proxy_valid_bool
    assert sl.atr_14_abs_used == 2.0
    assert sl.lower_sl_price == 99.0
    assert sl.upper_sl_price == 109.0
    assert sl.sl_distance_lower_abs == 1.0


def test_v3_direct_atr_preferred_with_mismatch_reason():
    sl = compute_sl_proxy({"atr_14": 3.0, "range_height_atr_14": 4.0}, 100.0, 108.0, 1.0)
    assert sl.atr_value_source == "direct_event_atr_14"
    assert sl.atr_14_abs_used == 3.0
    assert sl.sl_proxy_invalid_reason == "direct_derived_atr_mismatch"


def test_v3_invalid_zero_atr_rejected():
    sl = compute_sl_proxy({"range_height_atr_14": 0.0}, 100.0, 108.0, 1.0)
    assert not sl.sl_proxy_valid_bool
    assert sl.atr_value_source == "missing_or_invalid"


def test_v3_range_height_atr_ratio_not_treated_as_percent():
    row = compute_event_outcomes(event(), klines([(105, 111, 99, 105)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.5])[0]
    # range height is 10 and ratio is 1 => ATR is 10, so 0.5 ATR distance is 5 dollars, not 0.5%.
    assert row["sl_distance_lower_abs"] == 5.0
    assert row["lower_sl_price"] == 95.0


def test_v3_same_candle_exit_and_sl_ambiguity():
    row = compute_event_outcomes(event(), klines([(105, 116, 94, 105)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.5])[0]
    assert row["first_exit_side"] == "ambiguous_both"
    assert row["first_exit_ambiguous_bool"] is True
    assert row["first_sl_side"] == "ambiguous_both"
    assert row["first_sl_ambiguous_bool"] is True


def test_v3_activity_proxies():
    row = compute_event_outcomes(event(), klines([(105, 109, 101, 106), (106, 109, 101, 104)]), pl.DataFrame(), pl.DataFrame(), [2], [5], [0])[0]
    assert row["future_close_level_cross_count"] >= 1
    assert row["future_grid_level_cross_count"] == row["future_close_level_cross_count"]
    assert row["future_intrabar_level_touch_count"] >= row["future_close_level_cross_count"]
    assert row["future_unique_grid_levels_touched_count"] > 0
    assert row["fill_activity_lower_bound_proxy"] == row["future_close_level_cross_count"]
    assert row["fill_activity_upper_bound_proxy"] == row["future_intrabar_level_touch_count"]


def test_v3_summary_grains_not_multiplied(tmp_path: Path):
    rows = []
    for grid in [5, 10, 20]:
        for sl in [0.0, 0.5, 1.0]:
            r = compute_event_outcomes(event(), klines([(105, 106, 104, 105)]), pl.DataFrame(), pl.DataFrame({"funding_time_ms": [1], "funding_rate": [0.1]}), [1], [grid], [sl], range_run_id="range-test", outcome_run_id="outcome-test")[0]
            r["funding_rows_in_horizon"] = 1
            r["funding_source_status"] = "ok"
            rows.append(r)
    root = tmp_path / "run"
    write_partitioned_outcomes(pl.DataFrame(rows), root / "outcomes")
    _, _, perf = build_summaries(root)
    assert perf["unique_event_horizon_rows"] == 1
    assert perf["funding_joined_unique_event_horizon"] == 1
    assert len(perf["sl_probe_summary"]) == 3


def test_v3_no_hardcoded_fee_divisor_in_outcome_core():
    for path in Path("src/bybit_grid/research/outcome_core").glob("*.py"):
        assert "0.055" not in path.read_text()


def test_native_geometric_grid_levels_contract():
    levels = geometric_grid_levels(10_000, 30_000, 5)
    assert len(levels) == 6
    assert levels[0] == 10_000
    assert levels[-1] == 30_000
    assert np.all(np.diff(levels) > 0)
    assert np.allclose(levels[1:] / levels[:-1], (3.0) ** (1 / 5))


def test_native_geometric_grid_invalid_bounds_raise():
    import pytest

    for args in [(0, 10, 5), (10, 10, 5), (10, 9, 5), (10, 20, 1)]:
        with pytest.raises(ValueError):
            geometric_grid_levels(*args)


def test_v5_grid_semantic_fields_and_activity_use_n_plus_1_levels():
    row = compute_event_outcomes(event(), klines([(100, 110, 100, 110)]), pl.DataFrame(), pl.DataFrame(), [1], [5], [0.0])[0]
    levels = json.loads(row["geometric_grid_levels_json"])
    assert row["outcome_semantics_version"] == "v5_exact_outcome_window_provenance"
    assert row["grid_cell_number"] == 5
    assert row["grid_price_level_count"] == 6
    assert row["grid_interval_count"] == 5
    assert len(levels) == 6
    assert row["grid_interval_pct"] == ((110 / 100) ** (1 / 5) - 1) * 100
    assert row["future_intrabar_level_touch_count"] == 6
    assert row["future_internal_level_intrabar_touch_count"] == 4


def test_v5_ids_versioned_and_match_key_stable():
    v3 = deterministic_outcome_id("a", 60, 10, 0.5, "v3_atr_correct")
    v4 = deterministic_outcome_id("a", 60, 10, 0.5, "v4_native_grid_geometry")
    v5 = deterministic_outcome_id("a", 60, 10, 0.5, "v5_exact_outcome_window_provenance")
    assert len({v3, v4, v5}) == 3
    assert outcome_match_key("a", 60, 10, 0.5) == outcome_match_key("a", 60, 10, 0.5)


def test_v5_empty_schemaful_windows_are_explicit_missing_in_both_cores():
    frames = (
        pl.DataFrame(
            schema={
                "start_time_ms": pl.Int64,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        ),
        pl.DataFrame(schema={"open_time_ms": pl.Int64}),
    )
    for frame in frames:
        rows = [
            core.compute_event_outcomes(
                event(),
                frame,
                pl.DataFrame(),
                pl.DataFrame(),
                [3],
                [5],
                [0.5],
            )[0]
            for core in (outcome_numpy, outcome_fast)
        ]
        for row in rows:
            assert row["future_rows_available"] == 0
            assert row["future_missing_minutes_count"] == 3
            assert row["future_outcome_ineligible_reason"] == "missing_minutes"
        assert rows[0]["future_expected_minutes_count"] == rows[1][
            "future_expected_minutes_count"
        ]


def test_v5_mark_context_resolves_its_own_timestamp_column_in_both_cores():
    for trade_time_col, mark_time_col in (
        ("start_time_ms", "open_time_ms"),
        ("open_time_ms", "start_time_ms"),
    ):
        trade = pl.DataFrame(
            {
                trade_time_col: [60_000],
                "open": [105.0],
                "high": [106.0],
                "low": [104.0],
                "close": [105.0],
                "volume": [1.0],
            }
        )
        mark = pl.DataFrame({mark_time_col: [60_000], "close": [108.5]})
        rows = [
            core.compute_event_outcomes(
                event(), trade, mark, pl.DataFrame(), [1], [5], [0.5]
            )[0]
            for core in (outcome_numpy, outcome_fast)
        ]
        for field in (
            "mark_price_future_rows_available",
            "mark_price_max_deviation_from_last_pct",
        ):
            assert rows[0][field] == rows[1][field]
        assert rows[0]["mark_price_future_rows_available"] == 1
        assert rows[0]["mark_price_max_deviation_from_last_pct"] > 0.0


def _authoritative_v5_row() -> dict:
    return compute_event_outcomes(
        event(),
        klines([(105, 106, 104, 105)]),
        pl.DataFrame(),
        pl.DataFrame(),
        [1],
        [5],
        [0.5],
        range_run_id="range-test",
        outcome_run_id="outcome-test",
    )[0]


def test_v5_validator_rejects_grid_cell_number_below_two():
    row = _authoritative_v5_row()
    row.update(
        {
            "grid_count": 1,
            "grid_cell_number": 1,
            "grid_price_level_count": 2,
            "grid_interval_count": 1,
            "outcome_id": deterministic_outcome_id("a1", 1, 1, 0.5),
            "outcome_match_key": outcome_match_key("a1", 1, 1, 0.5),
        }
    )
    result = validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "grid cell number id material invalid" in result["failures"]


def test_v5_validator_returns_failure_for_malformed_auxiliary_count():
    row = _authoritative_v5_row()
    row["future_zero_volume_count"] = "invalid"
    result = validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "outcome auxiliary diagnostics must be nonnegative integers" in result[
        "failures"
    ]


def test_v5_validator_requires_exact_stable_match_key():
    row = _authoritative_v5_row()
    row["outcome_match_key"] = "forged"
    result = validate_outcome_window_semantics(pl.DataFrame([row]))
    assert result["outcome_window_semantic_audit_ok"] is False
    assert "outcome_match_key does not match stable semantic material" in result[
        "failures"
    ]

    missing = validate_outcome_window_semantics(
        pl.DataFrame([_authoritative_v5_row()]).drop("outcome_match_key")
    )
    assert missing["outcome_window_semantic_audit_ok"] is False
    assert any("outcome_match_key" in failure for failure in missing["failures"])


def test_v5_close_sl_buffers_have_distinct_ids_and_match_keys():
    buffers = [0.1234561, 0.1234562]
    assert len({deterministic_outcome_id("a1", 1, 5, value) for value in buffers}) == 2
    assert len({outcome_match_key("a1", 1, 5, value) for value in buffers}) == 2
    rows = compute_event_outcomes(
        event(),
        klines([(105, 106, 104, 105)]),
        pl.DataFrame(),
        pl.DataFrame(),
        [1],
        [5],
        buffers,
        range_run_id="range-test",
        outcome_run_id="outcome-test",
    )
    assert len({row["outcome_id"] for row in rows}) == 2
    assert len({row["outcome_match_key"] for row in rows}) == 2
    assert validate_outcome_window_semantics(pl.DataFrame(rows))[
        "outcome_window_semantic_audit_ok"
    ] is True
