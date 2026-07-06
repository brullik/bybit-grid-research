from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.klines import download_kline_range

def download_mark_kline_range(client: BybitClient, symbol: str, start_ms: int, end_ms: int, category='linear'):
    return download_kline_range(client, symbol, start_ms, end_ms, category, 'mark_klines', '/v5/market/mark-price-kline')
