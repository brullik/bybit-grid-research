import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.logging import redacted_json_dump, setup_logging
from bybit_grid.reporting import utc_now_iso, write_sprint_report


def _status(data: dict[str, Any] | None) -> str:
    if not data:
        return "not-run"
    if data.get("error"):
        return "error"
    return "ok" if data.get("retCode") in (0, "0", None) else "error"


settings = load_settings()
setup_logging(settings.log_level)
started_at = utc_now_iso()
out = settings.data_dir / "metadata" / "account_info_redacted.json"
out.parent.mkdir(parents=True, exist_ok=True)
info: dict[str, Any] | None = None
wallet: dict[str, Any] | None = None
error_summary = ""
status = "ok"

try:
    settings.require_private_credentials()
    with BybitClient(settings) as c:
        info = c.private_get("/v5/account/info")
        try:
            wallet = c.private_get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        except Exception as exc:
            wallet = {"error": str(exc), "accountType": "UNIFIED"}
            error_summary = f"wallet UNIFIED read failed: {exc}"
except Exception as exc:
    status = "error"
    error_summary = str(exc)
    info = {"error": str(exc)}

out.write_text(redacted_json_dump({"account_info": info, "wallet_balance": wallet}), encoding="utf-8")
account_result = info.get("result", {}) if isinstance(info, dict) else {}
write_sprint_report(
    settings.data_dir,
    {
        "command": "smoke_private_account",
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "status": status,
        "account_info_status": _status(info),
        "unifiedMarginStatus": account_result.get("unifiedMarginStatus"),
        "marginMode": account_result.get("marginMode"),
        "wallet_read_status": _status(wallet),
        "output_paths": [str(out)],
        "error_summary": error_summary,
    },
)
print(
    redacted_json_dump(
        {
            "status": status,
            "account_info_status": _status(info),
            "wallet_read_status": _status(wallet),
            "output_paths": [str(out)],
            "error_summary": error_summary,
        }
    )
)
raise SystemExit(1 if status == "error" else 0)
