import polars as pl

from bybit_grid.config import Settings
from bybit_grid.data.funding import download_funding_history
from bybit_grid.data.klines import download_kline_range
from bybit_grid.data.mark_klines import download_mark_kline_range
from bybit_grid.data.quality import save_gap_report
from scripts.download_sample_data import ONE_MINUTE_MS, sample_time_bounds


class FakeClient:
    def __init__(self, tmp_path, rows):
        self.settings = Settings(data_dir=tmp_path)
        self.rows = rows

    def public_get(self, endpoint, params):
        if endpoint == "/v5/market/funding/history":
            return {"result": {"list": self.rows}}
        return {"result": {"list": self.rows}}


def test_download_kline_range_writes_partition_without_expr_partition_by(tmp_path):
    rows = [["0", "1", "2", "0.5", "1.5", "10", "15"]]
    df = download_kline_range(FakeClient(tmp_path, rows), "BTCUSDT", 0, 0)
    assert df.height == 1
    assert (tmp_path / "raw" / "klines" / "symbol=BTCUSDT" / "year=1970" / "month=01" / "part.parquet").exists()


def test_download_mark_kline_range_writes_partition_without_expr_partition_by(tmp_path):
    rows = [["0", "1", "2", "0.5", "1.5"]]
    df = download_mark_kline_range(FakeClient(tmp_path, rows), "BTCUSDT", 0, 0)
    assert df.height == 1
    assert df["source"][0] == "mark-price-kline"
    assert df["turnover"][0] is None
    assert (tmp_path / "raw" / "mark_klines" / "symbol=BTCUSDT" / "year=1970" / "month=01" / "part.parquet").exists()


def test_download_funding_history_writes_partition_without_expr_partition_by(tmp_path):
    rows = [{"symbol": "BTCUSDT", "fundingRateTimestamp": "0", "fundingRate": "0.0001"}]
    df = download_funding_history(FakeClient(tmp_path, rows), "BTCUSDT", 0, 0)
    assert df.height == 1
    assert (tmp_path / "raw" / "funding" / "symbol=BTCUSDT" / "year=1970" / "part.parquet").exists()


def test_save_gap_report_includes_expected_boundary_gaps(tmp_path):
    df = pl.DataFrame({"symbol": ["BTCUSDT"], "open_time_ms": [60_000]})
    gaps = save_gap_report(tmp_path, df, expected_start_ms=0, expected_end_ms=120_000)
    assert gaps["gap_type"].to_list() == ["start_boundary", "end_boundary"]
    assert (tmp_path / "quality").exists()


def test_sample_time_bounds_are_minute_aligned_closed_candles():
    start, end = sample_time_bounds(days=1, now_ms=123_456_789)
    assert start % ONE_MINUTE_MS == 0
    assert end % ONE_MINUTE_MS == 0
    assert end == 123_420_000 - ONE_MINUTE_MS
    assert start == end - 24 * 60 * ONE_MINUTE_MS + ONE_MINUTE_MS
