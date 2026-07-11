from __future__ import annotations

import ast
import zipfile
from pathlib import Path

import polars as pl

from bybit_grid.common.source_safety_audit import audit_source_tree
from bybit_grid.research.cost_model.cycle_costs import geometric_cycle_costs
from bybit_grid.research.cost_model.models import CostScenario, FeeRate, load_cost_config
from bybit_grid.research.scoring.components import add_ex_post_components
from bybit_grid.research.scoring.outcome_grains import build_outcome_grains
from bybit_grid.research.walk_forward.leakage_audit import audit_splits
from bybit_grid.research.walk_forward.splits import build_splits


def test_safety_audit_has_no_external_rg_or_git_dependency():
    tree = ast.parse(Path("src/bybit_grid/common/source_safety_audit.py").read_text())
    names = {getattr(n, "id", "") for n in ast.walk(tree)}
    assert "subprocess" not in names
    assert audit_source_tree(Path.cwd()).ok


def test_no_hardcoded_0055_fee_in_cost_or_scoring_modules():
    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list(Path("src/bybit_grid/research/cost_model").glob("*.py"))
        + list(Path("src/bybit_grid/research/scoring").glob("*.py"))
    )
    assert "0.055" not in text
    assert "0.00055" not in text


def test_long_short_geometric_cycle_formulas_asymmetric_rates():
    rate = FeeRate(
        "BTCUSDT",
        maker_fee_rate=0.001,
        taker_fee_rate=0.002,
        fee_snapshot_id="snap",
        fee_source="manual_scenario",
    )
    scen = CostScenario("maker_taker", "maker", "taker", "taker", 0)
    out = geometric_cycle_costs(1.01, rate, scen)
    assert round(out["net_cycle_return_long_bps"], 8) == round(
        (0.01 - (0.001 + 0.002 * 1.01)) * 10_000, 8
    )
    assert round(out["net_cycle_return_short_bps"], 8) == round(
        (((0.01) / 1.01) - (0.001 + 0.002 / 1.01)) * 10_000, 8
    )
    assert out["fee_break_even_long_bool"] is True


def test_cost_config_has_four_versioned_scenarios():
    cfg = load_cost_config("config/cost_scenarios.yml")
    assert cfg["cost_model_version"] == "cost_v1"
    assert set(cfg["scenarios"]) == {
        "maker_maker",
        "maker_taker",
        "taker_taker",
        "stress_taker_plus_slippage",
    }


def test_grains_unique_and_funding_not_multiplied():
    df = pl.DataFrame(
        {
            "range_action_event_id": ["e1"] * 4,
            "future_horizon_minutes": [60] * 4,
            "grid_cell_number": [5, 5, 10, 10],
            "sl_atr_buffer": [0.0, 1.0, 0.0, 1.0],
            "funding_rate_sum": [0.01] * 4,
            "outcome_id": [f"o{i}" for i in range(4)],
            "outcome_match_key": [f"m{i}" for i in range(4)],
            "symbol": ["BTCUSDT"] * 4,
            "signal_time_ms": [1] * 4,
        }
    )
    grains, audit = build_outcome_grains(df)
    assert audit["duplicate_key_counts"] == {
        "event_horizon": 0,
        "event_horizon_sl": 0,
        "event_horizon_grid": 0,
        "expanded_scoring_input": 0,
    }
    assert grains["event_horizon"].height == 1
    assert grains["expanded_scoring_input"].height == 4
    assert audit["funding_event_horizon_rows"] == 1


def test_score_components_deterministic_and_risk_unproven():
    df = pl.DataFrame(
        {"range_action_event_id": ["e1"], "future_horizon_minutes": [60], "sl_atr_buffer": [1.0]}
    )
    a = add_ex_post_components(df)
    b = add_ex_post_components(df)
    assert a.equals(b)
    assert a["proxy_only_bool"].to_list() == [True]
    assert a["not_actual_native_fills_bool"].to_list() == [True]
    assert a["risk_budget_proven_bool"].to_list() == [False]
    assert a["ex_post_funding_position_path_unknown_bool"].to_list() == [True]


def test_walk_forward_regime_grouping_embargo_and_deterministic_ids():
    day = 86_400_000
    rows = [
        {
            "range_action_event_id": f"e{i}",
            "range_regime_id": f"r{i}",
            "signal_time_ms": i * day,
            "future_horizon_minutes": 2880,
            "symbol": "BTCUSDT",
        }
        for i in range(90)
    ]
    df = pl.DataFrame(rows)
    a = build_splits(df, "prototype_90d")
    b = build_splits(df, "prototype_90d")
    assert a.equals(b)
    assert a["fold_id"].str.starts_with("wf_").all()
    assert a["embargo_minutes"].min() >= 2880
    assert audit_splits(a)["leakage_violations"] == 0


def test_review_pack_allowlist(tmp_path: Path):
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("review_pack_manifest.json", "{}")
    import subprocess
    import sys

    res = subprocess.run(
        [
            sys.executable,
            "scripts/check_scoring_review_pack.py",
            "--zip",
            str(z),
            "--scoring-run-id",
            "x",
        ],
        text=True,
        capture_output=True,
    )
    assert res.returncode != 0


def test_whole_row_grain_invariance_catches_split_null_patterns():
    base = {
        "range_action_event_id": ["e1", "e1"],
        "future_horizon_minutes": [60, 60],
        "grid_cell_number": [5, 5],
        "sl_atr_buffer": [1.0, 1.0],
        "outcome_id": ["o1", "o2"],
        "outcome_match_key": ["m1", "m2"],
        "symbol": ["BTCUSDT", "BTCUSDT"],
        "signal_time_ms": [1, 1],
        "funding_rate_sum": [0.1, None],
        "funding_rate_mean": [None, 0.2],
    }
    import pytest

    with pytest.raises(ValueError):
        build_outcome_grains(pl.DataFrame(base))


def test_whole_row_grain_invariance_allows_identical_null_rows():
    df = pl.DataFrame(
        {
            "range_action_event_id": ["e1", "e1"],
            "future_horizon_minutes": [60, 60],
            "grid_cell_number": [5, 5],
            "sl_atr_buffer": [1.0, 1.0],
            "outcome_id": ["o1", "o2"],
            "outcome_match_key": ["m1", "m2"],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "signal_time_ms": [1, 1],
            "funding_rate_sum": [None, None],
        }
    )
    _, audit = build_outcome_grains(df)
    assert audit["representative_row_selection_version"] == "whole_row_v1"
    assert audit["synthetic_row_risk_detected_bool"] is False


def test_walk_forward_excludes_incomplete_max_horizon_events_and_marks_prototype():
    day = 86_400_000
    rows = []
    for i in range(90):
        rows.append(
            {
                "range_action_event_id": f"e{i}",
                "range_regime_id": f"r{i}",
                "signal_time_ms": i * day,
                "future_horizon_minutes": 2880,
                "future_data_complete_bool": i != 10,
                "symbol": "BTCUSDT",
            }
        )
    out = build_splits(pl.DataFrame(rows), "prototype_90d")
    assert "e10" not in out["range_action_event_id"].to_list()
    assert out["incomplete_label_excluded_count"].max() == 1
    assert out["sufficient_for_parameter_selection_bool"].unique().to_list() == [False]
