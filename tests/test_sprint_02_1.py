from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from bybit_grid.bybit.fgrid_constraints import (
    append_constraints,
    build_candidate_payloads,
    candidate_key,
)
from bybit_grid.bybit.rate_limit import TokenBucketRateLimiter


def test_report_writer_utf8_no_polars_box_repr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.report_universe_quality as report

    report.main()
    text = Path("reports/sprint_02_universe_quality_report.md").read_text(encoding="utf-8")
    assert "shape:" not in text
    assert "┌" not in text


def test_downloader_skips_blocked_by_default_and_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/processed").mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["A"],
            "trading_feasibility_status": ["blocked_by_min_investment"],
            "start_ms": [0],
            "end_ms": [60_000],
        }
    ).write_parquet("data/processed/download_manifest.parquet")
    import scripts.download_universe_data as d

    d.main.__globals__["__name__"] = "not_main"
    monkeypatch.setattr(
        "sys.argv",
        ["download", "--manifest", "data/processed/download_manifest.parquet", "--dry-run"],
    )
    d.main()
    metrics = json.loads(Path("reports/sprint_02_download_performance_report.json").read_text())
    assert metrics["download_blocked_by_policy"] is True
    assert metrics["downloadable_rows"] == 0

    monkeypatch.setattr(
        "sys.argv",
        [
            "download",
            "--manifest",
            "data/processed/download_manifest.parquet",
            "--dry-run",
            "--include-blocked",
            "--reason",
            "exploratory_data_only",
        ],
    )
    d.main()
    metrics = json.loads(Path("reports/sprint_02_download_performance_report.json").read_text())
    assert metrics["download_blocked_by_policy"] is False
    assert metrics["downloadable_rows"] == 1


def test_candidate_key_includes_stop_loss_and_bounds():
    meta = {
        "symbol": "A",
        "range_width_pct": 0.05,
        "cell_number_requested": 5,
        "leverage_requested": 1,
        "init_margin_requested": 100,
        "stop_loss_mult": 0.95,
        "min_price": 1,
        "max_price": 2,
    }
    changed = {**meta, "stop_loss_mult": 0.9}
    assert candidate_key(meta) != candidate_key(changed)


def test_append_constraints_dedupes_fresh_and_appended(tmp_path):
    path = tmp_path / "c.parquet"
    row = {
        "symbol": "A",
        "range_width_pct": 0.05,
        "cell_number_requested": 5,
        "leverage_requested": 1,
        "init_margin_requested": 100.0,
        "stop_loss_mult": 0.95,
        "min_price": 1.0,
        "max_price": 2.0,
        "feasible_user_5usdt_rule": False,
    }
    df = append_constraints(path, [row, {**row, "feasible_user_5usdt_rule": True}])
    assert df.height == 1
    df = append_constraints(path, [{**row, "feasible_user_5usdt_rule": False}])
    assert df.height == 1
    assert pl.read_parquet(path).height == 1


def test_stage_a_candidate_generation_diverse_and_bounded():
    candidates = build_candidate_payloads("AUSDT", 100, "0.1", stage="fast")
    metas = [m for _, m in candidates]
    assert len(candidates) == 4 * 4 * 3 * 5 * 2
    assert {m["range_width_pct"] for m in metas} == {0.02, 0.05, 0.1, 0.2}
    assert {m["cell_number_requested"] for m in metas} == {2, 5, 10, 20}
    assert {m["leverage_requested"] for m in metas} == {1, 3, 10}


def test_threaded_downloader_uses_global_rate_limiter(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import scripts.download_universe_data as d

    class Settings:
        data_dir = tmp_path / "data"
        bybit_api_base_url = "https://example.invalid"

    class Client:
        def __init__(self, settings, rate_limiter=None):
            self.settings = settings
            self.rate_limiter = rate_limiter

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def fake_downloader(client, symbol, start_ms, end_ms):
        client.rate_limiter.wait()
        return pl.DataFrame({"x": [1]})

    limiter = TokenBucketRateLimiter(100000)
    monkeypatch.setattr(d, "load_settings", lambda: Settings())
    monkeypatch.setattr(d, "BybitClient", Client)
    monkeypatch.setattr(d, "download_kline_range", fake_downloader)
    monkeypatch.setattr(d, "download_mark_kline_range", fake_downloader)
    monkeypatch.setattr(d, "download_funding_history", fake_downloader)
    res = d._download_symbol({"symbol": "A", "start_ms": 0, "end_ms": 1}, limiter, False)
    assert res["downloaded"] == 3
    assert limiter.wait_count == 3
