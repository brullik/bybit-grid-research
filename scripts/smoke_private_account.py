import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.logging import redacted_json_dump
from bybit_grid.logging import setup_logging
from bybit_grid.reporting import utc_now_iso, write_sprint_report

SENSITIVE_WALLET_AMOUNT_KEYS = {
    "walletBalance",
    "equity",
    "usdValue",
    "totalEquity",
    "cumRealisedPnl",
    "unrealisedPnl",
    "totalWalletBalance",
    "totalMarginBalance",
    "totalAvailableBalance",
    "availableToWithdraw",
    "availableToBorrow",
    "borrowAmount",
    "free",
    "locked",
}
STRICT_API_RESPONSE_ENVELOPE_CONTRACT = "strict-envelope-v1"


def _status(data: dict[str, Any] | None | object) -> str:
    if data is None:
        return "not-run"
    if type(data) is not dict or "error" in data or "status_code" in data:
        return "error"
    if ("retMsg" in data and type(data["retMsg"]) is not str) or (
        "debug_msg" in data and type(data["debug_msg"]) is not str
    ):
        return "error"
    return (
        "ok" if type(data.get("retCode")) is int and data["retCode"] == 0 else "error"
    )


def _sanitize_account_info(info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(info, dict):
        return info
    result = info.get("result") if isinstance(info.get("result"), dict) else {}
    safe_result_keys = {
        "unifiedMarginStatus",
        "marginMode",
        "dcpStatus",
        "smpGroup",
        "spotHedgingStatus",
    }
    sanitized: dict[str, Any] = {
        "retCode": info.get("retCode"),
        "retMsg": info.get("retMsg"),
        "result": {key: result.get(key) for key in safe_result_keys if key in result},
    }
    if info.get("error"):
        sanitized["error"] = info.get("error")
    return sanitized


def _extract_wallet_coins(wallet: dict[str, Any] | None) -> list[str]:
    if not isinstance(wallet, dict):
        return []
    rows = (
        wallet.get("result", {}).get("list", [])
        if isinstance(wallet.get("result"), dict)
        else []
    )
    coins: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for coin_row in row.get("coin", []):
            if isinstance(coin_row, dict) and coin_row.get("coin"):
                coins.add(str(coin_row["coin"]))
    return sorted(coins)


def _sanitize_wallet_balance(
    wallet: dict[str, Any] | None, account_type: str = "UNIFIED"
) -> dict[str, Any] | None:
    if not isinstance(wallet, dict):
        return wallet
    coins = _extract_wallet_coins(wallet)
    sanitized: dict[str, Any] = {
        "retCode": wallet.get("retCode"),
        "retMsg": wallet.get("retMsg"),
        "accountType": account_type,
        "coin_count": len(coins),
        "coins": coins,
        "balance_values_redacted": True,
    }
    if wallet.get("error"):
        sanitized["error"] = wallet.get("error")
    return sanitized


def sanitize_private_account_snapshot(
    info: dict[str, Any] | None, wallet: dict[str, Any] | None
) -> dict[str, Any | None]:
    return {
        "account_info": _sanitize_account_info(info),
        "wallet_balance": _sanitize_wallet_balance(wallet),
    }


def main() -> int:
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
                wallet = c.private_get(
                    "/v5/account/wallet-balance", {"accountType": "UNIFIED"}
                )
            except Exception as exc:
                wallet = {"error": str(exc), "accountType": "UNIFIED"}
                error_summary = f"wallet UNIFIED read failed: {exc}"
    except Exception as exc:
        status = "error"
        error_summary = str(exc)
        info = {"error": str(exc)}

    out.write_text(
        redacted_json_dump(sanitize_private_account_snapshot(info, wallet)),
        encoding="utf-8",
    )
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
    return 1 if status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
