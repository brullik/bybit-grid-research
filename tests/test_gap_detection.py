import polars as pl
from bybit_grid.data.quality import detect_1m_gaps

def test_detects_1m_gap():
    df=pl.DataFrame({'symbol':['BTCUSDT']*3,'open_time_ms':[0,60_000,180_000]})
    gaps=detect_1m_gaps(df)
    assert gaps.height == 1
    assert gaps['start_ms'][0] == 120_000
    assert gaps['missing_minutes'][0] == 1
