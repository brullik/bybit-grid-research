import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.bybit.client import BybitClient
from bybit_grid.bybit.models import BybitAPIError
from bybit_grid.bybit.fgrid_payloads import build_fgrid_validate_payload
from bybit_grid.config import load_settings
from bybit_grid.logging import redacted_json_dump
from bybit_grid.reporting import utc_now_iso, write_sprint_report


def static_payload(symbol: str, leverage: str, cell_number: int, init_margin: str) -> dict[str, Any]:
    return build_fgrid_validate_payload(
        symbol=symbol,
        last_price=Decimal("65000"),
        tick_size=Decimal("0.1"),
        leverage=Decimal(leverage),
        cell_number=cell_number,
        init_margin=init_margin,
    )


def _market_numbers(client: BybitClient, symbol: str) -> tuple[Decimal, Decimal]:
    ticker = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
    rows = ticker.get("result", {}).get("list", [])
    if not rows:
        raise ValueError(f"no ticker rows returned for {symbol}")
    last_price = Decimal(str(rows[0]["lastPrice"]))
    instruments = client.public_get(
        "/v5/market/instruments-info", {"category": "linear", "symbol": symbol}
    )
    inst_rows = instruments.get("result", {}).get("list", [])
    if not inst_rows:
        raise ValueError(f"no instrument rows returned for {symbol}")
    tick_size = Decimal(str(inst_rows[0]["priceFilter"]["tickSize"]))
    return last_price, tick_size


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redacted_json_dump(data), encoding="utf-8")


def _refusal_reason(settings) -> str | None:
    if not settings.grid_validate_enabled:
        return "GRID_VALIDATE_ENABLED is false"
    if not settings.bybit_api_key or not settings.bybit_api_secret:
        return "BYBIT_API_KEY and BYBIT_API_SECRET are required"
    if settings.live_trading_enabled:
        return "LIVE_TRADING_ENABLED must remain false for validate-only"
    if settings.allow_live_trading != "NO":
        return "ALLOW_LIVE_TRADING must remain NO for validate-only"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dynamic", action="store_true")
    parser.add_argument("--init-margin", default="100")
    parser.add_argument("--cell-number", type=int, default=10)
    parser.add_argument("--leverage", default="1")
    parser.add_argument("--lower-mult", default="0.90")
    parser.add_argument("--upper-mult", default="1.10")
    parser.add_argument("--stop-loss-mult", default="0.85")
    parser.add_argument("--payload-json")
    args = parser.parse_args()

    settings = load_settings()
    started_at = utc_now_iso()
    payload_path = settings.data_dir / "metadata" / "grid_validate_payload_redacted.json"
    response_path = settings.data_dir / "metadata" / "grid_validate_response_redacted.json"
    payload_mode = "payload-json" if args.payload_json else "dynamic" if args.dynamic else "static"
    response: dict[str, Any] = {}
    status = "ok"
    error_summary = ""

    try:
        if args.payload_json:
            payload = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
        elif args.dynamic:
            with BybitClient(settings) as client:
                last_price, tick_size = _market_numbers(client, args.symbol)
            payload = build_fgrid_validate_payload(
                symbol=args.symbol,
                last_price=last_price,
                tick_size=tick_size,
                leverage=Decimal(args.leverage),
                cell_number=args.cell_number,
                init_margin=args.init_margin,
                lower_mult=Decimal(args.lower_mult),
                upper_mult=Decimal(args.upper_mult),
                stop_loss_mult=Decimal(args.stop_loss_mult),
            )
        else:
            payload = static_payload(args.symbol, args.leverage, args.cell_number, args.init_margin)
        _write_json(payload_path, payload)

        if args.dry_run:
            response = {"dry_run": True, "network_request": bool(args.dynamic), "payload": payload}
            status = "dry-run"
        else:
            reason = _refusal_reason(settings)
            if reason:
                response = {"skipped": True, "reason": reason}
                status = "skipped"
                error_summary = reason
            else:
                with BybitClient(settings) as client:
                    response = client.private_post(settings.bybit_fgrid_validate_path, payload)
        _write_json(response_path, response)
    except Exception as exc:
        status = "error"
        error_summary = str(exc)
        response = getattr(exc, "response_data", {}) if isinstance(exc, BybitAPIError) else {}
        response = {
            **response,
            "error": error_summary,
            "pm_action": "Review redacted Bybit response/schema error; do not guess field changes silently.",
        }
        _write_json(response_path, response)

    write_sprint_report(
        settings.data_dir,
        {
            "command": "validate_sample_grid",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "status": status,
            "symbol": args.symbol,
            "payload_mode": payload_mode,
            "validate_endpoint": settings.bybit_fgrid_validate_path,
            "retCode": response.get("retCode"),
            "retMsg": response.get("retMsg"),
            "check_code": response.get("result", {}).get("checkCode") if isinstance(response.get("result"), dict) else None,
            "output_paths": [str(payload_path), str(response_path)],
            "error_summary": error_summary,
        },
    )
    print(redacted_json_dump(response))
    return 1 if status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
# RED probe only: no behavior
