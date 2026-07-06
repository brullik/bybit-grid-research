import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pathlib import Path
from bybit_grid.config import load_settings
from bybit_grid.logging import setup_logging, redacted_json_dump
from bybit_grid.bybit.client import BybitClient
from bybit_grid.reporting import write_sprint_report
settings=load_settings(); setup_logging(settings.log_level)
try:
    settings.require_private_credentials()
except ValueError as e:
    print(f'skipped: {e}'); write_sprint_report(settings.data_dir, {'account info summary': f'skipped: {e}'}); raise SystemExit(0)
with BybitClient(settings) as c:
    info=c.private_get('/v5/account/info'); wallet=c.private_get('/v5/account/wallet-balance', {'accountType':'UNIFIED'})
out=settings.data_dir/'metadata'/'account_info_redacted.json'; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(redacted_json_dump({'account_info':info,'wallet_balance':wallet}), encoding='utf-8')
write_sprint_report(settings.data_dir, {'account info summary':'saved redacted account_info_redacted.json'})
print('ok private account saved redacted JSON')
