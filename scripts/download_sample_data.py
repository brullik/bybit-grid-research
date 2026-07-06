import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import argparse, time
from bybit_grid.config import load_settings
from bybit_grid.logging import setup_logging
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.klines import download_kline_range
from bybit_grid.data.mark_klines import download_mark_kline_range
from bybit_grid.data.funding import download_funding_history
from bybit_grid.data.quality import save_gap_report
from bybit_grid.reporting import write_sprint_report
import polars as pl
p=argparse.ArgumentParser(); p.add_argument('--symbols', nargs='+', default=['BTCUSDT','ETHUSDT']); p.add_argument('--days', type=int, default=7); args=p.parse_args()
settings=load_settings(); setup_logging(settings.log_level); end=int(time.time()*1000); start=end-args.days*24*60*60*1000
all_k=[]
with BybitClient(settings) as c:
    for s in args.symbols:
        k=download_kline_range(c,s,start,end); download_mark_kline_range(c,s,start,end); download_funding_history(c,s,start,end)
        if not k.is_empty(): all_k.append(k)
gaps=save_gap_report(settings.data_dir, pl.concat(all_k) if all_k else pl.DataFrame())
write_sprint_report(settings.data_dir, {'env':settings.bybit_env,'sample data coverage':f'{args.symbols} days={args.days}','gap summary': gaps.to_dicts(), 'blockers':'none for public data'})
print(f'ok symbols={args.symbols} gaps={gaps.height}')
