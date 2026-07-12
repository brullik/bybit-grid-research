from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from bybit_grid.backtest.ohlc_replay.evidence import (
    MEMBERS,
    build_records,
    derive_scenario_audit,
    find_source_hygiene_violations,
)
from bybit_grid.backtest.ohlc_replay.scenarios import SCENARIO_CATALOG, SCENARIO_IDS

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True, check=False)


def test_git_unavailable_dot_git_absent_and_operator_artifacts_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    (tmp_path / "operator.zip").write_bytes(b"x")
    (tmp_path / "operator.jsonl").write_text("{}\n")
    (tmp_path / "src").mkdir()
    assert find_source_hygiene_violations(tmp_path) == []
    (tmp_path / "src" / "bad.zip").write_bytes(b"x")
    assert find_source_hygiene_violations(tmp_path) == ["src/bad.zip"]


def test_catalog_order_immutable_and_core_semantics():
    assert tuple(s.scenario_id for s in SCENARIO_CATALOG) == SCENARIO_IDS
    assert len(SCENARIO_CATALOG) == 24
    with pytest.raises(TypeError):
        SCENARIO_CATALOG[0].expected["x"] = True
    audit = derive_scenario_audit()
    assert audit["scenario_audit_ok"] is True
    c = audit["scenario_checks_by_id"]
    assert c["04_single_candle_path_insensitive"]["assignment_count"] == 2
    assert c["04_single_candle_path_insensitive"]["path_sensitive_bool"] is False
    assert c["05_single_candle_path_sensitive_long"]["path_sensitive_bool"] is True
    assert c["06_single_candle_path_sensitive_short"]["path_sensitive_bool"] is True
    s7 = c["07_equal_pnl_different_nested_ledger"]
    assert s7["exact_equal_pnl_bool"] and s7["nested_result_differs_bool"] and s7["ledger_differs_bool"]
    assert c["08_two_candle_four_assignments"]["assignment_count"] == 4
    assert c["13_positive_funding_long"]["funding_pnl_signs"] == ["negative"]
    assert c["14_positive_funding_short"]["funding_pnl_signs"] == ["positive"]
    assert c["15_negative_funding_long"]["funding_pnl_signs"] == ["positive"]
    assert c["16_flat_position_funding_zero"]["funding_pnl_signs"] == ["zero"]
    assert c["17_two_funding_boundaries"]["funding_event_count"] == 2
    assert c["21_cycle_count_envelope_one_to_two"]["completed_cycle_count_min"] == 1
    assert c["21_cycle_count_envelope_one_to_two"]["completed_cycle_count_max"] == 2
    assert c["22_bybit_source_enum_contract"]["candle_sources"] == ["bybit_trade_kline_1m", "bybit_trade_kline_1m"]


def test_scenario_audit_rejects_expected_mismatch():
    s = SCENARIO_CATALOG[3]
    bad = replace(s, expected=MappingProxyType({**dict(s.expected), "exact_assignment_count": 999}))
    audit = derive_scenario_audit((SCENARIO_CATALOG[:3] + (bad,) + SCENARIO_CATALOG[4:]))
    assert audit["scenario_audit_ok"] is False


def test_runner_builder_checker_happy_path_and_lifecycle(tmp_path):
    out, rep, zp = tmp_path / "out", tmp_path / "rep", tmp_path / "pack.zip"
    ok = _run("scripts/run_ohlc_replay_synthetic_matrix.py", "--output-root", str(out), "--report-root", str(rep))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads(ok.stdout)["status"] == "complete"
    bad = _run("scripts/run_ohlc_replay_synthetic_matrix.py", "--run-id", "bad", "--output-root", str(out), "--report-root", str(rep), "--fail-after-building-test-hook")
    assert bad.returncode == 1 and json.loads(bad.stdout)["status"] == "failed"
    mk = _run("scripts/make_ohlc_replay_review_pack.py", "--output-root", str(out), "--report-root", str(rep), "--output", str(zp))
    assert mk.returncode == 0, mk.stdout + mk.stderr
    chk = _run("scripts/check_ohlc_replay_review_pack.py", "--zip", str(zp))
    assert chk.returncode == 0, chk.stdout + chk.stderr
    with zipfile.ZipFile(zp) as z:
        assert tuple(z.namelist()) == MEMBERS
        assert len(json.loads(z.read("review_pack_manifest.json"))["sha256"]) == 13


def test_missing_zip_strict_json_no_traceback(tmp_path):
    r = _run("scripts/check_ohlc_replay_review_pack.py", "--zip", str(tmp_path / "missing.zip"))
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert json.loads(r.stdout)["review_pack_ok"] is False


def test_records_guardrails_false_and_reports_exact():
    files = build_records()
    manifest = json.loads(files["review_pack_manifest.json"])
    assert manifest["risk_budget_proven_bool"] is False
    assert manifest["parameter_selection_authorized_bool"] is False
    assert manifest["live_authorized_bool"] is False
