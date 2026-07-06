import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.config import load_settings
from bybit_grid.data.instruments import download_instruments
from bybit_grid.data.tickers import download_tickers
from bybit_grid.logging import redact, setup_logging
from bybit_grid.reporting import utc_now_iso, write_sprint_report

settings = load_settings()
setup_logging(settings.log_level)
settings.data_dir.mkdir(parents=True, exist_ok=True)
started_at = utc_now_iso()
try:
    with BybitClient(settings) as c:
        ins = download_instruments(c)
        tick = download_tickers(c)
    trading = (
        ins.filter(ins["status"] == "Trading").height
        if "status" in ins.columns and not ins.is_empty()
        else 0
    )
    write_sprint_report(
        settings.data_dir,
        {
            "command": "smoke_public_api",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "status": "ok",
            "counts": {
                "linear_instruments": ins.height,
                "trading_symbols": trading,
                "tickers": tick.height,
            },
            "env": settings.bybit_env,
            "public API status": "ok",
        },
    )
    print(f"ok instruments={ins.height} trading={trading} tickers={tick.height}")
except (httpx.HTTPStatusError, httpx.ProxyError, BybitAPIError) as exc:
    response = getattr(exc, "response", None)
    diagnostic = {
        "base_url": settings.bybit_api_base_url,
        "exception_type": type(exc).__name__,
        "status": getattr(response, "status_code", None) or getattr(exc, "status_code", None),
        "body_first_500": redact(getattr(response, "text", "")[:500] if response else ""),
        "proxy_or_bybit": "proxy" if isinstance(exc, httpx.ProxyError) else "bybit_or_edge",
        "recommended_pm_action": "verify that target network can reach Bybit API before private calls",
    }
    write_sprint_report(
        settings.data_dir,
        {
            "command": "smoke_public_api",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "status": "network-blocked",
            "error_summary": str(exc),
            "network diagnostic": diagnostic,
        },
    )
    print(diagnostic)
    raise SystemExit(2)
