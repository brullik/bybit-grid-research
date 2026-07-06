import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import argparse
from bybit_grid.config import load_settings
from bybit_grid.logging import setup_logging, redacted_json_dump
from bybit_grid.bybit.client import BybitClient
from bybit_grid.reporting import write_sprint_report
p=argparse.ArgumentParser(); p.add_argument('--symbol', default='BTCUSDT'); p.add_argument('--dry-run', action='store_true'); args=p.parse_args()
settings=load_settings(); setup_logging(settings.log_level)
if not settings.grid_validate_enabled:
    msg='skipped: GRID_VALIDATE_ENABLED is false; no create/close exists in Sprint 01'
    write_sprint_report(settings.data_dir, {'grid validate status':msg}); print(msg); raise SystemExit(0)
try: settings.require_private_credentials()
except ValueError as e: print(f'skipped: {e}'); raise SystemExit(0)
with BybitClient(settings) as c:
    res=c.validate_grid_bot({'category':'linear','symbol':args.symbol}, runtime_live=False)
(settings.data_dir/'metadata').mkdir(parents=True, exist_ok=True); (settings.data_dir/'metadata'/'grid_validate_redacted.json').write_text(redacted_json_dump(res), encoding='utf-8')
write_sprint_report(settings.data_dir, {'grid validate status':'attempted validate-only'})
print('ok validate-only attempted')
