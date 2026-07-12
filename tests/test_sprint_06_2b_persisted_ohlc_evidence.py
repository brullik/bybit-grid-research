from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path
from decimal import Decimal as D

import pytest

from bybit_grid.backtest.ohlc_replay import (
    FundingMarkPriceSource,
    FundingObservation,
    FundingRateSource,
    validate_funding_observations,
)
from bybit_grid.backtest.ohlc_replay.evidence import MEMBERS, read_json, read_jsonl
from bybit_grid.backtest.ohlc_replay.models import CandleSource, OhlcCandle1m
from bybit_grid.backtest.ohlc_replay.scenarios import (
    CANONICAL_SCENARIO_COUNT,
    SCENARIO_CATALOG,
    SCENARIO_IDS,
)

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, text=True, capture_output=True, check=False
    )


def test_exact_catalog_order():
    assert len(SCENARIO_CATALOG) == CANONICAL_SCENARIO_COUNT == 24
    assert tuple(s.scenario_id for s in SCENARIO_CATALOG) == SCENARIO_IDS


def test_funding_source_enums_reject_strings_and_mixed_sources():
    with pytest.raises(ValueError):
        FundingObservation(
            "linear",
            "BTCUSDT",
            60000,
            D("0"),
            D("1"),
            "synthetic",
            FundingMarkPriceSource.synthetic,
        )  # type: ignore[arg-type]
    c = (
        OhlcCandle1m(
            "linear",
            "BTCUSDT",
            60000,
            D("1"),
            D("1"),
            D("1"),
            D("1"),
            True,
            CandleSource.synthetic_1m,
        ),
        OhlcCandle1m(
            "linear",
            "BTCUSDT",
            120000,
            D("1"),
            D("1"),
            D("1"),
            D("1"),
            True,
            CandleSource.synthetic_1m,
        ),
        OhlcCandle1m(
            "linear",
            "BTCUSDT",
            180000,
            D("1"),
            D("1"),
            D("1"),
            D("1"),
            True,
            CandleSource.synthetic_1m,
        ),
    )
    with pytest.raises(ValueError, match="FundingRateSource"):
        validate_funding_observations(
            (
                FundingObservation("linear", "BTCUSDT", 120000, D("0"), D("1")),
                FundingObservation(
                    "linear",
                    "BTCUSDT",
                    180000,
                    D("0"),
                    D("1"),
                    FundingRateSource.bybit_funding_history,
                    FundingMarkPriceSource.synthetic,
                ),
            ),
            c,
            60000,
        )


def test_runner_complete_and_failed(tmp_path):
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    ok = _run(
        "scripts/run_ohlc_replay_synthetic_matrix.py",
        "--output-root",
        str(out),
        "--report-root",
        str(rep),
    )
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["status"] == "complete"
    bad = _run(
        "scripts/run_ohlc_replay_synthetic_matrix.py",
        "--run-id",
        "bad",
        "--output-root",
        str(out),
        "--report-root",
        str(rep),
        "--fail-after-building-test-hook",
    )
    assert bad.returncode == 1 and json.loads(bad.stdout)["status"] == "failed"
    assert read_json(out / "bad" / "ohlc_replay_run_status.json")["status"] == "failed"


def test_pack_builder_checker_and_members(tmp_path):
    out = tmp_path / "out"
    rep = tmp_path / "rep"
    z = tmp_path / "pack.zip"
    assert (
        _run(
            "scripts/run_ohlc_replay_synthetic_matrix.py",
            "--output-root",
            str(out),
            "--report-root",
            str(rep),
        ).returncode
        == 0
    )
    assert (
        _run(
            "scripts/make_ohlc_replay_review_pack.py",
            "--output-root",
            str(out),
            "--report-root",
            str(rep),
            "--output",
            str(z),
        ).returncode
        == 0
    )
    assert _run("scripts/check_ohlc_replay_review_pack.py", "--zip", str(z)).returncode == 0
    with zipfile.ZipFile(z) as zp:
        assert tuple(zp.namelist()) == MEMBERS
        m = json.loads(zp.read("review_pack_manifest.json"))
        assert len(m["sha256"]) == 13 and "review_pack_manifest.json" not in m["sha256"]


def test_strict_json_rejects_duplicate_float_noncanonical_blank(tmp_path):
    p = tmp_path / "x.json"
    p.write_bytes(b'{"a":1,"a":2}\n')
    with pytest.raises(ValueError):
        read_json(p)
    p.write_bytes(b'{"a":1.0}\n')
    with pytest.raises(ValueError):
        read_json(p)
    p.write_bytes(b'{"a":NaN}\n')
    with pytest.raises(ValueError):
        read_json(p)
    p.write_bytes(b'{"b":1,"a":2}\n')
    with pytest.raises(ValueError):
        read_json(p)
    jl = tmp_path / "x.jsonl"
    jl.write_bytes(b'{"a":1}\n\n')
    with pytest.raises(ValueError):
        read_jsonl(jl)


def test_missing_zip_strict_json_no_traceback(tmp_path):
    r = _run("scripts/check_ohlc_replay_review_pack.py", "--zip", str(tmp_path / "missing.zip"))
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert json.loads(r.stdout)["review_pack_ok"] is False


def test_no_generated_binary_artifacts_committed():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    forbidden = (".zip", ".parquet", ".db", ".sqlite")
    assert not [p for p in tracked if p.endswith(forbidden) or p.endswith(".jsonl")]
