import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bybit_grid.config import load_settings
from bybit_grid.logging import setup_logging
from bybit_grid.bybit.client import BybitClient
from bybit_grid.data.instruments import download_instruments
from bybit_grid.data.tickers import download_tickers
from bybit_grid.reporting import write_sprint_report
setup_logging(load_settings().log_level)
settings=load_settings(); settings.data_dir.mkdir(parents=True, exist_ok=True)
with BybitClient(settings) as c:
    ins=download_instruments(c); tick=download_tickers(c)
trading = ins.filter(ins['status']=='Trading').height if 'status' in ins.columns and not ins.is_empty() else 0
write_sprint_report(settings.data_dir, {'env': settings.bybit_env, 'public API status':'ok', 'linear instruments': ins.height, 'Trading symbols': trading, 'tickers': tick.height})
print(f'ok instruments={ins.height} trading={trading} tickers={tick.height}')
