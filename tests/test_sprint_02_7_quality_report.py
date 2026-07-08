from __future__ import annotations

from pathlib import Path
import zipfile

import polars as pl


def _manifest(symbols: list[str], start: int = 0, end: int = 120_000) -> pl.DataFrame:
    return pl.DataFrame({"symbol": symbols, "start_ms": [start] * len(symbols), "end_ms": [end] * len(symbols)})


def _write_klines(path: Path, symbol: str, times: list[int], bad: bool = False, volume=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(times)
    high = [2] * n
    low = [1] * n
    if bad:
        high[-1] = 0
    pl.DataFrame({"symbol": [symbol] * n, "open_time_ms": times, "open": [1] * n, "high": high, "low": low, "close": [1] * n, "volume": volume if volume is not None else [1] * n}).write_parquet(path)


def test_schema_bug_reproduction_and_stable_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.report_universe_quality as q
    rows = [q._base_row(f"A{i}", "klines", 0, 0) for i in range(101)] + [q._base_row("F", "funding", 0, 8 * 60 * 60_000)]
    df = pl.DataFrame(rows, schema=q.QUALITY_SCHEMA)
    assert df.schema["funding_rows_expected_approx"] == pl.Int64
    assert df.filter(pl.col("dataset") == "funding").item(0, "funding_rows_expected_approx") == 2


def test_manifest_driven_path_ignores_unrelated_symbol(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.report_universe_quality as q
    _write_klines(Path("data/raw/klines/symbol=A/year=2026/month=07/p.parquet"), "A", [0, 60_000, 120_000])
    _write_klines(Path("data/raw/klines/symbol=B/year=2026/month=07/p.parquet"), "B", [0, 60_000, 120_000])
    df = q.build_quality_summary(_manifest(["A"]), Path("data"))
    assert set(df["symbol"].to_list()) == {"A"}


def test_lazy_aggregate_duplicate_bad_boundary_and_mark_volume(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.report_universe_quality as q
    _write_klines(Path("data/raw/klines/symbol=A/year=2026/month=07/p.parquet"), "A", [60_000, 60_000, 120_000], bad=True)
    _write_klines(Path("data/raw/mark_klines/symbol=A/year=2026/month=07/p.parquet"), "A", [60_000, 120_000], volume=[None, None])
    df = q.build_quality_summary(_manifest(["A"], 0, 180_000), Path("data"))
    k = df.filter(pl.col("dataset") == "klines")
    assert k.item(0, "duplicate_candles") == 1
    assert k.item(0, "bad_ohlc") == 1
    assert k.item(0, "boundary_start_gap") == 1
    assert k.item(0, "boundary_end_gap") == 1
    m = df.filter(pl.col("dataset") == "mark_klines")
    assert m.item(0, "zero_volume_rows") == 0


def test_readiness_passes_with_50_clean_symbols():
    import scripts.report_research_readiness as r
    symbols = [f"S{i}" for i in range(50)]
    rows = []
    for s in symbols:
        rows += [
            {"symbol": s, "dataset": "klines", "rows": 3, "missing_gaps": 0, "duplicate_candles": 0, "bad_ohlc": 0, "zero_volume_rows": 0, "disk_bytes": 1},
            {"symbol": s, "dataset": "mark_klines", "rows": 3, "missing_gaps": 0, "duplicate_candles": 0, "bad_ohlc": 0, "zero_volume_rows": 0, "disk_bytes": 1},
            {"symbol": s, "dataset": "funding", "rows": 1, "missing_gaps": 0, "duplicate_candles": 0, "bad_ohlc": 0, "zero_volume_rows": 0, "disk_bytes": 1},
        ]
    metrics = r.compute_metrics(pl.DataFrame({"symbol": symbols}), _manifest(symbols), pl.DataFrame(rows))
    assert metrics["recommendation"] == "pass"
    assert metrics["symbols_ready_for_sprint_03"] == 50


def test_reports_utf8_ascii_and_zip_hygiene(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import scripts.report_universe_quality as q
    from scripts.make_share_zip import make_zip
    Path("data/processed").mkdir(parents=True)
    q.build_quality_summary(_manifest([]), Path("data")).write_parquet("data/processed/universe_quality_summary.parquet")
    Path("reports").mkdir()
    Path("reports/x.md").write_text("generated")
    Path(".env.local").write_text("SECRET=1")
    Path(".env.example").write_text("EXAMPLE=1")
    Path("src").mkdir()
    Path("src/app.py").write_text("print(1)")
    make_zip(Path("share.zip"))
    with zipfile.ZipFile("share.zip") as zf:
        names = set(zf.namelist())
    assert "src/app.py" in names
    assert ".env.example" in names
    assert ".env.local" not in names
    assert all(not n.startswith("reports/") and not n.startswith("data/") for n in names)
