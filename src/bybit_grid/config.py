from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    bybit_env: str = 'mainnet'
    bybit_api_base_url: str = 'https://api.bybit.com'
    bybit_api_key: str = ''
    bybit_api_secret: str = ''
    bybit_recv_window: int = 5000
    live_trading_enabled: bool = False
    allow_live_trading: str = 'NO'
    data_dir: Path = Field(default=Path('./data'))
    log_level: str = 'INFO'
    grid_validate_enabled: bool = False
    bybit_grid_validate_path: str = '/v5/grid-bot/order/validate'

    def require_private_credentials(self) -> None:
        if not self.bybit_api_key or not self.bybit_api_secret:
            raise ValueError('BYBIT_API_KEY and BYBIT_API_SECRET are required for private Bybit calls')

    def assert_live_trading_allowed(self, runtime_live: bool = False) -> None:
        if not (self.live_trading_enabled and self.allow_live_trading == 'YES' and runtime_live):
            raise PermissionError('Live trading is disabled. Need LIVE_TRADING_ENABLED=true, ALLOW_LIVE_TRADING=YES, and runtime --live.')

def load_settings() -> Settings:
    return Settings()
