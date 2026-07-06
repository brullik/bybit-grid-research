import polars as pl
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.storage import metadata_path

def download_instruments(client: BybitClient, category: str='linear') -> pl.DataFrame:
    cursor=''; rows=[]
    while True:
        params={'category':category, 'limit':1000}
        if cursor: params['cursor']=cursor
        result=client.public_get('/v5/market/instruments-info', params)['result']
        rows.extend(result.get('list', [])); cursor=result.get('nextPageCursor') or ''
        if not cursor: break
    df=pl.DataFrame(rows) if rows else pl.DataFrame()
    out=metadata_path(client.settings.data_dir, f'instruments_{category}.parquet'); out.parent.mkdir(parents=True, exist_ok=True); df.write_parquet(out)
    return df
