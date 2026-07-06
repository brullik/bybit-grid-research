from pathlib import Path
from bybit_grid.data.storage import kline_partition_path, funding_partition_path

def test_kline_path_generation():
    assert kline_partition_path(Path('data'),'klines','BTCUSDT', 1721000000000).as_posix().startswith('data/raw/klines/symbol=BTCUSDT/year=2024/month=07/')

def test_funding_path_generation():
    assert 'data/raw/funding/symbol=ETHUSDT/year=2024' in funding_partition_path(Path('data'),'ETHUSDT',1721000000000).as_posix()
