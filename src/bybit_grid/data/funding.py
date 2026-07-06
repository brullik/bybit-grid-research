import polars as pl
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.storage import funding_partition_path, utc_now_ms, write_parquet_merge

def download_funding_history(client: BybitClient, symbol: str, start_ms: int, end_ms: int, category='linear') -> pl.DataFrame:
    rows=[]; cur=start_ms
    while cur <= end_ms:
        res=client.public_get('/v5/market/funding/history', {'category':category,'symbol':symbol,'startTime':cur,'endTime':end_ms,'limit':200})['result'].get('list', [])
        if not res: break
        rows.extend(res); max_ts=max(int(r['fundingRateTimestamp']) for r in res); nxt=max_ts+1
        if nxt<=cur: break
        cur=nxt
        if len(res)<200: break
    fetched=utc_now_ms(); norm=[{'symbol':r.get('symbol',symbol),'category':category,'funding_rate_timestamp_ms':int(r['fundingRateTimestamp']),'funding_rate':float(r['fundingRate']),'source':'funding-history','fetched_at_ms':fetched} for r in rows]
    df=pl.DataFrame(norm).unique(['symbol','funding_rate_timestamp_ms']).sort('funding_rate_timestamp_ms') if norm else pl.DataFrame()
    if not df.is_empty():
        for part in df.partition_by(pl.col('funding_rate_timestamp_ms').map_elements(lambda x: x//(365*24*3600*1000), return_dtype=pl.Int64), as_dict=False):
            write_parquet_merge(funding_partition_path(client.settings.data_dir, symbol, int(part['funding_rate_timestamp_ms'][0])), part, ['symbol','funding_rate_timestamp_ms'])
    return df
