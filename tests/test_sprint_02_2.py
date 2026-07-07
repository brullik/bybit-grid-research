from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from bybit_grid.bybit.fgrid_feasibility import summarize_min_investment
from bybit_grid.bybit.fgrid_constraints import build_candidate_payloads, candidate_key
from bybit_grid.data.download_manifest import (
    last_closed_minute_ms,
    start_for_days_ms,
    build_download_manifest,
)
from bybit_grid.data.funding_quality import funding_status
from scripts.make_share_zip import make_zip


def test_manifest_timestamps_are_minute_aligned():
    end = last_closed_minute_ms(123_456_789)
    assert end % 60_000 == 0
    start = start_for_days_ms(end, 7)
    assert start % 60_000 == 0
    assert (end - start) // 60_000 + 1 == 10_080


def test_build_manifest_estimates_seven_days_rows(monkeypatch):
    import bybit_grid.data.download_manifest as dm

    monkeypatch.setattr(dm, "last_closed_minute_ms", lambda now_ms=None: 600_000_000)
    uni = pl.DataFrame({"symbol": ["AUSDT"], "turnover24h": [10.0], "launchTime": [0]})
    df = build_download_manifest(uni, pl.DataFrame(), 7, 1, 1)
    assert df.item(0, "estimated_kline_rows") == 10_080
    assert df.item(0, "estimated_mark_kline_rows") == 10_080
    assert df.item(0, "estimated_funding_rows") == 21


def test_downloader_days_override_recomputes_and_ascii(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    Path("data/processed").mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["A"],
            "trading_feasibility_status": ["blocked_by_min_investment"],
            "start_ms": [0],
            "end_ms": [1],
            "estimated_total_rows": [999],
        }
    ).write_parquet("data/processed/download_manifest.parquet")
    import scripts.download_universe_data as d

    monkeypatch.setattr(
        "sys.argv",
        [
            "download",
            "--manifest",
            "data/processed/download_manifest.parquet",
            "--dry-run",
            "--include-blocked",
            "--days-override",
            "7",
            "--reason",
            "exploratory_data_only",
        ],
    )
    d.main()
    out = capsys.readouterr().out
    assert "manifest_rows_total=1" in out
    assert "┌" not in out and "shape:" not in out
    assert "estimated_rows=20181" in out


def test_quality_report_finds_partition_files_and_funding_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = Path("data/raw")
    k = base / "klines/symbol=A/year=2026/month=07/part.parquet"
    m = base / "mark_klines/symbol=A/year=2026/month=07/part.parquet"
    f = base / "funding/symbol=A/year=2026/part.parquet"
    for p in (k, m, f):
        p.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "symbol": ["A"],
            "open_time_ms": [0],
            "open": [1],
            "high": [1],
            "low": [1],
            "close": [1],
            "volume": [1],
        }
    ).write_parquet(k)
    pl.DataFrame(
        {
            "symbol": ["A"],
            "open_time_ms": [0],
            "open": [1],
            "high": [1],
            "low": [1],
            "close": [1],
            "volume": [1],
        }
    ).write_parquet(m)
    pl.DataFrame(
        {
            "symbol": ["A"] * 21,
            "funding_rate_timestamp_ms": [i * 8 * 60 * 60_000 for i in range(21)],
        }
    ).write_parquet(f)
    import scripts.report_universe_quality as q

    q.main()
    df = pl.read_parquet("data/processed/universe_quality_summary.parquet")
    assert set(df["dataset"]) == {"klines", "mark_klines", "funding"}
    funding = df.filter(pl.col("dataset") == "funding")
    assert funding.item(0, "funding_rows_actual") == 21
    assert funding.item(0, "funding_rows_status") == "ok"


def test_funding_status_logic():
    assert funding_status(21, 21) == "ok"
    assert funding_status(1, 21) == "low"
    assert funding_status(0, 21) == "missing"
    assert funding_status(3, None) == "unknown_interval"


def test_min_investment_summary_thresholds():
    df = pl.DataFrame(
        {
            "symbol": ["A", "A", "B"],
            "investment_min": [4.0, 30.0, 200.0],
            "feasible_bybit": [True, True, True],
            "range_width_pct": [0.02, 0.05, 0.02],
            "cell_number_requested": [2, 5, 2],
            "leverage_requested": [10, 3, 10],
            "init_margin_requested": [5.0, 50.0, 250.0],
            "stop_loss_mult": [0.9, 0.95, 0.9],
        }
    )
    summary, agg = summarize_min_investment(df)
    assert summary.filter(pl.col("symbol") == "A").item(0, "user_5usdt_feasible_config_count") == 1
    assert agg["symbols_feasible_at_5"] == 1
    assert agg["symbols_feasible_at_250"] == 2


def test_min_investment_sweep_dedupe_resume():
    candidates = build_candidate_payloads("AUSDT", 100, "0.1", stage="fast")
    keys = [candidate_key(meta) for _, meta in candidates]
    assert len(keys) == len(set(keys))
    assert len(candidates) == 4 * 4 * 3 * 5 * 2


def test_share_zip_excludes_private_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/raw").mkdir(parents=True)
    Path("reports/runs").mkdir(parents=True)
    Path("src").mkdir()
    Path(".env").write_text("SECRET=1")
    Path("data/raw/a.parquet").write_text("x")
    Path("reports/runs/a.md").write_text("x")
    Path("src/app.py").write_text("print(1)")
    make_zip(Path("share.zip"))
    with zipfile.ZipFile("share.zip") as zf:
        names = set(zf.namelist())
    assert "src/app.py" in names
    assert ".env" not in names
    assert "data/raw/a.parquet" not in names
    assert "reports/runs/a.md" not in names
